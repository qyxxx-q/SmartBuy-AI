"""Stateful shopping turns. All cards, prices, actions and profile edits are server-owned."""
import json
import math
import re
from datetime import datetime, timezone
import catalog
from recommendations import recommendation, LABELS, TIPS, BASE_WEIGHTS
from profiles import local_profile, explicit_budget
from scoring import scenario_weights, ACTIVE

VERSION='shopping-advisor-v2'
METRIC_WORDS={'battery':r'续航|电池|充电','portability':r'便携|轻便|轻薄|重量|重不重',
              'performance':r'性能|配置|内存|处理器|游戏','screen':r'屏幕|字号|字体|看字',
              'ease':r'操作|简单|简易|易用|连接|兼容|上手','camera':r'拍照|影像|镜头|摄影',
              'price':r'预算|价格|便宜|多少钱|配件|省下|差价'}
BUY_WORDS=r'推荐|选购|怎么买|买哪|买个|想买|想选|换个|换成|预算|便宜|多少钱|比较|对比|哪款|哪一款|适合|为什么考虑|理由|报价|取舍|下单|购买|另一款|另外一款|给父母|给长辈|主要.*用|更看重|更在意'

def money(value):
    return '待核价' if value is None else '¥'+('{:,.2f}'.format(value).rstrip('0').rstrip('.'))

def clean_profile(value):
    allowed=('category','subcategory','budget','scenario','user_type','needs','weights','include_used','include_reference','curated_only','summary','source')
    profile={k:v for k,v in (value or {}).items() if k in allowed}
    profile.setdefault('category','手机');profile.setdefault('budget',3500);profile.setdefault('scenario','办公');profile.setdefault('needs','')
    profile['budget']=float(profile['budget'])
    if not math.isfinite(profile['budget']) or not 1<=profile['budget']<=50000:raise ValueError('预算必须在 1–50000 元之间')
    if profile['category'] not in catalog.CATEGORIES:raise ValueError('产品类别无效')
    if profile['scenario'] not in ('学习','办公','游戏','老人使用'):raise ValueError('主要用途无效')
    incoming=profile.get('weights') or scenario_weights(profile['scenario'],str(profile['needs']))
    if not isinstance(incoming,dict):raise ValueError('关注重点格式无效')
    weights={k:float(incoming.get(k,v)) for k,v in BASE_WEIGHTS.items()}
    if not all(math.isfinite(v) for v in weights.values()):raise ValueError('关注重点必须包含有效数值')
    weights={k:max(0,min(100,v)) for k,v in weights.items()}
    if not sum(weights.values()):raise ValueError('至少保留一个关注重点')
    profile.update(weights=weights,needs=str(profile['needs'])[:1000],include_used=profile.get('include_used') is True,include_reference=profile.get('include_reference') is not False)
    return profile

def signature(profile):
    return json.dumps({k:profile.get(k) for k in ('category','subcategory','budget','scenario','needs','weights','include_used','include_reference','curated_only')},ensure_ascii=True,sort_keys=True)

