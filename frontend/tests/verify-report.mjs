import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import {createSSRApp} from 'vue';
import {renderToString} from '@vue/server-renderer';
import {createServer} from 'vite';
const vite=await createServer({optimizeDeps:{noDiscovery:true,include:[]},server:{middlewareMode:true},appType:'custom'});
try{
 const ReportReading=(await vite.ssrLoadModule('/src/ReportReading.vue')).default;
 for(const filename of ['report_preview.json','report_warning_preview.json','report_unknown_preview.json','report_laptop_preview.json']){
  const doc=JSON.parse(await readFile('../backend/data/'+filename,'utf8'));
  const html=await renderToString(createSSRApp(ReportReading,{document:doc}));
  for(const heading of ['从你的需求出发','为什么考虑这款','两款怎么取舍','预算与报价凭据','按这三步确认'])assert.ok(html.includes(heading));
  assert.ok(html.includes(doc.product.name));assert.ok(html.includes(doc.peer.name));assert.ok(html.includes(doc.selection.label));
  if(!doc.selection.is_system_choice&&doc.system_choice)assert.ok(html.includes('当前系统首选'));
  if(!doc.product.recommendation_eligible)assert.ok(html.includes('不属于本次预算内推荐'));
  assert.ok(html.includes('完整采集时间'));console.log(filename+': structured reading page rendered');
 }
 const original=JSON.parse(await readFile('../backend/data/report_preview.json','utf8'));
 const injected={...original,profile:{...original.profile,needs:'<img src=x onerror=alert(1)>'}};
 const html=await renderToString(createSSRApp(ReportReading,{document:injected}));assert.ok(html.includes('&lt;img'));assert.ok(!html.includes('<img src=x'));
 console.log('Report: unknowns, manual selection, quote sources and untrusted text verified');
}finally{await vite.close()}
