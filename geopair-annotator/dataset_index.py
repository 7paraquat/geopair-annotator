"""Discover paired optical/SAR PNG images without distributing a private manifest."""
import hashlib
import json
from pathlib import Path
import re

SAFE = re.compile(r'^[A-Za-z0-9][A-Za-z0-9._-]*$')


def scan_dataset(root):
    root = Path(root).resolve()
    if not root.is_dir():
        raise ValueError('数据集目录不存在')
    items = []
    missing = []
    for region in sorted(root.iterdir()):
        if not region.is_dir():
            continue
        opt_dir = region / 'images/RGB_png'
        sar_dir = region / 'images/SAR_png'
        if not opt_dir.exists() and not sar_dir.exists():
            continue
        if not SAFE.fullmatch(region.name) or '..' in region.name:
            raise ValueError('地区文件夹名请使用英文字母、数字、横线或下划线：' + region.name)
        opt = {p.stem: p for p in opt_dir.glob('*.png') if p.is_file()}
        sar = {p.stem: p for p in sar_dir.glob('*.png') if p.is_file()}
        missing.extend(region.name + '/' + name for name in sorted(opt.keys() ^ sar.keys()))
        for stem in sorted(opt.keys() & sar.keys()):
            if not SAFE.fullmatch(stem) or '..' in stem:
                raise ValueError('影像文件名含不支持的字符：' + stem)
            for path in (opt[stem], sar[stem]):
                if not path.resolve().is_relative_to(root):
                    raise ValueError('影像路径越过数据集目录')
            items.append({'id':region.name+'/'+stem, 'region':region.name,
                          'rgb':opt[stem].relative_to(root).as_posix(),
                          'sar':sar[stem].relative_to(root).as_posix(),
                          # Compatibility metadata only; original masks are never opened.
                          'mask':f'{region.name}/masks/{stem}.tif'})
    if missing:
        raise ValueError('缺少光学或 SAR 配对文件，请补齐：\n' + '\n'.join(missing[:8]))
    if not items:
        raise ValueError('未找到配对 PNG。请选择包含 地区/images/RGB_png 和 SAR_png 的数据集根目录。')
    digest = hashlib.sha256(json.dumps(items, sort_keys=True).encode()).hexdigest()
    return {'items':items, 'count':len(items), 'selection_sha256':digest, 'scope':'all_available_pairs'}
