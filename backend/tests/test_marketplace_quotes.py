import json
import sys
import unittest
from datetime import datetime,timezone
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import catalog
import test_recommendations as fixtures
from app import local_profile
from recommendations import recommendation
from marketplace_quotes import jsonld_offers,zol_offers,pdd_public_offers,save_offers
from store_sources import nuxt_state,oppo_product
from crawl_lenovo_list import parse_products


class MarketplaceTests(unittest.TestCase):
    setUp=fixtures.RealCatalogTests.setUp
    tearDown=fixtures.RealCatalogTests.tearDown
    offer=fixtures.RealCatalogTests.offer

    def quote(self,**changes):
        result=dict(platform='淘宝',merchant='店铺待核验',variant='样机 A 容量待核对',amount=1500,
                    item_condition='new',condition_note='成色待核对',price_basis='listing',price_type='平台参考价',purchase_url='',conditions='公开参考价，不保证配置与库存')
        result.update(changes);return result

    def test_reference_quote_is_conditional_and_can_be_disabled(self):
        save_offers(101,'https://detail.zol.com.cn/example.shtml','<title>quote evidence</title>',[self.quote()])
        p=recommendation({'budget':2000})[0]
        self.assertEqual(p['id'],101);self.assertEqual(p['recommendation_tier'],'reference')
        self.assertIn('待核对',p['budget_status']);self.assertIn('待核对',p['reason'])
        self.assertGreater(p['metrics']['price'],0)
        self.assertEqual(recommendation({'budget':2000,'include_reference':False}),[])

    def test_same_source_keeps_each_platform_price_separate(self):
        count=save_offers(101,'https://detail.zol.com.cn/example.shtml','<title>quote evidence</title>',
                          [self.quote(platform='京东',amount=1500),self.quote(platform='淘宝',amount=1600)])
        self.assertEqual(count,2)
        p=recommendation({'budget':2000})[0]
        self.assertEqual({o['platform'] for o in p['platform_quotes']},{'京东','淘宝'})

    def test_used_price_requires_explicit_opt_in(self):
        quote=self.quote(platform='闲鱼',item_condition='used',price_basis='direct',price_type='配置报价',condition_note='二手九成新')
        save_offers(102,'https://www.goofish.com/item?id=123','<title>used evidence</title>',[quote])
        self.assertEqual(recommendation({'budget':2000}),[])
        p=recommendation({'budget':2000,'include_used':True})[0]
        self.assertEqual(p['id'],102);self.assertIn('二手',p['budget_status']);self.assertEqual(p['offer']['condition_note'],'二手九成新')

    def test_newest_out_of_stock_offer_invalidates_old_price(self):
        self.offer(101,1500)
        with catalog.connect() as d:
            d.execute("""INSERT INTO retailer_offers(product_id,platform,merchant,variant,amount,region,price_type,conditions,source_url,observed_at,snapshot_path,availability)
                         VALUES(101,'品牌官网','官方店','128GB',1500,'中国大陆','配置报价','已缺货','https://example.com/offer',?,'snapshot','out_of_stock')""",(datetime.now(timezone.utc).isoformat(),))
        self.assertEqual(recommendation({'budget':2000}),[])

    def test_low_budget_and_unitted_budget_are_preserved(self):
        self.assertEqual(local_profile('200元耳机')['budget'],200)
        self.assertEqual(local_profile('预算2000，给父母买手机')['budget'],2000)
        self.assertEqual(local_profile('预算2k，买手机')['budget'],2000)
        self.assertTrue(local_profile('1500元，接受二手闲鱼手机')['include_used'])
        self.assertFalse(local_profile('1500元手机，不接受二手')['include_used'])

    def test_four_platform_jsonld_contract_and_masked_price_rejection(self):
        obj={'@type':'Product','name':'样机 A 8GB+128GB','sku':'123','offers':{'price':1500,'priceCurrency':'CNY','seller':{'name':'店铺'},'availability':'https://schema.org/InStock','itemCondition':'https://schema.org/NewCondition'}}
        def html():return '<script type="application/ld+json">'+json.dumps(obj)+'</script>'
        for host,platform in [('item.jd.com','京东'),('item.taobao.com','淘宝'),('mobile.yangkeduo.com','拼多多'),('www.goofish.com','闲鱼')]:
            self.assertEqual(jsonld_offers(html(),'样机 A','https://'+host+'/item')[0]['platform'],platform)
        obj['offers']['price']='1??9'
        with self.assertRaises(ValueError):jsonld_offers(html(),'样机 A','https://item.jd.com/item')
        obj['offers']['price']='NaN'
        with self.assertRaises(ValueError):jsonld_offers(html(),'样机 A','https://item.jd.com/item')

    def test_comparison_price_does_not_mix_pro_model(self):
        def row(title,amount):return '<div class="brand-seller-top"><span class="brand-name"><a title="'+title+'" href="https://s.click.taobao.com/t?id=1">'+title+'</a></span><div class="merchant-price"><a class="price">￥'+str(amount)+'</a></div></div>'
        html='<title>Redmi Note 14 报价</title>'+row('Redmi Note 14 Pro 手机',938)+row('Redmi Note 14 5G 手机',1128)
        offers=zol_offers(html,'REDMI Note 14（国行）')
        self.assertEqual([o['amount'] for o in offers],[1128])

    def test_phone_comparison_reads_primary_offer_not_related_product(self):
        html='<title>iQOO Z10x 报价</title><h1>iQOO Z10x(8GB/128GB)</h1><div class="select-mol b2c-jd"><a href="https://union-click.jd.com/jdc?e=jd_123"><span class="m-price">¥1174</span></a></div><li class="pk-b2c-jd"><a href="https://item.jd.com/456"><em>¥99</em></a></li>'
        offers=zol_offers(html,'iQOO Z10x')
        self.assertEqual([o['amount'] for o in offers],[1174])

    def test_pdd_uses_visible_matching_card_not_hidden_or_related_price(self):
        html='<script>var minimumPrice=100</script><div class="index_inline_card_wrapper__x"><div class="index_inline_goods_name__x">Redmi Note14 手机</div><div class="index_inline_default_price__x"><span>¥</span>1375<span>.</span>5</div></div><div class="index_inline_card_wrapper__x"><div class="index_inline_goods_name__x">手机壳</div><div class="index_inline_default_price__x">¥9.9</div></div>'
        self.assertEqual(pdd_public_offers(html,'REDMI Note 14（国行）','https://mobile.yangkeduo.com/')[0]['amount'],1375.5)

    def test_official_store_uses_full_price_not_coupon_price(self):
        p=dict(goodsSkuId=123,goodsSpuName='OPPO K15x',goodsTopCategoryName='手机',name='OPPO K15x 6GB+128GB',visible=1,
               baseAttributes=[{'groupName':'参数','attributes':[{'name':k,'value':[v]} for k,v in [('电池','6500mAh'),('重量','212g'),('屏幕','6.75英寸')]]}],
               attributes={'skuItems':[{'skuId':123,'stock':True,'key2':'6GB+128GB'}]},priceTag={'price':'1699','buyPrice':'1389'},price=1389)
        with patch('store_sources.nuxt_state',return_value={'data':[{'resData':p}]}):
            self.assertEqual(oppo_product('html','OPPO K15x',123)['amount'],1699)
            with self.assertRaises(ValueError):oppo_product('html','OPPO K15s',123)

    def test_state_decoder_does_not_execute_scripts(self):
        state=nuxt_state('<script>window.__NUXT__=(function(a){return {data:[a]}})({name:"safe"});</script>')
        self.assertEqual(state['data'][0]['name'],'safe')
        with self.assertRaises(ValueError):nuxt_state('<script>window.__NUXT__=(function(){return process.exit()})();</script>')

    def test_lenovo_current_listing_keeps_exact_sku_and_config(self):
        html='<ul class="productDetailUl"><li><div class="search_name"><a href="https://item.lenovo.com.cn/product/123.html">联想小新14 轻薄笔记本</a></div><div class="search_mes">i5-13420H/Windows 11/14英寸/16GB/512G SSD/集成显卡</div><div>￥5799</div></li></ul>'
        html=html.replace('<div class="search_mes">','<div class="search_mes"><a>').replace('集成显卡</div>','集成显卡</a></div>')
        p=parse_products(html)[0]
        self.assertEqual(p['amount'],5799);self.assertEqual(p['sku'],'123')
        self.assertTrue(any(s['label']=='内存' and s['value']=='16GB' for s in p['specs']))

    def test_quote_reader_rejects_unknown_hosts_before_network(self):
        with patch('marketplace_quotes.requests.Session') as session:
            response=self.client.post('/api/quotes/refresh',json={'product_id':101,'url':'http://127.0.0.1:9000/price'})
        self.assertEqual(response.status_code,400);session.assert_not_called()


if __name__=='__main__':unittest.main()
