"""Status summaries from committed annotation pointers, without loading imagery."""
import json
import threading
from shared_masks import pointer

STATES = ('todo', 'in_progress', 'done', 'discussion')

class Progress:
    def __init__(self, root):
        self.root = root
        self.cache = {}
        self.lock = threading.RLock()

    def info(self, site, stem):
        path = pointer(self.root, site, stem)
        with self.lock:
            try:
                stat = path.stat()
            except FileNotFoundError:
                self.cache.pop((site, stem), None)
                return {'stem': stem, 'saved': False, 'workflow_status': 'todo'}
            key = (site, stem)
            stamp = (stat.st_mtime_ns, stat.st_size)
            if key not in self.cache or self.cache[key][0] != stamp:
                record = json.loads(path.read_text(encoding='utf-8'))
                state = record.get('workflow_status', 'done')
                if state not in STATES:
                    raise ValueError('无效已保存状态：' + stem)
                self.cache[key] = (stamp, {'stem': stem, 'saved': True, 'workflow_status': state})
            return dict(self.cache[key][1])

    def summary(self, sites, stems_for, current=''):
        regions, current_tiles = [], []
        for site in sites:
            counts = dict.fromkeys(STATES, 0)
            tiles = [self.info(site, stem) for stem in stems_for(site)]
            for item in tiles:
                counts[item['workflow_status']] += 1
            total = len(tiles)
            regions.append({'site': site, 'total': total, 'counts': counts,
                            'percent': round(100 * counts['done'] / total, 1) if total else 0})
            if site == current:
                current_tiles = tiles
        return {'regions': regions, 'tiles': current_tiles}