def proposed_patch(question,profile):
    patch={};amount=explicit_budget(question)
    if not re.search(r'预算|上限|不超过|最多|控制在',question) and (re.search(r'\d\s*[kK]\s*(?:视频|录像|屏|分辨率|拍摄|相机)',question) or re.search(r'差价|多花|多出|省下|省了|差\s*\d',question)):
        amount=None
    # Negated purchases or hypothetical comparisons are not requests to change slots.
    edit=bool(re.search(r'想买|想选|买个|选个|换成|改成|预算|控制在|上限|最多|不超过|给父母|给长辈|主要.*用|更看重|更在意|更重要|优先|接受二手|只要全新|不要二手',question))
    if not edit and amount is not None and re.search(r'\d\s*(?:元|块|千|万|[kK]).{0,8}(?:手机|电脑|笔记本|平板|耳机|相机)',question):edit=True
    if not edit:return patch
    if amount is not None:
        if not 1<=amount<=50000:raise ValueError('预算必须在 1–50000 元之间')
        patch['budget']=round(amount,2)
    if re.search(r'手机|电脑|笔记本|平板|耳机|相机|微单|单反',question) and not re.search(r'不要(?:买)?(?:手机|电脑|平板|耳机|相机)',question):
        parsed=local_profile(question);patch.update(category=parsed['category'],subcategory=parsed['subcategory'])
    for scenario,pattern in [('老人使用',r'父母|长辈|老年|老人'),('游戏',r'主要.*游戏|用于游戏|玩游戏|电竞'),('学习',r'学生|用于学习|网课|编程|做笔记'),('办公',r'主要.*办公|用于办公|工作用')]:
        if re.search(pattern,question):patch.update(scenario=scenario,user_type='长辈' if scenario=='老人使用' else '学生' if scenario=='学习' else '普通用户');break
    if 'scenario' in patch and patch['scenario']!=profile['scenario']:patch['weights']=scenario_weights(patch['scenario'],question)
    if re.search(r'更看重|更在意|更重要|优先|最关心',question):
        key=next((k for k,p in METRIC_WORDS.items() if re.search(p,question)),None)
        if key:patch['weights']={**{k:5 for k in BASE_WEIGHTS},key:50}
    if re.search(r'接受二手|考虑二手|可以二手|看看闲鱼',question):patch['include_used']=True
    if re.search(r'只要全新|不要二手|不接受二手',question):patch['include_used']=False
    patch={k:v for k,v in patch.items() if profile.get(k)!=v}
    if patch:
        # Record an updated need without retaining a contradictory old budget.
        merged={**profile,**patch}
        patch['needs']='预算'+money(merged['budget'])+'，选购'+merged['category']+'，主要用于'+merged['scenario']+'。补充：'+re.sub(r'预算[^，。；,;]*','',question)[:700]
    return patch

def apply_patch(profile,patch):
    allowed=('category','subcategory','budget','scenario','user_type','needs','weights','include_used','include_reference')
    if not isinstance(patch,dict) or any(k not in allowed for k in patch):raise ValueError('待确认的需求修改无效')
    return clean_profile({**profile,**patch})

def normalized(text):return re.sub(r'[^\w]','',str(text)).lower()

def mentioned(question,products):
    q=normalized(question);hits=[]
    for p in products:
        aliases=[normalized(p['name']),normalized(p['name'].replace(' 系列',''))]
        prefix=normalized(p['brand'])
        aliases += [s[len(prefix):] for s in aliases if prefix and s.startswith(prefix)]
        aliases=[s for s in aliases if len(s)>=3]
        found=next((s for s in sorted(aliases,key=len,reverse=True) if s in q),None)
        if found:hits.append((len(found),p))
    hits.sort(key=lambda x:-x[0]);chosen=[];covered=[]
    for length,p in hits:
        name=normalized(p['name'])
        if any(name in n for n in covered):continue
        chosen.append(p);covered.append(name)
    return chosen[:2]

def intent_for(question,has_focus):
    if re.search(r'区别|对比|比较|取舍|省下|差价|值得.*多花|两款.*(?:差|选|值得)|差\s*\d.*元',question):return 'compare'
    if re.search(r'便宜点|便宜一点|省点|价格低|换个便宜',question):return 'cheaper'
    if re.search(r'另一款|另外一款|另一个',question):return 'overview'
    if re.search(r'为什么|理由|考虑它|推荐它',question):return 'explain'
    if re.search(r'注意|下单|购买提醒|怎么检查|适合.*吗',question):return 'checklist'
    if re.search(r'推荐|重新筛选|帮我选|想买|想选|买个|哪款合适|买哪款',question):return 'recommend'
    if re.search(r'价格|报价|多少钱|预算|配件',question):return 'budget'
    if has_focus and any(re.search(pattern,question) for key,pattern in METRIC_WORDS.items() if key!='price'):return 'metric'
    if re.search(BUY_WORDS,question):return 'recommend'
    return 'general'

