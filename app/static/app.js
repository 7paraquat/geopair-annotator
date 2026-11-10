'use strict';
const $=id=>document.getElementById(id), G=MaskGeometry;
const ZH={background:'背景',building:'建筑物',vehicle:'车辆',ship:'船',aircraft:'飞机',bridge:'桥梁',solar_panel:'太阳能板',road:'道路',tree:'树',water:'水体',cropland:'耕地',grassland:'草地',bareland:'裸地'};
Object.assign(ZH,{building_facade:'建筑外立面',quay:'码头',red:'红色',gray:'灰色',white:'白色',blue:'蓝色',green:'绿色',brown:'棕色',black:'黑色',yellow:'黄色',purple:'紫色',concrete:'混凝土',metal:'金属',asphalt:'沥青',soil:'土壤',tile:'瓦片'});
const EDITOR_VERSION='20261029-dual-masks-1';
const S={pad:0,meta:null,site:'',stem:'',anns:[],selected:-1,h:1,w:1,revision:null,saved:'[]',undo:[],redo:[],draft:[],drag:null,mode:'select',view:'dual',show:true,zoom:1,imgs:[],tiles:[],offset:0,total:0,loading:false,queueLoading:false,saving:false,token:0,allSites:[],dataset:"earthmiss",sitePrefix:"EarthMiss--"};
const L={enabled:false,center:null,crop:null};
const STATE_LABELS={todo:'未标注',in_progress:'标注中',done:'已完成',discussion:'待讨论'};
S.workflow='in_progress';S.savedWorkflow='in_progress';S.mod='opt';S.redraw=false;
function drawDetail(){
 $('detail').hidden=!L.enabled||!S.imgs.length||S.loading;
 if($('detail').hidden)return;
 const size=Math.min(S.w,S.h,($('detail-opt').getBoundingClientRect().width||240)/(S.zoom*(Number($('detail-scale').value)||4)));
 const [cx,cy]=L.center||[S.w/2,S.h/2];
 const x=Math.max(-S.pad,Math.min(S.w+S.pad-size,cx-size/2)),y=Math.max(-S.pad,Math.min(S.h+S.pad-size,cy-size/2));
 L.crop={x,y,size};
 for(const mod of ['opt','sar']){const c=$('detail-'+mod),ctx=c.getContext('2d');ctx.clearRect(0,0,c.width,c.height);ctx.imageSmoothingEnabled=false;ctx.drawImage($(mod),x+S.pad,y+S.pad,size,size,0,0,c.width,c.height);drawDetailCrosshair(ctx,c);}
 $('detail-position').textContent=`中心 (${Math.round(x+size/2)}, ${Math.round(y+size/2)}) · ${Math.round(size)} × ${Math.round(size)} 像素`;
}
function drawDetailCrosshair(ctx,canvas){
 const scale=canvas.width/(canvas.getBoundingClientRect().width||240),cx=canvas.width/2,cy=canvas.height/2;
 const gap=3*scale,arm=9*scale;ctx.save();ctx.beginPath();
 ctx.moveTo(cx-arm,cy);ctx.lineTo(cx-gap,cy);ctx.moveTo(cx+gap,cy);ctx.lineTo(cx+arm,cy);
 ctx.moveTo(cx,cy-arm);ctx.lineTo(cx,cy-gap);ctx.moveTo(cx,cy+gap);ctx.lineTo(cx,cy+arm);
 ctx.strokeStyle='#16251e';ctx.lineWidth=3*scale;ctx.stroke();ctx.strokeStyle='#fff';ctx.lineWidth=scale;ctx.stroke();
 ctx.beginPath();ctx.arc(cx,cy,1.5*scale,0,Math.PI*2);ctx.fillStyle='#ffcc00';ctx.fill();ctx.strokeStyle='#16251e';ctx.lineWidth=.6*scale;ctx.stroke();ctx.restore();
}
function pointerScale(canvas){return canvas.id.startsWith('detail-')&&L.crop?canvas.getBoundingClientRect().width/L.crop.size:S.zoom;}
const clone=x=>JSON.parse(JSON.stringify(x));
const current=()=>S.anns[S.selected];
function geo(a,mod=S.mod){
 if(!a)return null;const mk=mod==='sar'?'sar_mask':'mask',pk=mod==='sar'?'sar_polygon':'polygon';
 return {get mask(){return a[mk];},set mask(v){a[mk]=v;},get polygon(){return a[pk];},set polygon(v){a[pk]=v;}};
}
function hydrate(a,h=S.h,w=S.w){
 const legacy=!Object.hasOwn(a,'sar_polygon'),rle=legacy?(a.sar_segmentation||a.segmentation):a.sar_segmentation;
 return {...a,polygon:a.polygon?clone(a.polygon):null,sar_polygon:legacy?(a.polygon?clone(a.polygon):null):(a.sar_polygon?clone(a.sar_polygon):null),mask:a.segmentation?G.decode(a.segmentation,h,w):null,sar_mask:rle?G.decode(rle,h,w):null};
}
function serial(){return S.anns.map(a=>({id:a.id,category:a.category,source_category:a.source_category||'',task:a.task||'',color:a.color||'',material:a.material||'',origin:a.origin||'manual',polygon:a.polygon?clone(a.polygon):null,segmentation:a.mask?G.encode(a.mask,S.h,S.w):null,sar_polygon:a.sar_polygon?clone(a.sar_polygon):null,sar_segmentation:a.sar_mask?G.encode(a.sar_mask,S.h,S.w):null}));}
function sideUI(){
 for(const mod of ['opt','sar']){$('edit-'+mod).classList.toggle('on',S.mod===mod);$('edit-'+mod).setAttribute('aria-pressed',S.mod===mod);$('pane-'+mod).classList.toggle('editing-side',S.mod===mod);}
 $('edit-side-note').textContent='当前调整：'+(S.mod==='opt'?'光学':'SAR')+' · 修改仅作用于本侧'+(S.redraw?' · 正在重画选中地物':'');
 const blocked=!canEdit()||S.loading||S.saving||S.queueLoading||!!S.drag||!!S.draft.length||S.redraw;
 for(const id of ['edit-opt','edit-sar','copy-other','clear-side','redraw-side'])$(id).disabled=blocked||(id!=='edit-opt'&&id!=='edit-sar'&&!current());
}
function switchSide(mod){
 if(mod===S.mod)return true;
 if(S.drag||S.draft.length||S.redraw){status('请先完成或取消当前绘制，再切换另一侧');return false;}
 S.mod=mod;sync();draw();return true;
}
function unionParts(poly){
 const parts=clippedParts(poly),mask=new Uint8Array(S.h*S.w);
 for(const p of parts)for(let i=0;i<mask.length;i++)mask[i]|=p.mask[i];
 return {polygon:parts.length===1?parts[0].polygon:null,mask};
}
const signature=()=>JSON.stringify(serial());
const dirty=()=>signature()!==S.saved||S.workflow!==S.savedWorkflow;
function status(t){$('status').textContent=t;}
function safe(fn){return (...args)=>{try{return Promise.resolve(fn(...args)).catch(e=>status('失败：'+e.message));}catch(e){status('失败：'+e.message);}};}
async function api(url,body){const r=await fetch(url,body===undefined?{cache:'no-store'}:{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});const d=await r.json();if(!r.ok){const e=Error(d.error||r.statusText);e.status=r.status;throw e;}return d;}
function remember(){S.undo.push(serial());if(S.undo.length>30)S.undo.shift();S.redo=[];}
function restore(rows){S.anns=rows.map(a=>hydrate(a));S.selected=Math.min(S.selected,S.anns.length-1);sync();draw();}
function undo(redo=false){if(!canEdit())return;if(S.loading||S.saving||S.drag)return;if(S.draft.length){S.draft.pop();draw();return;}const from=redo?S.redo:S.undo,to=redo?S.undo:S.redo;if(from.length){to.push(serial());restore(from.pop());}}
function optionList(el,items,empty=true){el.replaceChildren();if(empty)el.add(new Option('请选择',''));const labels=['color','material'].includes(el.id)?S.meta.attribute_labels?.[el.id]||{}:S.meta.category_labels;for(const v of items)el.add(new Option(labels[v]||ZH[v]||v,v));}
function color(a){const c=S.meta.label_map.classes.find(c=>c.value===a.category),i=c?c.id:255;return i===1?[255,255,255]:[(i*67)%206+35,(i*97)%206+35,(i*131)%206+35];}
function sync(){
 $('workflow-status').value=S.workflow;
 $('workflow-status').disabled=S.loading||S.saving||S.queueLoading||!S.stem;
 const a=current(),g=geo(a);$('fields').hidden=!a;$('empty').hidden=!!a;$('selection-info').textContent=a?'#'+a.id+' · '+(g?.polygon?'多边形 '+g.polygon.length+' 点':g?.mask?'像素掩膜':'本侧未确认'): '尚未选中';
 if(a){for(const k of ['color','material']){const items=[...S.meta[k==='color'?'colors':'materials']];if(a[k]&&!items.includes(a[k]))items.push(a[k]);optionList($(k),items);}for(const k of ['category','task','color','material'])$(k).value=a[k]||'';$('mask-on').checked=!a.hidden;}
 $('mask-list').replaceChildren();
 S.anns.forEach((a,i)=>{const row=document.createElement('div');row.className='mask-row';const select=document.createElement('button');select.type='button';select.className='mask-item'+(i===S.selected?' on':'')+(a.hidden?' off':'');select.textContent='#'+a.id+' '+(S.meta.category_labels[a.category]||ZH[a.category]||a.category||'待选类别')+(!a.mask?' · 光学未确认':'')+(!a.sar_mask?' · SAR未确认':'');select.onclick=()=>{if(S.drag||S.draft.length||S.redraw)return;S.selected=i;sync();draw();};row.append(select);
  for(const [label,action] of [['↑',()=>move(i,-1)],['↓',()=>move(i,1)],['×',()=>{if(!canEdit())return;remember();S.anns.splice(i,1);S.selected=Math.min(i,S.anns.length-1);sync();draw();}]]){const b=document.createElement('button');b.type='button';b.textContent=label;b.disabled=!canEdit()||S.loading||S.saving||!!S.drag||!!S.draft.length;b.onclick=action;row.append(b);}$('mask-list').append(row);
 });
 const busy=S.loading||S.saving||S.queueLoading;for(const id of ['dataset','site','filter','queue-status','category','task','color','material','add-category','new-color','new-material','head-prev','head-next','prev','next','page-prev','page-next','head-page-prev','head-page-next'])$(id).disabled=busy;for(const k of ['color','material'])$('add-'+k).disabled=busy||!a||!!S.drag||!!S.draft.length;$('undo').disabled=busy||(!S.undo.length&&!S.draft.length);$('redo').disabled=busy||!S.redo.length;$('save').disabled=busy||!S.stem;$('export').disabled=S.loading||S.saving||!S.revision;presenceUI();sideUI();
}
function move(i,d){if(!canEdit())return;if(i+d<0||i+d>=S.anns.length)return;remember();[S.anns[i],S.anns[i+d]]=[S.anns[i+d],S.anns[i]];S.selected=i+d;sync();draw();}
function draw(){
 if(!S.imgs.length)return;
 for(let k=0;k<2;k++){
  const mod=k?'sar':'opt',overlay=document.createElement('canvas');overlay.width=S.w;overlay.height=S.h;const oc=overlay.getContext('2d'),pixels=oc.createImageData(S.w,S.h);
  if(S.show)for(const a of S.anns){const g=geo(a,mod);if(a.hidden||!g.mask)continue;const c=color(a);for(let i=0;i<g.mask.length;i++)if(g.mask[i])pixels.data.set([...c,110],i*4);}oc.putImageData(pixels,0,0);
  const canvas=$(k?'sar':'opt'),ctx=canvas.getContext('2d');ctx.clearRect(0,0,canvas.width,canvas.height);ctx.fillStyle='#34423c';ctx.fillRect(0,0,canvas.width,canvas.height);ctx.save();ctx.translate(S.pad,S.pad);ctx.drawImage(S.imgs[k],0,0,S.w,S.h);ctx.drawImage(overlay,0,0);ctx.strokeStyle='#8ba397';ctx.lineWidth=1/S.zoom;ctx.strokeRect(0,0,S.w,S.h);
  const p=mod!==S.mod?null:S.draft.length?S.draft:(S.show&&!current()?.hidden&&['select','move'].includes(S.mode)?geo(current())?.polygon:null);
  if(p?.length){ctx.beginPath();p.forEach(([x,y],i)=>i?ctx.lineTo(x,y):ctx.moveTo(x,y));if(!S.draft.length)ctx.closePath();ctx.strokeStyle='#fff';ctx.lineWidth=2/S.zoom;ctx.stroke();p.forEach(([x,y],i)=>{ctx.fillStyle=i===0?'#ffcc00':'#fff';ctx.beginPath();ctx.arc(x,y,4/S.zoom,0,Math.PI*2);ctx.fill();});}
  if(mod===S.mod&&S.drag?.type==='rect'){const [x,y]=S.drag.start,[u,v]=S.drag.last;ctx.strokeStyle='#fff';ctx.strokeRect(x,y,u-x,v-y);}
  ctx.restore();
 }
 $('undo').disabled=!S.undo.length&&!S.draft.length;$('redo').disabled=!S.redo.length;presenceUI();
 sideUI();drawDetail();
}
function fit(){const count=S.view==='dual'?2:1;S.zoom=Math.max(.1,Math.min(2,(($('stage').clientWidth-50)/count-96)/S.w));layout();}
function layout(){S.pad=Math.ceil(48/S.zoom);for(const mod of ['opt','sar']){$('pane-'+mod).hidden=S.view!=='dual'&&S.view!==mod;const c=$(mod);c.width=S.w+2*S.pad;c.height=S.h+2*S.pad;c.style.width=c.width*S.zoom+'px';c.style.height=c.height*S.zoom+'px';}$('zoom-label').textContent=Math.round(S.zoom*100)+'%';draw();}
function pos(e,canvas){
 const r=canvas.getBoundingClientRect(),crop=canvas.id.startsWith('detail-')?L.crop:null;
 const x=crop?crop.x+(e.clientX-r.left)*crop.size/r.width:(e.clientX-r.left)*(S.w+2*S.pad)/r.width-S.pad;
 const y=crop?crop.y+(e.clientY-r.top)*crop.size/r.height:(e.clientY-r.top)*(S.h+2*S.pad)/r.height-S.pad;
 return [Math.max(-S.pad,Math.min(S.w+S.pad,x)),Math.max(-S.pad,Math.min(S.h+S.pad,y))];
}
function clippedParts(poly){
 const parts=[];
 for(const p of G.clip(poly,S.h,S.w)){try{parts.push({polygon:p,mask:G.raster(p,S.h,S.w)});}catch(e){if(!e.message.includes('没有覆盖任何像素中心'))throw e;}}
 if(!parts.length)throw Error('多边形未覆盖影像内的像素，请调整顶点');
 return parts;
}
function add(poly){
 if(!canEdit())throw Error('当前只读，请先获得编辑权');
 if(S.redraw){const a=current();if(!a)throw Error('请选择需要重画的地物');const shape=unionParts(poly);remember();Object.assign(geo(a),shape);S.redraw=false;S.draft=[];sync();draw();status('已重画本侧，另一侧保持原轮廓，请保存');return;}
 const parts=clippedParts(poly);remember();const category=$('category').value||'';let id=Math.max(0,...S.anns.map(a=>a.id))+1;
 const start=S.anns.length;S.anns.push(...parts.map(p=>({id:id++,category,...p,sar_polygon:clone(p.polygon),sar_mask:p.mask.slice(),origin:'manual'})));S.selected=start;S.draft=[];sync();draw();
 status(parts.length>1?`已裁剪为 ${parts.length} 块，请分别确认类别并保存`:'已按原图边界裁剪，请选择类别并保存');
}
function finishVertexEdit(){Object.assign(geo(current()),unionParts(geo(current()).polygon));}
function finish(){if(!canEdit())return;if(S.loading||S.saving||S.drag)return;if(!S.draft.length)return;add(S.draft);}
function cancel(){S.draft=[];S.redraw=false;if(S.drag){restore(S.drag.before);S.drag=null;}sync();draw();}
function brush(a,p,q){const radius=Number($('brush-size').value)/2,steps=Math.max(1,Math.ceil(Math.hypot(q[0]-p[0],q[1]-p[1])));for(let t=0;t<=steps;t++){const x=p[0]+(q[0]-p[0])*t/steps,y=p[1]+(q[1]-p[1])*t/steps;for(let iy=Math.max(0,Math.floor(y-radius));iy<Math.min(S.h,Math.ceil(y+radius));iy++)for(let ix=Math.max(0,Math.floor(x-radius));ix<Math.min(S.w,Math.ceil(x+radius));ix++)if((ix+.5-x)**2+(iy+.5-y)**2<=radius**2)a.mask[iy*S.w+ix]=S.mode==='paint'?1:0;}a.polygon=null;}
for(const mod of ['opt','sar','detail-opt','detail-sar']){
 const canvas=$(mod);
 canvas.addEventListener('pointerdown',safe(e=>{
  if(e.button!==0||S.loading||S.saving||!S.stem||S.drag||!canEdit())return;if(!switchSide(mod.endsWith('sar')?'sar':'opt'))return;const p=pos(e,canvas);e.preventDefault();
  if(S.mode==='polygon'){if(S.draft.length>=3&&Math.hypot(p[0]-S.draft[0][0],p[1]-S.draft[0][1])*pointerScale(canvas)<8){finish();return;}if(S.draft.length>=512)throw Error('最多512个顶点');S.draft.push(p);draw();return;}
  const a=geo(current()),before=serial();
  if(S.mode==='draw'){S.drag={type:'rect',start:p,last:p,before};}
  else if(S.mode==='move'){if(!a?.mask)throw Error('先选中需要移动的地物');S.drag={type:'move',start:p,last:p,before,mask:a.mask.slice(),polygon:a.polygon?clone(a.polygon):null};}
  else if(S.mode==='erase'||S.mode==='paint'){if(p[0]<0||p[0]>=S.w||p[1]<0||p[1]>=S.h)return;if(!a?.mask)throw Error('先选择有掩膜的标注');S.drag={type:'brush',last:p,before};brush(a,p,p);}
  else{const vertex=a?.polygon?.findIndex(v=>Math.hypot(v[0]-p[0],v[1]-p[1])*pointerScale(canvas)<8);if(vertex>=0)S.drag={type:'vertex',vertex,before};else{S.selected=-1;const ix=Math.floor(p[0]),iy=Math.floor(p[1]);for(let i=S.anns.length-1;i>=0;i--)if(ix>=0&&ix<S.w&&iy>=0&&iy<S.h&&!S.anns[i].hidden&&geo(S.anns[i]).mask?.[iy*S.w+ix]){S.selected=i;break;}sync();draw();return;}}
  canvas.setPointerCapture(e.pointerId);draw();
 }));
 canvas.addEventListener('pointermove',safe(e=>{if(S.loading||S.saving)return;const p=pos(e,canvas);if(L.enabled&&!mod.startsWith('detail-')&&!S.drag){L.center=p;drawDetail();}if(!S.drag||!canEdit())return;if(S.drag.type==='brush')brush(geo(current()),S.drag.last,p);if(S.drag.type==='vertex')geo(current()).polygon[S.drag.vertex]=p;if(S.drag.type==='move')translateSide(S.drag,p);S.drag.last=p;draw();}));
 canvas.addEventListener('pointerup',safe(e=>{if(!S.drag)return;if(!canEdit()){const before=S.drag.before;S.drag=null;restore(before);return;}const d=S.drag;S.drag=null;try{if(d.type==='rect'){const [x,y]=d.start,[u,v]=pos(e,canvas);add([[Math.min(x,u),Math.min(y,v)],[Math.max(x,u),Math.min(y,v)],[Math.max(x,u),Math.max(y,v)],[Math.min(x,u),Math.max(y,v)]]);}else{if(d.type==='vertex'||(d.type==='move'&&geo(current()).polygon))finishVertexEdit();if(!geo(current()).mask.some(Boolean))throw Error('涂抹会清空掩膜，已撤销；请用删除按钮移除整条标注');S.undo.push(d.before);if(S.undo.length>30)S.undo.shift();S.redo=[];}}catch(e){restore(d.before);throw e;}finally{sync();draw();}}));
 canvas.addEventListener('pointercancel',()=>{if(S.drag){const before=S.drag.before;S.drag=null;restore(before);}});
}
for(const mode of ['select','polygon','draw','erase','paint','move'])$('mode-'+mode).onclick=safe(()=>{if(mode!=='select'&&!canEdit())return;if(S.draft.length||S.drag||S.redraw)throw Error('请先闭合或取消当前绘制');S.mode=mode;for(const m of ['select','polygon','draw','erase','paint','move']){$('mode-'+m).classList.toggle('on',m===mode);$('mode-'+m).setAttribute('aria-pressed',m===mode);}draw();});
function translateSide(d,p){
 const g=geo(current()),dx=Math.round(p[0]-d.start[0]),dy=Math.round(p[1]-d.start[1]);
 if(d.polygon){g.polygon=d.polygon.map(([x,y])=>[x+dx,y+dy]);return;}
 const mask=new Uint8Array(S.h*S.w);
 for(let y=0;y<S.h;y++)for(let x=0;x<S.w;x++){const sx=x-dx,sy=y-dy;if(sx>=0&&sx<S.w&&sy>=0&&sy<S.h)mask[y*S.w+x]=d.mask[sy*S.w+sx];}
 g.mask=mask;g.polygon=null;
}
for(const mod of ['opt','sar'])$('edit-'+mod).onclick=safe(()=>switchSide(mod));
$('copy-other').onclick=safe(()=>{
 if(!canEdit()||S.loading||S.saving||S.drag||S.draft.length||!current())return;
 const from=geo(current(),S.mod==='opt'?'sar':'opt');if(!from.mask)throw Error('另一侧没有可复制的轮廓');
 if(!confirm('用另一侧轮廓替换当前侧？可撤销。'))return;
 remember();Object.assign(geo(current()),{polygon:from.polygon?clone(from.polygon):null,mask:from.mask.slice()});sync();draw();
});
$('clear-side').onclick=safe(()=>{
 if(!canEdit()||S.loading||S.saving||S.drag||S.draft.length||!current())return;
 if(!geo(current(),S.mod==='opt'?'sar':'opt').mask)throw Error('两侧均无轮廓时，请删除整条标注');
 if(!confirm('清除本侧轮廓并标为未确认？另一侧保留，可撤销。'))return;
 remember();Object.assign(geo(current()),{polygon:null,mask:null});sync();draw();
});
$('redraw-side').onclick=safe(()=>{
 if(!canEdit()||S.loading||S.saving||S.drag||S.draft.length||!current())return;
 $('mode-polygon').onclick();S.redraw=true;sync();status('在当前侧重新画轮廓，闭合后替换；取消则保留原轮廓');
});
$('finish').onclick=safe(finish);$('cancel').onclick=cancel;
$('full-mask').onclick=safe(()=>{if(S.loading||S.saving||!S.stem)return;if(S.draft.length||S.drag)throw Error('请先完成绘制');add([[0,0],[S.w,0],[S.w,S.h],[0,S.h]]);});
$('undo').onclick=()=>undo();$('redo').onclick=()=>undo(true);
$('mask-on').onchange=()=>{if(current()){current().hidden=!$('mask-on').checked;sync();draw();}};
$('toggle-mask').onclick=()=>{S.show=!S.show;$('toggle-mask').classList.toggle('on',S.show);draw();};
for(const key of ['category','color','material'])$(key).onchange=()=>{if(!current()||S.loading||S.saving||!canEdit())return;remember();current()[key]=$(key).value;sync();draw();status('有未保存修改');};
$('task').oninput=()=>{if(!current()||S.loading||S.saving||!canEdit())return;remember();current().task=$('task').value;status('有未保存修改');};
for(const kind of ['color','material'])$('add-'+kind).onclick=safe(async()=>{
 if(!current()||S.loading||S.saving||S.queueLoading||S.drag||S.draft.length||!canEdit())return;
 const a=current(),label=$('new-'+kind).value.trim();if(!label)throw Error('请先填写中文名称');
 S.saving=true;sync();
 try{const result=await api('/api/attributes',{kind,label});S.meta=await api('/api/meta');remember();a[kind]=result.value;$('new-'+kind).value='';status('已加入选项并选用于当前标注，请保存修改');}
 finally{S.saving=false;sync();}
});
$('brush-size').oninput=()=>{$('brush-label').textContent=$('brush-size').value+' px';};
for(const view of ['dual','opt','sar'])$('view-'+view).onclick=()=>{S.view=view;for(const v of ['dual','opt','sar'])$('view-'+v).classList.toggle('on',v===view);fit();};
$('zoom-in').onclick=()=>{S.zoom=Math.min(8,S.zoom*1.25);layout();};$('zoom-out').onclick=()=>{S.zoom=Math.max(.1,S.zoom/1.25);layout();};$('zoom-fit').onclick=fit;
$('local-zoom').onclick=()=>{if(S.drag)return;L.enabled=!L.enabled;$('local-zoom').classList.toggle('on',L.enabled);$('local-zoom').setAttribute('aria-pressed',L.enabled);drawDetail();};
$('detail-scale').onchange=()=>{if(!S.drag)drawDetail();};
async function save(){
 if(S.saving||S.loading||!S.stem)return;if(!canEdit())throw Error('当前没有编辑权，修改仍保留，请重新申请编辑');if(S.draft.length||S.drag||S.redraw)throw Error('请先闭合或取消当前绘制');
 const anns=serial();if(anns.some(a=>!a.category||(!a.segmentation&&!a.sar_segmentation)))throw Error('每条标注必须有类别和掩膜；缺失掩膜请删除后重画');
 const sig=JSON.stringify(anns),site=S.site,stem=S.stem,workflow=S.workflow;S.saving=true;sync();status('保存中…');
 try{const result=await api('/api/save',{site,stem,image_size:[S.h,S.w],base_revision:S.revision,geometry_mode:'per_modality',annotations:anns,workflow_status:workflow,lease_token:P.token,editor_version:EDITOR_VERSION});if(S.site===site&&S.stem===stem){S.revision=result.revision;S.saved=sig;S.savedWorkflow=workflow;$('source-info').textContent='已保存的人工标签 · 两侧可独立调整';$('workflow-current').textContent='已保存状态：'+STATE_LABELS[workflow];status(dirty()?'已保存快照，仍有未保存修改':'已保存 · '+STATE_LABELS[workflow]);await queue(false);void refreshProgress();}}
 catch(e){if(e.status===423)pauseEditing('readonly','编辑权已失效 · 当前修改保留，请重新申请编辑');else if(e.status===409)pauseEditing('stale','标注版本已变化 · 请先备份未保存内容，再重新加载');throw e;}
 finally{S.saving=false;sync();}
}
$('save').onclick=safe(save);
$('workflow-status').onchange=()=>{if(S.loading||S.saving||S.queueLoading||!S.stem||!canEdit())return;S.workflow=$('workflow-status').value;status('状态尚未保存，请点保存修改');};
$('export').onclick=safe(async()=>{if(S.draft.length||S.drag||dirty())throw Error('请先保存当前修改再导出');const r=await fetch('/api/export?'+new URLSearchParams({site:S.site,stem:S.stem}));if(!r.ok)throw Error((await r.json()).error);const url=URL.createObjectURL(await r.blob()),a=document.createElement('a');a.href=url;a.download=S.stem+'_paired.zip';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);});
function canLeave(){if(S.saving||S.loading||S.queueLoading){status('正在读写，请稍候');return false;}if(S.drag||S.draft.length||S.redraw){status('请先闭合或取消当前绘制');return false;}return !dirty()||confirm('当前修改尚未保存，确定放弃并切换？');}
const image=url=>new Promise((resolve,reject)=>{const i=new Image();i.onload=()=>resolve(i);i.onerror=()=>reject(Error('影像加载失败'));i.src=url;});
// Cache only immutable images. Annotation revisions always come from /api/tile.
const imagePairs=new Map();let prefetchEpoch=0;
function pairImages(site,stem){
 const key=JSON.stringify([site,stem]);let pending=imagePairs.get(key);
 if(pending){imagePairs.delete(key);imagePairs.set(key,pending);return pending;}
 const q=new URLSearchParams({site,stem});
 pending=Promise.all([image('/api/image?'+q+'&mod=opt'),image('/api/image?'+q+'&mod=sar')]).catch(e=>{if(imagePairs.get(key)===pending)imagePairs.delete(key);throw e;});
 imagePairs.set(key,pending);while(imagePairs.size>3)imagePairs.delete(imagePairs.keys().next().value);
 return pending;
}
async function prefetchNext(){
 const epoch=++prefetchEpoch,site=S.site,stem=S.stem,index=S.tiles.findIndex(t=>t.stem===stem);
 if(!site||!stem||S.loading||S.queueLoading||index<0||site!==$('site').value)return;
 try{
  let next=S.tiles[index+1]?.stem;
  if(!next&&index===S.tiles.length-1&&S.offset+S.tiles.length<S.total){
   const q=new URLSearchParams({site,offset:S.offset+40,limit:1,q:$('filter').value,status:$('queue-status').value});
   const page=await api('/api/tiles?'+q);next=page.items[0]?.stem;
  }
  if(next&&epoch===prefetchEpoch&&S.site===site&&S.stem===stem)await pairImages(site,next);
 }catch(_){/* Foreground load retries failed speculative requests. */}
}
async function load(stem){
 if(!canLeave())return;const token=++S.token;++prefetchEpoch;S.loading=true;drawDetail();sync();status('加载光学与 SAR 影像…');
 try{const site=$('site').value;await releaseEditing();await acquireEditing(site,stem);const query=new URLSearchParams({site,stem}),[record,[opt,sar]]=await Promise.all([api('/api/tile?'+query),pairImages(site,stem)]);if(token!==S.token)return;
  const [h,w]=record.image_size;if(opt.naturalWidth!==w||opt.naturalHeight!==h||sar.naturalWidth!==w||sar.naturalHeight!==h)throw Error('显示影像与标签尺寸不一致');
  const anns=record.annotations.map(a=>hydrate(a,h,w));S.site=record.site;S.stem=stem;S.h=h;S.w=w;S.anns=anns;S.selected=-1;S.redraw=false;S.revision=record.revision||null;S.undo=[];S.redo=[];S.draft=[];S.imgs=[opt,sar];S.saved=signature();$('source-info').textContent=record.source_kind==='saved_manual'?'已保存的人工标签 · 两侧可独立调整':'空白开始 · 仅加载光学与 SAR 影像';
  S.workflow=record.workflow_status==='todo'?'in_progress':record.workflow_status||(record.saved?'done':'in_progress');S.savedWorkflow=S.workflow;$('workflow-current').textContent='已保存状态：'+STATE_LABELS[record.workflow_status||(record.saved?'done':'todo')];
  L.center=null;L.crop=null;for(const id of ['opt','sar']){$(id).width=w;$(id).height=h;}$('scheme-warn').hidden=true;fit();renderQueue();status(stem+(record.saved?' · 已保存':' · 待保存双侧标签'));
 }catch(e){await releaseEditing();P.message='影像加载失败 · 请重新打开';throw e;}finally{S.loading=false;drawDetail();sync();void prefetchNext();void refreshOccupancy();}
}
function renderQueue(){$('list').replaceChildren();for(const item of S.tiles){const b=document.createElement('button');b.className='tile'+(item.stem===S.stem?' on':'');b.textContent=item.stem;const small=document.createElement('small'),state=item.workflow_status||(item.saved?'done':'todo');small.textContent=STATE_LABELS[state];small.className='state-'+state;b.append(small);if(P.occupied.has(item.stem)||(item.stem===S.stem&&canEdit())){const live=document.createElement('small');live.className='occupancy-badge';live.textContent=item.stem===S.stem&&canEdit()?'● 你正在标注':'● 有人正在标注';b.append(live);}b.onclick=safe(()=>load(item.stem));$('list').append(b);}$('queue-count').textContent=S.total?`${S.total} 张 · ${S.offset+1}–${Math.min(S.total,S.offset+S.tiles.length)}`:'无符合条件的影像';}
let progressPending=false;
async function refreshProgress(){
 if(progressPending)return;progressPending=true;const site=$('site').value;
 try{const d=await api('/api/progress?'+new URLSearchParams({site}));$('progress-list').replaceChildren();
  for(const region of d.regions){const row=document.createElement('div');row.className='region-row';const title=document.createElement('div');title.textContent=region.site.replace(S.sitePrefix,'')+` · ${region.counts.done}/${region.total} (${region.percent}%)`;const bar=document.createElement('progress');bar.max=region.total||1;bar.value=region.counts.done;bar.setAttribute('aria-label',title.textContent);const detail=document.createElement('div');detail.className='hint';detail.textContent=`未标注 ${region.counts.todo} · 标注中 ${region.counts.in_progress} · 待讨论 ${region.counts.discussion}`;row.append(title,bar,detail);$('progress-list').append(row);}
  $('progress-time').textContent='更新于 '+new Date().toLocaleTimeString()+' · 每15秒刷新';
  if(site===$('site').value){const map=new Map(d.tiles.map(t=>[t.stem,t]));let changed=false;for(const tile of S.tiles){const fresh=map.get(tile.stem);if(fresh&&fresh.workflow_status!==tile.workflow_status){Object.assign(tile,fresh);changed=true;}}if(changed)renderQueue();const live=map.get(S.stem);if(S.site===site&&live)$('workflow-current').textContent='已保存状态：'+STATE_LABELS[live.workflow_status];}
 }catch(e){$('progress-time').textContent='进度刷新失败，保留上次结果；稍后自动重试';}
 finally{progressPending=false;}
}
async function queue(open=false){++prefetchEpoch;S.queueLoading=true;sync();try{const q=new URLSearchParams({site:$('site').value,offset:S.offset,limit:40,q:$('filter').value,status:$('queue-status').value});const d=await api('/api/tiles?'+q);S.tiles=d.items;S.total=d.total;renderQueue();void refreshOccupancy();}finally{S.queueLoading=false;sync();}if(open&&S.tiles.length)await load(S.tiles[0].stem);else void prefetchNext();}
for(const prefix of ['', 'head-']){for(const [name,delta] of [['prev',-1],['next',1]])$(prefix+name).onclick=safe(async()=>{const i=S.tiles.findIndex(t=>t.stem===S.stem);if(i+delta>=0&&i+delta<S.tiles.length)await load(S.tiles[i+delta].stem);else if(canLeave()){const offset=S.offset+delta*40;if(offset>=0&&offset<S.total){S.offset=offset;await queue(true);}}});for(const [name,delta] of [['page-prev',-40],['page-next',40]])$(prefix+name).onclick=safe(async()=>{if(!canLeave())return;const offset=S.offset+delta;if(offset>=0&&offset<S.total){S.offset=offset;await queue(true);}});}
$('dataset').onchange=safe(async()=>{if(!canLeave()){$('dataset').value=S.dataset;return;}S.dataset=$('dataset').value;$('filter').value='';$('queue-status').value='all';clearScene();setSites();S.offset=0;sync();if($('site').value)await queue(true);else{S.tiles=[];S.total=0;renderQueue();status('此数据集暂无影像');}});
function clearScene(){void releaseEditing();P.occupied.clear();++prefetchEpoch;imagePairs.clear();S.anns=[];S.saved='[]';S.workflow='in_progress';S.savedWorkflow='in_progress';S.mod='opt';S.redraw=false;$('workflow-current').textContent='';S.stem='';S.site='';S.revision=null;S.selected=-1;S.imgs=[];S.undo=[];S.redo=[];S.draft=[];S.drag=null;L.center=null;L.crop=null;drawDetail();$('source-info').textContent='';for(const id of ['opt','sar'])$(id).getContext('2d').clearRect(0,0,$(id).width,$(id).height);}
function setSites(){$('site').replaceChildren();for(const site of S.allSites.filter(v=>v.startsWith(S.sitePrefix)===(S.dataset==='earthmiss')))$('site').add(new Option(site.startsWith(S.sitePrefix)?site.slice(S.sitePrefix.length):site,site));}
$('site').onchange=safe(async()=>{if(!canLeave()){$('site').value=S.site;return;}clearScene();S.offset=0;await queue(true);});
for(const id of ['filter','queue-status'])$(id).onchange=safe(async()=>{if(!canLeave())return;S.offset=0;await queue(false);});
$('add-category').onclick=safe(async()=>{if(S.loading||S.saving||S.drag||S.draft.length||!canEdit())return;await api('/api/categories',{value:$('new-category-en').value,label:$('new-category-zh').value});S.meta=await api('/api/meta');optionList($('category'),S.meta.categories);sync();status('类别已加入，编号保持不变');});
$('editor').onsubmit=e=>e.preventDefault();
window.addEventListener('beforeunload',e=>{if(dirty()||S.draft.length||S.drag){e.preventDefault();e.returnValue='';}});
window.addEventListener('keydown',safe(async e=>{if((e.ctrlKey||e.metaKey)&&e.key.toLowerCase()==='s'){e.preventDefault();await save();return;}if(['INPUT','SELECT','TEXTAREA'].includes(e.target.tagName))return;if((e.ctrlKey||e.metaKey)&&e.key.toLowerCase()==='z'){e.preventDefault();undo(e.shiftKey);}else if(e.key==='Enter'){e.preventDefault();finish();}else if(e.key==='Escape')cancel();else if(e.key==='Backspace'&&S.draft.length&&canEdit()){e.preventDefault();S.draft.pop();draw();}}));
// Safe frontend hot reload: never discard drafts or unsaved annotation changes.
let pendingVersion=null,updateChecking=false,lastActivity=Date.now();
for(const event of ['pointerdown','keydown','input','wheel'])window.addEventListener(event,()=>{lastActivity=Date.now();});
function applyPendingUpdate(){
 if(!pendingVersion||S.loading||S.queueLoading||S.saving||S.drag||S.draft.length||S.redraw||dirty()||Date.now()-lastActivity<15000)return false;
 try{sessionStorage.setItem('earthmiss-update-context',JSON.stringify({site:S.site,stem:S.stem,view:S.view,zoom:S.zoom,offset:S.offset,filter:$('filter').value,queueStatus:$('queue-status').value,selectedId:current()?.id,mod:S.mod}));}
 catch(_){$('update-notice').textContent='新版已就绪，请保存后手动刷新页面';return false;}
 window.location.reload();return true;
}
async function checkFrontendUpdate(){
 if(updateChecking||document.hidden)return;updateChecking=true;
 try{
  const response=await fetch('/index.html',{cache:'no-store'});if(!response.ok)return;
  const html=await response.text(),version=html.match(/data-editor-version="([^"]+)"/)?.[1];
  if(!version||version===EDITOR_VERSION)return;
  pendingVersion=version;$('update-notice').hidden=false;$('update-notice').textContent='新版已就绪。保存或取消当前修改后，空闲时自动更新并返回当前影像。';applyPendingUpdate();
 }catch(_){/* Keep editing normally if the update check is temporarily offline. */}
 finally{updateChecking=false;}
}
function updateContext(){try{const raw=sessionStorage.getItem('earthmiss-update-context');sessionStorage.removeItem('earthmiss-update-context');return raw?JSON.parse(raw):null;}catch(_){return null;}}
if(typeof setInterval==='function'){setInterval(()=>{void checkFrontendUpdate();},60000);setInterval(applyPendingUpdate,5000);}
// Included in app.js before bootstrap. Each document gets a distinct anonymous identity.
const P={client:crypto.randomUUID().replaceAll('-',''),site:'',stem:'',token:null,until:0,state:'none',message:'',generation:0,busy:false,checking:false,occupied:new Set()};
const canEdit=()=>P.state==='owned'&&P.until>Date.now()&&P.site===S.site&&P.stem===S.stem;
async function leaseRequest(body){
 const controller=new AbortController(),timer=setTimeout(()=>controller.abort(),12000);
 try{const r=await fetch('/api/lease',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body),signal:controller.signal});const result=await r.json();if(!r.ok)throw Error(result.error||'占用服务暂不可用');return result;}
 finally{clearTimeout(timer);}
}
function presenceUI(){
 const owned=canEdit(),hasImage=!!S.stem;
 $('presence').hidden=!hasImage;
 $('presence-text').textContent=owned?'● 你正在标注此影像':P.message||'正在确认编辑权…';
 $('presence').className=owned?'presence-own':'presence-readonly';
 $('claim-edit').hidden=owned||P.state==='stale';$('claim-edit').disabled=P.busy||S.loading||S.saving||!hasImage;
 $('reload-latest').hidden=P.state!=='stale';$('reload-latest').disabled=S.loading||S.saving;
 $('backup-draft').hidden=owned||!hasImage||(!dirty()&&!S.draft.length);
 const blocked=!owned||S.loading||S.saving||S.queueLoading;
 for(const id of ['mode-polygon','mode-draw','mode-erase','mode-paint','mode-move','finish','full-mask','category','task','color','material','add-category','new-category-en','new-category-zh','new-color','new-material','add-color','add-material','workflow-status','save'])$(id).disabled=blocked;
 if(!owned){$('undo').disabled=true;$('redo').disabled=true;}
 sideUI();
}
function pauseEditing(state,message){
 P.state=state;P.message=message;
 if(S.drag){const before=S.drag.before;S.drag=null;restore(before);}
 sync();
}
function releasePayload(){return P.token?{action:'release',site:P.site,stem:P.stem,token:P.token}:null;}
function beaconRelease(body){
 if(!body)return;
 try{navigator.sendBeacon('/api/lease',new Blob([JSON.stringify(body)],{type:'application/json'}));}catch(_){}
}
async function releaseEditing(){
 const body=releasePayload();P.generation++;P.token=null;P.until=0;P.state='none';P.message='';P.busy=false;
 if(body){try{await leaseRequest(body);}catch(_){beaconRelease(body);}}
}
async function acquireEditing(site,stem){
 const gen=P.generation,start=Date.now();P.site=site;P.stem=stem;P.state='checking';P.message='正在申请编辑权…';P.busy=true;
 try{
  const result=await leaseRequest({action:'acquire',site,stem,client:P.client});
  if(gen!==P.generation){if(result.owned)beaconRelease({action:'release',site,stem,token:result.token});return null;}
  if(result.owned){P.token=result.token;P.until=start+result.expires_in*1000;P.state='owned';P.message='';}
  else{P.token=null;P.until=0;P.state='readonly';P.message='● 有人正在标注 · 当前只读，请选择其他影像';}
  return result;
 }catch(_){if(gen===P.generation){P.state='offline';P.message='无法确认编辑权 · 当前只读，请检查网络后重新申请';}return null;}
 finally{if(gen===P.generation)P.busy=false;}
}
async function claimEditing(){
 if(P.busy||S.loading||S.saving||!S.stem)return;
 const revision=S.revision,result=await acquireEditing(S.site,S.stem);
 if(result?.owned&&result.revision!==revision){
  if(dirty()||S.draft.length)pauseEditing('stale','最新标注已变化 · 未保存内容保留，请先备份，再重新加载最新标注');
  else{await load(S.stem);return;}
 }
 sync();renderQueue();void refreshOccupancy();
}
async function heartbeatEditing(){
 if(!P.token||P.busy||S.loading||S.saving)return;
 const gen=P.generation,token=P.token,start=Date.now(),prior=P.state;P.busy=true;
 try{
  const result=await leaseRequest({action:'heartbeat',site:P.site,stem:P.stem,token});
  if(gen!==P.generation||token!==P.token)return;
  if(!result.owned){P.token=null;P.until=0;pauseEditing('readonly',result.occupied?'● 已由其他窗口接手 · 当前修改保留，只读状态':'编辑占用已到期 · 当前修改保留，请重新申请编辑');}
  else{
   P.until=start+result.expires_in*1000;
   if(prior==='stale'){P.state='stale';}
   else if(prior!=='owned'&&result.revision!==S.revision)pauseEditing('stale','最新标注已变化 · 请先备份未保存内容，再重新加载');
   else{P.state='owned';P.message='';}
   sync();
  }
 }catch(_){if(gen===P.generation)pauseEditing('offline','网络连接异常 · 未保存修改保留，暂停编辑，正在尝试恢复');}
 finally{if(gen===P.generation){P.busy=false;presenceUI();}}
}
async function refreshOccupancy(){
 if(P.checking||!$('site').value)return;P.checking=true;const site=$('site').value;
 try{const d=await api('/api/occupancy?'+new URLSearchParams({site}));if(site===$('site').value){P.occupied=new Set(d.items.map(x=>x.stem));renderQueue();}}
 catch(_){/* No claim is inferred from a failed status request. */}
 finally{P.checking=false;}
}
function backupDraft(){
 const data={site:S.site,stem:S.stem,image_size:[S.h,S.w],base_revision:S.revision,geometry_mode:'per_modality',active_modality:S.mod,annotations:serial(),unfinished_polygon:clone(S.draft),workflow_status:S.workflow};
 const url=URL.createObjectURL(new Blob([JSON.stringify(data,null,2)],{type:'application/json'})),a=document.createElement('a');a.href=url;a.download=S.stem+'_未保存标注.json';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
}
$('claim-edit').onclick=safe(claimEditing);$('reload-latest').onclick=safe(()=>load(S.stem));$('backup-draft').onclick=backupDraft;
window.addEventListener('pagehide',()=>{beaconRelease(releasePayload());P.generation++;P.token=null;P.until=0;P.state='none';});
window.addEventListener('pageshow',e=>{if(e.persisted&&S.stem)void claimEditing();});
window.addEventListener('online',()=>{if(P.token)void heartbeatEditing();});
window.addEventListener('offline',()=>{if(P.token)pauseEditing('offline','网络已断开 · 未保存修改保留，暂停编辑');});
if(typeof setInterval==='function'){
 setInterval(()=>{void heartbeatEditing();},20000);
 setInterval(()=>{if(!document.hidden)void refreshOccupancy();},10000);
 setInterval(()=>{if(P.state==='owned'&&Date.now()>=P.until)pauseEditing('expired','占用未及时续期 · 未保存修改保留，请重新申请编辑');},2000);
}

