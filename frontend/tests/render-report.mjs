import assert from 'node:assert/strict';
import {createCanvas,GlobalFonts,loadImage} from '@napi-rs/canvas';
import {existsSync} from 'node:fs';
import {readFile,writeFile} from 'node:fs/promises';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import {drawReport} from '../src/reportCanvas.js';
const fonts=[process.env.SMARTBUY_FONT,'C:/Windows/Fonts/msyh.ttc','/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf'].filter(Boolean);
for(const font of fonts){if(existsSync(font)){GlobalFonts.registerFromPath(font,'Microsoft YaHei');break}}
const root=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'../..');
const cases=['report_preview.json','report_warning_preview.json','report_unknown_preview.json','report_laptop_preview.json'];
for(const filename of cases){
 const report=JSON.parse(await readFile(path.join(root,'backend/data',filename),'utf8'));assert.equal(report.version,2);
 const images={};for(const p of [report.product,report.peer].filter(Boolean)){if(p.image_url?.startsWith('/api/product-images/'))images[p.id]=await loadImage(path.join(root,'backend/data/product_images',path.basename(p.image_url)));}
 for(const format of ['slide','full']){
  let calls=[];
  globalThis.window={document:{createElement:()=>{const canvas=createCanvas(1400,100);const c=canvas.getContext('2d');const fill=c.fillText.bind(c);c.fillText=(text,x,y,...args)=>{const w=c.measureText(String(text)).width;calls.push({text,x,y,right:x+(c.textAlign==='center'?w/2:w),left:x-(c.textAlign==='center'?w/2:0)});return fill(text,x,y,...args)};return canvas}}};
  const canvas=drawReport(report,'violet',format,images);
  assert.equal(canvas.width,format==='slide'?1920:1400);if(format==='slide')assert.equal(canvas.height,1080);else assert.ok(canvas.height>1500&&canvas.height<18000);
  const overflow=calls.filter(t=>t.left<-1||t.right>canvas.width+1||t.y>canvas.height||t.y<0);assert.deepEqual(overflow,[],filename+' '+format+' text overflow');
  if(report.reasons.some(r=>!r.known))assert.ok(calls.some(t=>t.text.includes('待确认事项')));
  if(filename==='report_preview.json'){
   const output=path.join(root,'docs',format==='slide'?'选购报告-PPT精简版.png':'选购报告-完整长图.png');await writeFile(output,canvas.toBuffer('image/png'));
   if(format==='full')await writeFile(path.join(root,'docs/选购报告示例.png'),canvas.toBuffer('image/png'));
   if(format==='full'){const preview=createCanvas(1400,1700);preview.getContext('2d').drawImage(canvas,0,0);await writeFile(path.join(root,'docs/选购报告-长图预览.png'),preview.toBuffer('image/png'));}
  }
  console.log(JSON.stringify({case:filename,format,width:canvas.width,height:canvas.height,textChecked:calls.length}));
 }
}
// A theme change preserves structure and can render without downloaded photos.
const report=JSON.parse(await readFile(path.join(root,'backend/data/report_preview.json'),'utf8'));
globalThis.window={document:{createElement:()=>createCanvas(1400,100)}};
const mint=drawReport(report,'mint','slide');await writeFile(path.join(root,'docs/选购报告-PPT薄荷绿.png'),mint.toBuffer('image/png'));
