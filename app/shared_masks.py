"""Shared OPT/SAR labels: stable user taxonomy, validated geometry, atomic revisions."""
import hashlib
import io
import json
import math
import os
from pathlib import Path
import re
import threading
import uuid
from contextlib import contextmanager

import numpy as np
import tifffile
from PIL import Image
from pycocotools import mask as coco

LOCK = threading.RLock()
SAFE = re.compile(r'^[A-Za-z0-9][A-Za-z0-9._-]*$')

class Conflict(ValueError):
    pass

@contextmanager
def writer(root):
    """Serialize commits across threads and Linux service processes."""
    with LOCK:
        root.mkdir(parents=True, exist_ok=True)
        with (root/'.writer.lock').open('a+b') as lock:
            if os.name == 'posix':
                import fcntl
                fcntl.flock(lock, fcntl.LOCK_EX)
            try:
                yield
            finally:
                if os.name == 'posix':
                    fcntl.flock(lock, fcntl.LOCK_UN)

def check_name(value):
    if not isinstance(value, str) or not SAFE.fullmatch(value) or '..' in value:
        raise ValueError('非法站点或影像标识')
    return value

def atomic_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name+'.'+uuid.uuid4().hex+'.tmp')
    try:
        with temp.open('w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, allow_nan=False)
            f.flush()
            os.fsync(f.fileno())
        os.replace(temp, path)
    finally:
        temp.unlink(missing_ok=True)

def label_map(root, categories, labels):
    """Append-only IDs. Index zero is unlabeled; one is explicit background."""
    with writer(root):
        path = root/'label_map.json'
        data = json.loads(path.read_text(encoding='utf-8')) if path.exists() else {
            'encoding':'uint8-indexed-tiff', 'ignore_index':0,
            'classes':[{'id':0,'value':'__unlabeled__','label':'未标注/忽略'},
                       {'id':1,'value':'background','label':'背景'}]}
        entries = data['classes']
        known = {item['value'] for item in entries}
        changed = not path.exists()
        # Labels may be renamed while all historical numeric IDs stay stable.
        for item in entries:
            label = labels.get(item['value'])
            if label is not None and item['label'] != label:
                item['label'] = label
                changed = True
        for value in categories:
            if value in known:
                continue
            next_id = max(item['id'] for item in entries)+1
            if next_id > 255:
                raise ValueError('8位标签最多支持254个前景类别；请先扩展导出格式')
            entries.append({'id':next_id, 'value':value, 'label':labels.get(value,value)})
            known.add(value)
            changed = True
        if changed:
            atomic_json(path,data)
        return data

def polygon_points(points, h, w):
    if not isinstance(points,list) or not 3 <= len(points) <= 512:
        raise ValueError('多边形需要3至512个顶点')
    p = []
    for point in points:
        if not isinstance(point,(list,tuple)) or len(point)!=2:
            raise ValueError('顶点必须是[x,y]')
        if any(isinstance(v,bool) or not isinstance(v,(float,int)) or not math.isfinite(v) for v in point):
            raise ValueError('顶点坐标不是有限数值')
        x,y = point
        if not 0 <= x <= w or not 0 <= y <= h:
            raise ValueError('顶点超出影像范围')
        p.append([float(x),float(y)])
    if len({tuple(v) for v in p}) != len(p):
        raise ValueError('多边形含重复顶点')
    def cross(a,b,c):
        return (b[0]-a[0])*(c[1]-a[1])-(b[1]-a[1])*(c[0]-a[0])
    def on(a,b,c):
        return abs(cross(a,b,c))<1e-9 and min(a[0],b[0])-1e-9<=c[0]<=max(a[0],b[0])+1e-9 and min(a[1],b[1])-1e-9<=c[1]<=max(a[1],b[1])+1e-9
    def intersects(a,b,c,d):
        a1,a2,b1,b2=cross(a,b,c),cross(a,b,d),cross(c,d,a),cross(c,d,b)
        return (a1*a2<0 and b1*b2<0) or on(a,b,c) or on(a,b,d) or on(c,d,a) or on(c,d,b)
    for i in range(len(p)):
        a,b,c=p[i-1],p[i],p[(i+1)%len(p)]
        if abs(cross(a,b,c))<1e-9 and (a[0]-b[0])*(c[0]-b[0])+(a[1]-b[1])*(c[1]-b[1])>0:
            raise ValueError('多边形边发生折返重叠')
        for j in range(i+1,len(p)):
            if j==i+1 or (i==0 and j==len(p)-1): continue
            if intersects(p[i],p[(i+1)%len(p)],p[j],p[(j+1)%len(p)]):
                raise ValueError('多边形边相交或相触，请调整顶点')
    area=abs(sum(p[i][0]*p[(i+1)%len(p)][1]-p[(i+1)%len(p)][0]*p[i][1] for i in range(len(p))))/2
    if area < 0.5: raise ValueError('多边形面积太小或顶点共线')
    return p

def polygon_mask(points,h,w):
    p=polygon_points(points,h,w)
    mask=np.zeros((h,w),dtype=np.uint8)
    for row in range(max(0,math.floor(min(y for x,y in p))),min(h,math.ceil(max(y for x,y in p)))):
        y=row+0.5
        xs=[]
        for i,(ax,ay) in enumerate(p):
            bx,by=p[(i+1)%len(p)]
            if (ay<=y<by) or (by<=y<ay): xs.append(ax+(y-ay)*(bx-ax)/(by-ay))
        xs.sort()
        for i in range(0,len(xs),2):
            left=max(0,math.ceil(xs[i]-0.5)); right=min(w,math.ceil(xs[i+1]-0.5))
            mask[row,left:right]=1
    if not mask.any(): raise ValueError('多边形没有覆盖任何像素中心')
    return mask

def encode(mask):
    rle=coco.encode(np.asfortranarray(mask.astype(np.uint8)))
    return {'size':list(mask.shape),'counts':rle['counts'].decode('ascii')}

def decode(rle,h,w):
    if not isinstance(rle,dict) or rle.get('size')!=[h,w] or not isinstance(rle.get('counts'),str):
        raise ValueError('掩膜尺寸/编码与原影像不一致')
    text=rle['counts']; counts=[]; i=0
    while i<len(text):
        number=0; shift=0
        while True:
            if i>=len(text) or shift>35: raise ValueError('无效RLE编码')
            c=ord(text[i])-48; i+=1
            if c<0 or c>63: raise ValueError('无效RLE字符')
            number|=(c&31)<<shift; shift+=5
            if not c&32:
                if c&16: number|=(-1)<<shift
                break
        if len(counts)>2: number+=counts[-2]
        if number<0 or number>h*w: raise ValueError('无效RLE游程')
        counts.append(number)
        if len(counts)>h*w+1: raise ValueError('RLE游程过多')
    if sum(counts)!=h*w: raise ValueError('RLE像素数量不匹配')
    flat=np.zeros(h*w,dtype=np.uint8); offset=0
    for index,n in enumerate(counts):
        if index%2: flat[offset:offset+n]=1
        offset+=n
    return flat.reshape((h,w),order='F')

def image_shape(path):
    with tifffile.TiffFile(path) as f: shape=f.series[0].shape
    if len(shape)==2: h,w=shape
    elif len(shape)==3 and shape[-1] in (1,3,4): h,w=shape[:2]
    elif len(shape)==3 and shape[0] in (1,3,4): h,w=shape[1:]
    else: raise ValueError('不支持的影像维度')
    if h<1 or w<1 or h*w>16777216: raise ValueError('影像尺寸超出审核范围')
    return [int(h),int(w)]

def pair_shape(data_root,site,stem):
    check_name(site);check_name(stem)
    opt=data_root/site/(stem+'.tif')
    sar=data_root/site/((stem[:-4] if stem.endswith('_OPT') else stem)+'_SAR.tif')
    shape=image_shape(opt)
    if image_shape(sar)!=shape: raise ValueError('光学和SAR尺寸不一致，不能输出共享掩膜')
    return shape

def pointer(root,site,stem):
    return root/check_name(site)/(check_name(stem)+'.json')

def side_geometry(raw, prefix, h, w, optional=False):
    poly=raw.get(prefix+'polygon'); segmentation=raw.get(prefix+'segmentation')
    if poly is None and segmentation is None and optional:
        return None,None,None,None
    if poly is not None:
        poly=polygon_points(poly,h,w); mask=polygon_mask(poly,h,w)
        if segmentation is not None and not np.array_equal(mask,decode(segmentation,h,w)):
            raise ValueError('多边形与掩膜不一致，请完成当前编辑')
    else:
        mask=decode(segmentation,h,w)
    y,x=np.nonzero(mask)
    if not len(x): raise ValueError('空掩膜请使用本侧不可确认或删除标注')
    return poly,mask,encode(mask),[int(x.min()),int(y.min()),int(x.max()+1),int(y.max()+1)]

def road_geometry(raw, prefix, category, mask, h, w):
    points = raw.get(prefix + 'road_centerline')
    width = raw.get(prefix + 'road_width')
    if points is None and width is None:
        return None, None
    if category != 'road' or mask is None or not isinstance(points, list) or not 2 <= len(points) <= 512:
        raise ValueError('道路中线与类别或本侧掩膜不一致')
    if isinstance(width, bool) or not isinstance(width, int) or not 1 <= width <= 200:
        raise ValueError('道路宽度需为1至200像素')
    cleaned = []
    for point in points:
        if not isinstance(point, (list, tuple)) or len(point) != 2 or any(
            isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v)
            or abs(v) > max(h, w) * 1024 for v in point
        ):
            raise ValueError('道路中线坐标无效')
        cleaned.append([float(point[0]), float(point[1])])
    expected = np.zeros((h, w), dtype=np.uint8)
    radius = width / 2
    for (ax, ay), (bx, by) in zip(cleaned, cleaned[1:]):
        dx, dy = bx - ax, by - ay
        length2 = dx * dx + dy * dy
        if length2 < 1e-12:
            raise ValueError('道路中线含重合的相邻点')
        x0, x1 = max(0, math.floor(min(ax, bx) - radius)), min(w, math.ceil(max(ax, bx) + radius))
        y0, y1 = max(0, math.floor(min(ay, by) - radius)), min(h, math.ceil(max(ay, by) + radius))
        if x0 >= x1 or y0 >= y1:
            continue
        y, x = np.ogrid[y0:y1, x0:x1]
        px, py = x + .5, y + .5
        t = np.clip(((px - ax) * dx + (py - ay) * dy) / length2, 0, 1)
        expected[y0:y1, x0:x1] |= ((px - ax - t * dx) ** 2 + (py - ay - t * dy) ** 2 <= radius ** 2 + 1e-9)
    if not np.array_equal(expected, mask):
        raise ValueError('道路中线、宽度与掩膜不一致，请重新生成')
    return cleaned, width

