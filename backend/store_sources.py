"""Decode public store data as literals; never execute page scripts or guess prices."""
import json
import re
import subprocess
from pathlib import Path
from urllib.parse import urlparse

ROOT=Path(__file__).resolve().parent


def nuxt_state(html):
    result=subprocess.run(['node',str(ROOT/'decode_store_state.cjs')],input=html.encode('utf-8'),
                          stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=15)
    if result.returncode: raise ValueError('商城公开数据无法解析：'+result.stderr.decode('utf-8',errors='replace')[:150])
    return json.loads(result.stdout.decode('utf-8'))


def walk(value):
    if isinstance(value,dict):
        yield value
        for item in value.values(): yield from walk(item)
    elif isinstance(value,list):
        for item in value: yield from walk(item)


def discover_oppo(html):
    sources={}
    for obj in walk(nuxt_state(html)):
        url=str(obj.get('url','')).strip()
        if obj.get('name') and re.fullmatch(r'https://www\.opposhop\.cn/cn/web/products/\d+\.html(?:\?.*)?',url):
            url=url.split('?')[0]
            sources[url]={'name':obj['name'],'url':url}
    return list(sources.values())


def oppo_product(html, expected_name=None, expected_sku=None):
    data=nuxt_state(html).get('data',[])
    p=next((x.get('resData') for x in data if isinstance(x,dict) and isinstance(x.get('resData'),dict)),None)
    if not p or not p.get('goodsSkuId') or not p.get('goodsSpuName'): raise ValueError('商品不存在或没有完整商品数据')
    name=p['goodsSpuName'].strip()
    normalize=lambda s:re.sub(r'[^\w]','',s).lower().replace('oneplus','一加')
    if expected_name and normalize(expected_name)!=normalize(name): raise ValueError('商品型号不一致')
    if expected_sku and str(p['goodsSkuId'])!=str(expected_sku): raise ValueError('商品 SKU 不一致')
    category=('平板' if re.search(r'\bPad\b|平板',name,re.I) else '耳机' if re.search(r'Enco|Buds|耳机',name,re.I)
              else '手机' if '手机' in str(p.get('goodsTopCategoryName','')) or name.startswith(('一加 ','OnePlus ')) else None)
    if not category: raise ValueError('当前范围不包含此类配件或穿戴产品')
    specs=[]
    for group in p.get('baseAttributes') or []:
        for attribute in group.get('attributes',[]):
            values=attribute.get('value') or []
            if not isinstance(values,list): values=[values]
            if attribute.get('name') and values:
                specs.append(dict(section=group['groupName'],label=attribute['name'],value='；'.join(str(v) for v in values)))
    sku=next((x for x in (p.get('attributes') or {}).get('skuItems',[]) if str(x.get('skuId'))==str(p['goodsSkuId'])),None)
    if not sku: raise ValueError('当前配置与SKU清单不匹配')
    ram=re.search(r'(\d+)\s*GB\s*\+',str(sku.get('key2','')),re.I)
    if ram: specs.append(dict(section='当前报价配置',label='运行内存 RAM',value=ram.group(1)+' GB；当前配置 '+sku['key2']))
    if len(specs)<3: raise ValueError('缺少完整官方规格')
    # buyPrice/price at the root include coupons or subsidies. Use the unconditional full price.
    amount=(p.get('priceTag') or {}).get('price')
    if not amount: raise ValueError('没有与当前SKU绑定的公开全额标价')
    amount=float(amount)
    if amount<=0: raise ValueError('公开价格无效')
    return dict(name=name,brand='一加' if name.startswith(('一加','OnePlus')) else 'OPPO',category=category,
                specs=specs,sku=str(p['goodsSkuId']),variant=p['name'],amount=amount,
                available=sku.get('stock') is True and p.get('visible')==1,
                conditional_price=(p.get('priceTag') or {}).get('buyPrice'))
