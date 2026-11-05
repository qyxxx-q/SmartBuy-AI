"""Attributable marketplace offers and explicitly labeled public comparison-page listings."""
import hashlib
import json
import math
import re
from datetime import datetime,timezone
from urllib.parse import urlparse,urljoin
from urllib.robotparser import RobotFileParser
import requests
from bs4 import BeautifulSoup
from flask import Blueprint,jsonify,request
from catalog import ROOT,connect

quotes_api=Blueprint('quotes',__name__)
HOSTS={'item.jd.com':'京东','item.m.jd.com':'京东','item.taobao.com':'淘宝','detail.tmall.com':'淘宝',
       'h5.m.taobao.com':'淘宝','mobile.yangkeduo.com':'拼多多','www.goofish.com':'闲鱼','h5.m.goofish.com':'闲鱼'}


def model_matches(name,title):
    def norm(s):
        return re.sub(r'[^\w]','',s.lower().replace('（国行）','').replace(' 系列','').replace('红米','redmi').replace('oneplus','一加'))
    key,value=norm(name),norm(title)
    if not key or key not in value:return False
    tail=value.split(key,1)[1]
    # Do not use a Pro/Plus/Ultra/SE model or a later generation for a base model.
    return not re.match(r'(?:pro|max|ultra|plus|lite|se|turbo|fe|[a-z](?![a-z]))',tail)


def rejected_title(title):
    return bool(re.search(r'手机壳|保护壳|钢化膜|贴膜|维修|回收|定金|订金|月供|配件|碎屏|故障|主板|仅包装|空盒',title))


def platform_for(url,referrals=False):
    host=(urlparse(url).hostname or '').lower()
    if host in HOSTS:return HOSTS[host]
    if referrals:
        if host in ('s.click.taobao.com','click.mz.simba.taobao.com'):return '淘宝'
        if host in ('union-click.jd.com','u.jd.com'):return '京东'
        if host in ('p.pinduoduo.com','yangkeduo.com'):return '拼多多'
    return None


def jsonld_offers(html,name,url):
    from crawl_prices import walk
    platform=platform_for(url)
    if not platform:raise ValueError('仅支持指定购物平台的公开商品页')
    soup=BeautifulSoup(html,'html.parser');results=[]
    for script in soup.select('script[type="application/ld+json"]'):
        try:data=json.loads(script.get_text())
        except (ValueError,TypeError):continue
        for obj in walk(data):
            if obj.get('@type')!='Product' or not model_matches(name,obj.get('name','')) or rejected_title(obj.get('name','')):continue
            offers=obj.get('offers') or []
            if isinstance(offers,dict):offers=[offers]
            for o in offers:
                if not isinstance(o,dict) or o.get('priceCurrency')!='CNY':continue
                if not str(o.get('availability','')).endswith('InStock'):continue
                condition=str(o.get('itemCondition') or obj.get('itemCondition') or '')
                kind='used' if condition.endswith(('UsedCondition','RefurbishedCondition')) else 'new' if condition.endswith('NewCondition') else None
                if not kind:continue
                if kind=='new' and re.search(r'二手|成新|翻新|已拆封',obj['name']):continue
                sku=obj.get('sku') or obj.get('productID')
                seller=o.get('seller') or {};merchant=seller.get('name') if isinstance(seller,dict) else str(seller)
                amount=float(o.get('price',0))
                if not sku or not merchant or not math.isfinite(amount) or amount<=0:continue
                results.append(dict(platform=platform,merchant=merchant,variant=obj['name']+' · SKU '+str(sku),amount=amount,
                                    item_condition=kind,condition_note='二手/翻新，成色与维修情况需核对' if kind=='used' else '页面声明全新',
                                    price_basis='direct',price_type='配置报价',purchase_url=url,
                                    conditions='公开商品页标价；店铺身份、配置、成色、库存和最终支付金额请在平台核对。'))
    if not results:raise ValueError('公开页没有可核验的型号、SKU、卖家、成色、在售状态和人民币价格，可能需要登录或授权接口')
    return results


