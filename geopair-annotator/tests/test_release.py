"""Test the built EXE without Python on PATH; all writes use isolated QA state."""
from pathlib import Path
import hashlib
import io
import json
import os
import shutil
import subprocess
import time
import urllib.request
import urllib.error
import zipfile
import numpy as np
from PIL import Image

root = Path(__file__).resolve().parents[1]
qa = root / 'qa' / time.strftime('%Y%m%d_%H%M%S')
software = qa / '中文路径 带空格' / 'GeoPairAnnotator'
shutil.copytree(root / 'dist/GeoPairAnnotator', software)
exe = software / 'GeoPairAnnotator.exe'
workspace = qa / '标注工作区'
data = qa / '数据集'
item = {'id':'Demo-City/sample_001','region':'Demo-City',
        'rgb':'Demo-City/images/RGB_png/sample_001.png',
        'sar':'Demo-City/images/SAR_png/sample_001.png'}
for field in ('rgb', 'sar'):
    target = data / item[field]
    target.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(np.full((32,48,3), 150 if field == 'rgb' else 80, np.uint8)).save(target)
before = {k: hashlib.sha256((data / item[k]).read_bytes()).hexdigest() for k in ('rgb','sar')}
env = dict(os.environ)
for key in list(env):
    if key.startswith('PYTHON'):
        del env[key]
env['PATH'] = os.environ['SystemRoot'] + '/System32;' + os.environ['SystemRoot']
process = None
def launch():
    global process, base
    process = subprocess.Popen([str(exe), '--headless', '--data', str(data), '--workspace', str(workspace)], env=env)
    for _ in range(100):
        if process.poll() is not None:
            raise AssertionError('EXE exited: ' + (workspace/'运行日志.txt').read_text(encoding='utf-8'))
        if (workspace/'running.json').exists(): break
        time.sleep(.1)
    status = json.loads((workspace/'running.json').read_text(encoding='utf-8'))
    assert status['count'] == 1
    base = status['url'].rstrip('/')
def stop():
    (workspace/'stop.request').write_text('stop')
    assert process.wait(timeout=15) == 0
def raw(path, payload=None):
    body = None if payload is None else json.dumps(payload).encode()
    req = urllib.request.Request(base+path, data=body, headers={'Content-Type':'application/json'})
    with urllib.request.urlopen(req, timeout=15) as response: return response.read()
def get(path, payload=None): return json.loads(raw(path, payload))
try:
    launch()
    duplicate = subprocess.run([str(exe), '--headless', '--data', str(data), '--workspace', str(workspace)], env=env, timeout=15)
    assert duplicate.returncode == 1, 'Duplicate workspace should be blocked'
    site = 'EarthMiss--'+item['region']; stem = Path(item['rgb']).stem
    query = '?site='+site+'&stem='+stem
    assert get('/api/sites')['sites'] == [site]
    assert b'<html' in raw('/').lower()
    for path in ['/app.20261029-dual-masks-1.js', '/geometry.js']:
        assert len(raw(path)) > 1000
    for mode in ('opt','sar'):
        assert Image.open(io.BytesIO(raw('/api/image'+query+'&mod='+mode))).size == (48,32)
    tile = get('/api/tile'+query)
    assert tile['source_kind'] == 'blank' and tile['annotations'] == []
    get('/api/categories', {'value':'qa_custom', 'label':'测试新增类别'})
    get('/api/attributes', {'kind':'color','label':'测试颜色'})
    annotation = {'id':1, 'category':'qa_custom', 'polygon':[[1,1],[9,1],[9,9],[1,9]],
                  'sar_polygon':[[11,11],[19,11],[19,19],[11,19]], 'sar_segmentation':None,
                  'color':'测试颜色', 'material':'metal', 'task':'测试功能'}
    payload = {'site':site,'stem':stem,'image_size':[32,48],'base_revision':None,
               'annotations':[annotation], 'geometry_mode':'per_modality','workflow_status':'done'}
    saved = get('/api/save',payload)
    restored = get('/api/tile'+query)
    assert restored['annotations'][0]['sar_polygon'] != restored['annotations'][0]['polygon']
    assert restored['annotations'][0]['task'] == '测试功能'
    try:
        get('/api/save',payload)
        raise AssertionError('Stale revision accepted')
    except urllib.error.HTTPError as exc:
        assert exc.code == 409
    with zipfile.ZipFile(io.BytesIO(raw('/api/export'+query))) as archive:
        opt = np.array(Image.open(io.BytesIO(archive.read('masks_opt/'+stem+'.tif'))))
        sar = np.array(Image.open(io.BytesIO(archive.read('masks_sar/'+stem+'.tif'))))
        category_id = next(v['id'] for v in restored['label_map']['classes'] if v['value']=='qa_custom')
        expected_opt=np.zeros((32,48),np.uint8);expected_opt[1:9,1:9]=category_id
        expected_sar=np.zeros((32,48),np.uint8);expected_sar[11:19,11:19]=category_id
        assert np.array_equal(opt,expected_opt) and np.array_equal(sar,expected_sar)
    assert get('/api/progress')['regions'][0]['percent'] == 100
    stop(); launch()
    assert get('/api/tile'+query)['revision'] == saved['revision']
    assert get('/api/meta')['category_labels']['qa_custom'] == '测试新增类别'
    stop()
    export = qa / '交回标注.zip'
    result = subprocess.run([str(exe), '--workspace', str(workspace), '--export', str(export)], env=env, timeout=20)
    assert result.returncode == 0
    with zipfile.ZipFile(export) as archive:
        names = archive.namelist()
        assert not any('.sqlite3' in name or name.endswith('.png') for name in names)
        manifest = json.loads(archive.read('package.json'))
        for name, digest in manifest['sha256'].items():
            assert hashlib.sha256(archive.read(name)).hexdigest() == digest
        assert any(name.endswith('/opt_mask.tif') for name in names)
        assert any(name.endswith('/sar_mask.tif') for name in names)
    assert all(hashlib.sha256((data/item[k]).read_bytes()).hexdigest()==v for k,v in before.items())
    # A half-missing pair must fail, rather than silently disappearing.
    (data/item['sar']).rename(data/'sar-temporary.png')
    bad = subprocess.run([str(exe),'--headless','--data',str(data),'--workspace',str(qa/'broken')], env=env, timeout=20)
    assert bad.returncode == 1
    (data/'sar-temporary.png').rename(data/item['sar'])
    report = {'passed':True, 'qa_dir':str(qa), 'exe':str(exe), 'python_on_path':False,
              'checks':['Chinese paths/spaces','bundled dependencies','single workspace lock','local frontend/assets',
              'optical/SAR imagery','blank initial annotations/no original masks','Chinese custom labels',
              'independent optical/SAR polygons','TIFF pixel equality','stale write rejected','progress',
              'restart persistence','export SHA256 integrity','original imagery unchanged','incomplete pair rejected']}
    (root/'test_report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(report,ensure_ascii=False))
finally:
    if process is not None and process.poll() is None:
        (workspace/'stop.request').write_text('stop')
        try: process.wait(timeout=15)
        except subprocess.TimeoutExpired: process.terminate()
