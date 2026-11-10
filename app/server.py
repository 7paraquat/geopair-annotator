#!/usr/bin/env python3
"""GUSO 标注清洗服务。读取已有掩膜并保存人工审核结果；不加载分割模型。"""

import os

import io
import base64
import hmac
import json
import re
import threading
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import shared_masks
from attributes import AttributeStore
from progress import Progress, STATES
from occupancy import Occupancy, Occupied
from earthmiss_source import EarthMiss, PREFIX, EXTRA_LABELS

import numpy as np
import tifffile
from PIL import Image

DATA_ROOT = Path(os.environ.get("GUSO_DATA_ROOT", "workspace/no_guso"))
REVIEW_ROOT = Path(os.environ.get("GUSO_REVIEW_ROOT", "workspace/state"))
SHARED_ROOT = Path(os.environ.get("GUSO_SHARED_ROOT", str(REVIEW_ROOT.parent / "reviews_shared")))
STATIC = Path(__file__).resolve().parent / "static"
EARTH = EarthMiss(os.environ.get('EARTHMISS_DATA_ROOT', 'dataset'),
                  os.environ.get('EARTHMISS_MANIFEST', 'workspace/selected.json'))
PORT = int(os.environ.get("GUSO_PORT", "8775"))
ACCESS_TOKEN = os.environ.get("GUSO_ACCESS_TOKEN", "")
CUSTOM_CATEGORIES_FILE = Path(
    os.environ.get("GUSO_CUSTOM_CATEGORIES", str(REVIEW_ROOT / "_custom_categories.json"))
)
ATTRIBUTES = AttributeStore(REVIEW_ROOT / 'custom_attributes.json')
PROGRESS = Progress(SHARED_ROOT)
OCCUPANCY = Occupancy(SHARED_ROOT)

CATEGORIES = [
    "building",
    "vehicle",
    "ship",
    "aircraft",
    "bridge",
    "solar_panel",
    "road",
    "water",
    "cropland",
    "grassland",
    "bareland",
    "building_facade",
    "quay",
]
RETIRED_CATEGORIES = {'tree'}
CATEGORY_LABELS = {'building_facade':'建筑外立面','quay':'码头'}
SAFE = re.compile(r"^[A-Za-z0-9._-]+$")


def load_custom_categories():
    if not CUSTOM_CATEGORIES_FILE.is_file():
        return []
    data = json.loads(CUSTOM_CATEGORIES_FILE.read_text(encoding='utf-8'))
    return [
        {"value": item["value"], "label": item["label"]}
        for item in data
        if ok_name(item.get("value")) and str(item.get("label", "")).strip()
    ]


def save_custom_category(value, label):
    value = str(value).strip().lower()
    label = str(label).strip()
    if not ok_name(value):
        raise ValueError("英文名只能包含字母、数字、点、横线和下划线")
    if not label or len(label) > 30:
        raise ValueError("中文名不能为空，且不能超过 30 个字符")
    items = load_custom_categories()
    if value in CATEGORIES:
        return {"value": value, "label": label, "existing": True}
    for item in items:
        if item["value"] == value:
            item["label"] = label
            break
    else:
        items.append({"value": value, "label": label})
    CUSTOM_CATEGORIES_FILE.parent.mkdir(parents=True, exist_ok=True)
    temp = CUSTOM_CATEGORIES_FILE.with_suffix(".tmp")
    temp.write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding='utf-8')
    os.replace(temp, CUSTOM_CATEGORIES_FILE)
    return {"value": value, "label": label, "existing": False}


def ok_name(value):
    return bool(value) and SAFE.match(value) and ".." not in value


def site_dir(site):
    if not ok_name(site):
        raise ValueError("非法站点名")
    if site.startswith(PREFIX):
        if site not in EARTH.sites():raise ValueError('地区不在当前数据清单中')
        return EARTH.root / site[len(PREFIX):]
    path = DATA_ROOT / site
    if not path.is_dir():
        raise ValueError("站点不存在")
    return path


def stem_of(filename):
    name = filename[:-4] if filename.endswith(".tif") else filename
    if name.endswith("_OPT"):
        return name
    return None


CONTINENT_RANK = {"Asia": 0, "Europe": 1, "NorthAmerica": 2, "SouthAmerica": 2}
def site_sort_key(name):
    parts = name.split("-")
    continent = parts[1] if len(parts) > 1 else ""
    rank = CONTINENT_RANK.get(continent, 9)
    head = parts[0] if parts else name
    number = int(head) if head.isdigit() else 10**9
    return (rank, number, name)


