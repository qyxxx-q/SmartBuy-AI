"""Build 25 source-backed course dossiers; rerunning never refreshes quote dates."""
import argparse,hashlib,json,re,time
from datetime import datetime,timezone
from urllib.parse import urlparse
import requests
from bs4 import BeautifulSoup
from catalog import ROOT,connect,init_catalog
from store_sources import nuxt_state

IDS=[86,87,113,88,85,82,83,1,126,143,137,130,127,120,91,94,95,4,124,92,93,90,6,117,118]
IMAGE_HOSTS={'msecfs.opposhop.cn','www.apple.com.cn','www.apple.com','store.storeimages.cdn-apple.com','p1.lefile.cn','p2.lefile.cn','p3.lefile.cn','p4.lefile.cn','www-cdn.djiits.com','se-cdn.djiits.com'}

def image_from(p):
    soup=BeautifulSoup((ROOT/p['snapshot_path']).read_bytes(),'html.parser')
    if 'opposhop.cn' in p['source_url']:
        state=nuxt_state(str(soup))
        data=next(x['resData'] for x in state['data'] if isinstance(x,dict) and x.get('resData'))
        sku=next(x for x in data['attributes']['skuItems'] if str(x['skuId'])==str(data['goodsSkuId']))
        for config in data['attributes']['configs']:
            for item in config.get('values',[]):
                if item.get('item')==sku.get('key1') and item.get('image'):return item['image']
        raise ValueError('未找到当前配色商品图片')
    if 'lenovo.com.cn' in p['source_url']:
        sku=p['source_url'].split('#sku=')[-1]
        li=next(li for li in soup.select('.productDetailUl>li') if li.select_one('.imgA') and '/'+sku+'.html' in li.select_one('.imgA')['href'])
        image=li.select_one('[data-imgurl]')['data-imgurl'] if li.select_one('[data-imgurl]') else li.select_one('.imgA img')['src']
        return 'https:'+image if image.startswith('//') else image
    ld=soup.select_one('script[type="application/ld+json"]')
    if ld:
        data=json.loads(ld.text)
        if data.get('@type')=='Product' and data.get('image'):return data['image']
    meta=soup.select_one('meta[property="og:image"]')
    if meta:return meta['content']
    raise ValueError('官方参数快照缺少型号图片')