def zol_offers(html,name):
    soup=BeautifulSoup(html,'html.parser')
    title=soup.title.get_text(' ',strip=True) if soup.title else ''
    if not model_matches(name,title):raise ValueError('比价页型号不符')
    results=[]
    heading=soup.find('h1');page_name=heading.get_text(' ',strip=True) if heading else name
    for row in soup.select('.b2c-item, .select-mol.b2c-jd, .select-mol.b2c-taobao, .select-mol.b2c-tmall'):
        link=row.find('a',href=True);price=row.select_one('.m-price')
        if not link or not price:continue
        platform=platform_for(link['href'],referrals=True)
        match=re.search(r'[\d,]+(?:\.\d+)?',price.get_text(' ',strip=True))
        if not platform or not match:continue
        purchase=''
        if platform=='京东':
            sku=re.search(r'[?&]e=jd_(\d+)(?:&|$)',link['href'])
            if sku:purchase='https://item.jd.com/'+sku.group(1)+'.html'
        results.append(dict(platform=platform,merchant='公开比价页收录店铺（身份未核验）',variant=page_name+'；具体套装与库存待核对',amount=float(match.group().replace(',','')),
                            item_condition='new',condition_note='未标记二手，实际成色仍需核对',price_basis='listing',price_type='平台参考价',purchase_url=purchase,
                            conditions='转引中关村在线本型号在售电商栏的公开报价，可能滞后；不是平台实时核验价，须确认商品页完整配置、套装、库存与最终支付价。'))
    for row in soup.select('.brand-seller-top'):
        link=row.select_one('.brand-name a');price=row.select_one('.merchant-price .price')
        if not link or not price:continue
        model=link.get('title') or link.get_text(' ',strip=True)
        platform=platform_for(link.get('href',''),referrals=True)
        if not platform or not model_matches(name,model) or rejected_title(model):continue
        amount=re.search(r'[\d,]+(?:\.\d+)?',price.get_text(' ',strip=True))
        if not amount:continue
        value=float(amount.group().replace(',',''))
        if value<=0:continue
        used=bool(re.search(r'二手|成新|翻新|已拆封',model))
        results.append(dict(platform=platform,merchant='公开比价页收录店铺（身份未核验）',variant=model+'；容量、成色和库存待核对',amount=value,
                            item_condition='used' if used else 'new',condition_note='二手，具体成色待核对' if used else '未标记二手，实际成色仍需核对',price_basis='listing',price_type='平台参考价',purchase_url='',
                            conditions='转引中关村在线公开平台报价，可能滞后或对应最低配置；不是平台实时核验价，须确认完整配置、店铺、库存、优惠条件与最终支付价。'))
    if not results:raise ValueError('未找到型号一致且标明购物平台的公开报价')
    return results


def pdd_public_offers(html,name,url):
    """Read the visible price on the matching card, never hidden minimum prices or other cards."""
    soup=BeautifulSoup(html,'html.parser');results=[]
    for row in soup.select('[class*="inline_card_wrapper"]'):
        heading=row.select_one('[class*="_goods_name__"]');price=row.select_one('[class*="_default_price__"]')
        if not heading or not price:continue
        title=heading.get_text(' ',strip=True)
        if not model_matches(name,title) or rejected_title(title):continue
        amount=re.search(r'\d+(?:\.\d+)?',price.get_text('',strip=True).replace(',',''))
        if not amount:continue
        used=bool(re.search(r'二手|成新|翻新|已拆封',title))
        results.append(dict(platform='拼多多',merchant='公开商品卡片（店铺身份未核验）',variant=title+'；容量、成色、拼单及配送条件待核对',amount=float(amount.group()),
                            item_condition='used' if used else 'new',condition_note='二手，成色待核对' if used else '未标记二手，实际成色仍需核对',price_basis='listing',price_type='平台参考价',purchase_url=url,
                            conditions='拼多多公开展示的拼单参考价，所选地区为中国；未采用隐藏最低价。容量、店铺、库存、拼单条件、运费和最终支付金额仍需在平台确认。'))
    if not results:raise ValueError('未找到型号一致的公开商品卡片价格；下载页或相关产品价格不能当作报价')
    return results


