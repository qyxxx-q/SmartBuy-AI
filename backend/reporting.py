"""A decision report with explicit selection, practical tradeoffs and dated evidence."""
from datetime import datetime, timezone
from urllib.parse import urlparse
import catalog
from comparison import compare_products
from scoring import ACTIVE, scenario_weights
from recommendations import LABELS, TIPS, BASE_WEIGHTS

NAMES={'performance':'日常配置是否够用','battery':'少一点充电焦虑','portability':'带着走是否轻松',
       'ease':'上手与连接是否顺手','camera':'影像规格是否合适','screen':'看内容是否舒服'}
MEANING={
 'performance':'先满足常用应用和软件的配置需求，再考虑额外性能余量。内存、核心数不能直接代表跨平台运行速度。',
 'battery':'续航相关规格值得优先核对，但标称容量与厂商测试时间不能直接换算成你的使用天数。',
 'portability':'经常通勤、随身携带或长时间握持时，重量会影响使用负担；配件和充电器也要一起考虑。',
 'ease':'先核对常用设备、软件和操作方式，连接功能多不代表操作一定简单。',
 'camera':'先围绕拍摄题材核对镜头、对焦与视频功能，像素等单项规格不能代表实际画质。',
 'screen':'阅读、上课与多任务使用时，屏幕规格值得关注；刷新率和尺寸不能代替清晰度与舒适度体验。'}
CHECKS={
 'performance':'带着必须使用的软件或游戏清单，核对系统与配置；有条件时查看同配置实测。',
 'battery':'核对典型值、额定值及测试模式；耳机要分清单次、充电盒累计与降噪开关条件。',
 'portability':'确认报价版本的重量口径，尤其区分耳机与充电盒、相机机身与镜头、电脑与充电器。',
 'ease':'让实际使用者试一遍常用流程，确认兼容设备、连接切换与解锁方式。',
 'camera':'查看常用题材和焦段的样张，核对防抖、对焦及视频模式的具体限制。',
 'screen':'尽量试一下字号、亮度和握持感，不能仅凭标称尺寸判断阅读体验。'}
ACCESSORIES={'手机':'保护壳、充电器是否随附，以及必要的数据迁移与设置',
             '电脑':'鼠标、转接器与必要软件；台式机还需显示器和键鼠',
             '平板':'兼容的手写笔、键盘与保护套是否另购',
             '耳机':'耳塞尺寸、充电线、试戴及拆封退换条件',
             '相机':'镜头、存储卡、备用电池与必要的拍摄配件'}

def money(value):
    return '待核价' if value is None else '¥'+('{:,.2f}'.format(value).rstrip('0').rstrip('.'))

def mini(p):
    if not p:return None
    keys=('id','name','brand','category','subcategory','image_url','score','confidence','price','budget_status',
          'recommendation_eligible','recommendation_tier','parameter_region_note','facts','source_url','offer')
    return {k:p.get(k) for k in keys}

