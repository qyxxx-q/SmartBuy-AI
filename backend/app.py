"""SmartBuy AI API. Run with: python app.py"""
import json
import re
from pathlib import Path

from flask import Flask, jsonify, request, send_from_directory

ROOT = Path(__file__).resolve().parent
DIST = ROOT.parent / 'frontend' / 'dist'
app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH']=12*1024*1024
from catalog import catalog_api, init_catalog
init_catalog()
app.register_blueprint(catalog_api)
from assistant import assistant_api, call_llm as llm_chat, public_config
app.register_blueprint(assistant_api)
from marketplace_quotes import quotes_api
app.register_blueprint(quotes_api)
from taobao_api import taobao_api
app.register_blueprint(taobao_api)
from comparison import comparison_api, compare_products
app.register_blueprint(comparison_api)

METRICS = ['performance', 'price', 'battery', 'portability', 'ease', 'camera', 'screen']
LABELS = {'performance': '性能', 'price': '价格', 'battery': '续航', 'portability': '便携', 'ease': '易用性', 'camera': '影像', 'screen': '屏幕'}
BASE_WEIGHTS = {'performance': 22, 'price': 23, 'battery': 14, 'portability': 12, 'ease': 12, 'camera': 7, 'screen': 10}
from recommendations import recommendation, buying_report
from scoring import scenario_weights, RULE_VERSION


from profiles import explicit_budget, local_profile


@app.route('/api/health', methods=['GET'])
def health():
    return jsonify(status='ok',llm_configured=public_config()['configured'],assistant=public_config(),scoring=RULE_VERSION)


@app.route('/')
def home():
    if not (DIST / 'index.html').exists():
        return '前端尚未构建，请在 frontend 目录运行 npm install 和 npm run build。', 503
    return send_from_directory(str(DIST), 'index.html')


@app.route('/assets/<path:filename>')
def assets(filename):
    return send_from_directory(str(DIST / 'assets'), filename)


@app.route('/api/product-images/<path:filename>')
def product_images(filename):
    return send_from_directory(str(ROOT / 'data' / 'product_images'), filename)


@app.route('/api/profile', methods=['POST'])
def profile():
    data = request.get_json(silent=True) or {}
    try:
        result = local_profile(data.get('text'))
    except ValueError as exc:
        return jsonify(error=str(exc)), 400
    try:
        raw = llm_chat([{'role':'system','content':'将数码产品购买需求解析为JSON，仅返回category(手机/电脑/平板/耳机/相机)、budget(人民币整数)、scenario(学习/办公/游戏/老人使用)、user_type、summary。不得虚构商品。'}, {'role':'user','content':str(data['text'])[:1000]}], True)
        if raw:
            parsed = json.loads(raw)
            for field in ('category','scenario','user_type','summary'):
                if isinstance(parsed.get(field), str) and parsed[field]: result[field] = parsed[field]
            if parsed.get('category') not in ('手机','电脑','平板','耳机','相机'): result['category'] = local_profile(data['text'])['category']
            if parsed.get('scenario') not in ('学习','办公','游戏','老人使用'): result['scenario'] = local_profile(data['text'])['scenario']
            # Explicit amounts supplied by the user take precedence over model guesses.
            if explicit_budget(str(data['text'])) is None and isinstance(parsed.get('budget'), (int,float)) and 1 <= parsed['budget'] <= 50000: result['budget'] = int(parsed['budget'])
            original=local_profile(data['text'])
            if original['scenario']=='老人使用': result['scenario']='老人使用';result['user_type']='长辈'
            if result['scenario']!=original['scenario']: result['weights']=scenario_weights(result['scenario'])
            result['source'] = '大语言模型'
    except Exception:
        result['source'] = '本地规则（模型暂不可用）'
    return jsonify(result)


@app.route('/api/recommend', methods=['POST'])
def recommend():
    try:
        payload = request.get_json(silent=True) or {}
        purpose=payload.get('purpose','recommend')
        if purpose not in ('recommend','compare','report'): raise ValueError('查询用途无效')
        all_products = recommendation(payload,include_unqualified=True)
        eligible=[p for p in all_products if p['recommendation_eligible']]
        pending=[p for p in all_products if p['recommendation_status']=='pending_price']
        over=[p for p in all_products if p['recommendation_status']=='over_budget']
        products=eligible if purpose=='recommend' else all_products
        with __import__('catalog').connect() as db:
            catalog_total=db.execute("SELECT COUNT(*) FROM catalog_products WHERE category=? AND validation_status='verified'",(payload.get('category','手机'),)).fetchone()[0]
        process={'category_total':catalog_total,'filtered_total':len(all_products),
                 'eligible':len(eligible),'pending_price':len(pending),'over_budget':len(over),
                 'weights':payload.get('weights') or scenario_weights(payload.get('scenario',''),str(payload.get('needs',''))),
                 'top_ids':[p['id'] for p in eligible[:3]]}
        return jsonify(products=products, count=len(products),pending_price=pending,over_budget=over,
                       process=process,
                       counts={'eligible':len(eligible),'pending_price':len(pending),'over_budget':len(over),'total':len(all_products)},
                       scoring_version=RULE_VERSION,
                       formula='优先以同地区、7天内的具体配置标价匹配预算。启用参考报价时，也提供有公开价格依据的核价候选，并降低预算维度得分；启用二手后才按二手报价匹配。无价格依据和超预算产品不进入TOP。未知参数不获加分。')
    except (ValueError, TypeError) as exc:
        return jsonify(error=str(exc)),400


@app.route('/api/report', methods=['POST'])
def report():
    data = request.get_json(silent=True) or {}
    try:
        products = recommendation(data,include_unqualified=data.get('product_id') is not None)
    except (ValueError,TypeError) as exc:
        return jsonify(error=str(exc)),400
    try:
        text, selected = buying_report(data, products, data.get('product_id'))
    except ValueError as exc:
        return jsonify(error=str(exc)),400
    document=None
    if selected:
        peer_id=data.get('compare_id')
        peer=next((p for p in products if p['id']==peer_id and p['id']!=selected['id']),None)
        if peer_id is not None and peer is None:return jsonify(error='对比产品不在当前品类或与报告对象相同'),400
        if peer is None:peer=next((p for p in products if p['id']!=selected['id'] and p['recommendation_eligible']),None)
        from reporting import build_report
        document=build_report(data,selected,peer,products)
        text='\n\n'.join(s['title']+'\n'+s['body'] for s in document['sections'])
    return jsonify(report=text,document=document,product=selected['name'] if selected else None,
                   product_id=selected['id'] if selected else None,source='官方参数与可追溯报价建议')


@app.route('/api/behavior', methods=['POST'])
def behavior():
    data = request.get_json(silent=True) or {}
    if data.get('action') not in ('view','favorite','recommend'): return jsonify(error='行为类型无效'),400
    try:
        from catalog import connect
        with connect() as db:
            if not db.execute("SELECT 1 FROM catalog_products WHERE validation_status='verified' AND id=?",(int(data.get('product_id')),)).fetchone(): raise ValueError('产品不存在')
            db.execute('INSERT INTO catalog_behaviors(product_id,action) VALUES(?,?)',(int(data['product_id']),data['action']))
    except (TypeError,ValueError) as exc: return jsonify(error=str(exc)),400
    return jsonify(status='ok')


if __name__ == '__main__':
    app.run(host='127.0.0.1',port=8000,debug=False)
