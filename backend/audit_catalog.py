import json
import hashlib
from catalog import connect,ROOT
with connect() as db:
    result={'counts':[dict(r) for r in db.execute("SELECT category,COUNT(*) count FROM catalog_products WHERE validation_status='verified' GROUP BY category")],
            'brands':[r[0] for r in db.execute("SELECT DISTINCT brand FROM catalog_products WHERE validation_status='verified' ORDER BY brand")],
            'products':[], 'snapshot_errors':[], 'missing_snapshots':[], 'parameter_count_errors':[],
            'quarantined':[dict(r) for r in db.execute("SELECT name,validation_note FROM catalog_products WHERE validation_status!='verified'")]}
    for p in db.execute("SELECT id,name,brand,spec_count,snapshot_path,content_sha256 FROM catalog_products WHERE validation_status='verified' ORDER BY id"):
        item=dict(p)
        item['sample']=[dict(r) for r in db.execute('SELECT label,substr(value,1,180) value FROM catalog_specs WHERE product_id=? LIMIT 3',(p['id'],))]
        result['products'].append(item)
        if not (ROOT/p['snapshot_path']).is_file():
            result['missing_snapshots'].append(p['id'])
        elif hashlib.sha256((ROOT/p['snapshot_path']).read_bytes()).hexdigest()!=p['content_sha256']:
            result['snapshot_errors'].append(p['id'])
        if db.execute('SELECT COUNT(*) FROM catalog_specs WHERE product_id=?',(p['id'],)).fetchone()[0]!=p['spec_count']:
            result['parameter_count_errors'].append(p['id'])
    result['integrity_check']=db.execute('PRAGMA integrity_check').fetchone()[0]
    result['foreign_key_errors']=[list(r) for r in db.execute('PRAGMA foreign_key_check')]
    result['specification_groups']=db.execute("SELECT COUNT(*) FROM catalog_specs s JOIN catalog_products p ON p.id=s.product_id WHERE p.validation_status='verified'").fetchone()[0]
print(json.dumps({k:v for k,v in result.items() if k!='products'},ensure_ascii=True,indent=2))
(ROOT/'data'/'catalog_audit.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