def save_offers(pid,url,html,offers,observed_at=None):
    stamp=observed_at or datetime.now(timezone.utc).isoformat(timespec='seconds');digest=hashlib.sha256(html.encode('utf-8')).hexdigest()
    folder=ROOT/'data'/'marketplace_snapshots';folder.mkdir(exist_ok=True);path=folder/(digest+'.html');path.write_bytes(html.encode('utf-8'))
    with connect() as db:
        p=db.execute("SELECT * FROM catalog_products WHERE id=? AND validation_status='verified'",(pid,)).fetchone()
        if not p:raise ValueError('产品不存在')
        if p['region'] not in ('中国大陆','中国大陆官网'):raise ValueError('地区不同，不能合并国内平台报价')
        inserted=0
        for o in offers:
            cursor=db.execute('''INSERT OR IGNORE INTO retailer_offers(product_id,platform,merchant,variant,amount,region,price_type,conditions,source_url,observed_at,snapshot_path,item_condition,condition_note,price_basis,purchase_url,availability)
                          VALUES(?,?,?,?,?,'中国大陆',?,?,?,?,?,?,?,?,?,?)''',
                       (pid,o['platform'],o['merchant'],o['variant'],o['amount'],o['price_type'],o['conditions'],url,stamp,str(path.relative_to(ROOT)),o['item_condition'],o['condition_note'],o['price_basis'],o['purchase_url'],'unknown' if o['price_basis']=='listing' else 'in_stock'))
            inserted+=cursor.rowcount
    return inserted


def fetch_public(url):
    if len(url)>4096:raise ValueError('商品链接过长')
    host=urlparse(url).hostname
    if urlparse(url).scheme!='https' or (host not in HOSTS and host!='detail.zol.com.cn'):raise ValueError('仅支持已列出的购物平台商品页或公开比价页')
    session=requests.Session();session.headers.update({'User-Agent':'SmartBuyResearch/1.0','Accept-Language':'zh-CN,zh;q=0.9'})
    robots=session.get('https://'+host+'/robots.txt',timeout=12,allow_redirects=False)
    if robots.status_code==200 and '<html' not in robots.text.lower():
        rp=RobotFileParser();rp.parse(robots.text.splitlines())
        if not rp.can_fetch('SmartBuyResearch',url):raise ValueError('来源站点 robots 不允许采集该页面')
    elif robots.status_code not in (200,301,302,404,410):raise ValueError('无法核验来源 robots 状态')
    response=session.get(url,timeout=18,allow_redirects=False)
    if response.is_redirect:raise ValueError('平台要求跳转，可能需要登录或打开客户端；未采集报价')
    response.raise_for_status()
    if len(response.content)>4000000:raise ValueError('商品页过大')
    response.encoding=response.apparent_encoding if 'charset' not in response.headers.get('Content-Type','').lower() else response.encoding
    return response.text


@quotes_api.route('/api/quotes/refresh',methods=['POST'])
def refresh_quote():
    data=request.get_json(silent=True) or {}
    try:
        pid=int(data.get('product_id'));url=str(data.get('url','')).strip()
        with connect() as db:
            p=db.execute("SELECT * FROM catalog_products WHERE id=? AND validation_status='verified'",(pid,)).fetchone()
        if not p:raise ValueError('产品不存在')
        html=fetch_public(url)
        host=urlparse(url).hostname
        offers=(zol_offers(html,p['name']) if host=='detail.zol.com.cn' else
                pdd_public_offers(html,p['name'],url) if host=='mobile.yangkeduo.com' and 'region=CN' in url else jsonld_offers(html,p['name'],url))
        count=save_offers(pid,url,html,offers)
        return jsonify(ok=True,count=count,message='已更新公开报价，重新推荐将按新价格匹配预算')
    except (ValueError,TypeError,requests.RequestException) as exc:
        return jsonify(error=str(exc)[:250]),400
