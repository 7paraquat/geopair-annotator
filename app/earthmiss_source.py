"""Selected EarthMiss image pairs and original semantic labels; source is read-only."""
import json
from pathlib import Path
import numpy as np
from PIL import Image
import shared_masks as masks

PREFIX = 'EarthMiss--'
# Original TIFF IDs are 0 ignored, then 1..8 in the published class order.
CLASSES = {1:'background',2:'building',3:'road',4:'water',5:'bareland',
           6:'forest',7:'cropland',8:'playground'}
EXTRA_LABELS = {'forest':'林地','playground':'运动场'}

class EarthMiss:
    def __init__(self, root, manifest):
        self.root=Path(root);self.items={};self.selection_sha256=None
        if not Path(manifest).exists():return
        data=json.loads(Path(manifest).read_text(encoding='utf-8'))
        self.selection_sha256=data['selection_sha256']
        for item in data['items']:
            region=masks.check_name(item['region']);stem=masks.check_name(Path(item['rgb']).stem)
            if item['id']!=region+'/'+stem:raise ValueError('筛选清单影像标识不一致')
            key=(PREFIX+region,stem)
            if key in self.items:raise ValueError('筛选清单有重复影像')
            for field in ['rgb','sar','mask']:
                p=Path(item[field])
                if p.is_absolute() or '..' in p.parts or p.parts[0]!=region:
                    raise ValueError('非法数据集路径')
                if p.stem!=stem:raise ValueError('配对文件名称不一致')
            self.items[key]=item
        if data['count']!=len(self.items):raise ValueError('筛选清单数量不一致')

    def sites(self):return sorted({site for site,stem in self.items})
    def stems(self,site):return sorted(stem for s,stem in self.items if s==site)
    def item(self,site,stem):
        if (site,stem) not in self.items:raise ValueError('影像不在当前数据清单中')
        return self.items[(site,stem)]
    def path(self,site,stem,field):
        p=(self.root/self.item(site,stem)[field]).resolve()
        if not p.is_relative_to(self.root.resolve()):raise ValueError('数据集路径越界')
        return p
    def shape(self,site,stem):
        sizes=[]
        for field in ['rgb','sar']:
            with Image.open(self.path(site,stem,field)) as im:sizes.append(im.size)
        if len(set(sizes))!=1:raise ValueError('EarthMiss 光学、SAR尺寸不一致')
        w,h=sizes[0]
        if h*w>16777216:raise ValueError('影像过大')
        return [h,w]
    def rgb(self,site,stem,mod):
        if mod not in ('opt','sar'):raise ValueError('无效影像模态')
        with Image.open(self.path(site,stem,'rgb' if mod=='opt' else 'sar')) as im:
            return np.asarray(im.convert('RGB'))
    def provenance(self,site,stem):
        return {'dataset':'earthmiss','source_item':self.item(site,stem),
                'selection_sha256':self.selection_sha256,
                'source_class_mapping':{str(k):v for k,v in CLASSES.items()},
                'source_ignore_index':0}
    def initial(self,site,stem,mapping):
        h,w=self.shape(site,stem)
        with Image.open(self.path(site,stem,'mask')) as im:labels=np.asarray(im)
        if labels.ndim!=2 or labels.dtype.kind not in 'ui':raise ValueError('原标签必须是单通道整数类别图')
        values=set(int(v) for v in np.unique(labels))
        if not values.issubset({0,*CLASSES}):raise ValueError('原标签存在未定义类别编号：'+str(values-{0,*CLASSES}))
        known={c['value'] for c in mapping['classes']}
        anns=[]
        for ident,category in CLASSES.items():
            mask=(labels==ident).astype(np.uint8)
            if not mask.any():continue
            if category not in known:raise ValueError('类别表缺少 '+category)
            y,x=np.nonzero(mask);rle=masks.encode(mask);box=[int(x.min()),int(y.min()),int(x.max()+1),int(y.max()+1)]
            anns.append({'id':ident,'category':category,'source_category':'EarthMiss:'+str(ident),
                         'origin':'earthmiss_original','polygon':None,'segmentation':rle,
                         'sar_segmentation':rle,'bbox_xyxy':box,'sar_bbox_xyxy':box,'sar_keep':True})
        return {'site':site,'stem':stem,'image_size':[h,w],'annotations':anns,
                'revision':None,'saved':False,'shared_mask':True,'label_map':mapping,
                'source_kind':'earthmiss_original',**self.provenance(site,stem)}
