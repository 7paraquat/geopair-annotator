import sys
from pathlib import Path
import tempfile
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from dataset_index import scan_dataset

class DatasetIndexTest(unittest.TestCase):
    def test_pairing_and_incomplete_input(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            opt=root/'Test-City/images/RGB_png/x.png'
            sar=root/'Test-City/images/SAR_png/x.png'
            opt.parent.mkdir(parents=True); sar.parent.mkdir(parents=True)
            opt.touch()
            with self.assertRaisesRegex(ValueError,'缺少'):scan_dataset(root)
            sar.touch()
            result=scan_dataset(root)
            self.assertEqual(result['count'],1)
            self.assertEqual(result['items'][0]['id'],'Test-City/x')
            self.assertEqual(scan_dataset(root)['selection_sha256'],result['selection_sha256'])
            self.assertFalse((root/result['items'][0]['mask']).exists())

    def test_empty(self):
        with tempfile.TemporaryDirectory() as temp:
            with self.assertRaisesRegex(ValueError,'未找到'):scan_dataset(temp)

if __name__=='__main__':unittest.main()
