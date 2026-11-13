"""Fetch a trusted GitHub release and validate its portable update archive."""
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import shutil
import tempfile
import urllib.parse
import urllib.request
import zipfile


PROGRAM_FILES = frozenset({
    'GeoPairAnnotator.exe', '_internal', 'README.md', 'LICENSE',
    'THIRD_PARTY_NOTICES.md', 'docs', 'third_party', 'examples',
    'version.json', 'release_manifest.json', 'update.ps1',
})
MAX_UNCOMPRESSED = 300 * 1024 * 1024
MAX_DOWNLOAD = 150 * 1024 * 1024
REPOSITORY = '7paraquat/geopair-annotator'
LATEST_RELEASE_URL = f'https://api.github.com/repos/{REPOSITORY}/releases/latest'
USER_AGENT = 'GeoPair-Annotator-Updater'


def version_tuple(value):
    parts = str(value).split('.')
    if len(parts) != 3 or any(not part.isdigit() for part in parts):
        raise ValueError('版本号格式应为 major.minor.patch')
    return tuple(map(int, parts))


def release_asset_url(asset, tag, filename):
    url = asset.get('browser_download_url', '')
    parsed = urllib.parse.urlsplit(url)
    expected = f'/{REPOSITORY}/releases/download/{tag}/{filename}'
    if (parsed.scheme != 'https' or parsed.netloc != 'github.com'
            or parsed.path != expected or parsed.query or parsed.fragment
            or asset.get('name') != filename):
        raise ValueError('GitHub Release 附件地址不符合仓库与版本')
    return url


def latest_release(current_version, opener=urllib.request.urlopen):
    request = urllib.request.Request(LATEST_RELEASE_URL, headers={
        'Accept': 'application/vnd.github+json', 'User-Agent': USER_AGENT})
    with opener(request, timeout=8) as response:
        payload = response.read(1024 * 1024 + 1)
    if len(payload) > 1024 * 1024:
        raise ValueError('GitHub 版本信息过大')
    release = json.loads(payload)
    tag = release.get('tag_name', '')
    if not re.fullmatch(r'v[0-9]+\.[0-9]+\.[0-9]+', tag):
        raise ValueError('GitHub Release 版本号无效')
    if release.get('draft') or release.get('prerelease'):
        return None
    version = tag[1:]
    if version_tuple(version) <= version_tuple(current_version):
        return None
    assets = {item.get('name'): item for item in release.get('assets', [])}
    archive_name = f'GeoPairAnnotator-v{version}-windows-x64.zip'
    checksum_name = archive_name + '.sha256'
    if archive_name not in assets or checksum_name not in assets:
        raise ValueError(f'GitHub v{version} 缺少 Windows ZIP 或 SHA256 附件')
    archive = assets[archive_name]
    size = archive.get('size')
    if isinstance(size, bool) or not isinstance(size, int) or not 0 < size <= MAX_DOWNLOAD:
        raise ValueError('GitHub 更新包大小无效')
    return {'version': version, 'tag': tag, 'name': archive_name, 'size': size,
            'archive_url': release_asset_url(archive, tag, archive_name),
            'checksum_url': release_asset_url(assets[checksum_name], tag, checksum_name)}


