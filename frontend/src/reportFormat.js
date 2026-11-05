export const money=value=>value==null?'待核价':'¥'+Number(value).toLocaleString('zh-CN',{maximumFractionDigits:2});
export const date=value=>value?new Date(value).toLocaleDateString('zh-CN',{timeZone:'Asia/Shanghai'}):'未记录';
export const observed=value=>value?new Date(value).toLocaleString('zh-CN',{timeZone:'Asia/Shanghai',hour12:false}):'未记录';
export const short=(value,n=90)=>{const chars=Array.from(String(value||''));return chars.length>n?chars.slice(0,n-1).join('')+'…':chars.join('')};
