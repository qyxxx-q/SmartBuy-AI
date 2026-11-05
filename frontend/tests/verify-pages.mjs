import assert from 'node:assert/strict';
import {createSSRApp} from 'vue';
import {renderToString} from '@vue/server-renderer';
import ElementPlus,{ID_INJECTION_KEY,ZINDEX_INJECTION_KEY} from 'element-plus';
import {createServer} from 'vite';
const vite=await createServer({optimizeDeps:{noDiscovery:true,include:[]},server:{middlewareMode:true},appType:'custom'});
function configured(app){app.use(ElementPlus);app.provide(ID_INJECTION_KEY,{prefix:1024,current:0});app.provide(ZINDEX_INJECTION_KEY,{current:0});return app;}
try{
  const modules={};
  for(const name of ['App','Personalized','Comparison','PurchaseReport','AssistantPage','ShoppingLinks'])modules[name]=(await vite.ssrLoadModule('/src/'+name+'.vue')).default;
  const response=await fetch('http://127.0.0.1:8000/api/recommend',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({category:'手机',budget:6000})});
  const result=await response.json();const products=result.products;
  const context={profile:{category:'手机',budget:6000,scenario:'办公',needs:'6000元手机',weights:{performance:22,price:23,battery:14,portability:12,ease:12,camera:7,screen:10}},products,pendingPrice:result.pending_price,overBudget:result.over_budget,selectedId:products[0]?.id,chatMessages:[{role:'user',text:'你好'},{role:'assistant',text:'**欢迎** <script>unsafe</script>',source:'测试'}],chatDraft:'',reportDocument:null};
  const markers={Personalized:'personal-page',Comparison:'comparison-page',PurchaseReport:'report-page',AssistantPage:'assistant-page'};
  for(const [name,marker] of Object.entries(markers)){
    if(name==='AssistantPage')globalThis.window={};
    const app=configured(createSSRApp(modules[name],{context}));
    const html=await renderToString(app);
    assert.ok(html.includes(marker));
    for(const [other,otherMarker] of Object.entries(markers))if(name!==other)assert.ok(!html.includes('class="'+otherMarker+'"'));
    if(name==='Personalized'){assert.ok(html.includes('预算匹配推荐'));for(const stage of ['输入需求','提取条件','筛选候选','排序与解释'])assert.ok(html.includes(stage));}
    if(name==='AssistantPage'){assert.ok(!html.includes('<script>unsafe</script>'));assert.ok(html.includes('&lt;script&gt;unsafe&lt;/script&gt;'));}
    delete globalThis.window;
    console.log(name+': distinct page rendered');
  }
  const profileResponse=await fetch('http://127.0.0.1:8000/api/profile',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({text:'2000元手机，给父母用，希望字体大、操作简单、续航好。'})});
  const elder=await profileResponse.json();assert.equal(elder.budget,2000);
  const elderResponse=await fetch('http://127.0.0.1:8000/api/recommend',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(elder)});
  const elderResult=await elderResponse.json();
  assert.ok(elderResult.products.every(p=>p.recommendation_eligible&&p.price<=2000));
  assert.ok(!elderResult.products.some(p=>p.name==='iPhone 17 Pro'));
  const elderContext={...context,profile:elder,products:elderResult.products,pendingPrice:elderResult.pending_price,overBudget:elderResult.over_budget};
  const elderHtml=await renderToString(configured(createSSRApp(modules.Personalized,{context:elderContext})));
  if(!elderResult.products.length){assert.ok(elderHtml.includes('暂时没有已确认在预算内的配置报价'));assert.ok(!elderHtml.includes('TOP 1</strong>'));}
  assert.ok(elderHtml.includes('尚不能确认符合预算，不参与 TOP 推荐'));
  const sample=elderResult.products[0]||elderResult.pending_price[0]||elderResult.over_budget[0];
  assert.ok(sample);
  // Deliberately inject cached unqualified products: they must never inherit TOP badges.
  const fixtures=[{...sample,id:-1,name:'测试预算内 A',price:1500,score:80,recommendation_eligible:true},{...sample,id:-2,name:'测试预算内 B',price:1600,score:70,recommendation_eligible:true},{...sample,id:-3,name:'测试预算内 C',price:1700,score:60,recommendation_eligible:true},{...sample,id:-4,name:'测试未核价旗舰',price:null,score:99,recommendation_eligible:false},{...sample,id:-5,name:'测试超预算缓存',price:9999,score:100,recommendation_eligible:true}];
  const podiumHtml=await renderToString(configured(createSSRApp(modules.Personalized,{context:{...elderContext,products:fixtures,pendingPrice:[],overBudget:[]}})));
  for(const n of [1,2,3])assert.ok(podiumHtml.includes('TOP '+n+'</strong>'));
  assert.ok(!podiumHtml.includes('测试未核价旗舰'));assert.ok(!podiumHtml.includes('测试超预算缓存'));
  assert.ok(podiumHtml.indexOf('测试预算内 A')<podiumHtml.indexOf('测试预算内 B'));
  console.log('Elder budget: only verified within-budget products receive TOP 1–3, including after cached navigation');
  const catalogResponse=await fetch('http://127.0.0.1:8000/api/catalog?q=EOS%20R50');
  const quotedCamera=(await catalogResponse.json()).products.find(p=>p.name==='EOS R50');
  assert.ok(quotedCamera);
  // Component display fixture; expiry itself is covered by backend pricing tests.
  const displayFixture={...quotedCamera,platform_quotes:['京东','淘宝'].map(platform=>quotedCamera.offers.find(o=>o.platform===platform)).filter(Boolean)};
  const quoteHtml=await renderToString(createSSRApp(modules.ShoppingLinks,{product:displayFixture,compact:true}));
  for(const platform of ['京东','淘宝','拼多多','闲鱼'])assert.ok(quoteHtml.includes(platform));
  assert.ok(quoteHtml.includes('5,499'));assert.ok(quoteHtml.includes('6,199'));
  assert.ok(quoteHtml.includes('参考价'));assert.ok(quoteHtml.includes('报价来源'));assert.ok(quoteHtml.includes('未取得公开报价'));
  console.log('Quote cards: four platforms, actual collected amounts, reference labels and candid missing-price states');
  const app=configured(createSSRApp(modules.App));const html=await renderToString(app);
  assert.equal((html.match(/class="app-nav/g)||[]).length,4);
  assert.ok(!html.includes('class="comparison-page"'));assert.ok(!html.includes('class="assistant-page"'));
  console.log('App: exactly four navigation items, only the active page rendered');
}finally{await vite.close()}