def save(root,data_root,payload,mapping,shape_resolver=None,metadata=None):
    site=check_name(payload.get('site')); stem=check_name(payload.get('stem'))
    workflow=payload.get('workflow_status','done')
    if workflow not in ('in_progress','done','discussion'):
        raise ValueError('无效影像状态')
    shape=shape_resolver(site,stem) if shape_resolver else pair_shape(data_root,site,stem); h,w=shape
    if payload.get('image_size')!=shape: raise ValueError('请求尺寸与原图不一致，禁止缩放标签')
    raws=payload.get('annotations')
    if not isinstance(raws,list) or len(raws)>4096: raise ValueError('标注列表不合法')
    ids={c['value']:c['id'] for c in mapping['classes'] if c['id']>0}
    dual=payload.get('geometry_mode')=='per_modality'
    if payload.get('geometry_mode') not in (None,'shared','per_modality'): raise ValueError('无效标注模式')
    classes=set(ids); cleaned=[]; seen=set(); result=np.zeros(shape,dtype=np.uint8); sar_result=np.zeros(shape,dtype=np.uint8)
    for raw in raws:
        if not isinstance(raw,dict): raise ValueError('标注格式不合法')
        ident=raw.get('id')
        if isinstance(ident,bool) or not isinstance(ident,int) or ident<=0 or ident in seen:
            raise ValueError('标注ID必须唯一且为正整数')
        seen.add(ident)
        category=raw.get('category')
        if category not in classes: raise ValueError('请为每条标注选择已有类别：'+str(category))
        poly,mask,rle,box=side_geometry(raw,'',h,w,optional=dual)
        if dual:
            if 'sar_segmentation' not in raw or 'sar_polygon' not in raw: raise ValueError('独立标注必须明确提供两侧轮廓')
            sar_poly,sar_mask,sar_rle,sar_box=side_geometry(raw,'sar_',h,w,optional=True)
            if mask is None and sar_mask is None: raise ValueError('两侧均无轮廓，请删除整条标注')
        else:
            if raw.get('sar_segmentation') is not None and not np.array_equal(mask,decode(raw['sar_segmentation'],h,w)):
                raise ValueError('共享模式不允许光学和SAR掩膜不同')
            sar_poly,sar_mask,sar_rle,sar_box=poly,mask,rle,box
        road_points, road_width = road_geometry(raw, '', category, mask, h, w)
        if dual:
            sar_road_points, sar_road_width = road_geometry(raw, 'sar_', category, sar_mask, h, w)
        else:
            sar_road_points, sar_road_width = road_points, road_width
        item={key:raw.get(key,'') for key in ['source_category','task','color','material','origin']}
        item.update(id=ident,category=category,bbox_xyxy=box,sar_bbox_xyxy=sar_box,
                    opt_keep=mask is not None,sar_keep=sar_mask is not None,segmentation=rle,sar_segmentation=sar_rle,polygon=poly,sar_polygon=sar_poly)
        item.update(road_centerline=road_points,road_width=road_width,
                    sar_road_centerline=sar_road_points,sar_road_width=sar_road_width)
        cleaned.append(item)
        if mask is not None: result[mask.astype(bool)]=ids[category]
        if sar_mask is not None: sar_result[sar_mask.astype(bool)]=ids[category]
    with writer(root):
        dest=pointer(root,site,stem)
        old=json.loads(dest.read_text(encoding='utf-8')) if dest.exists() else {}
        if 'base_revision' not in payload:
            raise ValueError('缺少版本号，请重新加载页面')
        if payload['base_revision']!=old.get('revision'):
            raise Conflict('该图已被另一窗口保存，请重新加载后合并修改')
        if old.get('geometry_mode')=='per_modality' and not dual:
            raise Conflict('此影像已启用两侧独立标注，请备份未保存内容并刷新新版，防止覆盖另一侧轮廓')
        rev=uuid.uuid4().hex
        relative=Path(site)/'_revisions'/stem/rev
        folder=root/relative
        folder.mkdir(parents=True)
        # TIFF is palette-indexed like EarthMiss; numeric IDs are preserved, never RGB.
        palette=[]
        for i in range(256): palette.extend([0,0,0] if i==0 else [255,255,255] if i==1 else [(i*67)%206+35,(i*97)%206+35,(i*131)%206+35])
        outputs={'opt_mask.tif':result,'sar_mask.tif':sar_result} if dual else {'mask.tif':result}
        for name,pixels in outputs.items():
            im=Image.fromarray(pixels,mode='P'); im.putpalette(palette)
            im.save(folder/name,format='TIFF',compression='raw')
            with Image.open(folder/name) as verified:
                if verified.mode!='P' or not np.array_equal(np.asarray(verified),pixels):
                    raise RuntimeError('TIFF写出复核失败')
        atomic_json(folder/'classes.json',mapping)
        record={'schema_version':'paired-mask-v5' if dual else 'guso-shared-mask-v4','site':site,'stem':stem,'image_size':shape,
                'workflow_status':workflow,
                'revision':rev,'mask_encoding':'coco_rle','shared_mask':not dual,'geometry_mode':'per_modality' if dual else 'shared','annotations':cleaned,
                'export_dir':relative.as_posix(),'overlap_policy':'last_annotation_wins',
                'label_map':mapping,'mask_sha256':hashlib.sha256((folder/('opt_mask.tif' if dual else 'mask.tif')).read_bytes()).hexdigest()}
        if dual:
            record['mask_sha256_by_modality']={mod:hashlib.sha256((folder/(mod+'_mask.tif')).read_bytes()).hexdigest() for mod in ('opt','sar')}
            record['coordinate_system']='Each mask uses original pixel coordinates of its own image; matching annotation IDs link objects, not pixels.'
        if metadata:
            for key in ('dataset','source_item','selection_sha256','source_class_mapping','source_ignore_index'):
                if key in metadata: record[key]=metadata[key]
        atomic_json(folder/'review.json',record)
        atomic_json(dest,record)  # commit point: readers see a complete immutable revision
    return {'ok':True,'count':len(cleaned),'revision':rev,'mask_sha256':record['mask_sha256']}

def export(root,site,stem):
    record=json.loads(pointer(root,site,stem).read_text(encoding='utf-8'))
    folder=(root/record['export_dir']).resolve()
    if not folder.is_relative_to(root.resolve()): raise ValueError('非法导出路径')
    import zipfile
    output=io.BytesIO()
    with zipfile.ZipFile(output,'w',zipfile.ZIP_DEFLATED) as z:
        if record.get('geometry_mode')=='per_modality':
            for mod in ('opt','sar'):z.write(folder/(mod+'_mask.tif'),'masks_'+mod+'/'+stem+'.tif')
            z.writestr('README.txt','光学与SAR分别使用 masks_opt 和 masks_sar。原图尺寸与类别ID不变；同一标注ID关联同一地物，轮廓独立。未标像素0应忽略，不作为背景负样本。opt_keep/sar_keep=false 表示本侧未确认，不应据此推断地物不存在。联合训练需选定输出坐标系；本工具没有修改影像配准。')
        else:z.write(folder/'mask.tif','masks/'+stem+'.tif')
        z.write(folder/'classes.json','classes.json')
        z.write(folder/'review.json','review.json')
    return output.getvalue()
