"""Explainable parameter-based preference scoring. No fabricated benchmarks or tie noise."""
import re

ACTIVE = {
    '手机': ('performance','price','battery','portability','ease','camera','screen'),
    '电脑': ('performance','price','battery','portability','ease','screen'),
    '平板': ('performance','price','battery','portability','ease','screen'),
    '耳机': ('performance','price','battery','portability','ease'),
    '相机': ('performance','price','battery','portability','ease','camera','screen'),
}
RULE_VERSION='marketplace-budget-v4'
ELDER_WEIGHTS=dict(performance=2,price=30,battery=25,portability=8,ease=25,camera=0,screen=10)


def is_elder_scenario(scenario='', needs=''):
    if scenario in ('老人使用','学习','游戏','办公'): return scenario=='老人使用'
    return bool(re.search(r'父母|长辈|老人|老年|爸爸|妈妈',needs))


def scenario_weights(scenario='', needs=''):
    return dict(ELDER_WEIGHTS if is_elder_scenario(scenario,needs) else
                dict(performance=22,price=23,battery=14,portability=12,ease=12,camera=7,screen=10))


def clamp(value): return max(0,min(100,value))


def extract_facts(specs, category):
    facts={}
    def pick(key, labels, patterns, unit, low, high, convert=lambda v:v):
        # Prefer named fields; PDF pages are a fallback with their original qualifiers.
        rows=[s for s in specs if re.search(labels,s['label'],re.I)]
        if not rows: rows=[s for s in specs if s['section']=='PDF 官方规格' or s['label'].lower()=='specifications']
        for row in rows:
            text=row['value']
            if key=='weight' and category=='耳机':
                ear=re.search(r'(?:耳机|earbuds?)\s*[:：]',text,re.I)
                if ear: text=text[ear.end():]
                case=re.search(r'充电盒|charging case|MagSafe',text,re.I)
                if case and case.start()>0: text=text[:case.start()]
            if row['section']=='PDF 官方规格':
                context=re.search(r'(?:^|\n)\s*(?:Memory|内存)\b' if key=='memory' else labels,text,re.I)
                if not context: continue
                text=text[context.start():context.start()+650]
            values=[]
            for pattern in patterns:
                for match in re.finditer(pattern,text,re.I):
                    if re.search(r'±\s*$',text[max(0,match.start()-5):match.start()]): continue
                    value=convert(float(match.group(1).replace(',','')))
                    if low<=value<=high: values.append(value)
                if values: break
            if values:
                lo,hi=min(values),max(values)
                optional=bool(re.search(r'up to|可选配|最高可|最大可',text,re.I))
                facts[key]={'value':lo,'max':hi,'unit':unit,'label':row['label'],
                            'source_url':row['source_url'],'text':row['value'][:500],
                            'display':('可选 / 上限 ' if optional else '')+('{:g}'.format(lo) if lo==hi else '{:g}–{:g}'.format(lo,hi))+' '+unit,
                            'qualifier':'包含最高或可选配置，并非默认配置' if optional else '原文含不同配置或使用模式，需核对具体条件' if lo!=hi else '保留官网测试及配置条件'}
                return
    pick('weight',r'重量|weight|mass|尺寸|dimension',[
        r'(?:重量|Weight|Mass)\s*[:：]?\s*(?:约|Approx\.?|Starting at|From)?\s*([\d.]+)\s*(?:千克|kg|kilograms)',
    ],'g',1,5000,lambda v:v*1000)
    if 'weight' not in facts:
        pick('weight',r'重量|weight|mass|尺寸|dimension',[
            r'(?:重量|Weight|Mass|Weight of a single earbud)\s*[:：]?\s*(?:约|Approx\.?|Starting at|From)?\s*([\d.]+)\s*(?:克|g\b|grams)',
            r'(?:约|Approx\.?)?\s*([\d.]+)\s*(?:克|g\b|grams)',
        ],'g',1,5000)
    pick('battery_mah',r'电池|续航|battery|charging', [r'([\d,]+(?:\.\d+)?)\s*mAh'], 'mAh',20,20000)
    pick('battery_hours',r'电源|电池|续航|battery|power|specifications',[
        r'(?:最长可达|最长|up to|maximum|Max\.?)\s*([\d.]+)\s*(?:小时|hours|hrs|h\b)',
        r'(?:single charge|单次充电|单次续航|播放时间)[^\d]{0,55}([\d.]+)\s*(?:小时|hours|hrs|h\b)',
    ],'小时',1,100)
    if category in ('手机','电脑','平板'):
        pick('memory',r'内存|memory|RAM', [r'(\d+(?:\.\d+)?)\s*GB(?:\s*(?:RAM|LPDDR|统一内存))?'], 'GB',2,128 if category=='电脑' else 32)
    pick('cpu_cores',r'芯片|处理器|chip|processor',[
        r'(\d+)\s*核(?:中央处理器|\s*CPU)',r'(\d+)[ -]core\s*CPU',
    ],'核',2,64)
    if category in ('手机','电脑','平板'):
        pick('screen_inches',r'屏幕|显示|display|screen',[
            r'(\d+(?:\.\d+)?)\s*(?:英寸|吋|inches|inch\b|[‐-]inch\b)',
        ],'英寸',4,35)
        pick('refresh',r'屏幕|显示|display|screen',[
            r'(?:刷新率|Refresh rate)[^\d]{0,30}(?:\d+\s*[-–~]\s*)?(\d+(?:\.\d+)?)\s*Hz',
            r'(\d+(?:\.\d+)?)\s*Hz',
        ],'Hz',30,360)
    pick('camera_mp',r'有效像素|摄像|主摄|camera|rear|image sensor',[
        r'([\d.]+)\s*MP',r'([\d.]+)\s*megapixels',
    ],'MP',2,250)
    if 'camera_mp' not in facts:
        pick('camera_mp',r'有效像素|摄像|主摄|camera', [r'([\d.]+)\s*万(?:像素)?'], 'MP',2,250,lambda v:v/100)
    pick('burst',r'连拍|连续拍摄|continuous shooting|burst',[
        r'([\d.]+)\s*(?:张/秒|张／秒|fps|frames per second)',
    ],'张/秒',1,200)
    return facts


