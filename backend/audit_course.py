"""Validate real course examples without browser automation or external calls."""
import json,hashlib
from collections import Counter
from pathlib import Path
from app import app
from catalog import connect,ROOT

client=app.test_client();checks={}
for name,budget,weights in [('elder_2000',2000,None),('elder_3000',3000,None),('portable',8000,dict(performance=0,price=0,battery=0,portability=100,ease=0,camera=0,screen=0)),('endurance',8000,dict(performance=0,price=0,battery=100,portability=0,ease=0,camera=0,screen=0))]:
    profile=dict(category='手机',scenario='老人使用',budget=budget,needs='2000元手机，给父母用，希望字体大、操作简单、续航好。')
    if weights:profile['weights']=weights
    r=client.post('/api/recommend',json=profile);assert r.status_code==200
    result=r.get_json();assert all(p['price']<=budget and p['recommendation_eligible'] for p in result['products'])
    checks[name]=dict(counts=result['counts'],top=[dict(id=p['id'],name=p['name'],price=p['price'],score=p['score']) for p in result['products'][:3]])
assert len(checks['elder_2000']['top'])==3
assert checks['elder_2000']['counts']!=checks['elder_3000']['counts']
assert checks['portable']['top']!=checks['endurance']['top']
profile=dict(category='手机',scenario='老人使用',budget=2000,needs='给父母用，希望字体大、操作简单、续航好。',product_id=86,compare_id=87)
report=client.post('/api/report',json=profile).get_json()['document'];assert report['peer']['id']==87
(ROOT/'data'/'report_preview.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
for filename,pid,peer,category in [('report_warning_preview.json',83,86,'手机'),('report_unknown_preview.json',98,86,'手机'),('report_laptop_preview.json',127,143,'电脑')]:
    payload=dict(category=category,budget=2000 if category=='手机' else 6000,scenario='办公',needs='核对预算、配置和使用体验',product_id=pid,compare_id=peer)
    response=client.post('/api/report',json=payload);assert response.status_code==200
    (ROOT/'data'/filename).write_text(json.dumps(response.get_json()['document'],ensure_ascii=False,indent=2),encoding='utf-8')
pair=client.post('/api/compare',json=dict(profile,product_ids=[86,87])).get_json();checks['comparison']=pair['counts']
with connect() as db:
    rows=[dict(r) for r in db.execute('SELECT p.id,p.name,p.category,c.* FROM curated_products c JOIN catalog_products p ON p.id=c.product_id')]
    for p in rows:
        path=ROOT/'data'/'product_images'/p['image_url'].split('/')[-1]
        assert path.exists() and hashlib.sha256(path.read_bytes()).hexdigest()==p['image_sha256']
        assert client.get(p['image_url']).status_code==200
        assert db.execute('SELECT COUNT(*) FROM catalog_specs WHERE product_id=?',(p['id'],)).fetchone()[0]>=3
    counts=Counter(p['category'] for p in rows);assert len(counts)==5 and 20<=len(rows)<=30
    checks['dossiers']=dict(count=len(rows),categories=dict(counts))
checks['llm_configured']=client.get('/api/health').get_json()['llm_configured']
(ROOT/'data'/'course_validation.json').write_text(json.dumps(checks,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(checks,ensure_ascii=True))