def download_release(release, destination, opener=urllib.request.urlopen):
    destination = Path(destination)
    destination.mkdir(parents=True, exist_ok=True)
    if shutil.disk_usage(destination).free < max(release['size'] * 3, 250 * 1024 * 1024):
        raise OSError('更新所在磁盘空间不足，至少需要 250 MB 可用空间')
    checksum_request = urllib.request.Request(release['checksum_url'], headers={'User-Agent': USER_AGENT})
    with opener(checksum_request, timeout=20) as response:
        checksum = response.read(4097)
    if len(checksum) > 4096:
        raise ValueError('SHA256 文件过大')
    match = re.fullmatch(rb'([0-9a-fA-F]{64})  ([A-Za-z0-9_.-]+)\s*', checksum)
    if not match or match.group(2).decode('ascii') != release['name']:
        raise ValueError('GitHub SHA256 文件内容无效')
    with tempfile.NamedTemporaryFile(prefix='geopair-download-', suffix='.zip', dir=destination, delete=False) as temp:
        target = Path(temp.name)
    try:
        digest = hashlib.sha256()
        received = 0
        archive_request = urllib.request.Request(release['archive_url'], headers={'User-Agent': USER_AGENT})
        with opener(archive_request, timeout=30) as response, target.open('wb') as file:
            while chunk := response.read(1024 * 1024):
                received += len(chunk)
                if received > MAX_DOWNLOAD or received > release['size']:
                    raise ValueError('GitHub 更新包大小与附件信息不符')
                file.write(chunk)
                digest.update(chunk)
        if received != release['size'] or digest.hexdigest().lower() != match.group(1).decode('ascii').lower():
            raise ValueError('GitHub 更新包 SHA256 校验失败')
        return target
    except BaseException:
        target.unlink(missing_ok=True)
        raise


def prepare_github_update(current_version, staging_parent, opener=urllib.request.urlopen):
    release = latest_release(current_version, opener)
    if release is None:
        return None
    archive = download_release(release, staging_parent, opener)
    try:
        stage, version = prepare_update(archive, current_version, staging_parent)
        if version != release['version']:
            shutil.rmtree(stage)
            raise ValueError('ZIP 内版本与 GitHub Release 不一致')
        return stage, version
    finally:
        archive.unlink(missing_ok=True)


def prepare_update(archive_path, current_version, staging_parent=None):
    archive_path = Path(archive_path)
    with zipfile.ZipFile(archive_path) as archive:
        entries = [entry for entry in archive.infolist() if not entry.is_dir()]
        names = [entry.filename for entry in entries]
        if len(names) != len(set(name.casefold() for name in names)):
            raise ValueError('更新包含重复路径')
        for entry in entries:
            path = PurePosixPath(entry.filename)
            if (len(path.parts) < 2 or path.parts[0] != 'GeoPairAnnotator'
                    or (path.parts[1] not in PROGRAM_FILES and not re.fullmatch(
                        r'RELEASE_NOTES_v[0-9]+\.[0-9]+\.[0-9]+\.md', path.parts[1]))
                    or '..' in path.parts
                    or '\\' in entry.filename or ':' in entry.filename
                    or entry.external_attr >> 16 & 0o170000 == 0o120000):
                raise ValueError('更新包包含非法文件路径：' + entry.filename)
        if sum(entry.file_size for entry in entries) > MAX_UNCOMPRESSED:
            raise ValueError('更新包解压后过大')
        if archive.testzip() is not None:
            raise ValueError('更新包校验失败')
        prefix = 'GeoPairAnnotator/'
        version = json.loads(archive.read(prefix + 'version.json'))['version']
        if version_tuple(version) <= version_tuple(current_version):
            raise ValueError(f'更新包版本 {version} 不高于当前版本 {current_version}')
        manifest = json.loads(archive.read(prefix + 'release_manifest.json'))
        expected = manifest['files']
        actual = {name[len(prefix):] for name in names if name != prefix + 'release_manifest.json'}
        if set(expected) != actual or manifest['version'] != version:
            raise ValueError('更新包文件清单不一致')
        for name in actual:
            if hashlib.sha256(archive.read(prefix + name)).hexdigest() != expected[name]:
                raise ValueError('更新包文件哈希不匹配：' + name)
        if prefix + 'GeoPairAnnotator.exe' not in names or prefix + 'update.ps1' not in names:
            raise ValueError('更新包缺少程序文件')
        stage_root = Path(tempfile.mkdtemp(prefix='geopair-update-', dir=staging_parent))
        try:
            for entry in entries:
                target = stage_root.joinpath(*PurePosixPath(entry.filename).parts)
                target.parent.mkdir(parents=True, exist_ok=True)
                with archive.open(entry) as source, target.open('wb') as dest:
                    shutil.copyfileobj(source, dest)
            return stage_root, version
        except BaseException:
            shutil.rmtree(stage_root)
            raise