def import_dji():
    # These are full public store responses from the probe, not search snippets.
    for pid,slug in ((117,'osmo-action-5-pro'),(118,'osmo-pocket-3')):
        path=ROOT/'data'/'curated_probes'/(slug+'.html');raw=path.read_bytes()
        soup=BeautifulSoup(raw,'html.parser')
        product=json.loads(soup.select_one('script[type="application/ld+json"]').text)
        offer=product['offers']
        if offer['priceCurrency']!='CNY' or not offer['url'].startswith('https://store.dji.com/cn/'):raise ValueError('不能导入海外报价')
        if slug.replace('-','') not in re.sub(r'[^a-z0-9]','',product['name'].lower()):raise ValueError('相机型号不一致')
        digest=hashlib.sha256(raw).hexdigest();target=ROOT/'data'/'price_snapshots'/(digest+'.html');target.write_bytes(raw)
        stamp=datetime.fromtimestamp(path.stat().st_mtime,timezone.utc).isoformat(timespec='seconds')
        with connect() as db:
            # Global specifications and China quotes remain separate regions; explicit
            # China product parameter collection below must succeed before changing it.
            row=db.execute('SELECT region FROM catalog_products WHERE id=?',(pid,)).fetchone()
            if row['region']!='中国大陆':continue
            db.execute('''INSERT OR IGNORE INTO retailer_offers(product_id,platform,merchant,variant,amount,currency,region,price_type,conditions,source_url,observed_at,snapshot_path,availability)
             VALUES(?,'品牌官网','DJI 大疆中国官方商城',?,?,'CNY','中国大陆','配置报价',?,?,?,?,?)''',
             (pid,product['name']+'；默认标准套装，配件另购',float(offer['price']),
              '中国商城商品自身结构化公开标价；不计补贴、优惠券和以旧换新。套装内容及最终支付金额请在来源页面核对。',
              offer['url']+'?set_region=CN',stamp,str(target.relative_to(ROOT)),'in_stock' if offer['availability'].endswith('/InStock') else 'out_of_stock'))

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--download',action='store_true');args=parser.parse_args()
    init_catalog()
    if args.download:
        for pid,slug in ((117,'osmo-action-5-pro'),(118,'osmo-pocket-3')):
            raw=(ROOT/'data'/'curated_probes'/(slug+'.html')).read_bytes()
            soup=BeautifulSoup(raw,'html.parser');product=json.loads(soup.select_one('script[type="application/ld+json"]').text)
            if product['offers']['priceCurrency']!='CNY':raise ValueError('相机商城并非中国地区')
            url=product['url']+'?set_region=CN';title=soup.title.text
            with connect() as db:
                p=dict(db.execute('SELECT * FROM catalog_products WHERE id=?',(pid,)).fetchone())
                digest=hashlib.sha256(raw).hexdigest();snap=ROOT/'data'/'official_snapshots'/(digest+'.html');snap.write_bytes(raw)
                stamp=datetime.fromtimestamp((ROOT/'data'/'curated_probes'/(slug+'.html')).stat().st_mtime,timezone.utc).isoformat(timespec='seconds')
                # Original global spec URLs/dates stay intact. The domestic item is
                # established by the China storefront, not by relabeling that evidence.
                db.execute('DELETE FROM catalog_specs WHERE product_id=? AND label=?',(pid,'Please Change Your Browser'))
                db.execute('INSERT OR REPLACE INTO catalog_specs(product_id,section,label,value,source_url,collected_at) VALUES(?,?,?,?,?,?)',
                    (pid,'基本信息','参数地区说明','技术参数摘录全球版官网，保留原始测试条件；报价来自中国商城，国内配件、无线频段和保修须另行核对。',url,stamp))
                count=db.execute('SELECT COUNT(*) FROM catalog_specs WHERE product_id=?',(pid,)).fetchone()[0]
                db.execute('UPDATE catalog_products SET source_url=?,region=?,source_title=?,collected_at=?,content_sha256=?,snapshot_path=?,spec_count=? WHERE id=?',
                    (url,'中国大陆',title,stamp,digest,str(snap.relative_to(ROOT)),count,pid))
    import_dji();out=ROOT/'data'/'product_images';out.mkdir(exist_ok=True)
    session=requests.Session();session.headers['User-Agent']='SmartBuyResearch/1.0'
    manifest=[]
    for pid in IDS:
        with connect() as db:
            p=dict(db.execute('SELECT * FROM catalog_products WHERE id=?',(pid,)).fetchone())
            quote=db.execute('SELECT * FROM retailer_offers WHERE product_id=? ORDER BY observed_at DESC,amount LIMIT 1',(pid,)).fetchone()
            existing=db.execute('SELECT * FROM curated_products WHERE product_id=?',(pid,)).fetchone()
        try:
            if existing and (out/existing['image_url'].split('/')[-1]).exists():
                url=existing['image_source_url'];digest=existing['image_sha256'];image=existing['image_url'];stamp=existing['image_collected_at']
            else:
                url=image_from(p)
                if urlparse(url).hostname not in IMAGE_HOSTS:raise ValueError('图片域名不在官网资源白名单')
                if not args.download:raise ValueError('请使用 --download 首次保存官方商品图')
                r=session.get(url,timeout=20);r.raise_for_status()
                if not r.headers.get('Content-Type','').startswith('image/'):raise ValueError('资源不是图片')
                digest=hashlib.sha256(r.content).hexdigest();suffix='.png' if r.content.startswith(b'\x89PNG') else '.webp' if r.content[8:12]==b'WEBP' else '.jpg'
                filename=digest+suffix;(out/filename).write_bytes(r.content);image='/api/product-images/'+filename
                stamp=datetime.now(timezone.utc).isoformat(timespec='seconds');time.sleep(.3)
            if not quote:raise ValueError('缺少报价凭据')
            note=('全球版参数及其原始日期保留；中国商城价格，国内配件、无线频段与保修另行核对。' if p['brand']=='DJI' else '官方商城列表配置；重量、续航和库存等未披露项保留未知。' if p['brand']=='联想' else
                  '官方参数页可能包含可选项，以报价配置为准；未知字段保留未知。')
            with connect() as db:
                db.execute('INSERT OR REPLACE INTO curated_products VALUES(?,?,?,?,?,?,?,?)',(pid,image,url,digest,stamp,quote['variant'],note,datetime.now(timezone.utc).isoformat(timespec='seconds')))
            item=dict(id=pid,name=p['name'],category=p['category'],spec_count=p['spec_count'],source_url=p['source_url'],spec_collected_at=p['collected_at'],
                      spec_sha256=p['content_sha256'],image_url=image,image_source_url=url,image_sha256=digest,image_collected_at=stamp,
                      configuration=quote['variant'],quote_amount=quote['amount'],quote_source=quote['source_url'],quote_observed_at=quote['observed_at'],quote_type=quote['price_type'],note=note,status='ok')
        except Exception as exc:item=dict(id=pid,name=p['name'],status='incomplete',error=str(exc))
        manifest.append(item);print(json.dumps(item,ensure_ascii=True),flush=True)
    (ROOT/'data'/'curated_manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')

if __name__=='__main__':main()
