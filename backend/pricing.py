"""Only dated, attributable offers; never turn missing prices into zero."""
from datetime import datetime, timezone
from shopping import attach_shopping


def attach_price(db, product, allow_used=False, budget=None, include_reference=True):
    attach_shopping(product)
    curated=db.execute('SELECT * FROM curated_products WHERE product_id=?',(product['id'],)).fetchone()
    product['curated']=dict(curated) if curated else None
    product['image_url']=curated['image_url'] if curated else None
    offers = [dict(r) for r in db.execute(
        'SELECT * FROM retailer_offers WHERE product_id=? ORDER BY observed_at DESC,id DESC',
        (product['id'],))]
    product.update(price=None, currency='CNY', offer=None, offers=offers,
                   price_note='暂未获得可核验的在售报价，不能判断是否符合预算。', history=[],platform_quotes=[])
    product['last_observed_offer']=offers[0] if offers else None
    fresh, seen = [], set()
    def region(value):
        return '中国大陆' if value.strip().lower() in ('中国大陆','中国大陆官网','中国内地','mainland china','china mainland') else value.strip().lower()
    for offer in offers:
        key=(offer['platform'],offer['source_url'],offer['variant'],offer.get('item_condition','new'))
        if key in seen: continue
        seen.add(key)
        try:
            age = (datetime.now(timezone.utc) - datetime.fromisoformat(offer['observed_at'])).total_seconds()
        except (TypeError,ValueError):
            continue
        if (0 <= age <= 7 * 86400 and offer['currency'] == 'CNY'
                and region(offer['region']) == region(product['region'])
                and (offer.get('availability','in_stock')=='in_stock' or (offer.get('price_basis')=='listing' and offer.get('availability')=='unknown'))):
            fresh.append(offer)
    # Keep each platform's actual offer separate, including used listings, for transparent comparison.
    for platform in ('京东','淘宝','拼多多','闲鱼','品牌官网'):
        candidates=[o for o in fresh if o['platform']==platform]
        for condition in ('new','used'):
            choices=[o for o in candidates if o.get('item_condition','new')==condition]
            if choices:
                chosen=min(choices,key=lambda o:(o.get('price_basis','direct')!='direct',o['amount']))
                product['platform_quotes'].append(chosen)
    fresh=[o for o in fresh if allow_used or o.get('item_condition','new')=='new']
    if not fresh:
        if offers:
            product['price_note'] = ('仅有二手报价，启用“接受二手”后可按二手价格匹配预算。' if product['platform_quotes'] else
                                    '没有同时满足 7 天有效期、人民币和同地区条件的报价，请到来源店铺重新确认。')
        return product
    # Prefer a concrete configuration over a family starting price.
    concrete = [o for o in fresh if o['price_type']=='配置报价' and o.get('price_basis','direct')=='direct']
    references=[o for o in fresh if o.get('price_basis')=='listing']
    within=[o for o in references if budget is not None and o['amount']<=budget]
    if include_reference and within and not any(o['amount']<=budget for o in concrete):
        chosen=min(within,key=lambda o:o['amount'])
    else: chosen = min(concrete or fresh,key=lambda o:o['amount'])
    product.update(price=chosen['amount'], currency=chosen['currency'], offer=chosen,
                   price_note=chosen['price_type']+'；'+chosen['variant']+'；'+chosen['conditions'])
    history = [o for o in offers if o['source_url'] == chosen['source_url']
               and o['platform'] == chosen['platform']
               and o['variant'] == chosen['variant'] and o['price_type'] == chosen['price_type']
               and o.get('item_condition','new') == chosen.get('item_condition','new')
               and o['currency'] == chosen['currency'] and o['region'] == chosen['region']]
    product['history'] = [{'observed_on':o['observed_at'], 'price':o['amount']} for o in reversed(history)]
    return product
