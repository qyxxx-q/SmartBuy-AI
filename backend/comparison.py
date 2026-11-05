"""Source-preserving comparison shared by the page, reports and assistant."""
import re
import unicodedata
from collections import OrderedDict
from flask import Blueprint, jsonify, request
import catalog
from recommendations import recommendation

comparison_api = Blueprint('comparison', __name__)
GROUPS = [('基本信息', r'主体|基本|上市|产品名称|品牌|型号|系统|兼容|包装|配件'),
          ('核心配置', r'CPU|GPU|处理|芯片|内存|存储|容量|硬盘|显卡|配置|processor|memory|chip'),
          ('屏幕与显示', r'显示|屏幕|分辨率|刷新|亮度|色域|触控|screen|display'),
          ('影像与声音', r'摄像|视频|拍摄|传感器|影像|镜头|像素|音频|声音|降噪|声学|扬声|麦克风|camera|audio'),
          ('续航与充电', r'电池|续航|充电|battery|power'),
          ('尺寸与便携', r'尺寸|重量|高度|宽度|厚度|weight|dimension'),
          ('连接与功能', r'网络|连接|接口|蓝牙|WLAN|Wi-Fi|NFC|SIM|定位|生物|识别|防护|防水|传输|功能')]

def normalized(value):
    # Keep qualifiers, model numbers, test conditions and regions. Cosmetic only.
    return re.sub(r'\s+', '', unicodedata.normalize('NFKC', value or '')).casefold()

def group_name(spec):
    text=spec['section']+' '+spec['label']
    # Battery capacity belongs to battery, not general storage capacity.
    for title in ('续航与充电','尺寸与便携','屏幕与显示','影像与声音'):
        pattern=dict(GROUPS)[title]
        if re.search(pattern,text,re.I): return title
    return next((name for name,pattern in GROUPS if re.search(pattern,text,re.I)), '其他官方参数')

def compare_products(a, b):
    if a['id']==b['id']: raise ValueError('请选择两款不同产品')
    if a['category']!=b['category']: raise ValueError('请选择同一品类的两款产品')
    ids=(a['id'],b['id']); cells=OrderedDict()
    for side,p in enumerate((a,b)):
        with catalog.connect() as db:
            specs=[dict(r) for r in db.execute('SELECT section,label,value,source_url,collected_at FROM catalog_specs WHERE product_id=? ORDER BY id',(p['id'],))]
        for spec in specs:
            group=group_name(spec);key=(group,normalized(spec['label']))
            if key not in cells: cells[key]={'label':spec['label'],'group':group,'values':[None,None]}
            value=cells[key]['values'][side]
            if value:
                value['value']+='\n'+spec['value']
            else: cells[key]['values'][side]=spec.copy()
    groups=[];counts=dict(same=0,different=0,unknown=0,total=0)
    for name in [g[0] for g in GROUPS]+['其他官方参数']:
        rows=[]
        for row in cells.values():
            if row['group']!=name:continue
            values=row['values']
            state='unknown' if any(v is None or not v['value'].strip() for v in values) else 'same' if normalized(values[0]['value'])==normalized(values[1]['value']) else 'different'
            row.update(state=state);rows.append(row);counts[state]+=1;counts['total']+=1
        if rows: groups.append({'id':'spec-group-'+str(len(groups)), 'name':name,'rows':rows})
    advantages=[[],[]]
    for key,label in [('price','预算余量'),('battery','续航参数'),('portability','便携参数'),('performance','性能参数'),('ease','操作与兼容'),('camera','影像参数'),('screen','屏幕参数')]:
        av=a.get('metrics',{}).get(key);bv=b.get('metrics',{}).get(key)
        if av is None or bv is None or abs(av-bv)<.5: continue
        side=0 if av>bv else 1;p=(a,b)[side]
        detail=p.get('metric_details',{}).get(key,{})
        advantages[side].append({'metric':key,'label':label,'basis':detail.get('basis',''),'rule':detail.get('rule','')})
    decision=[]
    for side,p in enumerate((a,b)):
        items=advantages[side][:3]
        headline='优先考虑 '+p['name']+'，如果你更关注'+('、'.join(x['label'] for x in items) if items else '它的具体配置、系统和使用习惯')+'。'
        if not p.get('recommendation_eligible'):headline+='当前'+p.get('budget_status','待核价')+'，仅供比较。'
        decision.append({'product_id':p['id'],'text':headline,'advantages':items})
    cautions=['“差异”表示官方原文不同，不自动判定谁更好；未知项不等于不支持。',
              '亮度、续航、重量等需保留配置与测试条件；多维分值是当前偏好的规则分，不是实测结果。']
    if a.get('subcategory')!=b.get('subcategory'):cautions.insert(0,'这两款属于不同细分类别，请先确认形态和用途能否互相替代。')
    if a.get('region')!=b.get('region'):cautions.insert(0,'参数地区不同，请特别核对网络、配件与保修。')
    for p in (a,b):
        if p.get('parameter_region_note'):cautions.append(p['name']+'：'+p['parameter_region_note'])
    return dict(product_ids=list(ids),groups=groups,counts=counts,decisions=decision,cautions=cautions)

@comparison_api.route('/api/compare',methods=['POST'])
def compare():
    data=request.get_json(silent=True) or {}
    try:
        ids=data.get('product_ids')
        if not isinstance(ids,list) or len(ids)!=2 or any(type(i) is not int for i in ids):raise ValueError('请选择两款产品')
        products=recommendation(data,include_unqualified=True)
        pair=[next((p for p in products if p['id']==i),None) for i in ids]
        if any(p is None for p in pair):raise ValueError('所选产品不在当前品类或筛选范围')
        return jsonify(compare_products(*pair))
    except (ValueError,TypeError) as exc:return jsonify(error=str(exc)),400
