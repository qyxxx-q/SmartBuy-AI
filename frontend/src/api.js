export async function api(path,body,options={}){
  const response=await fetch('/api/'+path,{...(body===undefined?{}:{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)}),...options});
  let data;try{data=await response.json()}catch{throw new Error('服务返回了无法读取的内容，请稍后重试')}
  if(!response.ok)throw new Error(data.error||'请求未成功');return data;
}
export const labels={performance:'配置与功能',price:'预算匹配',battery:'续航参考',portability:'便携参考',ease:'连接与易用',camera:'影像规格',screen:'屏幕规格'};
export const categories=['手机','电脑','平板','耳机','相机'];
export function scenarioWeights(scenario){
  const weights=scenario==='老人使用'?{performance:2,price:30,battery:25,portability:8,ease:25,camera:0,screen:10}:{performance:22,price:23,battery:14,portability:12,ease:12,camera:7,screen:10};
  if(scenario==='学习'){weights.price+=8;weights.portability+=7}
  if(scenario==='游戏'){weights.performance+=18;weights.screen+=10}
  const total=Object.values(weights).reduce((a,b)=>a+b,0);return Object.fromEntries(Object.entries(weights).map(([k,v])=>[k,Math.round(v*1000/total)/10]));
}
export const priceText=p=>p?.price==null?'到平台查看报价':'¥'+Number(p.price).toLocaleString()+(p.offer?.price_type==='官网起售价'?' 起':'');
export const stamp=v=>new Date(v).toLocaleString('zh-CN',{timeZone:'Asia/Shanghai',hour12:false});
