<script setup>
const props=defineProps({product:{type:Object,required:true},compact:Boolean});
const quote=platform=>{const list=(props.product.platform_quotes||[]).filter(o=>o.platform===platform);return list.find(o=>o.id===props.product.offer?.id)||list.find(o=>o.item_condition!=='used')||list[0]};
const money=o=>'¥'+Number(o.amount).toLocaleString();
const date=value=>new Date(value).toLocaleString('zh-CN',{timeZone:'Asia/Shanghai',hour12:false});
</script>
<template>
  <div :class="['shopping-links',compact&&'compact']" @click.stop>
    <p v-if="!compact">平台报价与购买入口</p>
    <div class="shopping-buttons"><div v-for="link in product.shopping_links" :key="link.platform" class="platform-quote"><a :href="quote(link.platform)?.purchase_url||link.url" target="_blank" rel="noopener noreferrer" :aria-label="'查看'+link.platform+'上的'+product.name"><span>{{link.platform}}</span><strong>{{quote(link.platform)?money(quote(link.platform)):'查价 ↗'}}</strong></a><div v-if="quote(link.platform)" class="quote-caption"><span>{{quote(link.platform).item_condition==='used'?'二手':quote(link.platform).price_basis==='listing'?'参考价':'全新标价'}}</span><a :href="quote(link.platform).source_url" target="_blank" rel="noopener noreferrer" :title="quote(link.platform).variant+'；'+quote(link.platform).conditions+'；采集于 '+date(quote(link.platform).observed_at)">报价来源 ↗</a></div><span v-else class="no-quote">未取得公开报价</span></div></div>
    <div v-if="product.offer" class="applied-quote"><b>预算匹配采用：{{product.offer.platform}} {{money(product.offer)}}</b><span>{{product.offer.item_condition==='used'?'二手 · '+product.offer.condition_note:product.offer.price_basis==='listing'?'公开参考价，配置、成色与库存待核对':'全新 · 具体配置公开标价'}}</span><small>{{product.offer.variant}}</small><a :href="product.offer.source_url" target="_blank" rel="noopener noreferrer">{{product.offer.price_basis==='listing'?'查看参考报价原文':'查看报价原文'}} ↗</a><time>采集于 {{date(product.offer.observed_at)}}</time></div>
    <small v-if="!compact">未取得报价的平台提供型号搜索。报价按不同配置、全新与二手分别核对；搜索入口不代表报价或店铺身份已核验。</small>
  </div>
</template>
<style scoped>
.shopping-links{margin-top:16px;border-top:1px solid #eceef6;padding-top:14px}.shopping-links p{font-size:12px;color:#545a73;margin:0 0 10px;line-height:1.6}.shopping-buttons{display:flex;flex-wrap:wrap;gap:8px}.shopping-buttons a{display:flex;align-items:center;gap:10px;padding:8px 12px;background:#f7f7fd;border:1px solid #e4e6f2;border-radius:8px;color:#575074;font-size:12px;text-decoration:none;transition:background .15s}.shopping-buttons a:hover{background:#eeebff;border-color:#c8c1f8;color:#6258e8}.shopping-buttons span{font-size:10px}.shopping-links small{display:block;line-height:1.6;color:#959aab;margin-top:10px;font-size:10px}.compact{border:0;padding:0;margin:14px 0 0}.compact .shopping-buttons a{padding:7px 10px}
</style>
<style scoped>
.shopping-buttons{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:8px}.platform-quote{min-width:0;border:1px solid #e8e6f3;background:#faf9ff;border-radius:9px;padding:9px 10px}.shopping-buttons .platform-quote>a{padding:0;border:0;background:none;justify-content:space-between;gap:5px;font-size:12px}.platform-quote strong{font-size:12px;color:#6c5ad1;white-space:nowrap}.quote-caption{display:flex;justify-content:space-between;gap:3px;flex-wrap:wrap;margin-top:6px}.quote-caption span,.quote-caption a,.no-quote{font-size:10px;color:#9390a7;text-decoration:none}.quote-caption a{color:#8171b6}.no-quote{display:block;margin-top:6px}.applied-quote{padding:10px 0 0;color:#7a7c8f;font-size:11px;line-height:1.75}.applied-quote b,.applied-quote span,.applied-quote time{display:block}.applied-quote b{font-weight:500;color:#70617e}.applied-quote small{margin:2px 0 0;font-size:10px}.applied-quote a{color:#8671bf;font-size:10px}.applied-quote time{font-size:10px;color:#a4a4b2}.compact .shopping-buttons .platform-quote>a{padding:0}
</style>
