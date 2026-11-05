"""Expand the catalog and collect matching SKU offers from accessible official stores."""
import argparse
import hashlib
import json
import re
import time
from datetime import datetime,timezone
from urllib.robotparser import RobotFileParser
from pathlib import Path
import requests
from bs4 import BeautifulSoup
from catalog import ROOT,connect,init_catalog
from shopping import default_subcategory
from store_sources import discover_oppo,oppo_product


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--limit',type=int,default=40);parser.add_argument('--retry-failed',action='store_true');parser.add_argument('--sources');args=parser.parse_args()
    init_catalog();session=requests.Session();session.headers.update({'User-Agent':'SmartBuyResearch/1.0','Accept-Language':'zh-CN,zh;q=0.9'})
    origin='https://www.opposhop.cn'
    robots=session.get(origin+'/robots.txt',timeout=20)
    rp=None
    if robots.status_code==200 and '<html' not in robots.text.lower():
        rp=RobotFileParser();rp.parse(robots.text.splitlines())
    elif robots.status_code not in (200,404,410): raise ValueError('robots 状态无法核验')
    if rp and not rp.can_fetch('SmartBuyResearch',origin+'/'): raise ValueError('robots 不允许访问')
    homepage=session.get(origin+'/',timeout=25);homepage.raise_for_status();homepage.encoding='utf-8'
    sources=json.loads(Path(args.sources).read_text(encoding='utf-8')) if args.sources else discover_oppo(homepage.text)
    if args.retry_failed and (ROOT/'data'/'store_crawl_log.json').exists():
        failed={x['url'] for x in json.loads((ROOT/'data'/'store_crawl_log.json').read_text(encoding='utf-8')) if x['status']!='ok'}
        sources=[s for s in sources if s['url'] in failed]
    (ROOT/'catalog_sources_stores.json').write_text(json.dumps(sources,ensure_ascii=False,indent=2),encoding='utf-8')
    logs=[];folder=ROOT/'data'/'store_snapshots';folder.mkdir(exist_ok=True)
    for source in sources[:args.limit]:
        entry=dict(source,status='failed')
        try:
            if rp and not rp.can_fetch('SmartBuyResearch',source['url']): raise ValueError('robots 不允许访问')
            time.sleep(1.1)
            response=session.get(source['url'],timeout=22);response.raise_for_status();response.encoding='utf-8'
            if not response.url.startswith(origin+'/cn/web/products/'): raise ValueError('商品页已重定向')
            p=oppo_product(response.text,source['name'],re.search(r'/(\d+)\.html',source['url']).group(1))
            digest=hashlib.sha256(response.content).hexdigest();snapshot=folder/(digest+'.html');snapshot.write_bytes(response.content)
            stamp=datetime.now(timezone.utc).isoformat(timespec='seconds');relative=str(snapshot.relative_to(ROOT))
            title=BeautifulSoup(response.text,'html.parser').title.get_text(' ',strip=True)
            with connect() as db:
                existing=db.execute('SELECT id FROM catalog_products WHERE source_url=? OR (name=? AND brand=? AND category=?)',(source['url'],p['name'],p['brand'],p['category'])).fetchone()
                if not existing:
                    pid=db.execute('''INSERT INTO catalog_products(name,brand,category,region,source_url,source_title,collected_at,content_sha256,snapshot_path,spec_count,subcategory)
                                      VALUES(?,?,?,'中国大陆',?,?,?,?,?,?,?)''',
                        (p['name'],p['brand'],p['category'],source['url'],title,stamp,digest,relative,len(p['specs']),default_subcategory(p))).lastrowid
                else:
                    pid=existing['id']
                    db.execute("UPDATE catalog_products SET collected_at=?,content_sha256=?,snapshot_path=?,spec_count=?,validation_status='verified' WHERE id=?",(stamp,digest,relative,len(p['specs']),pid))
                    db.execute('DELETE FROM catalog_specs WHERE product_id=?',(pid,))
                db.executemany('INSERT INTO catalog_specs(product_id,section,label,value,source_url,collected_at) VALUES(?,?,?,?,?,?)',
                               [(pid,s['section'],s['label'],s['value'],source['url'],stamp) for s in p['specs']])
                db.execute('''INSERT OR IGNORE INTO retailer_offers(product_id,platform,merchant,variant,amount,currency,region,price_type,conditions,source_url,observed_at,snapshot_path,availability)
                              VALUES(?,'品牌官网','OPPO 中国官方商城',?,?,'CNY','中国大陆','配置报价',?,?,?,?,?)''',
                           (pid,p['variant']+' · SKU '+p['sku'],p['amount'],'当前SKU公开全额标价；不计消费券、补贴、以旧换新和预估到手价。库存状态以采集时页面为准，最终支付以结算页为准。',source['url'],stamp,relative,'in_stock' if p['available'] else 'out_of_stock'))
            entry.update(status='ok',name=p['name'],category=p['category'],price=p['amount'] if p['available'] else None,available=p['available'])
        except Exception as exc: entry['message']=str(exc)[:200]
        logs.append(entry);print(json.dumps(entry,ensure_ascii=False),flush=True)
    (ROOT/'data'/'store_crawl_log.json').write_text(json.dumps(logs,ensure_ascii=False,indent=2),encoding='utf-8')
    from crawl_catalog import export_catalog
    export_catalog()


if __name__=='__main__':main()
