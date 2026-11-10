"""Offline, self-contained Windows launcher for the existing EarthMiss editor."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import sys
import threading
import time
import traceback
import uuid
import webbrowser
import zipfile

BASE = Path(sys.executable).parent if getattr(sys, 'frozen', False) else Path(__file__).parent
ASSETS = Path(getattr(sys, '_MEIPASS', Path(__file__).parent))
sys.path.insert(0, str(ASSETS / 'app'))


def read_json(path):
    return json.loads(path.read_text(encoding='utf-8'))


def write_json(path, value):
    temp = path.with_suffix('.tmp')
    temp.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')
    os.replace(temp, path)


def prepare(root, workspace):
    from dataset_index import scan_dataset
    source = scan_dataset(root)
    present = source['items']
    # Validate each pair without opening or requiring dataset masks.
    from PIL import Image
    for item in present:
        with Image.open(root / item['rgb']) as opt, Image.open(root / item['sar']) as sar:
            if opt.size != sar.size or opt.width * opt.height > 16777216:
                raise ValueError('配对影像尺寸不一致或过大：' + item['id'])
    manifest = {'count': len(present), 'items': present,
                'selection_sha256': source['selection_sha256'], 'scope': 'all_available_pairs'}
    write_json(workspace / 'selected.json', manifest)
    return manifest


def start_service(root, workspace, port=0):
    manifest = prepare(root, workspace)
    state = workspace / 'state'
    (state / 'reviews_shared').mkdir(parents=True, exist_ok=True)
    identity = workspace / 'identity.json'
    if not identity.exists():
        write_json(identity, {'workspace_id': uuid.uuid4().hex})
    os.environ.update(GUSO_DATA_ROOT=str(workspace / 'no_guso'), GUSO_REVIEW_ROOT=str(state),
                      GUSO_SHARED_ROOT=str(state / 'reviews_shared'), GUSO_ACCESS_TOKEN='',
                      GUSO_CUSTOM_CATEGORIES=str(state / 'custom_categories.json'),
                      EARTHMISS_DATA_ROOT=str(root), EARTHMISS_MANIFEST=str(workspace / 'selected.json'))
    import server
    server.STATIC = ASSETS / 'app/static'
    http = server.ThreadingHTTPServer(('127.0.0.1', port), server.Handler)
    threading.Thread(target=http.serve_forever, daemon=True).start()
    return server, http, manifest


def export_bundle(workspace, dest, service=None):
    """Snapshot saved records and label dictionaries; no imagery or editing leases."""
    import contextlib
    lock = service.shared_masks.LOCK if service else contextlib.nullcontext()
    attr_lock = service.ATTRIBUTES.lock if service else contextlib.nullcontext()
    # Same lock order as category writes; attribute operations do not nest these locks.
    with lock, attr_lock:
        temp = dest.with_name(dest.name + '.' + uuid.uuid4().hex + '.tmp')
        try:
            with zipfile.ZipFile(temp, 'w', zipfile.ZIP_DEFLATED) as archive:
                checksums = {}
                for file in sorted((workspace / 'state').rglob('*')):
                    if not file.is_file() or file.name.startswith('.') or '.sqlite3' in file.name or file.suffix == '.tmp':
                        continue
                    relative = file.relative_to(workspace).as_posix()
                    content = file.read_bytes()
                    archive.writestr(relative, content)
                    checksums[relative] = hashlib.sha256(content).hexdigest()
                for name in ('selected.json', 'identity.json'):
                    if (workspace / name).exists():
                        archive.write(workspace / name, name)
                archive.writestr('package.json', json.dumps({'format': 'earthmiss-desktop-1',
                    'created_local': time.strftime('%Y-%m-%d %H:%M:%S'), 'sha256': checksums}, ensure_ascii=False))
                archive.writestr('说明.txt', '此包包含已保存标注、类别表和历史版本，不含影像。不同人的同名影像不得直接覆盖合并；新增类别应按类别名称核对映射，不能仅比较像素ID。')
            os.replace(temp, dest)
        finally:
            temp.unlink(missing_ok=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--headless', action='store_true')
    parser.add_argument('--data')
    parser.add_argument('--workspace', default=str(BASE / 'workspace'))
    parser.add_argument('--port', type=int, default=0)
    parser.add_argument('--export')
    args = parser.parse_args()
    workspace = Path(args.workspace).resolve()
    workspace.mkdir(parents=True, exist_ok=True)
    # The OS releases this lock on exit, including an unexpected termination.
    import msvcrt
    instance_lock = (workspace / '.instance.lock').open('a+b')
    if instance_lock.seek(0, 2) == 0:
        instance_lock.write(b'0'); instance_lock.flush()
    instance_lock.seek(0)
    try:
        msvcrt.locking(instance_lock.fileno(), msvcrt.LK_NBLCK, 1)
    except OSError:
        raise RuntimeError('这个标注工作区已经打开，请使用已有窗口。')
    # Keep instance_lock alive until this function exits.
    sys.stdout = sys.stderr = (workspace / '运行日志.txt').open('a', encoding='utf-8', buffering=1)
    if args.export:
        export_bundle(workspace, Path(args.export).resolve())
        return
    config_path = workspace / 'config.json'
    config = read_json(config_path) if config_path.exists() else {}
    config.setdefault('data_root', '')
    if args.headless:
        service, http, manifest = start_service(Path(args.data or config['data_root']).resolve(), workspace, args.port)
        write_json(workspace / 'running.json', {'url': f'http://127.0.0.1:{http.server_port}/',
                   'count': manifest['count'], 'pid': os.getpid()})
        try:
            while not (workspace / 'stop.request').exists():
                time.sleep(.25)
        finally:
            http.shutdown(); http.server_close()
            (workspace / 'stop.request').unlink(missing_ok=True)
            (workspace / 'running.json').unlink(missing_ok=True)
        return
    import tkinter as tk
    from tkinter import ttk, filedialog, messagebox
    window = tk.Tk()
    window.title('GeoPair Annotator · 光学 / SAR 标注')
    window.geometry('650x410')
    window.minsize(650, 410)
    window.option_add('*Font', 'MicrosoftYaHei 10')
    frame = ttk.Frame(window, padding=24); frame.pack(fill='both', expand=True)
    ttk.Label(frame, text='GeoPair Annotator', font=('Microsoft YaHei', 18, 'bold')).pack(anchor='w')
    ttk.Label(frame, text='选择收到的数据集文件夹，然后开始标注。无需联网。').pack(anchor='w', pady=(8, 16))
    dataset = tk.StringVar(value=config['data_root'])
    row = ttk.Frame(frame); row.pack(fill='x')
    entry = ttk.Entry(row, textvariable=dataset); entry.pack(side='left', fill='x', expand=True)
    running = {'http': None, 'server': None, 'url': None}
    def choose():
        path = filedialog.askdirectory(title='选择包含各地区文件夹的 EarthM3 目录')
        if path: dataset.set(path)
    browse = ttk.Button(row, text='选择数据集', command=choose); browse.pack(side='left', padx=(8, 0))
    status = tk.StringVar(value='标注保存在软件目录下的 workspace 文件夹。')
    ttk.Label(frame, textvariable=status, wraplength=600).pack(anchor='w', pady=14)
    def start():
        if running['http']:
            webbrowser.open(running['url']); return
        try:
            if not dataset.get().strip(): raise ValueError('请先选择数据集文件夹。')
            status.set('正在检查配对影像，请稍候…'); window.update_idletasks()
            root = Path(dataset.get()).resolve()
            service, http, manifest = start_service(root, workspace)
            running.update(http=http, server=service, url=f'http://127.0.0.1:{http.server_port}/')
            write_json(config_path, {'data_root': str(root)})
            regions = len({item['region'] for item in manifest['items']})
            status.set(f'已打开 {regions} 个地区、{manifest["count"]} 组配对影像。\n只读取本地影像，标注单独保存。')
            entry.configure(state='disabled'); browse.configure(state='disabled')
            start_button.configure(text='再次打开标注界面')
            webbrowser.open(running['url'])
        except Exception as exc:
            traceback.print_exc(); status.set('未启动，请检查数据集目录。')
            messagebox.showerror('无法启动', str(exc), parent=window)
    start_button = ttk.Button(frame, text='开始标注', command=start); start_button.pack(fill='x', pady=(0, 10))
    def export():
        if not (workspace / 'state').exists():
            messagebox.showinfo('尚无标注', '请先启动标注并保存。', parent=window); return
        if not messagebox.askokcancel('导出前先保存', '请先在标注网页点击“保存修改”。\n只会导出已经保存的内容，继续导出？', parent=window): return
        identity = read_json(workspace / 'identity.json')['workspace_id'][:8]
        path = filedialog.asksaveasfilename(title='导出标注包交回负责人', defaultextension='.zip',
            initialfile=f'EarthMiss标注_{identity}_{time.strftime("%Y%m%d_%H%M%S")}.zip', filetypes=[('标注包', '*.zip')])
        if path:
            try:
                export_bundle(workspace, Path(path), running['server'])
                messagebox.showinfo('已导出', '把这个 ZIP 文件交回负责人即可。\n' + path, parent=window)
            except Exception as exc:
                traceback.print_exc(); messagebox.showerror('导出失败', str(exc), parent=window)
    ttk.Button(frame, text='导出全部已保存标注', command=export).pack(fill='x', pady=(0, 10))
    ttk.Button(frame, text='打开标注保存文件夹', command=lambda: os.startfile(workspace)).pack(fill='x')
    ttk.Label(frame, text='使用时保留此窗口。退出前先在网页保存；下次启动可继续标注。\n不要直接在 ZIP 压缩包中运行，请完整解压后双击 EXE。', wraplength=600).pack(anchor='w', pady=14)
    def close():
        if running['http']:
            if not messagebox.askokcancel('退出标注', '请确认网页中的修改已保存。退出后当前标注页面将停止服务。', parent=window): return
            running['http'].shutdown(); running['http'].server_close()
        window.destroy()
    window.protocol('WM_DELETE_WINDOW', close)
    window.mainloop()


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        try:
            traceback.print_exc()
            if '--headless' not in sys.argv and '--export' not in sys.argv:
                import ctypes
                ctypes.windll.user32.MessageBoxW(0, str(error), 'EarthMiss 标注助手', 16)
        finally:
            sys.exit(1)
