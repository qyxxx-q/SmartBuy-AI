"""Low-rate, allowlisted official specification crawler. No login or anti-bot bypass."""
import argparse
import hashlib
import json
import re
import time
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse, urljoin
from urllib.robotparser import RobotFileParser

import requests
from bs4 import BeautifulSoup
from catalog import ROOT, connect, init_catalog
from shopping import default_subcategory

AGENT = 'SmartBuyResearch/1.0'
ALLOWED = ('apple.com.cn','support.apple.com','consumer.huawei.com','consumer.huawei.cn','mi.com','sony.com','sony.com.cn','helpguide.sony.net','canon.com.cn','nikonimglib.com','lenovo.com','lenovo.com.cn','samsung.com','oppo.com','opposhop.cn','vivo.com','vivo.com.cn','honor.com','dell.com','oneplus.com','realme.com','asus.com.cn','dji.com','fujifilm-x.com')


def now():
    return datetime.now(timezone.utc).isoformat(timespec='seconds')


def official(url):
    host = urlparse(url).hostname or ''
    return urlparse(url).scheme == 'https' and any(host == d or host.endswith('.' + d) for d in ALLOWED)


def clean(value):
    return re.sub(r'[ \t\r\f\v]+', ' ', value).strip()


def extract(html):
    soup = BeautifulSoup(html, 'html.parser')
    title = clean(soup.title.get_text(' ',strip=True)) if soup.title else ''
    for tag in soup(['script','style','noscript','nav','footer','header','svg']): tag.decompose()
    main = soup.find('main') or soup.find(id='main') or soup.body or soup
    specs = []
    def add(section, label, value):
        label, value = clean(label), clean(value)
        if label and value and len(label) <= 100 and len(value) <= 16000 and label != value:
            if not any(s['section']==section and s['label']==label for s in specs):
                specs.append({'section':section,'label':label,'value':value})
    # Canon, Nikon and other table-based parameter pages.
    for table in main.find_all('table'):
        heading = table.find_previous(['h2','h3','h4'])
        section = clean(heading.get_text(' ',strip=True))[:100] if heading else '规格参数'
        for row in table.find_all('tr'):
            cells = row.find_all(['th','td'],recursive=False)
            if len(cells)>=2: add(section,cells[0].get_text(' ',strip=True),' | '.join(c.get_text(' ',strip=True) for c in cells[1:]))
    for dt in main.find_all('dt'):
        dd = dt.find_next_sibling('dd')
        if dd: add('规格参数',dt.get_text(' ',strip=True),dd.get_text(' ',strip=True))
    # Apple technical sections include variant qualifiers, kept together rather than guessed.
    for block in main.select('.techspecs-section'):
        heading = block.select_one('.techspecs-rowheader') or block.find(['h2','h3'])
        if heading:
            label = heading.get_text(' ',strip=True)
            value = block.get_text(' ',strip=True)
            add('技术规格',label,value[len(label):].strip())
    if main.select_one('.techspecs-section') and len(specs)>5:
        return title,specs,main.get_text('\n',strip=True)
    for block in main.select('.large-accordion__item'):
        heading=block.select_one('.large-accordion__title')
        content=block.select_one('.large-accordion__content')
        if heading and content: add('规格参数',heading.get_text(' ',strip=True),content.get_text(' ',strip=True))
    for block in main.select('.param-detail-item'):
        heading=block.select_one('.item-left-heading')
        content=block.select_one('.item-right')
        if heading and content: add('规格参数',heading.get_text(' ',strip=True),content.get_text(' ',strip=True))
    for block in main.select('.products-spec-component-list-item'):
        heading=block.select_one('.products-spec-component-title')
        content=block.select_one('.products-spec-component-list-item-right')
        if heading and content: add('规格参数',heading.get_text(' ',strip=True),content.get_text(' ',strip=True))
    for heading in main.select('.specs-con .xm-text.f-bold'):
        label=heading.get_text(' ',strip=True)
        block=heading.parent.parent
        value=block.get_text(' ',strip=True)
        if value.startswith(label): add('Specifications',label,value[len(label):].strip())
    # Newer Xiaomi accessory pages place spec blocks outside .specs-con.
    for heading in main.select('.xm-text.f-bold[data-key^="spec_"]'):
        label=heading.get_text(' ',strip=True)
        value=heading.parent.get_text(' ',strip=True)
        if value.startswith(label): add('Specifications',label,value[len(label):].strip())
    for block in main.select('.spec-content'):
        heading=block.select_one('.title')
        content=block.select_one('.tips')
        if heading and content: add('Specifications',heading.get_text(' ',strip=True),content.get_text(' ',strip=True))
    # Generic semantic heading blocks (Huawei, Xiaomi, Sony).
    for heading in main.find_all(['h2','h3','h4']):
        chunks = []
        for sibling in heading.next_siblings:
            if getattr(sibling,'name',None) in ('h1','h2','h3','h4'): break
            text = sibling.get_text(' ',strip=True) if hasattr(sibling,'get_text') else str(sibling).strip()
            if text: chunks.append(text)
            if len(' '.join(chunks))>12000: break
        if chunks: add('规格参数',heading.get_text(' ',strip=True),' '.join(chunks))
    # Huawei / Xiaomi frequently use divs instead of semantic headings.
    for block in main.select('.specs-item, .spec-item, .specs-items, .specifications-item, .specs-row, .specs-block'):
        lines = [clean(t) for t in block.stripped_strings if clean(t)]
        if len(lines)>1: add('规格参数',lines[0],' | '.join(lines[1:]))
    return title, specs, main.get_text('\n',strip=True)


