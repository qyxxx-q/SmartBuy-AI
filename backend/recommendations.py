"""Parameter-based preference ranking and source-grounded buying reports."""
import math
import re
import catalog
from pricing import attach_price
from scoring import parameter_scores, scenario_weights

LABELS = {'performance':'性能参数','price':'预算','battery':'续航参数','portability':'尺寸重量',
          'ease':'操作与兼容','camera':'影像参数','screen':'屏幕参数'}
BASE_WEIGHTS = dict(performance=22,price=23,battery=14,portability=12,ease=12,camera=7,screen=10)
PATTERNS = {
    'performance':r'芯片|处理器|内存|chip|processor|memory|CPU',
    'battery':r'电池|续航|充电|battery|charging|power',
    'portability':r'重量|尺寸|weight|dimensions',
    'ease':r'系统|兼容|辅助|连接|蓝牙|操作|system|compatib|bluetooth|connect',
    'camera':r'摄像|相机|像素|影像|传感器|camera|sensor|image',
    'screen':r'屏幕|显示|取景|display|screen|viewfinder',
}
TIPS = {
 '手机':('先看你每天的使用方式：通勤刷视频更值得关注续航和重量；拍娃、旅行则要看常用焦段的实拍。不要只因为芯片型号更新就提高预算。',
        '存储容量要留出照片和聊天记录的增长空间。购买前确认是否为国内版本、网络制式和保修地区；给长辈选购，最好让本人试试字体、音量和解锁流程。'),
 '电脑':('先列出必须运行的软件、插件和游戏，再检查系统兼容性。编程学习要核对开发工具；游戏或剪辑要看对应软件的实际测试，官网有芯片参数并不等于帧率或渲染速度已经达标。',
        '把内存、硬盘、显示器和接口一起核对。经常背着走，还要算上充电器重量；台式机的预算需加显示器和键鼠。内存或硬盘不能后期升级的机型，建议下单前一次确认容量。'),
 '平板':('网课、阅读和手写笔记的重点不同：阅读先试握持重量，手写先试延迟与误触，办公先确认所需软件功能是否完整。不要默认平板能完全替代电脑。',
        '先确认手写笔与键盘的具体兼容型号，配件通常另购。把保护套、手写笔和键盘计入总预算；如果主要在家或学校使用，也可先比较无线局域网版是否已满足需求。'),
 '耳机':('耳机适不适合你，佩戴感往往比参数更关键。通勤可重点试听降噪和环境音；会议要测试麦克风；运动则应确认佩戴稳定性及官方防护条件。',
        '确认手机、电脑的连接兼容性和切换方式。续航要区分单次与充电盒累计、开关降噪两种情况。下单前问清拆封试戴后的退换规则，避免买到不舒服却无法退换的型号。'),
 '相机':('先想清楚主要拍照片还是视频、经常拍什么题材，再决定机身。对新手来说，镜头焦段、握持和对焦操作同样影响体验，不能只看像素数量。',
        '确认报价是单机身还是套机。把镜头、存储卡、备用电池和必要配件计入总预算；拍视频还需核对录制格式、裁切、存储卡要求及使用条件。已有镜头时先核对卡口和转接兼容性。'),
}


