"""Reparse saved official snapshots without new network requests; quarantine mismatches."""
import json
from catalog import ROOT,connect,init_catalog
from crawl_catalog import extract,extract_pdf,validate,export_catalog

init_catalog()
sources={s['url']:s for s in json.loads((ROOT/'catalog_sources.json').read_text(encoding='utf-8'))}
with connect() as db:
    products=list(db.execute('SELECT * FROM catalog_products'))
    for p in products:
        try:
            source=sources.get(p['source_url'])
            if not source: raise ValueError('Source replaced after identity mismatch; retained for audit only')
            path=ROOT/p['snapshot_path']
            title,specs,body=extract_pdf(path) if path.suffix=='.pdf' else extract(path.read_text(encoding='utf-8'))
            validate(source,title,specs,body)
            db.execute('DELETE FROM catalog_specs WHERE product_id=?',(p['id'],))
            db.executemany('INSERT INTO catalog_specs(product_id,section,label,value,source_url,collected_at) VALUES(?,?,?,?,?,?)',[(p['id'],s['section'],s['label'],s['value'],p['source_url'],p['collected_at']) for s in specs])
            db.execute("UPDATE catalog_products SET spec_count=?,validation_status='verified',validation_note='' WHERE id=?",(len(specs),p['id']))
        except (ValueError, OSError) as exc:
            db.execute("UPDATE catalog_products SET validation_status='needs_review',validation_note=? WHERE id=?",(str(exc),p['id']))
            print(json.dumps({'quarantined':p['name'],'reason':str(exc)},ensure_ascii=True),flush=True)
print(json.dumps({'verified_products':export_catalog()}))
