import requests,json,hashlib
from pathlib import Path
from bs4 import BeautifulSoup
folder=Path(__file__).parent/'data'/'curated_probes';folder.mkdir(exist_ok=True)
for slug in ('osmo-pocket-3','osmo-action-5-pro'):
    try:
        r=requests.get('https://store.dji.com/cn/product/'+slug+'?set_region=CN',headers={'User-Agent':'SmartBuyResearch/1.0','Accept-Language':'zh-CN'},timeout=20)
        p=folder/(slug+'.html');p.write_bytes(r.content)
        soup=BeautifulSoup(r.content,'html.parser')
        print(json.dumps({'slug':slug,'url':r.url,'status':r.status_code,'title':soup.title.text if soup.title else '', 'ld':[t.text for t in soup.select('script[type="application/ld+json"]')], 'scripts':[(t.get('id'),len(t.text)) for t in soup.select('script') if len(t.text)>1000]},ensure_ascii=True),flush=True)
    except Exception as exc:print(str(exc),flush=True)