def brief(p,role='reference'):
    fields=('id','name','brand','category','subcategory','region','image_url','price','price_note','offer','budget_status','recommendation_eligible','recommendation_tier','confidence','score','facts','metric_details','metrics','parameter_region_note','shopping_links','shopping_keyword','platform_quotes','pros','cons','description','reason','evidence','score_note','score_label','scoring_version','collected_at','source_url','source_title')
    card={k:p.get(k) for k in fields};card.update(role=role,reasons=p.get('pros',[])[:2])
    return card

def prepare_turn(data):
    question=str(data.get('question','')).strip()[:3000]
    if data.get('profile') is not None and not isinstance(data['profile'],dict):raise ValueError('选购需求格式无效')
    profile=clean_profile(data.get('profile') if isinstance(data.get('profile'),dict) else {})
    original_signature=signature(profile);state=data.get('state')
    if state is None:state={}
    if not isinstance(state,dict):raise ValueError('对话状态格式无效')
    pending=state.get('pending_change');update=None;notice=None;budget_proposal=None
    confirm=data.get('confirmation')
    if re.fullmatch(r'(?:不调整|不用调整|保持原预算|不要改|算了)[。！!\s]*',question):confirm='reject'
    if confirm in ('apply','reject') or re.fullmatch(r'(?:确认|可以|好|就这样|按这个来|确认调整)[！!。\s]*',question):
        if pending and isinstance(pending,dict) and pending.get('base_signature')==original_signature:
            if confirm=='reject':notice='已保留原预算和需求。'
            else:profile=apply_patch(profile,pending.get('patch'));update=profile.copy();notice='需求已更新，下面按确认后的预算重新核对。'
            pending=None
        elif pending:pending=None;notice='当前需求已经变化，之前的预算提议已失效，请重新说明要调整的金额。'
    else:
        patch=proposed_patch(question,profile)
        if patch:
            if 'budget' in patch:
                pending=dict(patch=patch,base_signature=original_signature)
                budget_proposal=patch['budget']
            else:
                profile=apply_patch(profile,patch);update=profile.copy();pending=None;notice='已更新用途或关注重点，预算保持不变。'
    products=recommendation(profile,include_unqualified=True);by_id={p['id']:p for p in products}
    candidates=[p for p in products if p['recommendation_eligible']]
    focus=by_id.get(data.get('product_id')) or by_id.get(state.get('focus_id')) or (candidates[0] if candidates else None)
    peer=by_id.get(data.get('compare_id'))
    if not peer:
        pair_ids=state.get('pair_ids') or []
        if isinstance(pair_ids,list):peer=next((by_id[i] for i in pair_ids if type(i) is int and i in by_id and (not focus or i!=focus['id'])),None)
    if peer is focus:peer=None
    names=mentioned(question,products)
    if names:
        old=focus;focus=names[0];peer=names[1] if len(names)>1 else peer if peer is not focus else old if old is not focus else None
    if re.search(r'另一款|另外一款|另一个',question) and not re.search(r'区别|比较|对比',question) and peer:
        focus,peer=peer,focus
    if not peer and focus:peer=next((p for p in candidates if p['id']!=focus['id']),None)
    kind='confirm' if budget_proposal is not None else intent_for(question,bool(focus))
    if names and kind=='general':kind='overview'
    if kind=='general' and state.get('last_intent') not in (None,'general') and re.fullmatch(r'(?:可以|好的?|需要|继续|那就这样|看看|是的)[。！!\s]*',question):kind='overview' if focus else 'clarify'
    if not names and re.search(r'电影|食谱|学习计划|旅行路线|写一首|翻译|讲个故事',question):kind='general'
    if confirm in ('apply','reject') or notice and ('已更新' in notice or '需求已更新' in notice):kind='recommend'
    cards=[];sources=[];facts=[];rows=[];actions=[];follow_up='';lead='';paragraphs=[]
    def cite(url,label,stamp=None,source_type='参数'):
        if not url:return None
        old=next((s for s in sources if s['url']==url and s['type']==source_type),None)
        if old:return old['id']
        sid='S{:02d}'.format(len(sources)+1);sources.append(dict(id=sid,url=url,label=label,observed_at=stamp,type=source_type));return sid
    def spec_stamp(p,url):
        with catalog.connect() as db:
            row=db.execute('SELECT MAX(collected_at) FROM catalog_specs WHERE product_id=? AND source_url=?',(p['id'],url)).fetchone()
        if row and row[0]:return row[0]
        if p.get('offer') and url==p['offer']['source_url']:return p['offer']['observed_at']
        return p.get('collected_at') if url==p['source_url'] else None
    def add_card(p,role='reference'):
        if not p or any(c['id']==p['id'] for c in cards):return
        card=brief(p,role);offer=p.get('offer')
        card['source_id']=cite(offer['source_url'],p['name']+' · '+offer['merchant'],offer['observed_at'],'报价') if offer else cite(p['source_url'],p['name']+' · 产品资料',p.get('collected_at'))
        if offer:card['quote_notice']='公开参考价，配置与库存仍需核对' if p.get('recommendation_tier')=='reference' else '二手报价，成色与保修需核对' if offer.get('item_condition')=='used' else '采集标价，最终支付请到原页核对'
        else:card['quote_notice']='没有有效报价，不确认符合预算'
        cards.append(card)
    def evidence(p,key):
        detail=p.get('metric_details',{}).get(key)
        if detail:
            sid=cite(detail.get('source_url'),p['name']+' · '+LABELS[key],spec_stamp(p,detail.get('source_url')))
            facts.append(dict(title=LABELS[key],value=detail['basis'],explanation=detail['rule'],known=True,source_id=sid))
        else:facts.append(dict(title=LABELS[key],value='暂无足够的可核对资料',explanation='未披露不等于不支持；这项暂不作为已确认的优势。',known=False,source_id=None))
    if kind=='confirm':
        lead='先确认一下预算，避免把你不想增加的支出算进去。'
        paragraphs=['当前上限是 '+money(profile['budget'])+'；你提出的新上限是 '+money(budget_proposal)+'。确认前仍按原预算筛选。']
        follow_up='要将预算调整为 '+money(budget_proposal)+' 吗？'
        actions=[dict(type='confirm_profile',label='确认调整至 '+money(budget_proposal)),dict(type='keep_profile',label='保持原预算')]
    elif kind in ('recommend','cheaper'):
        eligible=candidates
        if kind=='cheaper' and focus and focus['price'] is not None:eligible=sorted((p for p in candidates if p['id']!=focus['id'] and p['price']<focus['price']),key=lambda p:(p['price'],-p['score']))
        cards_to_show=eligible[:3]
        if cards_to_show:
            lead=('预算不变，可以先核对这几款采集价更低的候选。' if kind=='cheaper' else '先按 '+money(profile['budget'])+' 的硬上限，为你缩小到这几款。')
            paragraphs=['这些产品有价格依据且金额不超过预算；起售价、过期或待核价记录不会混进预算内推荐。']
            for p in cards_to_show:add_card(p,'candidate')
            focus=cards_to_show[0];peer=cards_to_show[1] if len(cards_to_show)>1 else peer
            follow_up='你更在意续航、便携，还是上手是否顺手？'
        else:
            lead='当前没有找到'+('比所选产品更便宜、又有有效报价的候选。' if kind=='cheaper' else '有有效价格依据且符合这次预算的候选。')
            paragraphs=['预算保持 '+money(profile['budget'])+'。可以核对具体配置报价，或明确告诉我可接受的新预算；不会自动提高上限。']
            if focus:add_card(focus,'reference')
            follow_up='你希望先核对当前产品的报价，还是换一种选购方向？'
    elif kind=='compare':
        if focus and peer:
            for p in (focus,peer):add_card(p)
            lead=focus['name']+' 和 '+peer['name']+'，可以先看与你的用途最相关的差别。'
            keys=sorted((k for k in ACTIVE[profile['category']] if k!='price' and profile['weights'][k]>0),key=lambda k:-profile['weights'][k])[:3]
            for key in keys:
                ds=[p.get('metric_details',{}).get(key) for p in (focus,peer)]
                rows.append(dict(label=LABELS[key],values=[d['basis'] if d else '未披露 / 待确认' for d in ds]))
                for p,d in zip((focus,peer),ds):
                    if d:cite(d.get('source_url'),p['name']+' · '+LABELS[key],spec_stamp(p,d.get('source_url')))
            for p in (focus,peer):paragraphs.append(p['name']+'：'+p['budget_status']+'。'+('可以继续核对所需配置。' if p['recommendation_eligible'] else '仅供比较，不属于预算内推荐。'))
            if focus['price'] is not None and peer['price'] is not None:paragraphs.append('两条报价相差 '+money(abs(focus['price']-peer['price']))+'，配置或套装可能不同，先统一版本再判断是否值得。')
            paragraphs.append('参数参考与偏好分不代表实测，续航、重量和亮度等还要核对测试条件。')
            actions.append(dict(type='compare',label='进入产品对比',product_ids=[focus['id'],peer['id']]))
            follow_up='你更愿意为哪一项差别做取舍？'
        else:lead='还需要另一款同品类产品，才能说明具体取舍。';follow_up='你想与哪一款比较？'
    elif kind in ('metric','explain','overview','budget','checklist') and focus:
        add_card(focus);lead='我们先围绕 '+focus['name']+' 来核对。'
        if not focus['recommendation_eligible']:paragraphs.append('当前'+focus['budget_status']+'，仅供了解，不属于本次预算内推荐。')
        if kind=='budget':
            if focus['price'] is not None:
                delta=profile['budget']-focus['price'];paragraphs.append('当前采集报价 '+money(focus['price'])+'；'+('比预算多 '+money(-delta)+'。预算是硬上限时，先不下单。' if delta<0 else '按这条报价计算，名义余额为 '+money(delta)+'，尚未计入配件和运费。'))
                if focus.get('recommendation_tier')=='reference':paragraphs.append('这是公开参考价，不能保证你所需配置实际可按这个金额购买。')
            else:paragraphs.append('尚无有效配置报价，所以现在不能确认它在预算内。卡片可查看资料和各平台查询入口。')
            from reporting import ACCESSORIES
            paragraphs.append('建议一起核对：'+ACCESSORIES[profile['category']]+'。未取得报价的配件暂不计算金额。')
            follow_up='哪些配件是你这次必须一起买的？'
        elif kind=='checklist':
            paragraphs=list(TIPS[profile['category']])+['先对照完整型号、配置、地区和配件，再确认店铺经营主体、发票、保修与退换条件。']
            if profile['scenario']=='老人使用':paragraphs.append('给长辈多留一步：一起试调大字号、通话音量、解锁与常用应用。')
            follow_up='你最担心使用体验，还是下单时的配置和售后？'
        else:
            keys=[k for k,pattern in METRIC_WORDS.items() if k!='price' and re.search(pattern,question)] if kind=='metric' else []
            if not keys:keys=sorted((k for k in ACTIVE[profile['category']] if k!='price' and profile['weights'][k]>0),key=lambda k:-profile['weights'][k])[:3]
            for key in keys[:3]:evidence(focus,key)
            paragraphs=['以下是已经查到的参数和对应边界，不能直接保证实际体验。']+paragraphs
            if focus.get('parameter_region_note'):paragraphs.append(focus['parameter_region_note'])
            follow_up='需要把它和另一款放在一起比较吗？'
    elif kind in ('metric','explain','overview','budget','checklist'):
        kind='clarify';lead='还没有确定本次要核对的产品。';follow_up='你想了解哪个具体型号？'
    else:
        kind='general'
        if re.search(r'内存.*存储|存储.*内存',question):lead='内存主要影响同时运行应用的余量，存储容量决定能保存多少文件。';paragraphs=['两者不能互相替代。选具体产品时还要核对系统、所用软件以及是否支持后期升级。'];follow_up='你想结合当前产品的具体配置看看吗？'
        elif re.search(r'你好|您好|你是谁|hello',question,re.I):lead='你好，我是你的 SmartBuy 选购助手。';paragraphs=['我会沿用当前预算和用途，帮你核对产品、解释取舍，也能把选择继续带到对比页与购买报告。'];follow_up='你想先看推荐理由，还是比较当前两款？'
        else:lead='可以继续聊。当前本地模式主要帮助核对产品资料与选购思路。';paragraphs=['连接大模型后，可以进一步讨论学习、生活和一般知识；未连接时不会伪装成已经完成模型回答。'];follow_up='要先围绕当前选购问题继续吗？'
    if focus and any(c['id']==focus['id'] for c in cards):actions.append(dict(type='report',label='为当前产品生成报告',product_id=focus['id'],compare_id=peer['id'] if peer else None))
    state_out=dict(version=2,focus_id=focus['id'] if focus else None,pair_ids=[p['id'] for p in (focus,peer) if p],last_intent=kind,pending_change=pending)
    snapshot={k:profile.get(k) for k in ('category','budget','scenario','needs')}
    suggestions=([focus['name']+'的续航信息有哪些？','它和另一款有什么区别？','换个便宜点的','买它之前要注意什么？'] if focus else ['按当前预算推荐几款','更看重续航，重新筛选','怎么核验报价与配置？'])
    response=dict(version=2,intent=kind,title={'compare':'把取舍说清楚','recommend':'按当前需求筛选','budget':'把预算算清楚','metric':'参数与使用边界','confirm':'确认预算调整','cheaper':'找价格更低的候选'}.get(kind,'一起核对这次选择'),
        lead=lead,paragraphs=paragraphs,facts=facts,products=cards,comparison_rows=rows,sources=sources,actions=actions,
        follow_up=follow_up,suggestions=suggestions,state=state_out,profile_update=update,context_snapshot=snapshot,
        context_update=dict(selected_id=focus['id'] if focus else None,pair_ids=state_out['pair_ids']),notice=notice,
        generated_at=datetime.now(timezone.utc).isoformat())
    response['answer']=plain_answer(response)
    return response

