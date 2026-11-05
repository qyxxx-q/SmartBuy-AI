import json,sys,tempfile,unittest
from datetime import datetime,timezone,timedelta
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import catalog
from app import app

class CourseFeatures(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.old=catalog.DB;catalog.DB=Path(self.temp.name)/'test.sqlite3';catalog.init_catalog()
        self.client=app.test_client();self.profile=dict(category='手机',budget=2000,scenario='办公',needs='手机')
        stamp=datetime.now(timezone.utc).isoformat()
        with catalog.connect() as db:
            for pid,price,weight,battery in ((1,1500,160,4000),(2,1900,230,6500),(3,None,200,5000),(4,3000,210,6000)):
                db.execute("INSERT INTO catalog_products(id,name,brand,category,region,source_url,source_title,collected_at,content_sha256,snapshot_path,spec_count) VALUES(?,?,'样机','手机','中国大陆',?,'参数',?,'hash','test.html',4)",(pid,'样机'+str(pid),'https://example.com/p'+str(pid),stamp))
                specs=[('重量',str(weight)+' g'),('电池容量',str(battery)+' mAh'),('屏幕刷新率','120 Hz' if pid==1 else '120Hz'),('屏幕亮度','1000 nit；HDR 峰值' if pid==1 else '1000 nit；户外峰值')]
                if pid==1:specs.append(('防护等级','IP68；实验室条件'))
                for label,value in specs:db.execute("INSERT INTO catalog_specs(product_id,section,label,value,source_url,collected_at) VALUES(?,'官方参数',?,?,?,?)",(pid,label,value,'https://example.com/p'+str(pid),stamp))
                if price:db.execute("INSERT INTO retailer_offers(product_id,platform,merchant,variant,amount,region,price_type,conditions,source_url,observed_at,snapshot_path) VALUES(?,'品牌官网','官方商城','8GB+256GB',?,'中国大陆','配置报价','公开全额标价',?,?,'price.html')",(pid,price,'https://example.com/buy'+str(pid),stamp))

    def tearDown(self):catalog.DB=self.old;self.temp.cleanup()

    def test_grouped_comparison_keeps_conditions_sources_and_unknowns(self):
        r=self.client.post('/api/compare',json=dict(self.profile,product_ids=[1,2]));self.assertEqual(r.status_code,200)
        data=r.get_json();rows={r['label']:r for g in data['groups'] for r in g['rows']}
        self.assertEqual(rows['屏幕刷新率']['state'],'same')
        self.assertEqual(rows['屏幕亮度']['state'],'different')
        self.assertEqual(rows['防护等级']['state'],'unknown')
        self.assertIsNone(rows['防护等级']['values'][1])
        self.assertEqual(rows['屏幕亮度']['values'][0]['source_url'],'https://example.com/p1')
        self.assertEqual(rows['屏幕亮度']['values'][1]['source_url'],'https://example.com/p2')
        self.assertEqual(sum(data['counts'][k] for k in ('same','different','unknown')),data['counts']['total'])
        self.assertEqual(self.client.post('/api/compare',json=dict(self.profile,product_ids=[1,1])).status_code,400)
        self.assertEqual(self.client.post('/api/compare',json=dict(self.profile,product_ids=[True,2])).status_code,400)

    def test_budget_counts_and_weight_changes_are_real(self):
        data=self.client.post('/api/recommend',json=self.profile).get_json()
        self.assertEqual(data['counts'],dict(eligible=2,pending_price=1,over_budget=1,total=4))
        self.assertEqual(data['process']['top_ids'],[p['id'] for p in data['products'][:3]])
        lower=self.client.post('/api/recommend',json=dict(self.profile,budget=1600)).get_json()
        self.assertEqual([p['id'] for p in lower['products']],[1])
        weights=dict(performance=0,price=0,battery=0,portability=100,ease=0,camera=0,screen=0)
        light=self.client.post('/api/recommend',json=dict(self.profile,weights=weights)).get_json()
        weights.update(portability=0,battery=100)
        endurance=self.client.post('/api/recommend',json=dict(self.profile,weights=weights)).get_json()
        self.assertEqual(light['products'][0]['id'],1);self.assertEqual(endurance['products'][0]['id'],2)

    def test_stale_prices_stay_excluded_and_curated_is_explicit_scope(self):
        with catalog.connect() as db:
            db.execute('UPDATE retailer_offers SET observed_at=?',((datetime.now(timezone.utc)-timedelta(days=8)).isoformat(),))
        data=self.client.post('/api/recommend',json=self.profile).get_json()
        self.assertEqual(data['products'],[]);self.assertEqual(data['counts']['pending_price'],4)
        self.assertEqual(self.client.post('/api/recommend',json=dict(self.profile,curated_only=True)).get_json()['process']['filtered_total'],0)

    def test_report_uses_explicit_two_products_and_warns_over_budget(self):
        r=self.client.post('/api/report',json=dict(self.profile,product_id=1,compare_id=4));self.assertEqual(r.status_code,200)
        d=r.get_json()['document'];self.assertEqual(d['peer']['id'],4)
        section=next(s for s in d['sections'] if s['title']=='两款怎么取舍')
        self.assertIn('样机4',section['body']);self.assertIn('超出预算',section['body']);self.assertIn('buy4',section['body'])
        self.assertEqual(d['comparison']['product_ids'],[1,4])
        self.assertFalse(any(s['title'].startswith('报价页面') for s in d['sections']))
        self.assertEqual(self.client.post('/api/report',json=dict(self.profile,product_id=1,compare_id=1)).status_code,400)

    def test_assistant_follows_selected_pair_with_candid_local_mode(self):
        with patch('assistant.call_llm',return_value=None):
            data=self.client.post('/api/chat',json=dict(profile=self.profile,product_id=1,compare_id=4,question='它和另一款有什么区别？')).get_json()
        self.assertEqual(data['mode'],'local');self.assertIn('样机1',data['answer']);self.assertIn('样机4',data['answer']);self.assertIn('超出预算',data['answer'])
        with patch('assistant.call_llm',return_value=None):
            data=self.client.post('/api/chat',json=dict(profile=self.profile,product_id=1,question='为什么考虑它？')).get_json()
        self.assertIn('参数',data['answer']);self.assertIn('样机1',data['answer'])

    def test_report_distinguishes_manual_object_from_system_choice(self):
        ranked=self.client.post('/api/recommend',json=self.profile).get_json()['products']
        selected=ranked[1]['id']
        d=self.client.post('/api/report',json=dict(self.profile,product_id=selected)).get_json()['document']
        self.assertEqual(d['version'],2);self.assertEqual(d['selection']['mode'],'manual')
        self.assertFalse(d['selection']['is_system_choice']);self.assertEqual(d['system_choice']['id'],ranked[0]['id'])
        self.assertEqual(d['selection']['rank'],2);self.assertEqual(len(d['reasons']),3)
        self.assertIsNone(d['budget']['accessories_amount'])
        source_ids={s['id'] for s in d['sources']}
        self.assertTrue(all(q['source_id'] in source_ids for q in d['quotes'] if q['active']))
        self.assertTrue(all(r['source_id'] in source_ids for r in d['reasons'] if r['source_id']))

    def test_report_unknown_and_expired_quotes_never_create_budget_balance(self):
        with catalog.connect() as db:
            db.execute('UPDATE retailer_offers SET observed_at=?',((datetime.now(timezone.utc)-timedelta(days=8)).isoformat(),))
        d=self.client.post('/api/report',json=dict(self.profile,product_id=1)).get_json()['document']
        self.assertEqual(d['decision']['tone'],'warning');self.assertIsNone(d['budget']['remaining'])
        self.assertFalse(d['quotes'][0]['active']);self.assertIsNotNone(d['quotes'][0]['historical'])
        self.assertFalse(d['selection']['is_system_choice']);self.assertIsNone(d['system_choice'])
        self.assertTrue(any(not r['known'] for r in d['reasons']))
        self.assertEqual(len(d['checklist']),3)

    def test_report_reference_quote_is_conditional_with_full_evidence(self):
        with catalog.connect() as db:db.execute("UPDATE retailer_offers SET price_basis='listing',price_type='商城展示参考价',availability='unknown' WHERE product_id=1")
        d=self.client.post('/api/report',json=dict(self.profile,product_id=1)).get_json()['document']
        self.assertEqual(d['decision']['tone'],'conditional')
        self.assertIn('参考价',d['budget']['label']);self.assertEqual(d['budget']['remaining'],500)
        self.assertEqual(d['quotes'][0]['variant'],'8GB+256GB')
        self.assertEqual(d['quotes'][0]['conditions'],'公开全额标价')

    def test_report_actions_follow_product_category(self):
        for category,keyword in [('手机','充电器'),('电脑','软件'),('平板','手写笔'),('耳机','试戴'),('相机','存储卡')]:
            with catalog.connect() as db:db.execute('UPDATE catalog_products SET category=? WHERE id=1',(category,))
            d=self.client.post('/api/report',json=dict(self.profile,category=category,product_id=1)).get_json()['document']
            self.assertIn(keyword,d['budget']['accessories']);self.assertIn(keyword,d['checklist'][0]['body'])
            self.assertEqual(d['profile']['category'],category)

    def test_report_keeps_price_precision_and_normalizes_accepted_weights(self):
        with catalog.connect() as db:db.execute('UPDATE retailer_offers SET amount=1499.5 WHERE product_id=1')
        response=self.client.post('/api/report',json=dict(self.profile,budget=2000.5,product_id=1,weights={'battery':'30'}))
        self.assertEqual(response.status_code,200);d=response.get_json()['document']
        self.assertIn('2,000.5元',d['title']);self.assertEqual(d['budget']['remaining'],501)
        self.assertEqual(d['profile']['weights']['battery'],30)
        self.assertIn('¥1,499.5',response.get_json()['report'])

if __name__=='__main__':unittest.main()
