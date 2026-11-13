const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const G=require('../app/static/geometry.js');
const rectangle=G.threePointRectangle([[4,4],[16,10],[8,20]]);
const dot=(a,b)=>a[0]*b[0]+a[1]*b[1];
const edge=[rectangle[1][0]-rectangle[0][0],rectangle[1][1]-rectangle[0][1]];
const side=[rectangle[3][0]-rectangle[0][0],rectangle[3][1]-rectangle[0][1]];
assert.ok(Math.abs(dot(edge,side))<1e-9);
assert.deepEqual(G.threePointRectangle([[2,2],[12,2],[7,9]]),[[2,2],[12,2],[12,9],[2,9]]);
assert.throws(()=>G.threePointRectangle([[2,2],[2,2],[7,9]]),/太短/);
const outer=[[2,2],[38,2],[38,30],[2,30]],lines=[[[18,2],[18,30]],[[18,12],[38,12]]];
const regions=G.partitionRegions(outer,lines,32,40);
assert.equal(regions.count,3);
const all=G.assignPartitionBoundaries(regions,32,40);
assert.equal(all.filter(Boolean).length,G.raster(outer,32,40).filter(Boolean).length);
assert.equal(new Set([all[10*40+10],all[10*40+28],all[20*40+28]]).size,3);
assert.equal(G.partitionRegions(outer,[[[10,12],[20,12]]],32,40).count,1);
assert.equal(G.partitionRegions(outer,[[[10,10],[20,10],[20,20],[10,20],[10,10]]],32,40).count,2);

class Element{constructor(id){this.id=id;this.value='';this.children=[];this.style={};this.listeners={};this.classList={toggle(){}};this.clientWidth=500;this.tagName='BUTTON';}
 replaceChildren(){this.children=[];}append(...v){this.children.push(...v);}add(v){this.children.push(v);}setAttribute(){}addEventListener(k,f){this.listeners[k]=f;}setPointerCapture(){}
 getBoundingClientRect(){return {left:0,top:0,width:192,height:128};}
 getContext(){return {clearRect(){},fillRect(){},save(){},restore(){},translate(){},drawImage(){},createImageData(w,h){return {data:new Uint8ClampedArray(w*h*4)};},putImageData(){},beginPath(){},moveTo(){},lineTo(){},closePath(){},stroke(){},arc(){},fill(){},strokeRect(){}};}}
const elements={},el=id=>elements[id]??=new Element(id),saves=[];
const meta={category_labels:{grassland:'草地',tree:'林地',vehicle:'车辆'},categories:['grassland','tree','vehicle'],colors:[],materials:[],label_map:{classes:[{value:'grassland',id:3},{value:'tree',id:4},{value:'vehicle',id:5}]}};
const ctx=vm.createContext({console,crypto:require('node:crypto').webcrypto,AbortController,clearTimeout,navigator:{sendBeacon(){}},Blob,Uint8Array,Uint8ClampedArray,URLSearchParams,URL,setTimeout,Option:function(label,value){this.value=value;},MaskGeometry:G,confirm:()=>true,Image:class{},document:{getElementById:el,createElement:id=>new Element(id)},window:{addEventListener(){}},fetch:async(url,opts)=>{
 if(url==='/api/lease')return {ok:true,json:async()=>({released:true})};
 if(url.startsWith('/api/occupancy'))return {ok:true,json:async()=>({items:[]})};
 if(url==='/api/meta')return {ok:true,json:async()=>meta};
 if(url==='/api/sites')return {ok:true,json:async()=>({sites:[]})};
 if(url.startsWith('/api/tiles'))return {ok:true,json:async()=>({items:[],total:0})};
 if(url==='/api/save'){saves.push(JSON.parse(opts.body));return {ok:true,json:async()=>({revision:'r1'})};}
 throw Error(url);
}});
vm.runInContext(fs.readFileSync(__dirname+'/../app/static/app.js','utf8'),ctx);
const run=code=>vm.runInContext(code,ctx),event=(x,y)=>({button:0,pointerId:1,clientX:x,clientY:y,preventDefault(){}});
(async()=>{
 await new Promise(r=>setImmediate(r));
 run("S.site='test';S.stem='partition';S.h=32;S.w=40;S.zoom=1;S.imgs=[{},{}];S.loading=false;S.saving=false;P.site=S.site;P.stem=S.stem;P.state='owned';P.token='test';P.until=Date.now()+90000;");
 for(const mod of ['opt','sar'])el(mod).getBoundingClientRect=()=>({left:0,top:0,width:40,height:32});
 await el('mode-area').onclick();for(const p of outer)await el('opt').listeners.pointerdown(event(...p));await el('finish').onclick();
 assert.equal(run('S.mode'),'divide');
 for(const p of lines[0])await el('opt').listeners.pointerdown(event(...p));await el('finish').onclick();
 for(const p of lines[1])await el('opt').listeners.pointerdown(event(...p));await el('finish').onclick();
 assert.equal(run('S.partition.regions.count'),3);
 await el('undo-divider').onclick();assert.equal(run('S.partition.regions.count'),2);
 for(const p of lines[1])await el('opt').listeners.pointerdown(event(...p));await el('finish').onclick();
 await el('mode-classify').onclick();
 for(const [x,y,category] of [[10,10,'grassland'],[28,10,'tree'],[28,20,'grassland']]){el('partition-category').value=category;await el('opt').listeners.pointerdown(event(x,y));}
 await el('commit-partition').onclick();assert.equal(run('S.anns.length'),3);
 assert.equal(run('S.anns.every(a=>a.mask.length===S.w*S.h&&a.sar_mask.length===a.mask.length)'),true);
 await el('save').onclick();assert.equal(saves.length,1);assert.equal(saves[0].annotations.length,3);
 const combined=new Uint8Array(32*40);for(const ann of saves[0].annotations){const mask=G.decode(ann.segmentation,32,40);mask.forEach((v,i)=>{if(v){assert.equal(combined[i],0);combined[i]=1;}});}
 assert.deepEqual(combined,G.raster(outer,32,40));
 await el('mode-rect3').onclick();for(const p of [[4,4],[12,8],[7,15]])await el('opt').listeners.pointerdown(event(...p));
 assert.equal(run('S.anns.length'),4);assert.equal(run('current().category'),'vehicle');
 assert.equal(run('current().mask.some(Boolean)'),true);
 console.log('PASS: open dividers, three classes/regions, complete nonoverlapping coverage, save, and rotated three-point rectangle.');
})().catch(e=>{console.error(e);process.exitCode=1;});