safe(async()=>{const [meta,d]=await Promise.all([api('/api/meta'),api('/api/sites')]);S.meta=meta;optionList($('category'),S.meta.categories);optionList($('color'),S.meta.colors);optionList($('material'),S.meta.materials);S.allSites=d.sites;S.sitePrefix=d.earthmiss_prefix||'EarthMiss--';S.dataset=d.sites.some(v=>v.startsWith(S.sitePrefix))?'earthmiss':'guso';$('dataset').value=S.dataset;setSites();const resume=updateContext();if(resume&&d.sites.includes(resume.site)){ $('site').value=resume.site;S.offset=Number.isInteger(resume.offset)&&resume.offset>=0?resume.offset:0;$('filter').value=resume.filter||'';$('queue-status').value=resume.queueStatus||'all';await queue(false);if(resume.stem)await load(resume.stem);if(['dual','opt','sar'].includes(resume.view)){S.view=resume.view;for(const v of ['dual','opt','sar'])$('view-'+v).classList.toggle('on',v===S.view);}if(Number.isFinite(resume.zoom))S.zoom=Math.max(.1,Math.min(8,resume.zoom));if(['opt','sar'].includes(resume.mod))S.mod=resume.mod;S.selected=S.anns.findIndex(a=>a.id===resume.selectedId);sync();layout();}else if(d.sites.length)await queue(true);else status('暂无待标注影像');void refreshProgress();})();
if(typeof setInterval==='function')setInterval(()=>{if(!document.hidden)void refreshProgress();},15000);