def parameter_scores(product, specs, weights, budget, needs, scenario=''):
    category=product['category'];facts=extract_facts(specs,category)
    offer=product.get('offer')
    if category in ('手机','电脑','平板') and offer and offer.get('price_basis','direct')=='direct' and offer['price_type']=='配置报价':
        ram=re.search(r'(\d+(?:\.\d+)?)\s*GB\s*\+\s*\d+\s*(?:GB|TB)',offer['variant'],re.I)
        if ram:
            value=float(ram.group(1))
            facts['memory']=dict(value=value,max=value,unit='GB',label='当前报价配置 RAM',source_url=offer['source_url'],
                                 text=offer['variant'],display='{:g} GB'.format(value),qualifier='仅对应本次报价的具体配置，不取系列最高可选内存')
    elder=category=='手机' and is_elder_scenario(scenario,needs)
    metrics={k:None for k in weights};details={};active=ACTIVE[category]
    def numeric(metric, fact, low, high, lower=False):
        if fact not in facts: return
        value=facts[fact]['max'] if fact in ('burst','refresh') else facts[fact]['value']
        ratio=clamp((value-low)/(high-low)*100)
        score=100-ratio if lower else ratio
        metrics[metric]=round(30+score*.7,2)
        details[metric]={'basis':facts[fact]['display'],'rule':('越轻便携参考分越高' if lower else '按标注最高档位计算，具体模式及配置需核对' if fact in ('burst','refresh') else '按本类产品预设区间换算参考分'),
                         'source_url':facts[fact]['source_url'],'fact':fact}
    if category in ('手机','电脑','平板'):
        numeric('performance','memory',4,8 if elder else 32 if category=='电脑' else 16)
        if elder and 'memory' in facts:
            details['performance']['rule']='日常配置余量在 8GB 封顶，不因旗舰核心数继续加分；不代表系统流畅度实测'
        if 'cpu_cores' in facts and not elder:
            core=30+clamp((facts['cpu_cores']['value']-2)/14*100)*.7
            metrics['performance']=round((metrics['performance']+core)/2 if metrics['performance'] is not None else core,2)
            details['performance']={'basis':' / '.join(facts[k]['display'] for k in ('memory','cpu_cores') if k in facts),
                                    'rule':'内存和核心数仅作配置余量参考，不等同跨架构跑分','source_url':facts['cpu_cores']['source_url']}
    if category=='相机': numeric('performance','burst',3,40)
    numeric('camera','camera_mp',12,60 if category=='相机' else 108)
    limits={'手机':(140,300),'电脑':(900,3000),'平板':(280,900),'耳机':(3,400),'相机':(300,1300)}
    numeric('portability','weight',*limits[category],lower=True)
    if 'weight' in facts and facts['weight']['max']!=facts['weight']['value']:
        # Portability is conservative too: use the heavier listed configuration.
        lo,hi=limits[category];metrics['portability']=round(30+(100-clamp((facts['weight']['max']-lo)/(hi-lo)*100))*.7,2)
    if category in ('电脑','耳机') or 'battery_mah' not in facts:
        numeric('battery','battery_hours',3,24 if category=='电脑' else 30)
    else: numeric('battery','battery_mah',2500 if category=='手机' else 4000,7000 if category=='手机' else 12000)
    if elder:
        numeric('screen','screen_inches',5.5,6.7)
        if 'screen' in details: details['screen']['rule']='按标注屏幕尺寸估计阅读空间，6.7 英寸封顶；字号、清晰度与握持须本人试用'
    else: numeric('screen','refresh',60,144)
    body='\n'.join(s['label']+' '+s['value'] for s in specs)
    features=[('USB-C',r'USB[ -]?(?:Type[ -]?)?C|Type-C'),('蓝牙',r'Bluetooth|蓝牙'),
              ('无线网络',r'Wi-Fi|WiFi|无线局域网'),('辅助功能',r'辅助功能|accessibility'),
              ('NFC',r'\bNFC\b'),('手写笔',r'Apple Pencil|手写笔|stylus'),
              ('降噪',r'主动降噪|active noise cancel'),('环境音',r'通透|环境音|transparency'),
              ('多点连接',r'多点连接|multipoint'),('空间音频',r'空间音频|spatial audio')]
    hits=[]
    for label,pattern in features:
        for s in specs:
            text=s['label']+' '+s['value']
            if re.search(pattern,text,re.I) and not re.search(r'不支持|不具备|not supported|unsupported|^No\b',s['value'],re.I):
                hits.append(label);break
    elder_features=[('字体与显示调节',r'大字|字体大小|大字体|显示大小|字号|large (?:text|font)|text size|font size|text scaling'),
                    ('简易模式',r'简易模式|简易桌面|简易界面|简单模式|长辈模式|老人模式|easy mode|simple mode|assistive access|辅助访问'),
                    ('语音与朗读辅助',r'语音控制|语音助手|朗读|屏幕阅读|voice control|voice assistant|talkback|voiceover|screen reader|spoken content'),
                    ('紧急与听视辅助',r'紧急呼叫|紧急联系人|紧急求助|\bSOS\b|助听器|hearing aid|高对比度|放大器')]
    elder_hits=[]
    for label,pattern in elder_features:
        if any(re.search(pattern,part,re.I) and not re.search(r'不支持|不具备|not supported|unsupported|\bno\b',part,re.I)
               for s in specs for part in re.split(r'[。；;\n]',s['label']+' '+s['value'])):
            elder_hits.append(label)
    if elder:
        if elder_hits:
            metrics['ease']=min(95,35+15*len(elder_hits))
            details['ease']={'basis':'、'.join(elder_hits),'rule':'仅按明确记载的长辈相关辅助功能计分，未记载不推断支持；不以 NFC、蓝牙或功能总数替代易用性','source_url':product['source_url']}
    elif hits:
        metrics['ease']=round(min(94,40+len(hits)*7.5),2)
        details['ease']={'basis':'、'.join(hits),'rule':'已明确记载的连接和辅助功能覆盖；平台兼容性仍需确认','source_url':product['source_url']}
    if category=='耳机' and hits:
        audio=[h for h in hits if h in ('降噪','环境音','多点连接','空间音频')]
        if audio:
            metrics['performance']=min(94,42+len(audio)*13)
            details['performance']={'basis':'、'.join(audio),'rule':'已记录音频功能数量，不是音质或降噪实测','source_url':product['source_url']}
    price=product['price'];offer=product['offer'];is_reference=offer and offer.get('price_basis')=='listing'
    is_start=offer and offer['price_type']!='配置报价' and not is_reference
    if price is not None and not (is_start and price<=budget):
        metrics['price']=round(clamp(85+15*(1-price/budget)) if price<=budget else clamp(85-(price-budget)/budget*160),2)
        if is_reference: metrics['price']=round(metrics['price']*.75,2)
        details['price']={'basis':'¥{:,.0f} / 预算 ¥{:,.0f}'.format(price,budget),'rule':'预算内按剩余空间得到85–100分；预算外只能对比，不能进入推荐','source_url':offer['source_url']}
        if is_reference: details['price']['rule']='平台公开参考价，预算分按75%计入；容量、成色、库存和优惠条件尚需核对'
    known=[k for k in active if metrics[k] is not None and weights.get(k,0)>0]
    all_weight=sum(weights.get(k,0) for k in active)
    known_weight=sum(weights[k] for k in known)
    coverage=known_weight/all_weight if all_weight else 0
    # Missing evidence cannot raise a score by shrinking its denominator.
    base=sum(metrics[k]*weights[k] for k in known)/all_weight if all_weight else 0
    requested=[(word,pattern) for word,pattern in [('降噪',r'主动降噪|active noise cancel'),('手写',r'手写笔|Pencil|stylus'),
        ('游戏',r'光线追踪|ray tracing|独立显卡|GeForce|Adreno'),('拍照',r'光学防抖|OIS|防抖'),
        ('编程',r'内存|memory|RAM'),('续航',r'电池|battery'),('轻便',r'重量|weight|mass')]
        if word in needs]
    matched=[w for w,pattern in requested if re.search(pattern,body,re.I)]
    if elder:
        requested += [(label,pattern) for label,pattern in elder_features
                      if (label=='字体与显示调节' and re.search(r'字体|字号|大字',needs)) or
                         (label=='简易模式' and re.search(r'简单|简易|好操作',needs))]
        matched += [label for label,_ in requested if label in elder_hits and label not in matched]
    fit=55+40*len(matched)/len(requested) if requested else 70
    penalty=min(25,max(0,(price-budget)/budget)*25) if price is not None else 0
    score=round(clamp(base*.86+fit*.14*coverage-penalty),2)
    return dict(metrics=metrics,metric_details=details,facts=facts,score=score,
                confidence=round(coverage*100,1),matched_needs=matched,scoring_version=RULE_VERSION,
                score_note='按同地区配置标价或已标明条件的公开参考价匹配预算，再按场景排序。参考价的预算分折减，配置与库存须核对。缺失维度不获加分，数值仍留空；系列参数取保守值，同分保留。'+
                           ('长辈手机优先续航、辅助功能与阅读空间，性能余量封顶；字体、音量与操作体验需试用。' if elder else ''))
