"""Shared purchase requirement parsing for recommendations and conversation."""
import re
from scoring import scenario_weights


def explicit_budget(text):
    match=re.search(r'(?:预算|上限|不超过|最多)\s*[约为是:：]*\s*(\d+(?:\.\d+)?)\s*(万|千|[kK]|元|块)?',text)
    if not match: match=re.search(r'(\d+(?:\.\d+)?)\s*(万|千|[kK]|元|块)',text)
    if not match:return None
    return float(match.group(1))*{'万':10000,'千':1000,'k':1000,'K':1000,'元':1,'块':1,None:1}[match.group(2)]


def local_profile(text):
    text = str(text or '').strip()
    if not text:
        raise ValueError('请描述你的购买需求')
    category = next((c for c, words in [('耳机', ['耳机','降噪','耳塞']), ('相机', ['相机','单反','微单']), ('电脑', ['电脑','笔记本','编程','剪辑','游戏本']), ('平板', ['平板','手写','网课']), ('手机', ['手机','拍照','通话','折叠屏'])] if any(w in text for w in words)), '手机')
    subcategory = None
    if category=='手机' and '折叠' in text: subcategory='折叠屏手机'
    if category=='电脑':
        if any(w in text for w in ('游戏本','游戏笔记本','电竞本')): subcategory='游戏笔记本'
        elif any(w in text for w in ('台式','主机','桌面电脑')): subcategory='台式电脑'
        elif any(w in text for w in ('商务本','商务笔记本')): subcategory='商务笔记本'
    if category=='平板' and any(w in text for w in ('小尺寸','小平板','mini')): subcategory='小尺寸平板'
    if category=='耳机':
        if '头戴' in text: subcategory='头戴式耳机'
        elif any(w in text for w in ('开放式','不入耳','耳夹')): subcategory='开放式耳机'
    if category=='相机':
        if any(w in text for w in ('全画幅','全幅')): subcategory='全画幅微单'
        elif any(w in text.lower() for w in ('aps-c','半画幅','残幅')): subcategory='APS-C微单'
    amount=explicit_budget(text)
    budget=amount if amount is not None else (6000 if category=='电脑' else 3500)
    if not 1<=budget<=50000:raise ValueError('预算必须在 1–50000 元之间')
    budget=int(budget) if budget==int(budget) else round(budget,2)
    scenario = next((s for s, words in [('老人使用',['老人','父母','长辈','老年']),('游戏',['游戏','电竞','高帧']),('学习',['学生','学习','编程','网课','笔记']),('办公',['办公','商务','工作','剪辑'])] if any(w in text for w in words)), '办公')
    user_type = '长辈' if scenario == '老人使用' else '学生' if scenario == '学习' else '专业用户' if any(w in text for w in ['专业','设计','剪辑','开发']) else '普通用户'
    weights = scenario_weights(scenario,text)
    boosts = {'轻便':'portability','轻薄':'portability','续航':'battery','电池':'battery','性能':'performance','游戏':'performance','拍照':'camera','摄影':'camera','屏幕':'screen','大字':'ease','简单':'ease','便宜':'price','性价比':'price'}
    for word, metric in boosts.items():
        if word in text:
            weights[metric] += 15
    if scenario == '学习':
        weights['price'] += 8; weights['portability'] += 7
    if scenario == '游戏':
        weights['performance'] += 18; weights['screen'] += 10
    total = sum(weights.values())
    weights = {k:round(v*100/total, 1) for k,v in weights.items()}
    used=bool(re.search(r'二手|闲鱼|咸鱼|翻新',text)) and not bool(re.search(r'不要二手|不接受二手|只要全新|必须全新',text))
    return {'needs':text[:1000],'category':category,'subcategory':subcategory,'budget':budget,'scenario':scenario,'user_type':user_type,'weights':weights,'include_used':used,'include_reference':True,'summary':f'{user_type}，预算约 ¥{budget:,}，主要用于{scenario}。','source':'本地规则'}


