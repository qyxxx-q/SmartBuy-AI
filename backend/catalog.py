"""Verified official specifications and attributable store prices."""
import json
import os
import tempfile
from contextlib import closing
import sqlite3
import re
from pathlib import Path
from flask import Blueprint, jsonify, request
from pricing import attach_price
from shopping import default_subcategory

ROOT = Path(__file__).resolve().parent
DB = ROOT / 'smartbuy.sqlite3'
CATEGORIES = ('手机', '电脑', '平板', '耳机', '相机')
catalog_api = Blueprint('catalog', __name__)


class CatalogConnection(sqlite3.Connection):
    def __exit__(self, *args):
        try:
            return super().__exit__(*args)
        finally:
            self.close()


def connect(path=None):
    db = sqlite3.connect(str(path or DB), timeout=20, factory=CatalogConnection)
    db.row_factory = sqlite3.Row
    db.execute('PRAGMA foreign_keys=ON')
    return db


def restore_bundled_catalog(path=None):
    """Build a fresh runtime DB from readable, catalog-only JSON records."""
    destination = ROOT / 'smartbuy.sqlite3'
    seed = ROOT / 'data' / 'seed'
    if path is not None or Path(DB) != destination or destination.exists() or not seed.is_dir():
        return
    tables = ('catalog_products', 'catalog_specs', 'crawl_runs', 'crawl_pages',
              'catalog_price_observations', 'retailer_offers', 'curated_products')
    handle, temporary = tempfile.mkstemp(prefix='catalog-seed-', suffix='.tmp', dir=str(ROOT))
    os.close(handle)
    try:
        with closing(sqlite3.connect(temporary)) as check:
            check.executescript((ROOT / 'catalog_schema.sql').read_text(encoding='utf-8'))
            for table in tables:
                rows = json.loads((seed / (table + '.json')).read_text(encoding='utf-8'))
                fields = [r[1] for r in check.execute('PRAGMA table_info(' + table + ')')]
                if any(set(row) != set(fields) for row in rows):
                    raise RuntimeError('Invalid seed columns: ' + table)
                names = ','.join(fields)
                placeholders = ','.join('?' for _ in fields)
                check.executemany('INSERT INTO ' + table + '(' + names + ') VALUES(' + placeholders + ')',
                                  [[row[field] for field in fields] for row in rows])
            check.commit()
            if check.execute('PRAGMA integrity_check').fetchone()[0] != 'ok' or check.execute('PRAGMA foreign_key_check').fetchall():
                raise RuntimeError('Bundled catalog failed integrity check')
        os.replace(temporary, destination)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def init_catalog(path=None):
    restore_bundled_catalog(path)
    with connect(path) as db:
        db.executescript((ROOT / 'catalog_schema.sql').read_text(encoding='utf-8'))
        columns={row[1] for row in db.execute('PRAGMA table_info(catalog_products)')}
        if 'validation_status' not in columns:
            db.execute("ALTER TABLE catalog_products ADD COLUMN validation_status TEXT NOT NULL DEFAULT 'verified'")
            db.execute("ALTER TABLE catalog_products ADD COLUMN validation_note TEXT NOT NULL DEFAULT ''")
        if 'subcategory' not in columns:
            db.execute("ALTER TABLE catalog_products ADD COLUMN subcategory TEXT NOT NULL DEFAULT ''")
        offer_columns={row[1] for row in db.execute('PRAGMA table_info(retailer_offers)')}
        for name,definition in [('item_condition',"TEXT NOT NULL DEFAULT 'new'"),('condition_note',"TEXT NOT NULL DEFAULT '全新'"),
                                ('price_basis',"TEXT NOT NULL DEFAULT 'direct'"),('purchase_url',"TEXT NOT NULL DEFAULT ''"),
                                ('availability',"TEXT NOT NULL DEFAULT 'in_stock'")]:
            if name not in offer_columns: db.execute('ALTER TABLE retailer_offers ADD COLUMN '+name+' '+definition)
        # One public comparison page can carry separate offers from several platforms.
        schema=db.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='retailer_offers'").fetchone()[0]
        legacy=r'UNIQUE\s*\(\s*product_id\s*,\s*source_url\s*,\s*variant\s*,\s*observed_at\s*\)'
        if re.search(legacy,schema,re.I):
            replacement=re.sub(legacy,'UNIQUE(product_id,platform,source_url,variant,item_condition,observed_at)',schema,flags=re.I)
            replacement=re.sub(r'CREATE TABLE\s+(?:IF NOT EXISTS\s+)?["`]?retailer_offers["`]?', 'CREATE TABLE retailer_offers_migrating',replacement,count=1,flags=re.I)
            fields=[r[1] for r in db.execute('PRAGMA table_info(retailer_offers)')]
            names=','.join(fields)
            db.execute(replacement)
            db.execute('INSERT INTO retailer_offers_migrating('+names+') SELECT '+names+' FROM retailer_offers')
            db.execute('DROP TABLE retailer_offers')
            db.execute('ALTER TABLE retailer_offers_migrating RENAME TO retailer_offers')
        for row in db.execute("SELECT id,name,category FROM catalog_products WHERE subcategory=''").fetchall():
            db.execute('UPDATE catalog_products SET subcategory=? WHERE id=?',(default_subcategory(dict(row)),row['id']))


