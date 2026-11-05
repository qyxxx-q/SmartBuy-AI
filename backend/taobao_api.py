"""Taobao Alliance TOP search; item-level prices remain explicitly provisional."""
import hashlib
import json
import math
import os
import re
from datetime import datetime, timedelta, timezone
from urllib.parse import urlparse

import requests
from flask import Blueprint, jsonify, request
from catalog import ROOT, connect
from marketplace_quotes import model_matches, rejected_title, save_offers

taobao_api = Blueprint('taobao', __name__)
CONFIG_PATH = ROOT / 'data' / 'taobao_settings.json'
GATEWAY = 'https://eco.taobao.com/router/rest'
METHOD = 'taobao.tbk.dg.material.optional.upgrade'
DOC = 'https://developer.alibaba.com/docs/api.htm?apiId=64759'


def config():
    data = {}
    if CONFIG_PATH.exists():
        try:
            data = json.loads(CONFIG_PATH.read_text(encoding='utf-8'))
        except (ValueError, OSError):
            pass
    return {key: str(data.get(key) or os.getenv('TAOBAO_' + key.upper(), '')).strip()
            for key in ('app_key', 'app_secret', 'adzone_id')}


def public_config():
    value = config()
    return dict(configured=all(value.values()), key_present=bool(value['app_secret']),
                app_key=value['app_key'], adzone_id=value['adzone_id'], method=METHOD)


def local_access():
    # Reject DNS rebinding, cross-origin forms, and non-loopback clients.
    return (request.remote_addr in ('127.0.0.1', '::1')
            and request.host.split(':')[0] in ('127.0.0.1', 'localhost')
            and request.headers.get('Sec-Fetch-Site') != 'cross-site'
            and (not request.headers.get('Origin') or
                 request.headers['Origin'].rstrip('/') == request.host_url.rstrip('/')))


@taobao_api.before_request
def guard():
    if not local_access():
        return jsonify(error='请从本机 SmartBuy 页面使用淘宝配置与查询'), 403


@taobao_api.route('/api/taobao/config', methods=['GET', 'POST'])
def settings():
    if request.method == 'GET':
        return jsonify(public_config())
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify(error='请填写配置表单'), 400
    value = config()
    for key in value:
        if key in data and (key != 'app_secret' or data[key]):
            value[key] = str(data[key]).strip()
    pid = re.fullmatch(r'mm_\d+_\d+_(\d+)', value['adzone_id'])
    if pid:
        value['adzone_id'] = pid.group(1)
    if (not re.fullmatch(r'[A-Za-z0-9]{1,100}', value['app_key']) or
            not re.fullmatch(r'[1-9]\d{0,30}', value['adzone_id']) or
            not re.fullmatch(r'[^\s]{1,500}', value['app_secret'])):
        return jsonify(error='请填写 AppKey、AppSecret 和推广位 ID（也可粘贴完整 mm_… PID）'), 400
    try:
        CONFIG_PATH.parent.mkdir(exist_ok=True)
        tmp = CONFIG_PATH.with_suffix('.tmp')
        tmp.write_text(json.dumps(value, ensure_ascii=False), encoding='utf-8')
        tmp.replace(CONFIG_PATH)
    except OSError:
        return jsonify(error='本机配置保存失败，请检查目录权限'), 500
    return jsonify(public_config())


def sign(params, secret):
    message = secret + ''.join(k + str(params[k]) for k in sorted(params) if k != 'sign') + secret
    return hashlib.md5(message.encode('utf-8')).hexdigest().upper()


def search(keyword):
    value = config()
    if not all(value.values()):
        raise ValueError('淘宝 API 尚未配置：请先开通应用与接口权限，再填写 AppKey、AppSecret 和推广位 ID')
    params = dict(method=METHOD, app_key=value['app_key'], sign_method='md5', format='json', v='2.0',
                  timestamp=datetime.now(timezone(timedelta(hours=8))).strftime('%Y-%m-%d %H:%M:%S'),
                  q=keyword, adzone_id=value['adzone_id'], page_size='40', page_no='1',
                  biz_scene_id='2')
    params['sign'] = sign(params, value['app_secret'])
    try:
        response = requests.post(GATEWAY, data=params, timeout=(8, 25), allow_redirects=False)
        if response.status_code != 200:
            raise ValueError('淘宝接口 HTTP %s，请检查网络或稍后重试' % response.status_code)
        if len(response.content) > 4000000:
            raise ValueError('淘宝接口响应过大')
        body = response.json()
    except requests.RequestException:
        raise ValueError('淘宝接口连接失败，请检查网络后重试')
    except (TypeError, json.JSONDecodeError):
        raise ValueError('淘宝接口返回了无法解析的数据')
    if not isinstance(body, dict):
        raise ValueError('淘宝接口响应格式不正确')
    if 'error_response' in body:
        # Never echo upstream messages: they can contain request credentials.
        raise ValueError('淘宝拒绝了调用。请核对应用密钥、推广位、物料搜索升级版权限和消费者比价场景（biz_scene_id=2）权限，以及电脑时间')
    result = body.get('tbk_dg_material_optional_upgrade_response')
    if not isinstance(result, dict):
        raise ValueError('淘宝接口缺少商品查询结果')
    listing = result.get('result_list') or {}
    if not isinstance(listing, dict):
        raise ValueError('淘宝商品列表格式不正确')
    rows = listing.get('map_data', [])
    if not isinstance(rows, list):
        raise ValueError('淘宝商品列表格式不正确')
    return rows


