"""Persistent optical attribute choices, with stable legacy values."""
import json
import os
import threading
import unicodedata
from pathlib import Path

DEFAULTS = {
    'color': dict(zip(['red','gray','white','blue','green','brown','black','yellow','purple'],
                     ['红色','灰色','白色','蓝色','绿色','棕色','黑色','黄色','紫色'])),
    'material': dict(zip(['concrete','metal','asphalt','soil','tile'],
                        ['混凝土','金属','沥青','土壤','瓦片']))
}

class AttributeStore:
    def __init__(self, path):
        self.path = Path(path)
        self.lock = threading.RLock()

    def choices(self):
        with self.lock:
            custom = json.loads(self.path.read_text(encoding='utf-8')) if self.path.exists() else {}
            return {kind: {**defaults, **custom.get(kind, {})} for kind, defaults in DEFAULTS.items()}

    def add(self, kind, label):
        if kind not in DEFAULTS:
            raise ValueError('只支持颜色或材质')
        if not isinstance(label, str):
            raise ValueError('请输入名称')
        label = unicodedata.normalize('NFKC', label).strip()
        if not label or len(label) > 30 or any(unicodedata.category(c).startswith('C') for c in label):
            raise ValueError('名称需为1至30个可见字符')
        with self.lock:
            choices = self.choices()
            for value, text in choices[kind].items():
                if label.casefold() in (value.casefold(), text.casefold()):
                    return {'value': value, 'label': text, 'existing': True}
            custom = json.loads(self.path.read_text(encoding='utf-8')) if self.path.exists() else {}
            custom.setdefault(kind, {})[label] = label
            self.path.parent.mkdir(parents=True, exist_ok=True)
            temp = self.path.with_suffix('.tmp')
            temp.write_text(json.dumps(custom, ensure_ascii=False, indent=2), encoding='utf-8')
            os.replace(temp, self.path)
            return {'value': label, 'label': label, 'existing': False}