def validate(source,title,specs,body):
    if len(body)<300 or re.search(r'access denied|verify you are human|captcha|just a moment',title,re.I):
        raise ValueError('Blocked or empty page')
    if len(specs)<(1 if source.get('format')=='pdf' else 3): raise ValueError('Insufficient structured specifications; adapter required')
    expected=source.get('identity',source['name'].replace(' 系列',''))
    normalize=lambda s:re.sub(r'[^\w]','',s).lower()
    identity_text=title if source['brand']=='Apple' else title+' '+body
    if normalize(expected) not in normalize(identity_text):
        raise ValueError('Product identity mismatch (redirect or wrong page)')


def extract_pdf(path):
    runtime=os.getenv('SMARTBUY_PDF_PYTHON',sys.executable)
    output=subprocess.run([runtime,str(ROOT/'extract_official_pdf.py'),str(path)],stdout=subprocess.PIPE,stderr=subprocess.PIPE,check=True)
    pages=json.loads(output.stdout.decode('utf-8'))
    specs=[{'section':'PDF 官方规格','label':'第 {} 页'.format(i+1),'value':text.strip()} for i,text in enumerate(pages) if len(text.strip())>100]
    body='\n'.join(pages)
    return body.splitlines()[0][:150] if body else '',specs,body


def export_catalog(db_path=None):
    with connect(db_path) as db:
        products=[]
        for row in db.execute("SELECT * FROM catalog_products WHERE validation_status='verified' ORDER BY category,brand,name"):
            item=dict(row); item['specifications']=[dict(r) for r in db.execute('SELECT section,label,value,source_url,collected_at FROM catalog_specs WHERE product_id=?',(row['id'],))]; products.append(item)
    export=ROOT/'data'/'official_catalog.json'; export.write_text(json.dumps(products,ensure_ascii=False,indent=2),encoding='utf-8')
    return len(products)


