<script setup>
import { computed,defineAsyncComponent,onMounted,reactive,ref } from 'vue';
import UiIcon from './UiIcon.vue';
import Personalized from './Personalized.vue';
import {api} from './api';
const Comparison=defineAsyncComponent(()=>import('./Comparison.vue'));
const PurchaseReport=defineAsyncComponent(()=>import('./PurchaseReport.vue'));
const AssistantPage=defineAsyncComponent(()=>import('./AssistantPage.vue'));
const tabs=[{id:'personal',name:'个性推荐',icon:'spark',sub:'从你的需求出发'},{id:'compare',name:'产品对比',icon:'compare',sub:'把差别看得更清楚'},{id:'report',name:'购买报告',icon:'report',sub:'留存你的选购结论'},{id:'assistant',name:'智能助手',icon:'chat',sub:'想问什么，随时聊聊'}];
const active=ref('personal'),catalogCount=ref(78),modelReady=ref(false);
const current=computed(()=>tabs.find(t=>t.id===active.value));
const context=reactive({profile:{curated_only:false,category:'手机',subcategory:null,budget:2000,scenario:'老人使用',user_type:'长辈',needs:'2000元手机，给父母用，希望字体大、操作简单、续航好。',weights:{performance:2,price:30,battery:25,portability:8,ease:25,camera:0,screen:10}},products:[],selectedId:null,compareSeedId:null,comparePair:[],process:null,autoReport:false,reportDocument:null,assistantState:{},assistantSuggestions:[],chatMessages:[],chatDraft:''});
function navigate(tab,product){if(product){context.selectedId=product.id;if(context.profile.category!==product.category)context.profile.needs='预算'+context.profile.budget+'元，想选购'+product.category+'，主要用于'+context.profile.scenario+'。';context.profile.category=product.category;context.profile.subcategory=null;if(!context.products.some(p=>p.id===product.id))context.products=[product,...context.products.filter(p=>p.category===product.category)];if(tab==='compare')context.compareSeedId=product.id;if(tab==='report')context.autoReport=true;}active.value=tab;window.scrollTo({top:0,behavior:'instant'});}
onMounted(async()=>{try{const [health,catalog]=await Promise.all([api('health'),api('catalog')]);modelReady.value=health.llm_configured;catalogCount.value=catalog.products.length;}catch{}});
</script>
<template>
<div class="app-shell">
 <aside class="app-sidebar"><a class="app-brand" href="#" @click.prevent="navigate('personal')"><span class="brand-symbol"><UiIcon name="spark" :size="25"/></span><span>SmartBuy <b>AI</b><small>更懂你的数码选购伙伴</small></span></a><div class="nav-caption">我的选购空间</div><nav aria-label="主栏目"><button v-for="tab in tabs" :key="tab.id" :class="['app-nav',active===tab.id&&'active']" @click="navigate(tab.id)"><UiIcon :name="tab.icon"/><span>{{tab.name}}<small>{{tab.sub}}</small></span><i v-if="active===tab.id"></i></button></nav><div class="sidebar-note"><span class="note-orbit">✧</span><h4>好选择，从了解开始</h4><p>官方参数、真实需求，<br>为每一次选择多想一步。</p><span class="library-chip">{{catalogCount}} 款产品已收录</span></div><button class="sidebar-status" @click="navigate('assistant')"><i :class="{ready:modelReady}"></i>{{modelReady?'已配置大模型':'智能助手 · 可连接大模型'}}<span>↗</span></button><small class="sidebar-copy">SMARTBUY · YOUR NEXT GOOD CHOICE</small></aside>
 <main class="app-main"><header class="app-topbar"><span>工作台 <i>/</i> <b>{{current.name}}</b></span><div><span class="top-library">官方产品资料库</span><span class="user-avatar">SB</span></div></header><div class="page-wrap"><Personalized v-if="active==='personal'" :context="context" @navigate="navigate"/><Comparison v-else-if="active==='compare'" :context="context" @navigate="navigate"/><PurchaseReport v-else-if="active==='report'" :context="context"/><AssistantPage v-else :context="context" @navigate="navigate" @model-change="modelReady=$event"/></div></main>
</div>
</template>