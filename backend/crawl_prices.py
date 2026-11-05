"""Public store prices with model validation, snapshots, throttling and no login bypass."""
import argparse
import hashlib
import json
import re
import time
from datetime import datetime, timezone
from urllib.parse import urlparse
from urllib.robotparser import RobotFileParser
import requests
from bs4 import BeautifulSoup
from catalog import ROOT, connect, init_catalog

SOURCES = [
 ('iPhone 17','https://www.apple.com.cn/shop/buy-iphone/iphone-17'),
 ('iPhone 17 Pro','https://www.apple.com.cn/shop/buy-iphone/iphone-17-pro'),
 ('MacBook Air 系列','https://www.apple.com.cn/shop/buy-mac/macbook-air'),
 ('MacBook Pro 系列','https://www.apple.com.cn/shop/buy-mac/macbook-pro'),
 ('Mac mini','https://www.apple.com.cn/shop/buy-mac/mac-mini'),
 ('iPad Air 系列','https://www.apple.com.cn/shop/buy-ipad/ipad-air'),
 ('iPad Pro 系列','https://www.apple.com.cn/shop/buy-ipad/ipad-pro'),
 ('iPad mini','https://www.apple.com.cn/shop/buy-ipad/ipad-mini'),
 ('AirPods 4','https://www.apple.com.cn/shop/buy-airpods/airpods-4'),
 ('AirPods Pro 3','https://www.apple.com.cn/shop/buy-airpods/airpods-pro-3'),
]
ALLOWED = {'www.apple.com.cn','item.jd.com','apple.jd.com','apple.tmall.com','apple.world.tmall.com','detail.tmall.com'}


def normalize(s):
    return re.sub(r'[^a-z0-9]', '', s.lower())


def matches(name, text):
    expected=normalize(name.replace(' 系列',''))
    value=normalize(text)
    if expected not in value: return False
    if expected=='iphone17' and re.search(r'iphone17(?:pro|e)',value): return False
    if expected=='iphone17pro' and 'iphone17promax' in value: return False
    return True


def walk(value):
    if isinstance(value,dict):
        yield value
        for child in value.values(): yield from walk(child)
    elif isinstance(value,list):
        for child in value: yield from walk(child)


def apple_offers(html, name):
    soup=BeautifulSoup(html,'html.parser')
    title=soup.title.get_text(' ',strip=True) if soup.title else ''
    if not matches(name,title): raise ValueError('商店页面型号不一致，可能已换代或重定向')
    offers=[]
    metrics=soup.find('script',id='metrics')
    if metrics:
        for obj in walk(json.loads(metrics.get_text())):
            amount=(obj.get('price') or {}).get('fullPrice') if isinstance(obj.get('price'),dict) else None
            if amount and obj.get('partNumber') and matches(name,obj.get('name','')):
                offers.append((obj['name']+' · '+obj['partNumber'],float(amount),'配置报价'))
    if not offers:
        for script in soup.find_all('script'):
            if 'productSelectionData:' not in script.text: continue
            data=json.JSONDecoder().raw_decode(script.text.split('productSelectionData:',1)[1].lstrip())[0]
            for p in data.get('products',[]):
                if p.get('isComingSoon') or p.get('comingSoon') or p.get('refurbProduct'): continue
                prices=data.get('displayValues',{}).get('prices',{})
                price=prices.get(p.get('price') or p.get('fullPrice'),{})
                amount=price.get('currentPrice',{}).get('raw_amount')
                if not amount: continue
                details=[str(v) for k,v in p.items() if k.startswith('dimension') and k!='dimensionSteporder' and v]
                if p.get('partNumber'):
                    offers.append((name+' · '+' / '.join(details)+' · '+p['partNumber'],float(amount),'配置报价'))
            if not offers and data.get('mainDisplayValues',{}).get('prices'):
                prices=data['mainDisplayValues']['prices']
                amounts=[float(v['currentPrice']['raw_amount']) for v in prices.values()
                         if v.get('currentPrice',{}).get('raw_amount')]
                if amounts:
                    offers.append((name+'；选择页最低起售配置，内存与硬盘需确认',min(amounts),'官网起售价'))
    # Starting prices are only extracted from the main product's explicit metadata.
    if not offers:
        description=soup.find('meta',attrs={'name':'description'})
        value=description.get('content','') if description else ''
        m=re.search(r'RMB\s*([\d,]+)\s*起',value)
        if m and matches(name,value):
            offers.append((name+'；起售配置需在购买页选择',float(m.group(1).replace(',','')),'官网起售价'))
    if not offers: raise ValueError('未找到与本型号绑定的公开完整价格')
    return sorted(set(offers),key=lambda x:(x[1],x[0]))