def recommendation(data, include_unqualified=False):
    category = data.get('category','手机')
    if category == '笔记本': category = '电脑'
    if category not in catalog.CATEGORIES: raise ValueError('产品类别无效')
    budget = float(data.get('budget',3500))
    if not math.isfinite(budget) or not 1 <= budget <= 50000:
        raise ValueError('预算必须在 1–50000 元之间')
    incoming = data.get('weights') or scenario_weights(data.get('scenario',''),str(data.get('needs','')))
    if not isinstance(incoming,dict): raise ValueError('偏好格式无效')
    weights = {}
    for key, default in BASE_WEIGHTS.items():
        value = float(incoming.get(key,default))
        if not math.isfinite(value): raise ValueError('权重必须是有限数值')
        weights[key] = max(0,min(100,value))
    total = sum(weights.values())
    if not total: raise ValueError('至少保留一个关注因素')
    needs = str(data.get('needs',''))
    with catalog.connect() as db:
        rows = db.execute("SELECT * FROM catalog_products WHERE category=? AND validation_status='verified'",(category,)).fetchall()
        products = []
        for row in rows:
            if data.get('curated_only') is True and not db.execute('SELECT 1 FROM curated_products WHERE product_id=?',(row['id'],)).fetchone():continue
            p = attach_price(db,dict(row),allow_used=data.get('include_used') is True,budget=budget,include_reference=data.get('include_reference') is not False)
            if data.get('subcategory') and p['subcategory']!=data['subcategory']:
                continue
            # A desktop is not a substitute when the user explicitly wants a laptop.
            if category == '电脑' and any(w in needs for w in ('笔记本','轻薄本','便携电脑','游戏本')) and p['subcategory']=='台式电脑':
                continue
            specs = [dict(r) for r in db.execute('SELECT section,label,value,source_url FROM catalog_specs WHERE product_id=? ORDER BY id',(p['id'],))]
            p['parameter_region_note']=next((s['value'] for s in specs if s['label']=='参数地区说明'),'')
            evidence = {}
            for key, pattern in PATTERNS.items():
                hit = next((s for s in specs if re.search(pattern,s['label'],re.I)),None)
                # Long PDF pages are kept as evidence, never converted to invented specifications.
                if not hit:
                    hit = next((s for s in specs if re.search(pattern,s['value'],re.I)),None)
                if hit:
                    text = hit['value']
                    match = re.search(pattern,text,re.I)
                    start = max(0,match.start()-25) if match and len(text)>260 else 0
                    evidence[key] = {'label':hit['label'], 'value':text[start:start+260]+('…' if len(text)>start+260 else ''),
                                     'source_url':hit['source_url']}
            price = p['price']
            is_start = bool(p['offer'] and p['offer']['price_type'] != '配置报价')
            status = '待核价' if price is None else '起售价在预算内，配置待确认' if is_start and price<=budget else '超出预算' if price>budget else '配置报价在预算内'
            reference=bool(p['offer'] and p['offer'].get('price_basis')=='listing')
            # A public comparison-page listing is a conditional budget lead, explicitly labeled.
            is_start=is_start and not reference
            status = ('平台参考价在预算内，配置待核对' if reference and price is not None and price<=budget else status)
            eligible=price is not None and not is_start and price<=budget and (not reference or data.get('include_reference') is not False)
            if eligible and p['offer'].get('item_condition')=='used': status='二手报价在预算内，成色需核对'
            eligibility='eligible' if eligible else 'over_budget' if price is not None and price>budget else 'pending_price'
            scored = parameter_scores(p,specs,weights,budget,needs,data.get('scenario',''))
            order = sorted(evidence,key=lambda k:weights[k],reverse=True)
            pros = [LABELS[k]+'：'+evidence[k]['value'] for k in order[:3]]
            cons = [status+'。'+p['price_note'],
                    p['parameter_region_note'] or '参数来自 '+p['region']+'；跨地区购买前请确认配置、服务与保修一致。',
                    '评分根据可核对参数和需求计算，不代表性能、音质或画质实测；缺失信息会降低可信度。']
            facts=scored['facts']
            measured=[LABELS[k]+'：'+scored['metric_details'][k]['basis']
                      for k in sorted(scored['metric_details'],key=lambda k:weights.get(k,0),reverse=True)
                      if k!='price' and weights.get(k,0)>0]
            p.update(scored)
            p.update(evidence=evidence,pros=measured[:3] or pros,cons=cons,
                     budget_status=status,recommendation_eligible=eligible,recommendation_status=eligibility,
                     recommendation_tier='reference' if reference else 'verified',
                     eligibility_reason=('公开平台参考价不超过预算，配置、成色、优惠和库存仍需核对' if reference else
                                         '已取得同地区有效配置报价，金额不超过预算') if eligible else status+'，不进入预算内推荐',
                     description=' · '.join(measured[:2])[:180] or '查看官方规格与购物平台报价',
                     reason=('公开参考价不超过预算，配置、成色与库存待核对。' if eligible and reference else
                             '已通过预算核对。' if eligible else '仅供了解与对比，不属于预算内推荐。')+
                            '按你的偏好与可核对参数计算，选购参考分 '+str(scored['score'])+'。'+
                            ('资料中已找到：'+ '、'.join(scored['matched_needs'])+'。' if scored['matched_needs'] else '')+status+'。',
                     score_label='选购参考分')
            products.append(p)
    return sorted((p for p in products if include_unqualified or p['recommendation_eligible']),
                  key=lambda p:(-p['score'],-p['confidence'],p['id']))



