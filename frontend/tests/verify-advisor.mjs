import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import {createSSRApp} from 'vue';
import {renderToString} from '@vue/server-renderer';
import ElementPlus,{ID_INJECTION_KEY,ZINDEX_INJECTION_KEY} from 'element-plus';
import {createServer} from 'vite';
import {contextSignature,applyAdvisorTurn,prepareNavigation,restoredPairIds} from '../src/advisorContext.js';
const data=JSON.parse(await readFile('../backend/data/assistant_examples.json','utf8'));
const initial={profile:data.profile,products:data.pool,selectedId:null,comparePair:[],chatMessages:[],chatDraft:'',assistantState:{}};
const context=structuredClone(initial);const token=contextSignature(context);
const reordered=structuredClone(context);reordered.profile.weights=Object.fromEntries(Object.entries(reordered.profile.weights).reverse());assert.equal(contextSignature(reordered),token);
const first=data.examples[0].result;assert.equal(applyAdvisorTurn(context,data.pool,first,token),true);
assert.equal(context.selectedId,first.state.focus_id);assert.equal(context.assistantState.version,2);
const earlier=contextSignature(context);context.profile.budget=1600;assert.equal(applyAdvisorTurn(context,data.pool,first,earlier),false);assert.equal(context.profile.budget,1600);
const pending=data.examples[3].result;const unchanged=structuredClone(initial);applyAdvisorTurn(unchanged,data.pool,pending,contextSignature(unchanged));assert.equal(unchanged.profile.budget,2000);assert.equal(unchanged.assistantState.pending_change.patch.budget,3000);
const confirmed=data.examples[4].result;applyAdvisorTurn(unchanged,data.pool,confirmed,contextSignature(unchanged));assert.equal(unchanged.profile.budget,3000);
const pair=data.examples[2].result.products;const navigation=prepareNavigation(context,{type:'compare'},pair);assert.deepEqual(context.comparePair.map(p=>p.id),pair.map(p=>p.id));assert.equal(navigation.product.id,pair[0].id);
context.reportDocument={stale:true};assert.equal(prepareNavigation(context,{type:'report'},pair).tab,'report');assert.equal(context.reportDocument,null);
assert.throws(()=>prepareNavigation(context,{type:'report'},[{...pair[0],category:'电脑'}]));
assert.deepEqual(restoredPairIds(data.pool,pair[0].id,pair),pair.map(p=>p.id));
assert.deepEqual(restoredPairIds(data.pool,pair[1].id,pair),[pair[1].id,pair[0].id]);
assert.equal(restoredPairIds(data.pool,-1,pair),null);assert.equal(restoredPairIds([],null,pair),null);
const vite=await createServer({optimizeDeps:{noDiscovery:true,include:[]},server:{middlewareMode:true},appType:'custom'});
function configured(app){app.use(ElementPlus);app.provide(ID_INJECTION_KEY,{prefix:888,current:0});app.provide(ZINDEX_INJECTION_KEY,{current:0});return app}
try{
 const Answer=(await vite.ssrLoadModule('/src/AssistantAnswer.vue')).default;
 const Page=(await vite.ssrLoadModule('/src/AssistantPage.vue')).default;
 for(const example of data.examples){
  const turn=example.result;const message={role:'assistant',text:turn.answer,source:turn.source,data:turn};
  const html=await renderToString(createSSRApp(Answer,{message}));assert.ok(html.includes(turn.lead));
  for(const p of turn.products){assert.ok(html.includes(p.name));assert.ok(html.includes('生成报告'))}
  if(turn.intent==='compare'){assert.ok(html.includes('answer-table-wrap'));assert.ok(html.includes('进入产品对比'))}
  if(turn.intent==='confirm'){assert.ok(html.includes('确认调整至'));assert.ok(html.includes('保持原预算'))}
  if(turn.sources.length)assert.ok(html.includes('来源与采集日期'));
 }
 const pageContext=structuredClone(initial);pageContext.chatMessages=data.examples.slice(0,3).flatMap(e=>[{role:'user',text:e.question},{role:'assistant',text:e.result.answer,source:e.result.source,data:e.result}]);
 const html=await renderToString(configured(createSSRApp(Page,{context:pageContext})));
 for(const label of ['当前选购','修改需求','语音输入','购买报告','来源与采集日期'])assert.ok(html.includes(label));
 const injected=structuredClone(first);injected.lead='<script>untrusted</script>';const escaped=await renderToString(createSSRApp(Answer,{message:{data:injected,text:injected.answer}}));assert.ok(!escaped.includes('<script>untrusted</script>'));assert.ok(escaped.includes('&lt;script&gt;'));
 console.log('Advisor: real product cards, comparison, budget confirmation, context races, cross-page actions and escaped content verified.');
}finally{await vite.close()}
