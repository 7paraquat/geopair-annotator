"""Create a clean binary release ZIP and SHA256 checksum."""
from pathlib import Path
import hashlib
import zipfile

root=Path(__file__).resolve().parent
source=root/'dist/GeoPairAnnotator'
if not (source/'GeoPairAnnotator.exe').exists():
    raise SystemExit('请先运行 python build.py')
if (source/'workspace').exists():
    raise SystemExit('发布目录包含个人工作区，请使用重新构建的干净目录。')
output=root/'release'; output.mkdir(exist_ok=True)
target=output/'GeoPairAnnotator-windows-x64.zip'
with zipfile.ZipFile(target,'w',zipfile.ZIP_DEFLATED) as archive:
    for path in sorted(source.rglob('*')):
        if path.is_file():archive.write(path,path.relative_to(source.parent).as_posix())
with zipfile.ZipFile(target) as archive:
    assert archive.testzip() is None
digest=hashlib.sha256(target.read_bytes()).hexdigest()
target.with_suffix('.zip.sha256').write_text(digest+'  '+target.name+'\n',encoding='utf-8')
print(target)
