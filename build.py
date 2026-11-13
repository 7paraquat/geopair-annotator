"""Build a standalone Windows application from this repository alone."""
from pathlib import Path
import shutil
import subprocess
import sys

root = Path(__file__).resolve().parent
if sys.platform != 'win32':
    raise SystemExit('请在 Windows x64 上构建 Windows 免安装包。')
command = [sys.executable, '-m', 'PyInstaller', '--noconfirm', '--clean', '--onedir', '--windowed',
           '--name','GeoPairAnnotator','--distpath',str(root/'dist'),'--workpath',str(root/'build'),
           '--specpath',str(root),'--paths',str(root/'app'),
           '--add-data',f'{root / "app/static"};app/static','--collect-all','pycocotools']
for module in ('matplotlib','scipy','pandas','torch','IPython','pytest','cv2','sympy'):
    command.extend(['--exclude-module',module])
for dependency in ('numpy','Pillow','tifffile','pycocotools'):
    command.extend(['--copy-metadata',dependency])
command.append(str(root/'desktop.py'))
subprocess.run(command,cwd=root,check=True)
release = root/'dist/GeoPairAnnotator'
for name in ('README.md','LICENSE','THIRD_PARTY_NOTICES.md','version.json','update.ps1'):
    shutil.copy2(root/name,release/name)
shutil.copytree(root/'docs',release/'docs',dirs_exist_ok=True)
shutil.copytree(root/'third_party',release/'third_party',dirs_exist_ok=True)
python_license=Path(sys.base_prefix)/'LICENSE.txt'
if python_license.is_file():
    shutil.copy2(python_license,release/'third_party/Python-LICENSE.txt')
shutil.copytree(root/'examples',release/'examples',dirs_exist_ok=True,ignore=shutil.ignore_patterns('__pycache__'))
print(release)