def marketplace_offers(html, name, expected_merchant):
    """Only Product-owned offers, never search results or related-product price text."""
    soup=BeautifulSoup(html,'html.parser')
    results=[]
    for script in soup.select('script[type="application/ld+json"]'):
        try: data=json.loads(script.text)
        except ValueError: continue
        for obj in walk(data):
            if obj.get('@type') != 'Product' or not matches(name,obj.get('name','')): continue
            if re.search(r'二手|成新|退货|翻新',obj.get('name','')): continue
            offers=obj.get('offers',[])
            if isinstance(offers,dict): offers=[offers]
            for offer in offers:
                seller=offer.get('seller') or {}
                if not isinstance(seller,dict) or seller.get('name')!=expected_merchant: continue
                if offer.get('priceCurrency')!='CNY' or not obj.get('sku'): continue
                if not str(offer.get('itemCondition','')).endswith('NewCondition'): continue
                if not str(offer.get('availability','')).endswith('InStock'): continue
                amount=float(offer.get('price',0))
                if amount>0: results.append((obj['name']+' · SKU '+str(obj['sku']),amount,'配置报价'))
    if not results: raise ValueError('公开页未提供可验证的全新在售 SKU、店铺身份和价格；未导入')
    return results


def fetch(session,url):
    host=urlparse(url).hostname
    if urlparse(url).scheme!='https' or host not in ALLOWED: raise ValueError('不在价格来源白名单')
    response=session.get(url,timeout=25,allow_redirects=False)
    if response.is_redirect:
        from urllib.parse import urljoin
        target=urljoin(url,response.headers['Location'])
        if urlparse(target).hostname not in ALLOWED: raise ValueError('重定向离开可信店铺')
        return fetch(session,target)
    response.raise_for_status()
    return response


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--db')
    parser.add_argument('--marketplace-sources',help='JSON: product_name,url,merchant,platform; only allowlisted hosts')
    args=parser.parse_args()
    init_catalog(args.db)
    session=requests.Session();session.headers['User-Agent']='SmartBuyResearch/1.0'
    sources=[dict(product_name=n,url=u,merchant='Apple 中国大陆在线商店',platform='品牌官网') for n,u in SOURCES]
    if args.marketplace_sources:
        sources+=json.loads(open(args.marketplace_sources,encoding='utf-8').read())
    else:
        sources += [dict(product_name='iPhone 17',url='https://item.jd.com/100278222276.html',
                         merchant='Apple产品京东自营旗舰店',platform='京东')]
    logs=[];robots={};stamp=datetime.now(timezone.utc).isoformat(timespec='seconds')
    snapshot_dir=ROOT/'data'/'price_snapshots';snapshot_dir.mkdir(exist_ok=True)
    for source in sources:
        time.sleep(1.2)
        entry=dict(source,observed_at=stamp,status='failed')
        try:
            host=urlparse(source['url']).hostname
            if host not in robots:
                res=fetch(session,'https://'+host+'/robots.txt')
                rp=RobotFileParser();rp.parse(res.text.splitlines());robots[host]=rp
            if not robots[host].can_fetch('SmartBuyResearch',source['url']): raise ValueError('robots 不允许采集')
            response=fetch(session,source['url'])
            digest=hashlib.sha256(response.content).hexdigest()
            snapshot=snapshot_dir/(digest+'.html');snapshot.write_bytes(response.content)
            entry['snapshot_path']=str(snapshot.relative_to(ROOT))
            offers=(apple_offers(response.text,source['product_name']) if host=='www.apple.com.cn'
                    else marketplace_offers(response.text,source['product_name'],source['merchant']))
            with connect(args.db) as db:
                product=db.execute("SELECT * FROM catalog_products WHERE name=? AND validation_status='verified'",(source['product_name'],)).fetchone()
                if not product: raise ValueError('数据库无对应已核验型号')
                if product['region'] not in ('中国大陆','中国大陆官网'): raise ValueError('地区不同，不能合并国内报价')
                for variant,amount,kind in offers:
                    db.execute('''INSERT OR IGNORE INTO retailer_offers(product_id,platform,merchant,variant,amount,currency,region,price_type,conditions,source_url,observed_at,snapshot_path)
                        VALUES(?,?,?,?,?,'CNY','中国大陆',?,?,?,?,?)''',
                        (product['id'],source['platform'],source['merchant'],variant,amount,kind,
                         '公开全额标价；不计分期月供、教育优惠、补贴、以旧换新或会员券。库存与最终支付价请以店铺结算为准。',
                         response.url,stamp,entry['snapshot_path']))
            entry.update(status='ok',offer_count=len(offers))
        except Exception as exc: entry['message']=str(exc)[:500]
        logs.append(entry);print(json.dumps(entry,ensure_ascii=False),flush=True)
    (ROOT/'data'/'price_crawl_log.json').write_text(json.dumps(logs,ensure_ascii=False,indent=2),encoding='utf-8')


if __name__=='__main__': main()