def positive_price(value):
    try:
        number = float(value)
        return number if math.isfinite(number) and number > 0 else None
    except (ValueError, TypeError):
        return None


def offers_for(rows, name):
    offers = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        basic = row.get('item_basic_info') or {}
        price = row.get('price_promotion_info') or {}
        pub = row.get('publish_info') or {}
        if not all(isinstance(x, dict) for x in (basic, price, pub)):
            continue
        title = str(basic.get('title') or '')
        if (not model_matches(name, title) or rejected_title(title) or
                re.search(r'适用于|适用|租赁|租机|以租代购|分期首付|预售|海外版|港版|美版|日版|有锁', title) or
                row.get('presale_info')):
            continue
        category = str(basic.get('category_name') or '')
        if re.search(r'配件|保护|贴膜|手机壳|充电器|数据线|支架|电池|收纳', category):
            continue
        amount = positive_price(price.get('zk_final_price'))
        item_id = str(row.get('item_id') or '')
        merchant = str(basic.get('shop_title') or '')
        link = str(pub.get('click_url') or '')
        if link.startswith('//'):
            link = 'https:' + link
        parsed = urlparse(link)
        if (not amount or not item_id or not merchant or parsed.scheme != 'https' or
                parsed.username or parsed.password or parsed.hostname not in
                ('item.taobao.com', 'detail.tmall.com', 's.click.taobao.com', 'uland.taobao.com')):
            continue
        used = bool(re.search(r'二手|成新|翻新|已拆封|展示机|官换', title))
        conditions = ('淘宝联盟 API 的商品级标价（zk_final_price），未采用券后预估价、国补价、划线价或佣金。'
                      '可能对应最低配置，具体容量、套装、成色、库存、运费及最终支付金额需在平台核对；店名不代表旗舰店身份已认证。')
        offers.append(dict(platform='淘宝', merchant=merchant, variant=title + ' · 商品 ' + item_id,
                           amount=amount, item_condition='used' if used else 'new',
                           condition_note='二手/拆封，成色待核对' if used else '未标记二手，成色待核对',
                           price_basis='listing', price_type='淘宝API参考价', purchase_url=link,
                           conditions=conditions))
    return offers


@taobao_api.route('/api/taobao/test', methods=['POST'])
def test_connection():
    try:
        rows = search('手机')
        return jsonify(ok=True, message='淘宝接口调用成功，返回 %d 条搜索结果；这不代表每条都满足型号与预算条件' % len(rows))
    except ValueError as exc:
        return jsonify(error=str(exc)), 400


@taobao_api.route('/api/taobao/refresh', methods=['POST'])
def refresh():
    data = request.get_json(silent=True) or {}
    try:
        pid = int(data.get('product_id'))
        with connect() as db:
            product = db.execute("SELECT * FROM catalog_products WHERE id=? AND validation_status='verified'", (pid,)).fetchone()
        if not product:
            raise ValueError('产品不存在')
        if product['region'] not in ('中国大陆', '中国大陆官网'):
            raise ValueError('此产品不是国行资料，请选择中国大陆产品查询')
        rows = search(product['name'])
        offers = offers_for(rows, product['name'])
        if not offers:
            return jsonify(ok=True, count=0, message='调用成功，但没有型号、店铺、链接和标价证据完整的报价；未导入不确定商品')
        # Persist only normalized public evidence, never request params or credentials.
        snapshot = json.dumps(dict(method=METHOD, product=product['name'], offers=offers), ensure_ascii=False)
        count = save_offers(pid, DOC, snapshot, offers)
        return jsonify(ok=True, count=count, message='已导入 %d 条淘宝 API 参考报价，重新推荐后按价格匹配预算' % count)
    except (ValueError, TypeError, AttributeError) as exc:
        return jsonify(error=str(exc) if isinstance(exc, ValueError) else '请选择有效产品'), 400
