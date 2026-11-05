import json
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path
from flask import Flask

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import catalog
from crawl_catalog import extract, official, validate


class CatalogTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.original=catalog.DB
        catalog.DB=Path(self.temp.name)/'catalog.sqlite3'
        catalog.init_catalog()
        app=Flask(__name__); app.register_blueprint(catalog.catalog_api)
        self.client=app.test_client()
        with catalog.connect() as db:
            db.execute('INSERT INTO catalog_products(name,brand,category,region,source_url,source_title,collected_at,content_sha256,snapshot_path) VALUES(?,?,?,?,?,?,?,?,?)',('Test Phone','Test','手机','中国大陆','https://www.apple.com.cn/test','Test Phone','2026-10-20T00:00:00+00:00','hash','snapshot.html'))

    def tearDown(self):
        catalog.DB=self.original
        self.temp.cleanup()

    def test_filter_and_unknown_price(self):
        result=self.client.get('/api/catalog?category=手机').get_json()
        self.assertEqual(len(result['products']),1)
        self.assertIsNone(result['products'][0]['price'])
        self.assertEqual(self.client.get('/api/catalog?category=相机').get_json()['products'],[])
        self.assertEqual(self.client.get('/api/catalog?brand=%27%20OR%201=1--').get_json()['products'],[])
        self.assertEqual(self.client.get('/api/catalog/99999').status_code,404)

    def test_quarantine_not_exposed(self):
        with catalog.connect() as db: db.execute("UPDATE catalog_products SET validation_status='needs_review'")
        self.assertEqual(self.client.get('/api/catalog').get_json()['products'],[])
        self.assertEqual(self.client.get('/api/catalog/1').status_code,404)

    def test_shopping_links_and_subcategory_filter(self):
        from urllib.parse import urlparse,parse_qs
        with catalog.connect() as db:
            db.execute("UPDATE catalog_products SET subcategory='折叠屏手机',name='Phone A & B' WHERE id=1")
        data=self.client.get('/api/catalog?subcategory=折叠屏手机').get_json()
        self.assertEqual(len(data['products']),1)
        product=data['products'][0]
        self.assertIsNone(product['price'])
        self.assertEqual([l['platform'] for l in product['shopping_links']],['京东','淘宝','拼多多','闲鱼'])
        params=['keyword','q','search_key']
        for link,param in zip(product['shopping_links'],params):
            self.assertEqual(link['kind'],'平台搜索')
            self.assertEqual(parse_qs(urlparse(link['url']).query)[param][0],product['shopping_keyword'])
            self.assertEqual(urlparse(link['url']).scheme,'https')
        self.assertEqual(self.client.get('/api/catalog?subcategory=直板手机').get_json()['products'],[])
        detail=self.client.get('/api/catalog/1').get_json()
        self.assertEqual(detail['shopping_links'],product['shopping_links'])

    def test_source_uniqueness(self):
        with catalog.connect() as db:
            with self.assertRaises(sqlite3.IntegrityError):
                db.execute('INSERT INTO catalog_products SELECT * FROM catalog_products')

    def test_semantic_adapters(self):
        html='<title>Test Phone</title><main><div class="techspecs-section"><div class="techspecs-rowheader">芯片</div><p>A19</p></div><li class="large-accordion__item"><button><span class="large-accordion__title">电池</span></button><div class="large-accordion__content">5000 mAh（典型值）</div></li><div class="param-detail-item"><div class="item-left-heading">尺寸</div><div class="item-right">163 mm</div></div></main>'
        _,specs,_=extract(html)
        values={s['label']:s['value'] for s in specs}
        self.assertEqual(values['芯片'],'A19')
        self.assertEqual(values['电池'],'5000 mAh（典型值）')
        self.assertEqual(values['尺寸'],'163 mm')

    def test_accessory_and_oneplus_adapters(self):
        html='<title>OnePlus 13</title><main><div class="spec-content"><div class="title">Dimensions</div><div class="tips">Weight: 210g</div></div><div><span class="xm-text f-bold" data-key="spec_18">Charging</span><div>Battery: 475mAh</div></div></main>'
        _,specs,_=extract(html)
        values={s['label']:s['value'] for s in specs}
        self.assertEqual(values['Dimensions'],'Weight: 210g')
        self.assertEqual(values['Charging'],'Battery: 475mAh')

    def test_wrong_model_is_rejected(self):
        with self.assertRaises(ValueError):
            validate({'brand':'Apple','name':'AirPods 4'},'AirPods 5 - 技术规格',[{}]*4,'x'*400)
        self.assertFalse(official('https://apple.com.cn.attacker.example/specs'))
        self.assertTrue(official('https://support.apple.com/zh-cn/121203'))


if __name__=='__main__': unittest.main()