@catalog_api.route('/api/catalog')
def list_catalog():
    clauses, values = ["validation_status='verified'"], []
    for key in ('category', 'brand', 'subcategory'):
        if request.args.get(key):
            clauses.append(key + '=?'); values.append(request.args[key])
    if request.args.get('curated')=='1':clauses.append('id IN (SELECT product_id FROM curated_products)')
    if request.args.get('q'):
        clauses.append('(name LIKE ? OR brand LIKE ?)')
        values.extend(['%' + request.args['q'][:100] + '%'] * 2)
    with connect() as db:
        rows = db.execute('SELECT id,name,brand,category,subcategory,region,source_url,source_title,collected_at,price,currency,price_note,spec_count FROM catalog_products WHERE ' + ' AND '.join(clauses) + ' ORDER BY category,brand,name', values).fetchall()
        counts = [dict(r) for r in db.execute("SELECT category,COUNT(*) count FROM catalog_products WHERE validation_status='verified' GROUP BY category")]
        brands = [r[0] for r in db.execute("SELECT DISTINCT brand FROM catalog_products WHERE validation_status='verified' ORDER BY brand")]
        subcategories=[dict(r) for r in db.execute("SELECT category,subcategory,COUNT(*) count FROM catalog_products WHERE validation_status='verified' GROUP BY category,subcategory ORDER BY category,subcategory")]
        runs = [dict(r) for r in db.execute('SELECT id,started_at,finished_at,success_count,failure_count FROM crawl_runs ORDER BY id DESC LIMIT 1')]
        products = [attach_price(db, dict(r)) for r in rows]
        curated_count=db.execute('SELECT COUNT(*) FROM curated_products').fetchone()[0]
    return jsonify(products=products, curated_count=curated_count,categories=list(CATEGORIES), counts=counts, brands=brands, subcategories=subcategories, latest_run=runs[0] if runs else None)


@catalog_api.route('/api/catalog/<int:product_id>')
def product_detail(product_id):
    with connect() as db:
        row = db.execute("SELECT * FROM catalog_products WHERE id=? AND validation_status='verified'", (product_id,)).fetchone()
        if not row: return jsonify(error='产品不存在'),404
        product = dict(row)
        attach_price(db, product)
        product['specifications'] = [dict(r) for r in db.execute('SELECT section,label,value,source_url FROM catalog_specs WHERE product_id=? ORDER BY id', (product_id,))]
    return jsonify(product)
