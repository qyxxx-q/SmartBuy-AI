import json
import sys
import tempfile
import unittest
from unittest.mock import patch
from datetime import datetime, timedelta, timezone
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import catalog
from app import app, local_profile
from recommendations import recommendation, buying_report
from crawl_prices import apple_offers, marketplace_offers


class RealCatalogTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.original=catalog.DB
        catalog.DB=Path(self.temp.name)/'test.db'
        catalog.init_catalog()
        with catalog.connect() as db:
            for i,name,status in [(101,'样机 A','verified'),(102,'样机 B','verified'),(103,'旧型号','needs_review')]:
                db.execute('''INSERT INTO catalog_products(id,name,brand,category,region,source_url,source_title,collected_at,content_sha256,snapshot_path,validation_status)
                  VALUES(?,?,'品牌','手机','中国大陆',?,?,'2026-01-01','hash','snapshot',?)''',(i,name,'https://example.com/'+str(i),name,status))
                db.execute("INSERT INTO catalog_specs(product_id,section,label,value,source_url,collected_at) VALUES(?,'参数','电池','5000mAh，实验室条件','https://example.com','2026-01-01')",(i,))
        self.client=app.test_client()

    def tearDown(self):
        catalog.DB=self.original
        self.temp.cleanup()

    def offer(self,pid,amount,age=0,variant='128GB',kind='配置报价'):
        now=(datetime.now(timezone.utc)-timedelta(days=age)).isoformat()
        with catalog.connect() as db:
            db.execute("""INSERT INTO retailer_offers(product_id,platform,merchant,variant,amount,region,price_type,conditions,source_url,observed_at,snapshot_path)
              VALUES(?,'品牌官网','官方店',?,?,'中国大陆',?,'公开标价','https://example.com/offer',?,'snapshot')""",(pid,variant,amount,kind,now))

    def test_real_ids_unknown_and_expired_prices(self):
        self.offer(101,999,age=8)
        self.assertEqual(recommendation({'category':'手机','budget':2000}),[])
        products=recommendation({'category':'手机','budget':2000},include_unqualified=True)
        self.assertEqual({p['id'] for p in products},{101,102})
        self.assertTrue(all(p['price'] is None for p in products))
        self.assertTrue(all(p['metrics']['price'] is None for p in products))
        self.assertTrue(all(p['history']==[] for p in products))

    def test_budget_ranking_and_history_does_not_mix_variants(self):
        self.offer(101,3000,variant='256GB')
        self.offer(101,1500,variant='128GB')
        self.offer(102,2500)
        low=recommendation({'budget':2000})
        self.assertEqual(low[0]['id'],101)
        self.assertEqual(low[0]['price'],1500)
        self.assertEqual(len(low[0]['history']),1)
        self.assertEqual(len(low),1)
        all_products=recommendation({'budget':2000},include_unqualified=True)
        self.assertEqual(next(p for p in all_products if p['id']==102)['budget_status'],'超出预算')
        high=recommendation({'budget':4000})
        self.assertEqual(high[1]['budget_status'],'配置报价在预算内')

    def test_starting_price_does_not_prove_budget_fit(self):
        self.offer(101,1000,kind='官网起售价')
        self.assertEqual(recommendation({'budget':2000}),[])
        p=next(p for p in recommendation({'budget':2000},include_unqualified=True) if p['id']==101)
        self.assertIn('待确认',p['budget_status'])
        self.assertIsNone(p['metrics']['price'])

    def test_selected_report_and_behavior_use_catalog_ids(self):
        data={'category':'手机','budget':2000,'product_id':102,'needs':'给父母买手机','scenario':'老人使用'}
        response=self.client.post('/api/report',json=data)
        self.assertEqual(response.status_code,200)
        body=response.get_json()
        self.assertEqual(body['product_id'],102)
        self.assertIn('现在不能说它在预算内',body['report'])
        self.assertIn('给长辈多留一步',body['report'])
        self.assertGreater(len(body['report']),700)
        self.assertEqual(self.client.post('/api/behavior',json={'product_id':102,'action':'view'}).status_code,200)
        self.assertEqual(self.client.post('/api/behavior',json={'product_id':103,'action':'view'}).status_code,400)
        data['product_id']=999
        self.assertEqual(self.client.post('/api/report',json=data).status_code,400)

    def test_empty_and_new_categories(self):
        for text,category in [('2000元降噪耳机','耳机'),('10000元旅行相机','相机'),('6000元笔记本','电脑')]:
            self.assertEqual(local_profile(text)['category'],category)
        self.assertEqual(self.client.post('/api/report',json={'category':'相机'}).status_code,200)
        self.assertEqual(self.client.post('/api/chat',json={'profile':{'category':'相机'},'question':'推荐哪款'}).status_code,200)

    def test_explicit_subcategories_and_platform_links(self):
        self.assertEqual(local_profile('7000元游戏本')['subcategory'],'游戏笔记本')
        self.assertEqual(local_profile('10000元折叠屏手机')['subcategory'],'折叠屏手机')
        self.assertEqual(local_profile('1000元开放式耳机')['subcategory'],'开放式耳机')
        with catalog.connect() as db:
            db.execute("UPDATE catalog_products SET subcategory='折叠屏手机' WHERE id=102")
        products=recommendation({'category':'手机','subcategory':'折叠屏手机'},include_unqualified=True)
        self.assertEqual([p['id'] for p in products],[102])
        self.assertEqual(len(products[0]['shopping_links']),4)

    def test_elder_2000_budget_never_recommends_unpriced_or_expensive_flagship(self):
        with catalog.connect() as db:
            db.execute("UPDATE catalog_products SET name='iPhone 17 Pro' WHERE id=102")
            for pid,value in [(101,'8 GB'),(102,'16 GB')]:
                db.execute("INSERT INTO catalog_specs(product_id,section,label,value,source_url,collected_at) VALUES(?,'参数','RAM',?,'https://example.com','2026-01-01')",(pid,value))
        self.offer(101,1899)
        profile=local_profile('2000元手机，给父母用，希望字体大、操作简单、续航好。')
        self.assertGreater(profile['weights']['ease'],profile['weights']['performance'])
        for weights in (profile['weights'],dict(performance=100,price=0,battery=0,portability=0,ease=0,camera=0,screen=0)):
            profile['weights']=weights
            result=self.client.post('/api/recommend',json=profile).get_json()
            self.assertEqual([p['id'] for p in result['products']],[101])
            self.assertEqual([p['id'] for p in result['pending_price']],[102])
        self.offer(102,9999)
        result=self.client.post('/api/recommend',json=profile).get_json()
        self.assertEqual([p['id'] for p in result['products']],[101])
        self.assertEqual([p['id'] for p in result['over_budget']],[102])
        self.assertEqual([p['score'] for p in result['products']],sorted([p['score'] for p in result['products']],reverse=True))

    def test_no_qualified_candidate_has_no_automatic_report_but_comparison_works(self):
        result=self.client.post('/api/recommend',json={'budget':2000}).get_json()
        self.assertEqual(result['products'],[])
        self.assertEqual(result['counts'],dict(eligible=0,pending_price=2,over_budget=0,total=2))
        comparison=self.client.post('/api/recommend',json={'budget':2000,'purpose':'compare'}).get_json()
        self.assertEqual(len(comparison['products']),2)
        self.assertTrue(all(not p['recommendation_eligible'] for p in comparison['products']))
        report=self.client.post('/api/report',json={'budget':2000}).get_json()
        self.assertIsNone(report['document'])
        self.assertIn('暂不生成推荐结论',report['report'])
        explicit=self.client.post('/api/report',json={'budget':2000,'product_id':102}).get_json()
        self.assertIn('不属于本次预算内推荐',explicit['report'])

    def test_budget_boundary_latest_price_and_region(self):
        self.offer(101,2000)
        self.assertEqual([p['id'] for p in recommendation({'budget':2000})],[101])
        self.offer(101,2000.01)
        self.assertEqual(recommendation({'budget':2000}),[])
        self.offer(102,1000)
        with catalog.connect() as db:
            db.execute("UPDATE retailer_offers SET region='中国台湾' WHERE product_id=102")
        self.assertEqual(recommendation({'budget':2000}),[])

    def test_model_cannot_override_explicit_elder_budget(self):
        with patch('app.llm_chat',return_value=json.dumps({'category':'手机','budget':10000,'scenario':'游戏'})):
            profile=self.client.post('/api/profile',json={'text':'2000元手机，给父母用，操作简单'}).get_json()
        self.assertEqual(profile['budget'],2000)
        self.assertEqual(profile['scenario'],'老人使用')

    def test_crawler_rejects_wrong_model_and_related_prices(self):
        html='<title>购买 iPhone 18</title><p>iPhone 17 ¥5999</p>'
        with self.assertRaises(ValueError): apple_offers(html,'iPhone 17')
        with self.assertRaises(ValueError): marketplace_offers('<p>自营 ¥1999</p>','iPhone 17','官方店')
        product={'@type':'Product','name':'iPhone 17 256GB','sku':'123','offers':{'price':5999,'priceCurrency':'CNY','seller':{'name':'官方店'},'itemCondition':'https://schema.org/NewCondition','availability':'https://schema.org/InStock'}}
        def page():return '<script type="application/ld+json">'+json.dumps(product)+'</script>'
        self.assertEqual(marketplace_offers(page(),'iPhone 17','官方店')[0][1],5999)
        product['name']='99成新 iPhone 17 256GB'
        with self.assertRaises(ValueError): marketplace_offers(page(),'iPhone 17','官方店')


if __name__=='__main__': unittest.main()
