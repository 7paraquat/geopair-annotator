"""Exercise GitHub release discovery, downloads, and ZIP validation offline."""
import hashlib
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
import zipfile

root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root))
import updater


class FakeResponse(io.BytesIO):
    pass


class GitHubUpdateTests(unittest.TestCase):
    def setUp(self):
        (root / 'qa').mkdir(exist_ok=True)
        self.version = '0.4.1'
        self.name = f'GeoPairAnnotator-v{self.version}-windows-x64.zip'
        prefix = 'GeoPairAnnotator/'
        files = {
            'GeoPairAnnotator.exe': b'executable',
            'update.ps1': b'update script',
            'version.json': json.dumps({'version': self.version}).encode(),
            'RELEASE_NOTES_v0.4.1.md': b'notes',
        }
        manifest = {'version': self.version,
                    'files': {name: hashlib.sha256(data).hexdigest() for name, data in files.items()}}
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, 'w', zipfile.ZIP_DEFLATED) as archive:
            for name, data in files.items():
                archive.writestr(prefix + name, data)
            archive.writestr(prefix + 'release_manifest.json', json.dumps(manifest))
        self.archive = buffer.getvalue()
        self.archive_url = f'https://github.com/{updater.REPOSITORY}/releases/download/v{self.version}/{self.name}'
        self.checksum_url = self.archive_url + '.sha256'
        self.release = {'tag_name': 'v' + self.version, 'draft': False, 'prerelease': False,
                        'assets': [
                            {'name': self.name, 'size': len(self.archive), 'browser_download_url': self.archive_url},
                            {'name': self.name + '.sha256', 'size': 110, 'browser_download_url': self.checksum_url}]}

    def opener(self, request, timeout):
        url = request.full_url
        if url == updater.LATEST_RELEASE_URL:
            return FakeResponse(json.dumps(self.release).encode())
        if url == self.archive_url:
            return FakeResponse(self.archive)
        if url == self.checksum_url:
            digest = hashlib.sha256(self.archive).hexdigest()
            return FakeResponse(f'{digest}  {self.name}\n'.encode())
        raise AssertionError(url)

    def test_full_update_and_version_comparison(self):
        self.assertIsNone(updater.latest_release(self.version, self.opener))
        with tempfile.TemporaryDirectory(dir=root / 'qa') as directory:
            stage, version = updater.prepare_github_update('0.4.0', directory, self.opener)
            self.assertEqual(version, self.version)
            self.assertEqual((stage / 'GeoPairAnnotator/version.json').read_text(),
                             json.dumps({'version': self.version}))
            self.assertEqual(list(Path(directory).glob('geopair-download-*.zip')), [])

    def test_reject_wrong_origin_and_checksum(self):
        self.release['assets'][0]['browser_download_url'] = 'https://example.org/update.zip'
        with self.assertRaisesRegex(ValueError, '地址'):
            updater.latest_release('0.4.0', self.opener)
        self.release['assets'][0]['browser_download_url'] = self.archive_url
        self.archive = self.archive + b'changed'
        self.release['assets'][0]['size'] = len(self.archive)
        with tempfile.TemporaryDirectory(dir=root / 'qa') as directory:
            release = updater.latest_release('0.4.0', self.opener)
            bad_checksum = lambda request, timeout: FakeResponse(
                b'0' * 64 + b'  ' + (self.name + '\n').encode()) if request.full_url == self.checksum_url else self.opener(request, timeout)
            with self.assertRaisesRegex(ValueError, 'SHA256'):
                updater.download_release(release, directory, bad_checksum)
            self.assertEqual(list(Path(directory).glob('geopair-download-*.zip')), [])

    def test_reject_missing_assets(self):
        self.release['assets'].pop()
        with self.assertRaisesRegex(ValueError, '缺少'):
            updater.latest_release('0.4.0', self.opener)


if __name__ == '__main__':
    unittest.main()
