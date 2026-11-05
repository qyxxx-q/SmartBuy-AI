"""Bounded public homepage inspection; do not collect behind access restrictions."""
import hashlib
import json
import re
from datetime import datetime, timezone
from urllib.parse import urljoin, urlparse
from urllib.robotparser import RobotFileParser
from pathlib import Path
import requests
from bs4 import BeautifulSoup

ROOT=Path(__file__).resolve().parent
URL='https://www.taobao.com/wow/z/tbhome/pcsem/alimama?keyword=%E6%B7%98%E5%AE%9D'

def main():
    result={'url':URL,'attempted_at':datetime.now(timezone.utc).isoformat(timespec='seconds'),
            'authenticated':False,'imported':0}
    folder=ROOT/'data'/'market_probes';folder.mkdir(exist_ok=True)
    session=requests.Session()
    session.headers.update({'User-Agent':'SmartBuyResearch/1.0','Accept-Language':'zh-CN,zh;q=0.9'})
    try:
        robots=session.get('https://www.taobao.com/robots.txt',timeout=(8,15),allow_redirects=False)
        result['robots_status']=robots.status_code
        if robots.status_code==200 and '<html' not in robots.text.lower():
            path=folder/'taobao-home-robots-20261030.txt';path.write_bytes(robots.content)
            result['robots_snapshot']=str(path.relative_to(ROOT))
            rp=RobotFileParser();rp.parse(robots.text.splitlines())
            result['robots_allowed']=rp.can_fetch('SmartBuyResearch',URL)
            if not result['robots_allowed']:
                result.update(status='disallowed',message='淘宝 robots 不允许此路径的自动采集，未请求首页商品内容')
                return result
        elif robots.status_code not in (404,410):
            result.update(status='robots_unverified',message='无法核验 robots，未继续采集');return result
        response=session.get(URL,timeout=(8,20),allow_redirects=False)
        result['http_status']=response.status_code
        if response.is_redirect:
            result.update(status='redirected',message='来源要求跳转，未跟随登录或验证流程');return result
        if response.status_code!=200:
            result.update(status='unavailable',message='首页请求未成功');return result
        if len(response.content)>4000000:
            result.update(status='too_large',message='超出页面读取限额');return result
        digest=hashlib.sha256(response.content).hexdigest()
        path=folder/('taobao-home-'+digest+'.html');path.write_bytes(response.content)
        response.encoding='utf-8'
        soup=BeautifulSoup(response.text,'html.parser')
        result['snapshot']=str(path.relative_to(ROOT));result['sha256']=digest
        result['title']=soup.title.get_text(' ',strip=True) if soup.title else ''
        links=[]
        for a in soup.select('a[href]'):
            url=urljoin(URL,a['href']);host=urlparse(url).hostname
            if host not in ('item.taobao.com','detail.tmall.com') or not re.search(r'[?&]id=\d+',url):continue
            title=a.get_text(' ',strip=True)
            if re.search(r'手机|笔记本|电脑|平板|耳机|相机',title):links.append({'title':title[:250],'url':url})
        result['product_links']=links[:30]
        result['structured_products']=len(soup.select('script[type="application/ld+json"]'))
        result.update(status='inspected',message='仅保存公开首页与候选链接；商品配置、卖家及价格需逐项核对，不自动把首页广告数字当作报价')
        return result
    except requests.RequestException as exc:
        result.update(status='network_error',message=type(exc).__name__+'：网络请求失败，未新增报价');return result

if __name__=='__main__':
    result=main()
    (ROOT/'data'/'taobao_home_probe_20261030.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(result,ensure_ascii=True))
