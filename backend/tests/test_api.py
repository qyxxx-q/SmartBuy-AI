import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app import app, local_profile, recommendation


class SmartBuyTests(unittest.TestCase):
    def setUp(self):
        self.client = app.test_client()

    def test_complete_purchase_flow(self):
        profile = self.client.post('/api/profile', json={'text':'我是大学生，需要6000元左右电脑用于编程，希望轻便。'})
        self.assertEqual(profile.status_code, 200)
        parsed = profile.get_json()
        self.assertEqual(parsed['category'], '电脑')
        self.assertEqual(parsed['budget'], 6000)
        results = self.client.post('/api/recommend', json=parsed)
        self.assertEqual(results.status_code, 200)
        products = results.get_json()['products']
        self.assertTrue(all(p['recommendation_eligible'] and p['price']<=6000 for p in products))
        self.assertEqual(len(products),results.get_json()['counts']['eligible'])
        self.assertTrue(all(p['source_url'].startswith('https://') for p in products))
        self.assertFalse(any('云川' in p['name'] for p in products))
        self.assertEqual(self.client.post('/api/report', json=parsed).status_code, 200)
        self.assertEqual(self.client.post('/api/chat', json={'question':'为什么推荐？','profile':parsed,'product_id':products[0]['id'] if products else None}).status_code, 200)

    def test_missing_prices_are_not_zero(self):
        products = recommendation({'category':'手机','budget':1800},include_unqualified=True)
        for product in products:
            if product['price'] is None:
                self.assertIsNone(product['metrics']['price'])
                self.assertEqual(product['budget_status'],'待核价')
            else:
                self.assertGreater(product['price'],0)

    def test_invalid_input(self):
        self.assertEqual(self.client.post('/api/profile',json={'text':''}).status_code,400)
        self.assertEqual(self.client.post('/api/recommend',json={'category':'手机','budget':0}).status_code,400)

    def test_page_is_served_by_backend(self):
        page = self.client.get('/')
        self.assertEqual(page.status_code, 200)
        self.assertIn(b'SmartBuy AI', page.data)
        page.close()


if __name__ == '__main__': unittest.main()
