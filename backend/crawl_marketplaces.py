"""Refresh configured public platform quotes; record failures instead of making up prices."""
import argparse
import json
import time
from datetime import datetime,timezone
from pathlib import Path
from urllib.parse import urlparse
from catalog import ROOT,connect,init_catalog
from marketplace_quotes import fetch_public,zol_offers,pdd_public_offers,jsonld_offers,save_offers


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--sources',default=str(ROOT/'marketplace_sources.json'));args=parser.parse_args()
    init_catalog();sources=json.loads(Path(args.sources).read_text(encoding='utf-8'));logs=[]
    for source in sources:
        entry=dict(source,status='failed',attempted_at=datetime.now(timezone.utc).isoformat(timespec='seconds'))
        if source.get('disabled'):
            entry.update(status='skipped',message=source.get('disabled_reason','来源已停用'))
            logs.append(entry);print(json.dumps(entry,ensure_ascii=False),flush=True)
            continue
        try:
            time.sleep(1.2)
            with connect() as db:
                p=db.execute("SELECT * FROM catalog_products WHERE name=? AND validation_status='verified'",(source['product_name'],)).fetchone()
            if not p:raise ValueError('没有对应的已核验产品资料')
            html=fetch_public(source['url']);host=urlparse(source['url']).hostname
            offers=(zol_offers(html,p['name']) if host=='detail.zol.com.cn' else
                    pdd_public_offers(html,p['name'],source['url']) if source.get('adapter')=='pdd_public' else
                    jsonld_offers(html,p['name'],source['url']))
            entry.update(status='ok',inserted=save_offers(p['id'],source['url'],html,offers))
        except Exception as exc:entry['message']=str(exc)[:300]
        logs.append(entry);print(json.dumps(entry,ensure_ascii=False),flush=True)
    (ROOT/'data'/'marketplace_crawl_log.json').write_text(json.dumps(logs,ensure_ascii=False,indent=2),encoding='utf-8')


if __name__=='__main__':main()
