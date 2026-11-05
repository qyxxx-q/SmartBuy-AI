PRAGMA foreign_keys=ON;
CREATE TABLE IF NOT EXISTS catalog_products (
 id INTEGER PRIMARY KEY, name TEXT NOT NULL, brand TEXT NOT NULL,
 category TEXT NOT NULL CHECK(category IN ('手机','电脑','平板','耳机','相机')),
 region TEXT NOT NULL, source_url TEXT NOT NULL UNIQUE, source_title TEXT NOT NULL,
 collected_at TEXT NOT NULL, content_sha256 TEXT NOT NULL, snapshot_path TEXT NOT NULL,
 price REAL CHECK(price IS NULL OR price>=0), currency TEXT,
 price_note TEXT NOT NULL DEFAULT '官网参数页未提供可核验的具体配置价格',
 spec_count INTEGER NOT NULL DEFAULT 0,
 validation_status TEXT NOT NULL DEFAULT 'verified', validation_note TEXT NOT NULL DEFAULT '',
 subcategory TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS catalog_specs (
 id INTEGER PRIMARY KEY, product_id INTEGER NOT NULL REFERENCES catalog_products(id) ON DELETE CASCADE,
 section TEXT NOT NULL, label TEXT NOT NULL, value TEXT NOT NULL,
 source_url TEXT NOT NULL, collected_at TEXT NOT NULL,
 UNIQUE(product_id,section,label)
);
CREATE TABLE IF NOT EXISTS crawl_runs (
 id INTEGER PRIMARY KEY, started_at TEXT NOT NULL, finished_at TEXT,
 success_count INTEGER NOT NULL DEFAULT 0, failure_count INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS crawl_pages (
 id INTEGER PRIMARY KEY, run_id INTEGER NOT NULL REFERENCES crawl_runs(id), url TEXT NOT NULL,
 status TEXT NOT NULL, http_status INTEGER, message TEXT NOT NULL, collected_at TEXT NOT NULL,
 robots_status TEXT, content_sha256 TEXT
);
CREATE TABLE IF NOT EXISTS catalog_price_observations (
 id INTEGER PRIMARY KEY, product_id INTEGER NOT NULL REFERENCES catalog_products(id),
 observed_at TEXT NOT NULL, variant TEXT NOT NULL, amount REAL NOT NULL CHECK(amount>=0),
 currency TEXT NOT NULL, region TEXT NOT NULL, source_url TEXT NOT NULL,
 UNIQUE(product_id,observed_at,variant,source_url)
);
CREATE INDEX IF NOT EXISTS idx_catalog_filters ON catalog_products(category,brand);
CREATE INDEX IF NOT EXISTS idx_catalog_specs ON catalog_specs(product_id);
CREATE TABLE IF NOT EXISTS retailer_offers (
 id INTEGER PRIMARY KEY, product_id INTEGER NOT NULL REFERENCES catalog_products(id),
 platform TEXT NOT NULL, merchant TEXT NOT NULL, variant TEXT NOT NULL,
 amount REAL NOT NULL CHECK(amount>0), currency TEXT NOT NULL DEFAULT 'CNY',
 region TEXT NOT NULL, price_type TEXT NOT NULL, conditions TEXT NOT NULL,
 source_url TEXT NOT NULL, observed_at TEXT NOT NULL, snapshot_path TEXT NOT NULL,
 item_condition TEXT NOT NULL DEFAULT 'new', condition_note TEXT NOT NULL DEFAULT '全新',
 price_basis TEXT NOT NULL DEFAULT 'direct', purchase_url TEXT NOT NULL DEFAULT '',
 availability TEXT NOT NULL DEFAULT 'in_stock',
 UNIQUE(product_id,platform,source_url,variant,item_condition,observed_at)
);
CREATE TABLE IF NOT EXISTS catalog_behaviors (
 id INTEGER PRIMARY KEY, product_id INTEGER NOT NULL REFERENCES catalog_products(id),
 action TEXT NOT NULL, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS curated_products (
 product_id INTEGER PRIMARY KEY REFERENCES catalog_products(id),
 image_url TEXT NOT NULL, image_source_url TEXT NOT NULL,
 image_sha256 TEXT NOT NULL, image_collected_at TEXT NOT NULL,
 configuration TEXT NOT NULL, note TEXT NOT NULL,
 curated_at TEXT NOT NULL
);
