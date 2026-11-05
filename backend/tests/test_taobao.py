import copy
import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import taobao_api as tb
from app import app


class TaobaoTests(unittest.TestCase):
    def row(self, title='OPPO K15x 8GB 256GB'):
        return dict(item_id='opaque-id', item_basic_info=dict(title=title, shop_title='测试商店', category_name='手机'),
                    price_promotion_info=dict(zk_final_price='1699', final_promotion_price='999', reserve_price='1999'),
                    publish_info=dict(click_url='//item.taobao.com/item.htm?id=123'))

    def test_signature_matches_top_sorted_secret_envelope(self):
        self.assertEqual(tb.sign({'foo':'1','bar':'2','sign':'ignored'}, 'test'),
                         hashlib.md5(b'testbar2foo1test').hexdigest().upper())

    def test_reference_price_not_coupon_or_reserve(self):
        offer = tb.offers_for([self.row()], 'OPPO K15x')[0]
        self.assertEqual(offer['amount'], 1699)
        self.assertEqual(offer['price_basis'], 'listing')
        self.assertEqual(offer['purchase_url'], 'https://item.taobao.com/item.htm?id=123')
        self.assertIn('待核对', offer['condition_note'])

    def test_rejects_wrong_models_accessories_presales_and_bad_urls(self):
        for title in ['OPPO K15x Pro', 'OPPO K15x 手机壳', '适用 OPPO K15x', 'OPPO K15x 租机']:
            self.assertEqual(tb.offers_for([self.row(title)], 'OPPO K15x'), [])
        for field, value in [('presale_info', {'presale_deposit':'100'}),
                             ('publish_info', {'click_url':'https://evil.example/item'}),
                             ('price_promotion_info', {'zk_final_price':'NaN'})]:
            row=self.row(); row[field]=value
            self.assertEqual(tb.offers_for([row], 'OPPO K15x'), [])
        used=tb.offers_for([self.row('OPPO K15x 二手 99成新')], 'OPPO K15x')[0]
        self.assertEqual(used['item_condition'], 'used')

    def test_missing_config_never_contacts_platform(self):
        with patch.object(tb, 'config', return_value=dict(app_key='', app_secret='', adzone_id='')), patch.object(tb.requests, 'post') as post:
            with self.assertRaises(ValueError): tb.search('手机')
            post.assert_not_called()

    def test_contract_https_post_and_sensitive_errors_are_hidden(self):
        response=Mock(status_code=200,content=b'{}')
        response.json.return_value={'tbk_dg_material_optional_upgrade_response':{'result_list':{'map_data':[self.row()]}}}
        with patch.object(tb, 'config', return_value=dict(app_key='123',app_secret='DO-NOT-LEAK',adzone_id='456')), patch.object(tb.requests,'post',return_value=response) as post:
            self.assertEqual(len(tb.search('OPPO K15x')),1)
            args,kw=post.call_args
            self.assertEqual(args[0],tb.GATEWAY)
            self.assertEqual(kw['data']['biz_scene_id'],'2')
            self.assertNotIn('DO-NOT-LEAK',str(kw))
            self.assertFalse(kw['allow_redirects'])
            response.json.return_value={'error_response':{'msg':'DO-NOT-LEAK'}}
            with self.assertRaises(ValueError) as exc:tb.search('手机')
            self.assertNotIn('DO-NOT-LEAK',str(exc.exception))

    def test_settings_mask_secret_pid_and_reject_cross_origin(self):
        with tempfile.TemporaryDirectory() as folder, patch.object(tb,'CONFIG_PATH',Path(folder)/'settings.json'), patch.dict(tb.os.environ,{},clear=True):
            client=app.test_client()
            data=dict(app_key='123',app_secret='test-secret',adzone_id='mm_1_2_345')
            r=client.post('/api/taobao/config',json=data,environ_base={'REMOTE_ADDR':'127.0.0.1'})
            self.assertEqual(r.status_code,200)
            self.assertNotIn('test-secret',r.get_data(as_text=True))
            self.assertEqual(json.loads(r.data)['adzone_id'],'345')
            self.assertEqual(tb.config()['app_secret'],'test-secret')
            for headers in [{'Origin':'https://evil.example'}, {'Host':'evil.example'}, {'Sec-Fetch-Site':'cross-site'}]:
                self.assertEqual(client.post('/api/taobao/config',json=data,headers=headers,environ_base={'REMOTE_ADDR':'127.0.0.1'}).status_code,403)


if __name__=='__main__':unittest.main()
