"""Official current search-list configurations and clearly labeled display prices."""
import hashlib
import argparse
import json
import re
from urllib.parse import urlencode
from datetime import datetime,timezone
from pathlib import Path
import requests
from bs4 import BeautifulSoup
from catalog import ROOT,connect,init_catalog
from marketplace_quotes import save_offers

URL='https://s.lenovo.com.cn/search/?key=%E5%B0%8F%E6%96%B0'


def parse_products(html):
    soup=BeautifulSoup(html,'html.parser');products=[]
    for row in soup.select('.productDetailUl > li'):
        title=row.select_one('.search_name a');config=row.select_one('.search_mes a')
        if not title or not config:continue
        name=title.get_text(' ',strip=True);text=config.get_text(' ',strip=True);link=title.get('href','')
        sku=re.fullmatch(r'https://item\.lenovo\.com\.cn/product/(\d+)\.html',link)
        if not sku or not any(w in name for w in ('笔记本','轻薄本','游戏本','电脑','一体机')):continue
        if any(w in name for w in ('内胆包','支架','套装配件','鼠标','电源','贴膜')):continue
        price=re.search(r'[¥￥]\s*([\d,]+(?:\.\d+)?)',row.get_text(' ',strip=True))
        if not price:continue
        parts=[s.strip() for s in re.split(r'[/丨|]',text) if s.strip()]
        specs=[dict(section='官网商城当前列表',label='完整配置原文',value=text)]
        for label,pattern in [('处理器',r'Intel|英特尔|AMD|锐龙|酷睿'),('操作系统',r'Windows|Linux'),('屏幕',r'英寸'),
                              ('内存',r'^\d+\s*(?:GB|G)(?:[（(].*)?$'),('硬盘',r'SSD|硬盘'),('显卡',r'显卡|RTX|GTX|Radeon')]:
            value=next((s for s in parts if re.search(pattern,s,re.I)),None)
            if value:
                if label=='内存':value=re.sub(r'^(\d+)\s*G\b',r'\1 GB',value,flags=re.I)
                specs.append(dict(section='官网商城当前列表',label=label,value=value))
        if len(specs)<3:continue
        products.append(dict(name=name+' · '+sku.group(1),sku=sku.group(1),variant=name+'；'+text,amount=float(price.group(1).replace(',','')),
                             specs=specs,purchase_url=link,subcategory='一体电脑' if '一体' in name else '台式电脑' if '台式' in name else
                             '游戏笔记本' if re.search(r'游戏|拯救者|电竞|Legion|LOQ',name,re.I) else '轻薄笔记本'))
    return products


def main():
    global URL
    parser=argparse.ArgumentParser();parser.add_argument('--snapshot');parser.add_argument('--keyword',default='小新');args=parser.parse_args()
    URL='https://s.lenovo.com.cn/search/?'+urlencode({'key':args.keyword})
    init_catalog()
    if args.snapshot:
        path=Path(args.snapshot)
        stamp=datetime.fromtimestamp(path.stat().st_mtime,timezone.utc).isoformat(timespec='seconds')
        html=path.read_text(encoding='utf-8')
    else:
        response=requests.get(URL,timeout=25,headers={'User-Agent':'SmartBuyResearch/1.0'});response.raise_for_status()
        response.encoding='utf-8';html=response.text;stamp=datetime.now(timezone.utc).isoformat(timespec='seconds')
    products=parse_products(html)
    digest=hashlib.sha256(html.encode('utf-8')).hexdigest();folder=ROOT/'data'/'store_snapshots';folder.mkdir(exist_ok=True)
    snapshot=folder/(digest+'.html');snapshot.write_bytes(html.encode('utf-8'))
    logs=[]
    for p in products:
        source=URL+'#sku='+p['sku']
        with connect() as db:
            existing=db.execute('SELECT id FROM catalog_products WHERE source_url=?',(source,)).fetchone()
            if existing:
                pid=existing['id'];db.execute('DELETE FROM catalog_specs WHERE product_id=?',(pid,))
                db.execute('UPDATE catalog_products SET collected_at=?,content_sha256=?,snapshot_path=?,spec_count=? WHERE id=?',(stamp,digest,str(snapshot.relative_to(ROOT)),len(p['specs']),pid))
            else:
                pid=db.execute('''INSERT INTO catalog_products(name,brand,category,region,source_url,source_title,collected_at,content_sha256,snapshot_path,spec_count,subcategory,validation_note)
                                  VALUES(?,'联想','电脑','中国大陆',?,'联想商城当前搜索列表',?,?,?,?,?,'官方列表原文，完整规格和库存仍需在具体商品页核对')''',
                               (p['name'],source,stamp,digest,str(snapshot.relative_to(ROOT)),len(p['specs']),p['subcategory'])).lastrowid
            db.executemany('INSERT INTO catalog_specs(product_id,section,label,value,source_url,collected_at) VALUES(?,?,?,?,?,?)',
                           [(pid,s['section'],s['label'],s['value'],source,stamp) for s in p['specs']])
        offer=dict(platform='品牌官网',merchant='联想中国官方商城',variant=p['variant'],amount=p['amount'],item_condition='new',condition_note='全新检索，所选配置和库存需核对',
                   price_basis='listing',price_type='商城展示参考价',purchase_url=p['purchase_url'],
                   conditions='联想商城当前搜索列表的SKU展示价，不采用旧活动页、划线价、补贴和优惠券。尚未核验配送地区、库存及结算价，请进入具体SKU核对后购买。')
        save_offers(pid,source,html,[offer],observed_at=stamp);logs.append(dict(id=pid,name=p['name'],price=p['amount']))
    (ROOT/'data'/'lenovo_list_log.json').write_text(json.dumps(logs,ensure_ascii=False,indent=2),encoding='utf-8')
    from crawl_catalog import export_catalog
    export_catalog();print(json.dumps({'products':len(products),'within_6000':sum(p['amount']<=6000 for p in products)},ensure_ascii=False))


if __name__=='__main__':main()