def plain_answer(turn):
    blocks=[turn['lead']]+turn['paragraphs']
    blocks += [f['title']+'：'+f['value']+'。'+f['explanation']+(' ['+f['source_id']+']' if f['source_id'] else '') for f in turn['facts']]
    blocks += [c['name']+'：'+money(c['price'])+'；'+c['budget_status']+'。'+c['quote_notice']+' ['+c['source_id']+']' for c in turn['products']]
    blocks += [r['label']+'：'+' / '.join(r['values']) for r in turn['comparison_rows']]
    if turn['follow_up']:blocks.append(turn['follow_up'])
    return '\n\n'.join(blocks)

def model_payload(turn):
    payload={k:turn[k] for k in ('intent','lead','paragraphs','facts','comparison_rows','sources','follow_up','context_snapshot')}
    payload['products']=[{k:p.get(k) for k in ('id','name','price','offer','budget_status','recommendation_eligible','recommendation_tier','parameter_region_note')} for p in turn['products']]
    return payload

def checked_model(raw,turn):
    """Keep actions/cards authoritative. Reject ungrounded IDs, prices and claims."""
    if turn['intent']=='general':
        if not isinstance(raw,str) or not raw.strip():raise ValueError('模型没有返回有效文字')
        return raw.strip()[:6000],''
    try:value=json.loads(raw)
    except (ValueError,TypeError):raise ValueError('模型未按有据回答格式返回，已改用本地资料核对')
    if not isinstance(value,dict):raise ValueError('模型回答格式无效，已改用本地资料核对')
    answer=value.get('answer');refs=value.get('source_ids');ids=value.get('product_ids')
    if not isinstance(answer,str) or not answer.strip() or len(answer)>6000:raise ValueError('模型回答文字无效')
    allowed_refs={s['id'] for s in turn['sources']};allowed_ids={p['id'] for p in turn['products']}
    if not isinstance(refs,list) or any(type(s) is not str or s not in allowed_refs for s in refs):raise ValueError('模型引用了未检索的来源，已使用本地核对结果')
    if not isinstance(ids,list) or any(type(i) is not int or i not in allowed_ids for i in ids):raise ValueError('模型引用了未核对产品，已使用本地核对结果')
    embedded=set(re.findall(r'\[(S\d+)\]',answer))
    if embedded-set(refs) or (turn['sources'] and not embedded):raise ValueError('模型缺少可核对的引用，已使用本地结果')
    if turn['intent'] in ('recommend','cheaper') and allowed_ids and not ids:raise ValueError('模型未说明所用候选，已使用本地结果')
    # Numerical claims stay in the server's verified cards, never in generated prose.
    without_names=answer
    for p in sorted(turn['products'],key=lambda p:-len(p['name'])):without_names=without_names.replace(p['name'],'')
    without_refs=re.sub(r'\[S\d+\]','',without_names)
    if re.search(r'\d|[¥￥$]|[零一二三四五六七八九十百千万两]+(?:元|块)',without_refs):raise ValueError('模型包含额外数值，金额与参数已改用核对卡片呈现')
    with catalog.connect() as db:
        known=[dict(r) for r in db.execute("SELECT id,name,brand FROM catalog_products WHERE validation_status='verified'")]
    for item in mentioned(answer,known):
        if item['id'] not in allowed_ids:raise ValueError('模型提到了未检索的产品，已使用本地结果')
    if re.search(r'保证|全网最低|实时最低|百分之百|一定(?:更|适合|不会)|绝对|已替你下单',answer):raise ValueError('模型含未经证实的承诺，已使用本地核对结果')
    if any(not fact['known'] for fact in turn['facts']):
        claims=re.sub(r'未披露不等于不支持|未知不等于不支持|不代表不支持|不能据此认为不支持|是否支持|尚不能确认支持','',answer)
        if re.search(r'不支持|不具备|支持简易模式|自带长辈模式',claims):raise ValueError('模型把未知信息写成确定能力，已使用本地核对结果')
    if not any(p['recommendation_eligible'] for p in turn['products']) and re.search(r'预算内首选|确认在预算内|放心下单',answer):raise ValueError('模型结论不符合预算约束，已使用本地结果')
    for p in turn['products']:
        if p['recommendation_eligible']:continue
        name=re.escape(p['name'])
        if re.search(r'(?<!不)(?<!不能)(?:推荐|首选|优先考虑)\s*'+name,answer) or re.search(name+r'.{0,8}(?:是首选|最推荐|最值得买)',answer):raise ValueError('模型推荐了未通过预算核对的产品，已使用本地结果')
    follow=value.get('follow_up')
    if follow is not None and (not isinstance(follow,str) or len(follow)>180 or follow.count('？')+follow.count('?')>1):raise ValueError('模型追问格式不合适，已使用本地结果')
    if follow:
        follow_check=follow
        for p in turn['products']:follow_check=follow_check.replace(p['name'],'')
        if re.search(r'\d|[¥￥$]|[零一二三四五六七八九十百千万两]+(?:元|块)',follow_check):raise ValueError('模型追问含额外金额或数值，已使用本地追问')
    return answer.strip(),follow