def build_report(data, selected, peer, products):
    p=selected;category=p['category'];budget=float(data.get('budget',3500));elder=category=='手机' and data.get('scenario')=='老人使用'
    needs=str(data.get('needs') or data.get('summary') or '根据当前预算与用途选择合适的'+category)[:1000]
    incoming=data.get('weights') or scenario_weights(data.get('scenario',''),needs)
    weights={k:max(0,min(100,float(incoming.get(k,v)))) for k,v in BASE_WEIGHTS.items()}
    eligible=[x for x in products if x['recommendation_eligible']];first=eligible[0] if eligible else None
    rank=next((i+1 for i,x in enumerate(eligible) if x['id']==p['id']),None)
    title=('给父母的' if elder else '学习用' if data.get('scenario')=='学习' else '游戏用' if data.get('scenario')=='游戏' else '')+\
          money(budget)[1:]+'元'+category+'选购建议'
    sources=[]
    def cite(url,kind,name,stamp=None):
        if not url:return None
        old=next((s for s in sources if s['url']==url and s['kind']==kind),None)
        if old:return old['id']
        sid='S{:02d}'.format(len(sources)+1)
        sources.append(dict(id=sid,url=url,kind=kind,label=name,host=urlparse(url).netloc,observed_at=stamp))
        return sid
    with catalog.connect() as db:
        for item in (p,peer):
            if not item:continue
            for row in db.execute('SELECT DISTINCT source_url,collected_at FROM catalog_specs WHERE product_id=?',(item['id'],)):
                cite(row['source_url'],'参数',item['name']+' · 参数原文',row['collected_at'])
    if not p['recommendation_eligible']:
        conclusion=p['name']+' 当前'+p['budget_status']+'，不属于本次预算内推荐。'+('现在不能说它在预算内，建议先核对所需配置的有效报价。' if p['price'] is None else '预算是硬上限时，先看预算内替代项，不急着下单。')
        tone='warning';status='先核价再决定' if p['price'] is None else '暂缓下单'
    elif p.get('recommendation_tier')=='reference':
        conclusion=p['name']+' 可列入核价候选，公开参考价不超过预算；请先核对配置、库存和最终支付价，再决定是否购买。'
        tone='conditional';status='有条件的预算候选'
    else:
        conclusion='可以先考虑 '+p['name']+' 的已报价配置；把下面的使用体验和购买条件核对清楚，再做最后决定。'
        tone='positive';status='采集报价在预算内'
    if p.get('offer',{} ) and p['offer'].get('item_condition')=='used':
        conclusion+='这是一条二手报价，成色、电池状况和保修需单独确认。';tone='conditional';status='二手核价候选'
    priorities=sorted((k for k in ACTIVE[category] if k!='price' and weights.get(k,0)>0),key=lambda k:-weights.get(k,0))
    reasons=[]
    for key in priorities[:3]:
        detail=p.get('metric_details',{}).get(key);known=detail is not None
        meaning=MEANING[key];check=CHECKS[key];heading=NAMES[key]
        if key=='battery':
            check={'手机':'确认充电器是否随附、充电协议和日常充电习惯；优先参考同配置续航实测。',
                   '电脑':'区分视频播放、联网办公和高负载测试，核对相同内存、屏幕及电池配置。',
                   '平板':'核对屏幕亮度、联网方式与使用任务，手写、网课和游戏的耗电情况不同。',
                   '耳机':CHECKS[key],
                   '相机':'区分拍照张数与录像时长，核对分辨率、帧率、温度和屏幕开关等测试条件。'}[category]
        if key=='portability':
            check={'手机':'确认所选容量与配色版本的重量，尽量握持试一下手感。',
                   '电脑':'一起考虑充电器与常用配件重量；每天背着走时，尽量试背实际组合。',
                   '平板':'加上保护套、手写笔或键盘后，再判断是否适合随身携带。',
                   '耳机':'分清单只耳机、充电盒和含包装重量，佩戴舒适度需要实际试戴。',
                   '相机':'区分单机身、含电池与镜头的重量，再按常用拍摄组合判断负担。'}[category]
        if key=='screen' and category=='电脑':check='试一下显示缩放、反光和常用软件界面；不能仅凭刷新率判断阅读舒适度。'
        if elder and key=='ease':
            heading='给长辈，上手更要亲自试';meaning='字体、音量、解锁和常用应用入口，比功能数量更影响长辈是否用得顺手。'
            check='给长辈多留一步：一起试调大字号、接听电话和解锁；未确认的简易模式与音量表现不作保证。'
        if elder and key=='screen':meaning='较大的阅读空间有助于调大字号，但清晰度、握持与户外可读性仍需本人试用。'
        if elder and key=='performance':meaning='日常配置余量够用即可，不因旗舰型号或核心数量继续提高预算。'
        reasons.append(dict(metric=key,title=heading,known=known,label=LABELS[key],
            evidence=detail['basis'] if known else '当前资料未提供足够的可核对信息',meaning=meaning,
            check=check,rule=detail.get('rule','') if detail else '当前资料尚未明确这项能力；未披露不代表不支持。',
            source_id=cite(detail.get('source_url'),'参数',p['name']+' · '+LABELS[key]) if detail else None))
    # Zero or single-metric profiles still receive a complete reading plan, clearly
    # distinguishing a factual reason from an unanswered purchasing question.
    for key in ACTIVE[category]:
        if len(reasons)>=3:break
        if key=='price' or any(r['metric']==key for r in reasons):continue
        reasons.append(dict(metric=key,title=NAMES[key],known=False,label=LABELS[key],evidence='本次未将这一维度作为已验证的推荐理由',meaning=MEANING[key],check=CHECKS[key],rule='未纳入本次关注重点，购买前可继续核对。',source_id=None))
    chosen_quote=[]
    for item in (p,peer):
        if not item:continue
        offer=item.get('offer');historical=item.get('last_observed_offer') if not offer else None
        q=dict(product_id=item['id'],name=item['name'],amount=item['price'],status=item['budget_status'],active=bool(offer),
               source_id=None,variant=None,merchant=None,price_type=None,observed_at=None,conditions=None,historical=None)
        if offer:
            q.update({k:offer.get(k) for k in ('variant','merchant','price_type','observed_at','conditions','item_condition','availability','price_basis')})
            q['source_id']=cite(offer['source_url'],'报价',item['name']+' · '+offer['merchant'],offer['observed_at'])
            q['url']=offer['source_url']
        elif historical:
            q['historical']={k:historical.get(k) for k in ('amount','observed_at','variant','source_url')}
            q['historical']['source_id']=cite(historical['source_url'],'历史报价',item['name']+' · 历史报价记录',historical['observed_at'])
        chosen_quote.append(q)
    remaining=round(budget-p['price'],2) if p['price'] is not None else None
    budget_label='待核价，不能计算余额' if remaining is None else '超出预算' if remaining<0 else '按采集价计算的余额'
    if p.get('offer') and not p['recommendation_eligible'] and remaining is not None and remaining>=0:budget_label='配置待确认的名义差额'
    if p.get('recommendation_tier')=='reference' and remaining is not None and remaining>=0:budget_label='按参考价计算的名义差额'
    budget_note='这笔差额尚未计入配件和运费；请核对必要配件报价后，再确认实际总支出。'
    if not p['recommendation_eligible']:budget_note='当前不构成预算内推荐。'+budget_note
    if p.get('recommendation_tier')=='reference':budget_note='参考价不保证你所需配置可按此价购买。'+budget_note
    comparison=compare_products(p,peer) if peer else None
    rows=[];choices=[]
    if peer:
        keys=sorted((k for k in ACTIVE[category] if k!='price' and weights.get(k,0)>0),key=lambda k:-weights.get(k,0))[:4]
        for key in keys:
            ds=[item.get('metric_details',{}).get(key) for item in (p,peer)]
            values=[d['basis'] if d else '未披露 / 暂无可核对信息' for d in ds]
            rows.append(dict(metric=key,label=LABELS[key],values=values,known=[bool(d) for d in ds],note=MEANING[key]))
        for i,item in enumerate((p,peer)):
            other=(peer,p)[i]
            adv=sorted(comparison['decisions'][i]['advantages'],key=lambda x:-weights.get(x['metric'],0))
            adv=[a for a in adv if weights.get(a['metric'],0)>0][:2]
            focus='、'.join(a['label'] for a in adv)
            when=('你更关注'+focus+'时，可以先核对这款。') if focus else '当前资料不足以说明它在关注维度明显领先，优先确认具体配置与使用习惯。'
            if not item['recommendation_eligible']:when='当前'+item['budget_status']+'，仅供比较；先核价或选择预算内候选。'
            if item.get('recommendation_tier')=='reference':when+='这条价格是公开参考价，尚不能承诺实际可购。'
            missing=[LABELS[k] for k in keys if item.get('metrics',{}).get(k) is None]
            sacrifice=('需要补充：'+'、'.join(missing)+'。') if missing else '规格优势不等于实际体验，仍需核对测试条件与具体版本。'
            if item['price'] is not None and other['price'] is not None and item['price']>other['price']:
                sacrifice='采集报价高出 '+money(item['price']-other['price'])+'，先确认这些差别是否值得你的额外支出。'+sacrifice
            choices.append(dict(product_id=item['id'],name=item['name'],when=when,caution=sacrifice))
    price_gap=abs(p['price']-peer['price']) if peer and p['price'] is not None and peer['price'] is not None else None
    tradeoff=dict(rows=rows,choices=choices,price_gap=price_gap,
                  gap_note=('两条报价相差 '+money(price_gap)+'；配置、套装或价格条件可能不同，不直接当作同规格性价比结论。') if price_gap is not None else '有产品缺少有效报价，暂不计算价差。',
                  caveat='参数和当前偏好规则用于解释选择，不代表续航、性能、音质或画质实测。')
    if peer and p.get('subcategory')!=peer.get('subcategory'):
        tradeoff['caveat']+='两款产品的形态不同，请先确认是否适合相同用途。'
    experience=('给长辈多留一步：一起试字号、通话音量、解锁和常用应用入口。' if elder else TIPS[category][0])
    checklist=[dict(title='先核对完整配置',body='对照型号、容量、地区、全新或二手状态及装箱清单；'+ACCESSORIES[category]+'。先统一配置，再把最终支付总额与预算对照。'),
               dict(title='再确认实际体验',body=experience),
               dict(title='最后确认店铺与售后',body='核对经营主体、官方或自营身份、发票、保修与到货时间。补贴、会员券、以旧换新满足条件后再计算；问清拆封、试用和退换规则，超出硬预算时先不下单。')]
    summary=next((r['meaning'] for r in reasons if r['known']), '资料仍需补充，先把关键配置与体验核对清楚。')
    unresolved=[r['label'] for r in reasons if not r['known']]
    decision_note=('特别留意：'+ '、'.join(unresolved)+' 尚未核实。') if unresolved else '购买前仍需确认实际体验和最终支付金额。'
    profile=dict(category=category,scenario=data.get('scenario') or '日常使用',budget=budget,needs=needs,summary=data.get('summary'),weights=weights)
    doc=dict(version=2,title=title,generated_at=datetime.now(timezone.utc).isoformat(),profile=profile,
        product=mini(p),peer=mini(peer),system_choice=mini(first),comparison=comparison,
        selection=dict(mode='manual' if data.get('product_id') is not None else 'automatic',rank=rank,
                       is_system_choice=bool(first and first['id']==p['id']),eligible_count=len(eligible),
                       label='手动选择的报告对象' if data.get('product_id') is not None else '系统当前首选'),
        decision=dict(status=status,tone=tone,conclusion=conclusion,summary=summary,note=decision_note),
        reasons=reasons,tradeoff=tradeoff,
        budget=dict(limit=budget,product_price=p['price'],remaining=remaining,label=budget_label,note=budget_note,
                    accessories=ACCESSORIES[category],accessories_amount=None),quotes=chosen_quote,
        checklist=checklist,sources=sources,
        limitations=[x for x in [p.get('parameter_region_note'),peer.get('parameter_region_note') if peer else None,tradeoff['caveat'],
                    '报价采集日期与报告生成日期分别记录；超过有效期或不符合地区、库存和配置条件的报价不用于预算推荐。'] if x])
    # Plain text is also the complete, accessible export and keeps full source URLs.
    sections=[dict(title='选购结论',body='你的需求：'+needs+'。\n预算上限：'+money(budget)+'；'+doc['selection']['label']+'：'+p['name']+'。\n'+conclusion+'\n'+decision_note),
              dict(title='为什么适合你',body='\n'.join(r['title']+'\n依据：'+r['evidence']+'。\n'+r['meaning']+'\n购买前：'+r['check'] for r in reasons))]
    pair_body='\n'.join(c['name']+'：'+c['when']+'\n'+c['caution'] for c in choices) if peer else '本次未选第二款；可以先围绕所选对象核对需求、配置与预算。'
    if peer:
        pair_body+='\n'+tradeoff['gap_note']+'\n'+'\n'.join(q['name']+'：'+money(q['amount'])+'；'+q['status']+'。'+('报价来源：'+q['url'] if q.get('url') else '暂无有效报价。') for q in chosen_quote)
    sections.append(dict(title='两款怎么取舍',body=pair_body+'\n'+tradeoff['caveat']))
    quote_body='\n'.join(q['name']+'：'+money(q['amount'])+'；'+q['status']+'。\n'+(q['merchant']+' · '+q['price_type']+'\n'+q['variant']+'\n采集时间：'+q['observed_at']+'\n条件：'+q['conditions'] if q['active'] else '没有有效配置报价；历史资料不计入本次预算。') for q in chosen_quote)
    sections.append(dict(title='预算与报价凭据',body=budget_label+'：'+money(abs(remaining) if remaining is not None else None)+'。\n'+budget_note+'\n配件核对：'+ACCESSORIES[category]+'。\n'+quote_body))
    sections.append(dict(title='购买行动清单',body='\n'.join(str(i+1)+'. '+v['title']+'：'+v['body'] for i,v in enumerate(checklist))))
    sections.append(dict(title='来源与说明',body='\n'.join('['+s['id']+'] '+s['label']+'：'+s['url']+('；采集于 '+s['observed_at'] if s['observed_at'] else '') for s in sources)+'\n'+'\n'.join(doc['limitations'])))
    doc['sections']=sections
    return doc
