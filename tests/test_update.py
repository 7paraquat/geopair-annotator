"""Exercise archive validation and replacement without touching a real workspace."""
from pathlib import Path
import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
import zipfile

root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root))
from updater import prepare_update

old_archive = root / 'release/GeoPairAnnotator-v0.3.0-windows-x64.zip'
new_archive = root / 'release/GeoPairAnnotator-v0.4.1-windows-x64.zip'
assert old_archive.is_file() and new_archive.is_file()
legacy_roots = {'GeoPairAnnotator.exe', '_internal', 'README.md', 'LICENSE',
                'THIRD_PARTY_NOTICES.md', 'RELEASE_NOTES_v0.2.0.md', 'docs',
                'third_party', 'examples', 'version.json', 'release_manifest.json', 'update.ps1'}
with zipfile.ZipFile(new_archive) as archive:
    assert all(Path(name).parts[1] in legacy_roots for name in archive.namelist() if not name.endswith('/'))
with tempfile.TemporaryDirectory(prefix='geopair-update-qa-', dir=root / 'qa') as directory:
    qa = Path(directory)
    with zipfile.ZipFile(old_archive) as archive:
        archive.extractall(qa / 'old')
    install = qa / 'old/GeoPairAnnotator'
    workspace = install / 'workspace'
    workspace.mkdir()
    marker = workspace / 'state/reviews_shared/region/sample.json'
    marker.parent.mkdir(parents=True)
    marker.write_text('{"category":"road","label":"道路"}', encoding='utf-8')
    before = hashlib.sha256(marker.read_bytes()).hexdigest()
    malicious = qa / 'malicious.zip'
    with zipfile.ZipFile(malicious, 'w') as archive:
        archive.writestr('GeoPairAnnotator/workspace/state/overwrite.json', '{}')
    try:
        prepare_update(malicious, '0.1.0', qa)
    except ValueError as exc:
        assert '非法文件路径' in str(exc)
    else:
        raise AssertionError('Update accepted workspace payload')
    stage, version = prepare_update(new_archive, '0.3.0', qa)
    assert version == '0.4.1'
    script = qa / 'update-runner.ps1'
    shutil.copy2(install / 'update.ps1', script)
    result = subprocess.run(['powershell.exe', '-NoProfile', '-ExecutionPolicy', 'Bypass',
        '-File', str(script), '-InstallDir', str(install), '-StageDir', str(stage),
        '-WaitPid', '999999', '-SkipLaunch'], capture_output=True, text=True, timeout=120)
    assert result.returncode == 0, result.stderr + result.stdout
    assert json.loads((install / 'version.json').read_text(encoding='utf-8'))['version'] == version
    assert hashlib.sha256(marker.read_bytes()).hexdigest() == before
    assert (install / 'GeoPairAnnotator.exe').is_file()
    assert (install / 'release_manifest.json').is_file()
    assert not stage.exists()
print('PASS: v0.3 ZIP upgraded; workspace bytes unchanged; new EXE and version installed.')
