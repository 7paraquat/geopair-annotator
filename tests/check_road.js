const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const G=require('../app/static/geometry.js');

function expected(points,width,h,w){
 const out=new Uint8Array(h*w),r=width/2;
 for(let y=0;y<h;y++)for(let x=0;x<w;x++){
  const px=x+.5,py=y+.5;
  for(let i=1;i<points.length;i++){
   const [ax,ay]=points[i-1],[bx,by]=points[i],dx=bx-ax,dy=by-ay;
   const t=Math.max(0,Math.min(1,((px-ax)*dx+(py-ay)*dy)/(dx*dx+dy*dy)));
   if(Math.hypot(px-ax-t*dx,py-ay-t*dy)<=r+1e-10){out[y*w+x]=1;break;}
  }
 }
 return out;
}
for(const points of [
 [[4,4],[24,4]], [[-8,8],[12,8],[12,25]], [[3,3],[30,27]],
 [[8,-5],[8,14],[35,14]], [[50,50],[52,52]],
])for(const width of [1,2,5,12,25]){
 const h=32,w=40;
 if(points[0][0]>w)assert.throws(()=>G.roadRaster(points,width,h,w),/未覆盖/);
 else assert.deepEqual(G.roadRaster(points,width,h,w),expected(points,width,h,w));
}
assert.throws(()=>G.roadRaster([[1,1],[1,1]],5,32,40),/重合/);
assert.throws(()=>G.roadRaster([[1,1],[5,5]],0,32,40),/宽度/);

class Element{
 constructor(id){this.id=id;this.value='';this.children=[];this.style={};this.listeners={};this.classList={toggle(){}};this.clientWidth=500;this.tagName='BUTTON';}
 replaceChildren(){this.children=[];}append(...v){this.children.push(...v);}add(v){this.children.push(v);}setAttribute(){}addEventListener(k,f){this.listeners[k]=f;}setPointerCapture(){}
 getBoundingClientRect(){return {left:0,top:0,width:192,height:128};}
 getContext(){return {clearRect(){},fillRect(){},save(){},restore(){},translate(){},drawImage(){},createImageData(w,h){return {data:new Uint8ClampedArray(w*h*4)};},putImageData(){},beginPath(){},moveTo(){},lineTo(){},closePath(){},stroke(){},arc(){},fill(){},strokeRect(){}};}
}
const elements={},el=id=>elements[id]??=new Element(id),saves=[];
const meta={category_labels:{},categories:['road'],colors:[],materials:[],label_map:{classes:[{value:'road',id:8}]}};
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
 run("S.site='test';S.stem='road';S.h=64;S.w=96;S.zoom=2;S.imgs=[{},{}];S.loading=false;S.saving=false;P.site=S.site;P.stem=S.stem;P.state='owned';P.token='test';P.until=Date.now()+90000;");
 el('road-width').value='8';await el('mode-road').onclick();
 for(const point of [[20,20],[100,20],[120,60]])await el('opt').listeners.pointerdown(event(...point));
 assert.equal(run('S.draft.length'),3);await el('finish').onclick();
 assert.equal(run('S.anns.length'),1);assert.equal(run('current().category'),'road');
 assert.equal(run('current().mask.reduce((a,b)=>a+b,0)'),run('current().sar_mask.reduce((a,b)=>a+b,0)'));
 await el('mode-road-edit').onclick();await el('sar').listeners.pointerdown(event(100,20));
 await el('sar').listeners.pointermove(event(100,30));await el('sar').listeners.pointerup(event(100,30));
 assert.notEqual(run('JSON.stringify(current().road_centerline)'),run('JSON.stringify(current().sar_road_centerline)'));
 el('road-width').value='12';el('road-width').onchange();
 assert.equal(run('current().sar_road_width'),12);assert.equal(run('current().road_width'),8);
 await el('save').onclick();assert.equal(saves.length,1);assert.equal(saves[0].annotations[0].category,'road');
 assert.deepEqual(saves[0].annotations[0].sar_segmentation.size,[64,96]);
 run('restore(serial())');assert.equal(run('current().sar_road_width'),12);
 console.log('PASS: road pixel oracle, input validation, centerline editing, independent sensor width, save and reload.');
})().catch(e=>{console.error(e);process.exitCode=1;});