def list_sites():
    sites = []
    if DATA_ROOT.is_dir():
        for entry in os.scandir(DATA_ROOT):
            if entry.is_dir() and entry.name.endswith("-Samples"):
                sites.append(entry.name)
    sites.sort(key=site_sort_key)
    return EARTH.sites() + sites


def list_tiles(site):
    if site.startswith(PREFIX):
        site_dir(site)
        return EARTH.stems(site)
    folder = site_dir(site)
    names = {entry.name for entry in os.scandir(folder) if entry.is_file()}
    stems = [name[:-4] for name in names
             if name.endswith('_OPT.tif') and name[:-8] + '_SAR.tif' in names]
    def tile_key(stem):
        tail = stem.rsplit("_", 2)
        # 形如 1_Africa_Hill_000011_OPT，按末尾序号排，避免 2 排到 10 后面
        if len(tail) >= 2 and tail[-2].isdigit():
            return (0, int(tail[-2]), stem)
        return (1, 0, stem)

    stems.sort(key=tile_key)
    return stems


def tile_info(site, stem):
    info = PROGRESS.info(site, stem)
    return {**info, 'has_ann': info['saved'], 'ann_state': 'manual' if info['saved'] else 'none'}


def read_opt_rgb(path):
    arr = tifffile.imread(path)
    if arr.ndim == 2:
        arr = np.stack([arr, arr, arr], axis=-1)
    elif arr.ndim == 3 and arr.shape[0] in (1, 3, 4) and arr.shape[0] < arr.shape[1]:
        arr = np.moveaxis(arr[:3], 0, -1)
        if arr.shape[-1] == 1:
            arr = np.repeat(arr, 3, axis=-1)
    else:
        arr = arr[..., :3]
    if arr.dtype != np.uint8:
        arr = arr.astype(np.float32)
        peak = np.percentile(arr, 99) or 1.0
        arr = np.clip(arr / peak * 255.0, 0, 255).astype(np.uint8)
    return arr


def read_sar_rgb(path):
    arr = tifffile.imread(path)
    if arr.ndim == 3:
        if arr.shape[0] in (1, 3, 4) and arr.shape[0] < arr.shape[1]:
            arr = arr[0]
        else:
            arr = arr[..., 0]
    arr = arr.astype(np.float32)
    lo, hi = np.percentile(arr, [1, 99])
    if hi <= lo:
        hi = lo + 1.0
    gray = np.clip((arr - lo) / (hi - lo) * 255.0, 0, 255).astype(np.uint8)
    return np.stack([gray, gray, gray], axis=-1)


def jpeg_bytes(rgb, quality=85):
    buf = io.BytesIO()
    Image.fromarray(rgb).save(buf, format="JPEG", quality=quality)
    return buf.getvalue()


_jpeg_cache = {}
_jpeg_lock = threading.Lock()


def cached_jpeg(key, render):
    with _jpeg_lock:
        hit = _jpeg_cache.pop(key, None)
        if hit is not None:
            _jpeg_cache[key] = hit
            return hit
    body = render()
    with _jpeg_lock:
        _jpeg_cache.pop(key, None)
        _jpeg_cache[key] = body
        while len(_jpeg_cache) > 160:
            _jpeg_cache.pop(next(iter(_jpeg_cache)))
    return body


def load_mask_rles(site, stem):
    # This endpoint must never fall back to generated or legacy masks.
    record = load_tile_record(site, stem)
    return [{'id': a['id'], 'segmentation': a['segmentation']}
            for a in record['annotations']]


def current_label_map():
    custom = load_custom_categories()
    extra = list(EXTRA_LABELS) if EARTH.items else []
    return shared_masks.label_map(SHARED_ROOT, CATEGORIES + [v['value'] for v in custom] + extra,
                                 {**EXTRA_LABELS, **{v['value']: v['label'] for v in custom}, **CATEGORY_LABELS})


def load_tile_record(site, stem):
    shape = EARTH.shape(site,stem) if site.startswith(PREFIX) else shared_masks.pair_shape(DATA_ROOT, site, stem)
    path = shared_masks.pointer(SHARED_ROOT, site, stem)
    if path.exists():
        record = json.loads(path.read_text(encoding='utf-8'))
        if record['image_size'] != shape:
            raise ValueError('原图尺寸已变化，请核对数据')
        record['saved'] = True
        record['source_kind'] = 'saved_manual'
        record.setdefault('workflow_status', 'done')
        return record
    return {'site': site, 'stem': stem, 'source_kind':'blank', 'image_size': shape, 'annotations': [],
            'revision': None, 'saved': False, 'shared_mask': True, 'workflow_status':'todo',
            'label_map': current_label_map()}


