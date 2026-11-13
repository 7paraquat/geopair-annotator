"""Road centerline export and mask validation on an isolated workspace."""
import json
from pathlib import Path
import sys
import tempfile

import numpy as np
import tifffile

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'app'))
import shared_masks as masks


def raster(points, width, h, w):
    yy, xx = np.mgrid[:h, :w]
    px, py = xx + .5, yy + .5
    output = np.zeros((h, w), dtype=np.uint8)
    for (ax, ay), (bx, by) in zip(points, points[1:]):
        dx, dy = bx - ax, by - ay
        t = np.clip(((px - ax) * dx + (py - ay) * dy) / (dx * dx + dy * dy), 0, 1)
        output |= ((px - ax - t * dx) ** 2 + (py - ay - t * dy) ** 2 <= (width / 2) ** 2 + 1e-9)
    return output


with tempfile.TemporaryDirectory(prefix='earthmiss-road-') as folder:
    root = Path(folder) / 'state'
    opt = [[-5, 8], [30, 8], [45, 25]]
    sar = [[-5, 10], [30, 10], [45, 25]]
    h, w = 40, 48
    opt_mask, sar_mask = raster(opt, 8, h, w), raster(sar, 12, h, w)
    mapping = masks.label_map(root, ['road'], {'road': '道路'})
    annotation = {'id': 1, 'category': 'road', 'polygon': None,
                  'segmentation': masks.encode(opt_mask), 'road_centerline': opt,
                  'road_width': 8, 'sar_polygon': None,
                  'sar_segmentation': masks.encode(sar_mask),
                  'sar_road_centerline': sar, 'sar_road_width': 12}
    payload = {'site': 'EarthMiss--Test', 'stem': 'Test_clip_1', 'image_size': [h, w],
               'base_revision': None, 'geometry_mode': 'per_modality',
               'annotations': [annotation]}
    result = masks.save(root, None, payload, mapping, lambda site, stem: [h, w])
    record = json.loads((root / payload['site'] / (payload['stem'] + '.json')).read_text(encoding='utf-8'))
    revision = root / record['export_dir']
    assert result['count'] == 1
    assert record['annotations'][0]['road_width'] == 8
    assert record['annotations'][0]['sar_road_width'] == 12
    assert np.array_equal(tifffile.imread(revision / 'opt_mask.tif'), opt_mask * 2)
    assert np.array_equal(tifffile.imread(revision / 'sar_mask.tif'), sar_mask * 2)
    assert not np.array_equal(opt_mask, sar_mask)
    bad = dict(payload, base_revision=result['revision'], annotations=[dict(annotation, road_width=9)])
    try:
        masks.save(root, None, bad, mapping, lambda site, stem: [h, w])
    except ValueError as error:
        assert '不一致' in str(error)
    else:
        raise AssertionError('Mismatched width was accepted')
    unchanged = json.loads((root / payload['site'] / (payload['stem'] + '.json')).read_text(encoding='utf-8'))
    assert unchanged['revision'] == result['revision']

print('PASS: independent optical/SAR road geometry saved at original size; mismatched width rejected.')