def buying_report(data, products, selected_id=None):
    if not products:
        return '目前没有已确认在预算内的有效配置报价，暂不生成推荐结论。请在待核价区核对完整配置和实际价格，或在购买报告中主动选择要了解的产品。', None
    selected = next((p for p in products if p['id']==selected_id),None)
    if selected_id is not None and selected is None: raise ValueError('所选产品不在当前推荐列表中')
    p = selected or products[0]
    budget = float(data.get('budget',3500))
    needs = str(data.get('needs') or data.get('summary') or '根据当前预算与偏好选购')[:1000].rstrip('。.!！')
    sections = ['先说结论\n你希望：'+needs+'。当前预算为 ¥{:,.0f}。'.format(budget)+
                ('按公开参考价，'+p['name']+' 可以列入预算核对候选；容量、成色、库存和最终支付价尚待确认，请核对后再决定。' if p.get('recommendation_tier')=='reference' and p['recommendation_eligible'] else
                 '可以先考虑 '+p['name']+' 的已报价配置。' if p['recommendation_eligible'] else
                 p['name']+' 的状态是“'+p['budget_status']+'”，不属于本次预算内推荐，暂不建议按此预算下单。')+
                ('它是你当前选中的产品，下面围绕它说明。' if selected else '这是当前数据库范围内的候选，并不代表全市场最优。')+
                '目前只能确认官网资料和已采集报价，不能据此保证实际体验。',
                '为什么值得看\n'+'\n'.join('• '+x for x in p['pros'])+
                '\n这些是可核对的规格与报价配置摘录，可能包含系列中不同配置，不能把不同版本的最高参数拼成一台产品。']
    if p['offer']:
        o=p['offer']
        delta=budget-o['amount']
        money=('这是一条平台参考价，与预算差额约 ¥{:,.0f}；不能保证所需配置实际可按此价购买。'.format(delta) if o.get('price_basis')=='listing' else
               '按这条报价，还剩 ¥{:,.0f}，可用于必要配件，但不要默认其他配置同价。'.format(delta)
               if delta>=0 else '这条报价已超出预算 ¥{:,.0f}。如果预算是硬上限，建议暂缓购买，先核对更低配置或其他候选。'.format(-delta))
        sections.append('预算怎么安排\n'+o['merchant']+' 的'+o['price_type']+'为 ¥{:,.0f}。'.format(o['amount'])+
                        '对应：'+o['variant']+'。\n'+money+'\n报价条件：'+o['conditions']+
                        '\n采集时间：'+o['observed_at']+'；这是采集时的公开标价，不是结算承诺。')
    else:
        sections.append('预算怎么安排\n这款尚无有效报价，所以现在不能说它在预算内，也不建议仅凭排名下单。可以点击产品卡片上的京东、淘宝或拼多多入口，按型号搜索并比较完整配置、价格与库存，再把必要配件和运费一起算入 ¥{:,.0f} 的总预算。'.format(budget))
    tips=TIPS[p['category']]
    if p.get('parameter_region_note'):
        sections.append('参数地区与版本\n'+p['parameter_region_note'])
    sections.append('怎么判断适不适合你\n'+tips[0]+'\n'+tips[1])
    if data.get('scenario')=='老人使用':
        sections.append('给长辈多留一步\n尽量一起试用：看字是否清楚、声音是否够大、常用功能是否好找。付款前确认附近售后，再帮家人设置联系人和常用应用。')
    alternatives=[x for x in products if x['id']!=p['id'] and x['recommendation_eligible']][:2]
    sections.append('还可以怎么比较\n'+('\n'.join('• '+x['name']+'：'+x['budget_status']+'。'+
        ('同样可核对'+ '、'.join(LABELS[k] for k in list(x['evidence'])[:2])+'。' if x['evidence'] else '资料还需补充。')+
        '不要直接比较不同容量、地区或套装的价格。' for x in alternatives) if alternatives else '当前没有其他已确认在预算内的配置报价，不强行给出替代款。'))
    sections.append('下单前按这四步确认\n1. 对照完整型号、容量、颜色、地区和配件清单，尤其注意系列页与具体 SKU 的差别。\n'
                    '2. 核对店铺经营主体、自营或官方授权身份、全新状态、发票及保修范围。\n'
                    '3. 分清公开标价、会员价、补贴价和以旧换新价；只有你满足条件的优惠才计入预算。\n'
                    '4. 确认到货时间、退换条件与最终支付总额；若超过硬预算，先不下单。')
    fact_sources=sorted(set(f['source_url'] for f in p['facts'].values() if f.get('source_url') and f['source_url']!=p['source_url']))
    sections.append('资料来源\n商品资料：'+p['source_url']+(''.join('\n参数原文：'+url for url in fact_sources))+('\n报价页面：'+p['offer']['source_url'] if p['offer'] else '')+
                    '\n选购参考分根据参数、偏好及预算计算，未采集的参数不补造；跨平台或不同测试条件的数值不能等同实测排名。')
    sections.append('去平台比价\n可使用页面上的京东、淘宝、拼多多入口，搜索“'+p['shopping_keyword']+'”。先统一容量、地区和套装，再比较最终支付价。搜索结果中的店铺身份与库存请在平台核对。')
    return '\n\n'.join(sections),p
