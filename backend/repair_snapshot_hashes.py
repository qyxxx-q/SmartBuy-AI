"""Preserve saved snapshot bytes and reconcile hashes after Windows newline conversion."""
import hashlib
from pathlib import Path
from catalog import ROOT,connect


def main():
    repaired=0
    with connect() as db:
        for row in db.execute('SELECT id,snapshot_path,content_sha256 FROM catalog_products').fetchall():
            path=ROOT/row['snapshot_path']
            if not path.exists():continue
            data=path.read_bytes();digest=hashlib.sha256(data).hexdigest()
            if digest==row['content_sha256']:continue
            corrected=path.with_name(digest+path.suffix);corrected.write_bytes(data)
            db.execute('UPDATE catalog_products SET snapshot_path=?,content_sha256=? WHERE id=?',(str(corrected.relative_to(ROOT)),digest,row['id']))
            repaired+=1
        for row in db.execute('SELECT DISTINCT snapshot_path FROM retailer_offers').fetchall():
            path=ROOT/row['snapshot_path']
            if not path.exists():continue
            data=path.read_bytes();digest=hashlib.sha256(data).hexdigest()
            if digest==path.stem:continue
            corrected=path.with_name(digest+path.suffix);corrected.write_bytes(data)
            db.execute('UPDATE retailer_offers SET snapshot_path=? WHERE snapshot_path=?',(str(corrected.relative_to(ROOT)),row['snapshot_path']))
    print('Reconciled catalog snapshot hashes:',repaired)


if __name__=='__main__':main()