def save_review(payload):
    if not isinstance(payload, dict):
        raise ValueError('请求必须是对象')
    legacy = 'lease_token' not in payload and 'editor_version' not in payload
    with OCCUPANCY.saving(payload.get('site'), payload.get('stem'), payload.get('lease_token'), legacy=legacy):
        result = _save_review(payload)
        if legacy:
            result['frontend_update_required'] = True
        return result


def _save_review(payload):
    if not isinstance(payload, dict):
        raise ValueError('请求必须是对象')
    site=payload.get('site','')
    if isinstance(site,str) and site.startswith(PREFIX):
        metadata=EARTH.provenance(site,payload.get('stem'))
        return shared_masks.save(SHARED_ROOT,DATA_ROOT,payload,current_label_map(),EARTH.shape,metadata)
    return shared_masks.save(SHARED_ROOT, DATA_ROOT, payload, current_label_map())


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def require_auth(self):
        if not ACCESS_TOKEN:
            return True
        expected = "Basic " + base64.b64encode(("guso:" + ACCESS_TOKEN).encode("utf-8")).decode("ascii")
        supplied = self.headers.get("Authorization", "")
        if hmac.compare_digest(supplied, expected):
            return True
        self.send_response(401)
        self.send_header("WWW-Authenticate", 'Basic realm="GUSO Clean Tool", charset="UTF-8"')
        self.send_header("Content-Length", "0")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Connection", "close")
        self.close_connection = True
        self.end_headers()
        return False

    def log_message(self, fmt, *args):
        print("%s - %s" % (self.address_string(), fmt % args))

    def send_json(self, payload, status=200):
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def send_bytes(self, body, content_type, cache="no-store"):
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", cache)
        self.end_headers()
        self.wfile.write(body)

    def read_json(self):
        length = int(self.headers.get("Content-Length") or 0)
        if length < 0 or length > 64 * 1024 * 1024:
            raise ValueError("请求体过大")
        raw = self.rfile.read(length) if length else b"{}"
        return json.loads(raw.decode("utf-8"))

    def do_GET(self):
        if not self.require_auth():
            return
        try:
            parsed = urlparse(self.path)
            path = parsed.path
            query = parse_qs(parsed.query)
            if path in ("/", "/index.html"):
                body = (STATIC / "index.html").read_bytes()
                self.send_bytes(body, "text/html; charset=utf-8")
                return
            if path in ('/geometry.js', '/app.js', '/app.20261029-dual-masks-1.js'):
                name = 'app.js' if path == '/app.20261029-dual-masks-1.js' else path[1:]
                if path == '/app.js' and query.get('v') == ['20261028-occupancy-1']:
                    name = 'app.20261028-occupancy-1.js'
                self.send_bytes((STATIC / name).read_bytes(), 'application/javascript; charset=utf-8')
                return
            if path == '/api/export':
                if query.get('site',[''])[0].startswith(PREFIX):EARTH.item(query['site'][0],query.get('stem',[''])[0])
                self.send_bytes(shared_masks.export(SHARED_ROOT, query.get('site',[''])[0], query.get('stem',[''])[0]), 'application/zip')
                return
            if path == "/api/meta":
                custom_categories = load_custom_categories()
                attributes = ATTRIBUTES.choices()
                self.send_json(
                    {
                        "shared_mode": True,
                        "label_map": current_label_map(),
                        "categories": [c["value"] for c in current_label_map()["classes"] if c["id"] > 0 and c['value'] not in RETIRED_CATEGORIES],
                        "category_labels": {
                            c["value"]: c["label"] for c in current_label_map()["classes"] if c["label"] != c["value"]
                        },
                        "colors": list(attributes['color']),
                        "materials": list(attributes['material']),
                        "attribute_labels": attributes,
                        "review_root": str(SHARED_ROOT),
                        "annotation_source": "manual_only_blank_then_saved",
                    }
                )
                return
            if path == "/api/sites":
                self.send_json({"sites": list_sites(), "earthmiss_prefix": PREFIX, "earthmiss_count": len(EARTH.items)})
                return
            if path == '/api/occupancy':
                site=query.get('site',[''])[0]
                site_dir(site)
                self.send_json(OCCUPANCY.status(site))
                return
            if path == '/api/progress':
                self.send_json(PROGRESS.summary(list_sites(), list_tiles, query.get('site',[''])[0]))
                return
            if path == "/api/tiles":
                site = query.get("site", [""])[0]
                offset = max(0, int(query.get("offset", ["0"])[0]))
                limit = min(100, max(1, int(query.get("limit", ["40"])[0])))
                search = query.get("q", [""])[0].strip().lower()
                status = query.get("status", ["all"])[0]
                if status not in {'all', 'saved', *STATES}:
                    raise ValueError("无效筛选状态")
                stems = list_tiles(site)
                if search:
                    stems = [stem for stem in stems if search in stem.lower()]
                if status != "all":
                    def matches(stem):
                        info = tile_info(site, stem)
                        if status == "saved": return info["saved"]
                        return info['workflow_status'] == status
                    stems = [stem for stem in stems if matches(stem)]
                page = stems[offset : offset + limit]
                items = [tile_info(site, stem) for stem in page]
                self.send_json({"total": len(stems), "offset": offset, "items": items})
                return
            if path == "/api/tile":
                site = query.get("site", [""])[0]
                stem = query.get("stem", [""])[0]
                if not ok_name(stem):
                    raise ValueError("非法影像名")
                site_dir(site)
                self.send_json(load_tile_record(site, stem))
                return
            if path == "/api/masks":
                site = query.get("site", [""])[0]
                stem = query.get("stem", [""])[0]
                if not ok_name(stem):
                    raise ValueError("非法影像名")
                site_dir(site)
                self.send_json({"annotations": load_mask_rles(site, stem)})
                return
            if path == "/api/image":
                site = query.get("site", [""])[0]
                stem = query.get("stem", [""])[0]
                modality = query.get("mod", ["opt"])[0]
                if not ok_name(stem):
                    raise ValueError("非法影像名")
                folder = site_dir(site)
                key = (site, stem, modality)

                def render():
                    if site.startswith(PREFIX):return jpeg_bytes(EARTH.rgb(site,stem,modality))
                    if modality == "sar":
                        name = stem[:-4] + "_SAR.tif" if stem.endswith("_OPT") else stem + "_SAR.tif"
                        rgb = read_sar_rgb(folder / name)
                    else:
                        rgb = read_opt_rgb(folder / f"{stem}.tif")
                    return jpeg_bytes(rgb)

                self.send_bytes(cached_jpeg(key, render), "image/jpeg", "private, max-age=86400")
                return
            self.send_json({"error": "未知路径"}, 404)
        except Exception as exc:
            traceback.print_exc()
            self.send_json({"error": str(exc)}, 423 if isinstance(exc, Occupied) else 409 if isinstance(exc, shared_masks.Conflict) else 400 if isinstance(exc, (ValueError, FileNotFoundError)) else 500)

    def do_POST(self):
        if not self.require_auth():
            return
        try:
            parsed = urlparse(self.path)
            payload = self.read_json()
            if parsed.path == '/api/lease':
                if not isinstance(payload,dict):raise ValueError('请求必须是对象')
                site=shared_masks.check_name(payload.get('site'));stem=shared_masks.check_name(payload.get('stem'))
                if site.startswith(PREFIX):EARTH.item(site,stem)
                elif stem not in list_tiles(site):raise ValueError('影像不存在')
                self.send_json(OCCUPANCY.operate(payload.get('action'),site,stem,payload.get('client'),payload.get('token')))
                return
            if parsed.path == "/api/save":
                self.send_json(save_review(payload))
                return
            if parsed.path == '/api/attributes':
                self.send_json(ATTRIBUTES.add(payload.get('kind'), payload.get('label')))
                return
            if parsed.path == "/api/categories":
                with shared_masks.LOCK:
                    if payload.get('value') in ('__unlabeled__', 'background', *RETIRED_CATEGORIES):
                        raise ValueError('该名称是保留类别')
                    result = save_custom_category(payload.get("value"), payload.get("label"))
                    current_label_map()
                self.send_json(result)
                return
            self.send_json({"error": "未知路径"}, 404)
        except Exception as exc:
            traceback.print_exc()
            self.send_json({"error": str(exc)}, 423 if isinstance(exc, Occupied) else 409 if isinstance(exc, shared_masks.Conflict) else 400 if isinstance(exc, (ValueError, FileNotFoundError)) else 500)


def main():
    REVIEW_ROOT.mkdir(parents=True, exist_ok=True)
    server = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    print(f"clean tool http://127.0.0.1:{PORT}", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