def crawl(sources, db_path=None):
    init_catalog(db_path)
    session=requests.Session()
    session.headers.update({'User-Agent':AGENT,'Accept-Language':'zh-CN,zh;q=0.9,en;q=0.7'})
    robots_cache={}
    with connect(db_path) as db:
        run_id=db.execute('INSERT INTO crawl_runs(started_at) VALUES(?)',(now(),)).lastrowid
    success=0; failed=0
    snapshot_dir=ROOT/'data'/'official_snapshots'; snapshot_dir.mkdir(parents=True,exist_ok=True)
    for source in sources:
        url=source['url']; status_code=None; robots_state='not_checked'; sha=None
        try:
            if not official(url): raise ValueError('URL outside official domain allowlist')
            origin='{0.scheme}://{0.netloc}'.format(urlparse(url))
            if origin not in robots_cache:
                rr=session.get(origin+'/robots.txt',timeout=20)
                if rr.status_code==200:
                    parser=RobotFileParser(); parser.parse(rr.text.splitlines()); robots_cache[origin]=parser
                elif rr.status_code in (404,410): robots_cache[origin]=None
                else: raise ValueError('robots.txt unavailable: HTTP '+str(rr.status_code))
            parser=robots_cache[origin]
            if parser and not parser.can_fetch(AGENT,url): raise ValueError('robots.txt disallows this URL')
            robots_state='allowed' if parser else 'not_published'
            delay=1
            if parser:
                try: delay=parser.crawl_delay(AGENT) or parser.crawl_delay('*') or 1
                except AttributeError: pass  # Python 3.7 RobotFileParser without a default entry
            time.sleep(max(1,delay))
            response=session.get(url,timeout=25)
            status_code=response.status_code
            response.raise_for_status()
            if not official(response.url): raise ValueError('Redirect outside official domain allowlist: '+response.url)
            response.encoding=response.apparent_encoding if 'charset' not in response.headers.get('Content-Type','').lower() else response.encoding
            html=response.text
            sha=hashlib.sha256(response.content).hexdigest()
            is_pdf=response.content.startswith(b'%PDF')
            snapshot=snapshot_dir/(sha+('.pdf' if is_pdf else '.html')); snapshot.write_bytes(response.content)
            title,specs,body=extract_pdf(snapshot) if is_pdf else extract(html)
            validate(source,title,specs,body)
            stamp=now()
            with connect(db_path) as db:
                existing=db.execute('SELECT id FROM catalog_products WHERE source_url=?',(url,)).fetchone()
                values=(source['name'],source['brand'],source['category'],source.get('region','中国大陆'),title,stamp,sha,str(snapshot.relative_to(ROOT)),len(specs))
                if existing:
                    pid=existing['id']
                    db.execute('UPDATE catalog_products SET name=?,brand=?,category=?,region=?,source_title=?,collected_at=?,content_sha256=?,snapshot_path=?,spec_count=? WHERE id=?',values+(pid,))
                else:
                    pid=db.execute('INSERT INTO catalog_products(name,brand,category,region,source_title,collected_at,content_sha256,snapshot_path,spec_count,source_url) VALUES(?,?,?,?,?,?,?,?,?,?)',values+(url,)).lastrowid
                db.execute('DELETE FROM catalog_specs WHERE product_id=?',(pid,))
                db.executemany('INSERT INTO catalog_specs(product_id,section,label,value,source_url,collected_at) VALUES(?,?,?,?,?,?)',[(pid,s['section'],s['label'],s['value'],url,stamp) for s in specs])
                db.execute("UPDATE catalog_products SET validation_status='verified',validation_note='' WHERE id=?",(pid,))
                db.execute('UPDATE catalog_products SET subcategory=? WHERE id=?',(source.get('subcategory') or default_subcategory(source),pid))
            status='success'; message='{} specification groups'.format(len(specs)); success+=1
        except Exception as exc:
            status='failed'; message=str(exc)[:500]; failed+=1
        with connect(db_path) as db:
            db.execute('INSERT INTO crawl_pages(run_id,url,status,http_status,message,collected_at,robots_status,content_sha256) VALUES(?,?,?,?,?,?,?,?)',(run_id,url,status,status_code,message,now(),robots_state,sha))
        print(json.dumps({'name':source['name'],'status':status,'message':message},ensure_ascii=True),flush=True)
    with connect(db_path) as db:
        db.execute('UPDATE crawl_runs SET finished_at=?,success_count=?,failure_count=? WHERE id=?',(now(),success,failed,run_id))
    total=export_catalog(db_path)
    print(json.dumps({'run_id':run_id,'success':success,'failed':failed,'total_products':total}),flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--sources',default=str(ROOT/'catalog_sources.json'))
    parser.add_argument('--brand')
    parser.add_argument('--db')
    parser.add_argument('--pending',action='store_true',help='Only fetch URLs not yet imported successfully')
    args=parser.parse_args()
    sources=json.loads(Path(args.sources).read_text(encoding='utf-8-sig'))
    sources=[s for s in sources if s.get('enabled',True)]
    if args.brand: sources=[s for s in sources if s['brand']==args.brand]
    if args.pending:
        init_catalog(args.db)
        with connect(args.db) as db: done={r[0] for r in db.execute("SELECT source_url FROM catalog_products WHERE validation_status='verified'")}
        sources=[s for s in sources if s['url'] not in done]
    crawl(sources,args.db)
