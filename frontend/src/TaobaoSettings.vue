<script setup>
import { onMounted, ref } from 'vue';
const value=ref({app_key:'',app_secret:'',adzone_id:''}),configured=ref(false),keyPresent=ref(false),busy=ref(false),message=ref('');
async function call(path,body){const response=await fetch('/api/taobao/'+path,body===undefined?{}:{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});const data=await response.json();if(!response.ok)throw new Error(data.error||'请求失败');return data}
function sync(data){configured.value=data.configured;keyPresent.value=data.key_present;value.value={app_key:data.app_key,app_secret:'',adzone_id:data.adzone_id}}
async function save(test=false){busy.value=true;message.value='';try{sync(await call('config',value.value));message.value='配置已保存在本机，尚未验证权限。';if(test){message.value='正在测试淘宝接口…';message.value=(await call('test',{})).message}}catch(e){message.value=e.message}finally{value.value.app_secret='';busy.value=false}}
onMounted(async()=>{try{sync(await call('config'))}catch(e){message.value=e.message}});
</script>
<template>
<details class="taobao-settings"><summary>淘宝 API 配置 <small>{{configured?'已配置 · 可测试权限':'待开通账号与接口权限'}}</small></summary>
<p>先完成淘宝联盟入驻，并在开放平台申请应用及“物料搜索升级版”和消费者比价场景权限。AppKey / AppSecret 来自应用；推广位 ID 来自淘宝联盟推广位管理。</p>
<nav><a href="https://pub.alimama.com/" target="_blank" rel="noopener noreferrer">淘宝联盟 ↗</a><a href="https://open.taobao.com/" target="_blank" rel="noopener noreferrer">淘宝开放平台 ↗</a><a href="https://developer.alibaba.com/docs/api.htm?apiId=64759" target="_blank" rel="noopener noreferrer">接口文档 ↗</a></nav>
<form @submit.prevent="save(true)"><label>AppKey<input v-model="value.app_key" autocomplete="off" required /></label><label>AppSecret<input v-model="value.app_secret" type="password" autocomplete="new-password" :placeholder="keyPresent?'已保存，留空保留原密钥':'在本机填写应用密钥'" :required="!keyPresent"/></label><label>推广位 ID / 完整 PID<input v-model="value.adzone_id" placeholder="数字 ID 或 mm_…" required /></label><div><button class="secondary-btn" type="button" :disabled="busy" @click="save(false)">保存配置</button><button class="primary-btn" :disabled="busy">{{busy?'处理中…':'保存并测试调用'}}</button></div></form>
<p>密钥保存在此电脑的后端配置文件中，不会返回到页面。配置完成后，打开下方产品的“查看参数”，点击“调用淘宝 API 更新报价”。商品级价格会标为参考价，容量、库存、运费仍需核对。</p><p v-if="message" role="status">{{message}}</p>
</details>
</template>
<style scoped>
.taobao-settings{padding:20px;border:1px solid #e4def7;border-radius:14px;background:#fff;margin:20px 0}.taobao-settings summary{cursor:pointer;font-weight:600}.taobao-settings small{margin-left:14px;color:#79718f;font-weight:400}.taobao-settings p{font-size:13px;color:#737487;line-height:1.8}.taobao-settings nav{display:flex;gap:20px;flex-wrap:wrap}.taobao-settings a{color:#685ce2;font-size:13px}.taobao-settings form{display:grid;gap:14px;margin:20px 0;grid-template-columns:repeat(3,minmax(0,1fr))}.taobao-settings label{display:grid;gap:8px;font-size:13px}.taobao-settings input{border:1px solid #deddeb;border-radius:7px;padding:10px;min-width:0}.taobao-settings form>div{grid-column:1/-1;display:flex;gap:12px}@media(max-width:700px){.taobao-settings form{grid-template-columns:1fr}}
</style>
