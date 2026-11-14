const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const G=require('../app/static/geometry.js');

class Element{
 constructor(id){this.id=id;this.value='';this.children=[];this.style={};this.listeners={};this.classList={toggle(){}};this.clientWidth=500;this.tagName='BUTTON';}
 replaceChildren(){this.children=[];}append(...values){this.children.push(...values);}add(value){this.children.push(value);}
 setAttribute(){}addEventListener(name,fn){this.listeners[name]=fn;}setPointerCapture(){}
 getBoundingClientRect(){return {left:0,top:0,width:40,height:32};}
 getContext(){return {clearRect(){},fillRect(){},save(){},restore(){},translate(){},drawImage(){},createImageData(w,h){return {data:new Uint8ClampedArray(w*h*4)};},putImageData(){},beginPath(){},moveTo(){},lineTo(){},closePath(){},stroke(){},arc(){},fill(){},strokeRect(){}};}
}
const elements={},el=id=>elements[id]??=new Element(id),saves=[];
const meta={category_labels:{building:'建筑物',road:'道路'},categories:['building','road'],colors:[],materials:[],label_map:{classes:[{value:'building',id:1},{value:'road',id:2}]}};
const context=vm.createContext({console,crypto:require('node:crypto').webcrypto,AbortController,clearTimeout,navigator:{sendBeacon(){}},Blob,Uint8Array,Uint8ClampedArray,URLSearchParams,URL,setTimeout,Option:function(label,value){this.value=value;},MaskGeometry:G,confirm:()=>true,Image:class{},document:{getElementById:el,createElement:id=>new Element(id)},window:{addEventListener(){}},fetch:async(url,options)=>{
 if(url==='/api/lease')return {ok:true,json:async()=>({released:true})};
 if(url.startsWith('/api/occupancy'))return {ok:true,json:async()=>({items:[]})};
 if(url==='/api/meta')return {ok:true,json:async()=>meta};
 if(url==='/api/sites')return {ok:true,json:async()=>({sites:[]})};
 if(url.startsWith('/api/tiles'))return {ok:true,json:async()=>({items:[],total:0})};
 if(url==='/api/save'){saves.push(JSON.parse(options.body));return {ok:true,json:async()=>({revision:'r1'})};}
 throw Error(url);
}});
vm.runInContext(fs.readFileSync(__dirname+'/../app/static/app.js','utf8'),context);
const run=code=>{const value=vm.runInContext(code,context);return value===undefined?undefined:JSON.parse(JSON.stringify(value));};
const event=(x,y)=>({button:0,pointerId:1,clientX:x,clientY:y,preventDefault(){}});
(async()=>{
 await new Promise(resolve=>setImmediate(resolve));
 run("S.site='test';S.stem='multi';S.h=32;S.w=40;S.zoom=1;S.imgs=[{},{}];S.loading=false;S.saving=false;P.site=S.site;P.stem=S.stem;P.state='owned';P.token='test';P.until=Date.now()+90000;");
 run("const p1=[[2,2],[8,2],[8,8],[2,8]],p2=[[12,2],[18,2],[18,8],[12,8]],road=[[3,16],[18,16]];S.anns=[{id:1,category:'building',polygon:p1,mask:G.raster(p1,S.h,S.w),sar_polygon:clone(p1),sar_mask:G.raster(p1,S.h,S.w)},{id:2,category:'building',polygon:p2,mask:G.raster(p2,S.h,S.w),sar_polygon:clone(p2),sar_mask:G.raster(p2,S.h,S.w)},{id:3,category:'road',polygon:null,mask:G.roadRaster(road,4,S.h,S.w),road_centerline:road,road_width:4,sar_polygon:null,sar_mask:G.roadRaster(road,4,S.h,S.w),sar_road_centerline:clone(road),sar_road_width:4}];S.saved=signature();sync();");
 el('mask-list').children[0].children[0].onclick({});
 el('mask-list').children[1].children[0].onclick({ctrlKey:true});
 el('mask-list').children[2].children[0].onclick({ctrlKey:true});
 assert.equal(run('S.multi.size'),3);
 const original=run('serial()');
 await el('mode-move').onclick();
 await el('sar').listeners.pointerdown(event(10,10));
 await el('sar').listeners.pointermove(event(13,12));
 await el('sar').listeners.pointerup(event(13,12));
 assert.equal(run('S.undo.length'),1);
 assert.deepEqual(run('S.anns[0].sar_polygon[0]'),[5,4]);
 assert.deepEqual(run('S.anns[1].sar_polygon[0]'),[15,4]);
 assert.deepEqual(run('S.anns[2].sar_road_centerline[0]'),[6,18]);
 assert.equal(run('S.anns[2].sar_road_width'),4);
 assert.deepEqual(run('S.anns.map(a=>a.polygon)'),original.map(a=>a.polygon));
 assert.deepEqual(run('S.anns[2].road_centerline'),original[2].road_centerline);
 assert.equal(run('S.anns[0].sar_mask[4*40+5]'),1);
 await el('save').onclick();
 assert.equal(saves.length,1);
 assert.deepEqual(Array.from(G.decode(saves[0].annotations[0].sar_segmentation,32,40)),run('Array.from(S.anns[0].sar_mask)'));
 el('undo').onclick();
 assert.deepEqual(run('serial()'),original);
 el('redo').onclick();
 assert.deepEqual(run('S.anns[2].sar_road_centerline[0]'),[6,18]);
 await el('sar').listeners.pointerdown(event(10,10));
 await el('sar').listeners.pointerup(event(90,90));
 assert.deepEqual(run('S.anns[0].sar_polygon[0]'),[5,4]);
 el('mask-list').children[0].children[0].onclick({});
 assert.equal(run('S.multi.size'),1);
 console.log('PASS: multiselect, SAR-only group move, road parameters, save, undo/redo, invalid move rollback, single selection.');
})().catch(error=>{console.error(error);process.exitCode=1;});
