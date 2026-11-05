import {money,date,observed,short} from './reportFormat.js';

// Only same-origin catalog images; a failed image never blocks the report export.
export async function loadReportImages(doc){
 const images={};if(typeof Image==='undefined')return images;
 await Promise.all([doc.product,doc.peer].filter(Boolean).map(p=>new Promise(resolve=>{
  if(!p.image_url?.startsWith('/api/product-images/'))return resolve();
  const img=new Image();let done=false;const finish=ok=>{if(done)return;done=true;clearTimeout(timer);if(ok)images[p.id]=img;resolve()};
  const timer=setTimeout(()=>finish(false),5000);img.onload=()=>finish(true);img.onerror=()=>finish(false);img.src=p.image_url;
 })));return images;
}

export function drawReport(doc,theme='violet',format='full',images={}){
 if(doc.version!==2)throw new Error('请重新生成报告，以使用新的导出格式');
 const slide=format==='slide',width=slide?1920:1400;
 const canvas=window.document.createElement('canvas');canvas.width=width;canvas.height=slide?1080:100;
 let c=canvas.getContext('2d');
 const accent=theme==='mint'?'#278570':'#7960bd',pale=theme==='mint'?'#edf7f1':'#f3effb',dark=theme==='mint'?'#234e47':'#3c3158',ink='#393046',muted='#7d7088';
 const font=(size,bold=false)=>`${bold?600:400} ${size}px "Microsoft YaHei","PingFang SC",sans-serif`;
 function text(value,x,y,size=22,color=ink,bold=false){c.font=font(size,bold);c.fillStyle=color;c.fillText(String(value??''),x,y)}
 function lines(value,w,size){c.font=font(size);const result=[];for(const para of String(value||'').split('\n')){let line='';for(const char of para){if(c.measureText(line+char).width>w&&line){result.push(line);line=char}else line+=char}result.push(line)}return result}
 function fitted(value,w,size,max){const rows=lines(value,w,size);if(rows.length<=max)return rows;const result=rows.slice(0,max);c.font=font(size);let last=result[max-1];while(last&&c.measureText(last+'…').width>w)last=last.slice(0,-1);result[max-1]=last+'…';return result}
 function paragraph(value,x,y,w,size=22,color=muted,line=34,bold=false,max=null){const rows=max?fitted(value,w,size,max):lines(value,w,size);rows.forEach((v,i)=>text(v,x,y+i*line,size,color,bold));return rows.length*line}
 function rect(x,y,w,h,r,fill){c.beginPath();c.moveTo(x+r,y);c.arcTo(x+w,y,x+w,y+h,r);c.arcTo(x+w,y+h,x,y+h,r);c.arcTo(x,y+h,x,y,r);c.arcTo(x,y,x+w,y,r);c.closePath();c.fillStyle=fill;c.fill()}
 function photo(p,x,y,w,h){rect(x,y,w,h,16,'#ffffff');const img=images[p.id];if(img){const iw=img.naturalWidth||img.width,ih=img.naturalHeight||img.height;const scale=Math.min((w-20)/iw,(h-20)/ih);c.drawImage(img,x+(w-iw*scale)/2,y+(h-ih*scale)/2,iw*scale,ih*scale)}else{c.textAlign='center';text(p.category||'产品',x+w/2,y+h/2+8,28,'#c6b8d5');c.textAlign='left'}}
 function reset(h){canvas.height=h;c=canvas.getContext('2d');c.fillStyle='#faf8fc';c.fillRect(0,0,width,h)}
 const p=doc.product,b=doc.budget,q=doc.quotes[0],remaining=b.remaining==null?null:Math.abs(b.remaining);
 if(slide){
  reset(1080);const grad=c.createLinearGradient(0,0,1920,245);grad.addColorStop(0,dark);grad.addColorStop(1,accent);c.fillStyle=grad;c.fillRect(0,0,1920,245);
  text('SMARTBUY AI  /  选购决策简报',52,43,18,'#e5dced',true);text('PPT 精简版 · 完整配置与来源见长图 / 网页',1270,43,16,'#e4d9ef');
  paragraph(doc.title,52,104,1460,39,'#fff',47,true,1);paragraph(p.name,52,157,1450,27,'#eee5f6',35,true,1);
  paragraph(doc.selection.label+(doc.selection.is_system_choice?' · 与系统首选一致':doc.system_choice?' · 系统当前首选：'+doc.system_choice.name:' · 当前无预算内首选'),52,201,1510,17,'#e5d9ee',24,false,1);paragraph('需求：'+doc.profile.needs,52,230,1510,16,'#e5d9ee',22,false,1);photo(p,1670,65,195,155);
  rect(48,265,1824,96,16,'#fff');
  const stats=[['预算上限',money(doc.profile.budget)],[(q?.price_type||'有效报价'),money(p.price)],[b.remaining<0?'超出预算':'名义余额 · 未计配件',money(remaining)],['评分信息覆盖 · 非质量分',p.confidence+'%']];
  stats.forEach(([label,value],i)=>{text(label,76+i*454,296,16,muted);text(value,76+i*454,337,29,i===2&&b.remaining<0?'#b8764f':accent,true)});
  rect(48,379,1824,82,14,pale);text(doc.decision.status,70,410,19,accent,true);paragraph(doc.decision.conclusion+' '+doc.decision.note,70,439,1770,20,'#756782',27,false,1);
  doc.reasons.slice(0,3).forEach((r,i)=>{const x=48+i*616;rect(x,481,592,191,15,r.known?'#fff':'#fffaf0');text(r.known?'有参数依据':'待确认事项',x+22,511,15,r.known?accent:'#ac8951');text(r.title,x+22,545,22,ink,true);paragraph(r.evidence,x+22,578,548,21,accent,28,true,2);paragraph(r.known?r.meaning:r.check,x+22,631,548,17,muted,24,false,2)});
  rect(48,694,1120,283,16,'#fff');text('两款怎么取舍',72,732,23,ink,true);
  if(doc.peer){
   doc.tradeoff.choices.forEach((choice,i)=>paragraph((i===0?'A：':'B：')+choice.when,72,758+i*24,1060,16,i===0?accent:'#368c76',22,false,1));
   text('关注维度',72,819,16,muted);paragraph('A · '+p.name,210,819,430,18,accent,23,true,1);paragraph('B · '+doc.peer.name,675,819,465,18,'#368c76',23,true,1);
   doc.tradeoff.rows.slice(0,3).forEach((r,i)=>{const y=852+i*34;rect(66,y-20,1084,31,3,i%2===0?'#faf8fd':'#fff');text(r.label,76,y,16,muted);paragraph(r.values[0],210,y,430,17,ink,21,false,1);paragraph(r.values[1],675,y,465,17,ink,21,false,1)});
   paragraph(doc.tradeoff.gap_note,72,960,1060,16,'#a18a72',23,false,1);
  }else{paragraph('本次聚焦 '+p.name+'，未选择第二款产品。',74,789,1060,24,accent,38,true,2);paragraph('可在网页中选择同品类候选，查看完整参数与取舍。缺少有效报价时，先核对具体配置与价格。',74,884,1040,21,muted,34,false,2)}
  rect(1188,694,684,283,16,'#fff');text('报价凭据 · 购买行动',1212,732,23,ink,true);
  doc.quotes.slice(0,2).forEach((quote,i)=>{const y=767+i*62;const source=doc.sources.find(s=>s.id===quote.source_id);paragraph(short(quote.name,24)+'  '+money(quote.amount),1212,y,634,19,accent,25,true,1);paragraph(quote.active?`[${quote.source_id}] ${source?.host||quote.merchant} · ${date(quote.observed_at)} · ${quote.price_type}${quote.item_condition==='used'?' · 二手':''}`:'暂无有效报价，不确认预算匹配',1212,y+23,634,15,muted,21,false,1);paragraph(quote.active?quote.variant:'配置与报价待核对',1212,y+43,634,14,'#ad9eb8',20,false,1)});
  const stepsY=doc.quotes.length>1?904:855;
  doc.checklist.forEach((item,i)=>text(String(i+1).padStart(2,'0')+'  '+item.title,1212,stepsY+i*24,17,'#8f7d9e'));
  text('参数参考与当前偏好用于解释选择，不代表实测；未核实项目请在下单前确认。',52,1015,17,muted);
  text('生成于 '+observed(doc.generated_at)+'  ·  报价以采集日期为准，实际配置、库存及支付金额请到来源页核对。',52,1047,16,'#aa9cb3');
  return canvas;
 }
 // Long report: measure first, draw second. No text is truncated in body cards.
 const jobs=[];let y=620;
 function job(h,draw){const top=y;jobs.push(()=>draw(top,h));y+=h+22}
 function heading(title,top,num){rect(76,top+22,42,36,10,pale);text(typeof num==='number'?String(num).padStart(2,'0'):String(num),85,top+47,17,accent,true);text(title,135,top+49,26,ink,true)}
 function card(title,body,num,size=23){const rows=lines(body,1228,size);const h=100+rows.length*35;job(h,(top,height)=>{rect(48,top,1304,height,18,'#fff');heading(title,top,num);paragraph(body,84,top+99,1228,size,'#786982',35)})}
 card('从你的需求出发',doc.profile.needs+'\n'+doc.selection.label+'；'+(doc.selection.is_system_choice?'与系统首选一致。':doc.system_choice?'系统当前首选为 '+doc.system_choice.name+'，本报告围绕所选对象展开。':'当前没有预算内首选。')+'\n选购参考分 '+p.score+'；评分信息覆盖 '+p.confidence+'%，用于说明资料，不代表实测成绩。',1);
 const reasonWidth=400;const reasonBodies=doc.reasons.map(r=>'依据：'+r.evidence+'\n'+r.meaning+'\n购买前：'+r.check+'\n'+r.rule+(r.source_id?'\n['+r.source_id+'] 参数原文':''));
 const reasonHeight=140+Math.max(...reasonBodies.map(body=>lines(body,reasonWidth-34,20).length))*31;
 job(reasonHeight+80,(top,h)=>{rect(48,top,1304,h,18,'#fff');heading('为什么考虑这款',top,2);doc.reasons.forEach((r,i)=>{const x=76+i*421;rect(x,top+78,400,reasonHeight-18,12,r.known?pale:'#fff8eb');text(r.known?'有参数依据':'待确认事项',x+17,top+109,15,r.known?accent:'#a7864f');paragraph(r.title,x+17,top+145,365,21,ink,29,true,2);paragraph(reasonBodies[i],x+17,top+199,366,20,'#796784',31)})});
 if(doc.peer){
  const rowHeights=doc.tradeoff.rows.map(r=>30+Math.max(...r.values.map(v=>lines(v,495,21).length))*31);
  const choices=doc.tradeoff.choices.map(v=>v.name+'\n'+v.when+'\n'+v.caution);
  const ch=Math.max(...choices.map(v=>lines(v,580,21).length))*33+24;
  const h=215+rowHeights.reduce((s,h)=>s+h,0)+ch+95;
  job(h,(top,height)=>{rect(48,top,1304,height,18,'#fff');heading('两款怎么取舍',top,3);paragraph('A · '+p.name,220,top+98,495,23,accent,31,true,2);paragraph('B · '+doc.peer.name,770,top+98,495,23,'#368c76',31,true,2);let rowY=top+165;
   doc.tradeoff.rows.forEach((r,i)=>{rect(76,rowY,1248,rowHeights[i],4,i%2===0?'#faf8fd':'#fff');paragraph(r.label,90,rowY+28,115,18,muted,26);paragraph(r.values[0],220,rowY+28,495,21,ink,31);paragraph(r.values[1],770,rowY+28,495,21,ink,31);rowY+=rowHeights[i]});
   doc.tradeoff.choices.forEach((v,i)=>{rect(76+i*634,rowY+18,614,ch,12,i===0?pale:'#edf7f2');paragraph(choices[i],92+i*634,rowY+51,580,21,'#786482',33)});
   paragraph(doc.tradeoff.gap_note,84,rowY+ch+76,1230,20,'#9d826b',30);paragraph(doc.tradeoff.caveat,84,rowY+ch+113,1230,17,muted,27);
  });
 }else card('两款怎么取舍','本次先聚焦一款。未选择第二款，或没有其他预算内候选；先核对具体配置与价格。',3);
 card('预算如何安排',b.label+'：'+money(remaining)+'。\n'+b.note+'\n配件核对：'+b.accessories+'。配件费用尚待核对，未计入本次预算。',4);
 for(const quote of doc.quotes){
  const body=quote.name+' · '+money(quote.amount)+'\n'+quote.status+'\n'+(quote.active?quote.merchant+' · '+quote.price_type+'\n完整配置：'+quote.variant+'\n采集于 '+observed(quote.observed_at)+'\n报价条件：'+quote.conditions+'\n['+quote.source_id+'] 报价原页见来源清单':
   '暂无有效报价，不计入预算。'+(quote.historical?'\n历史记录：'+money(quote.historical.amount)+'；'+observed(quote.historical.observed_at)+'。只作资料，不作为当前可购价。':''));
  card('报价凭据',body,'→');
 }
 card('下单前，按这三步确认',doc.checklist.map((v,i)=>(i+1)+'. '+v.title+'\n'+v.body).join('\n\n'),5);
 card('来源与资料范围',doc.sources.map(s=>'['+s.id+'] '+s.label+'\n'+s.url+(s.observed_at?'\n采集于 '+observed(s.observed_at):'')).join('\n\n')+'\n\n'+doc.limitations.join('\n'),6,19);
 reset(y+150);const grad=c.createLinearGradient(0,0,width,425);grad.addColorStop(0,dark);grad.addColorStop(1,accent);c.fillStyle=grad;c.fillRect(0,0,width,425);
 text('SMARTBUY AI / PERSONAL BUYING REPORT',64,56,20,'#eadff4',true);paragraph(doc.title,64,130,1030,42,'#fff',54,true,2);paragraph(p.name,64,205,1030,30,'#eee4f6',40,true,2);photo(p,1146,80,190,190);
 text(doc.selection.label+(doc.selection.is_system_choice?' · 与系统首选一致':''),64,289,18,'#e1d4ee');paragraph(doc.decision.conclusion+' '+doc.decision.note,64,339,1270,23,'#f1e9f9',35,false,2);
 rect(48,449,1304,126,18,'#fff');[['预算上限',money(doc.profile.budget)],[(q?.price_type||'有效报价'),money(p.price)],[b.remaining<0?'超出预算':'名义余额 · 未计配件',money(remaining)]].forEach(([label,value],i)=>{text(label,82+i*435,489,18,muted);text(value,82+i*435,541,36,i===2&&b.remaining<0?'#b8764f':accent,true)});
 jobs.forEach(draw=>draw());text('把选择留给自己，把依据留在这份报告里。',64,y+40,24,accent,true);text('生成于 '+observed(doc.generated_at)+' · 具体配置、库存和最终支付金额以购买页面为准。',64,y+85,18,muted);text('SMARTBUY AI  /  YOUR NEXT GOOD CHOICE',64,y+121,13,'#ae9eb9');return canvas;
}

export function canvasBlob(canvas){return new Promise((resolve,reject)=>canvas.toBlob(blob=>blob?resolve(blob):reject(new Error('图片生成失败，请重试')),'image/png'))}
