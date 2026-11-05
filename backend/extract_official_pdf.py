"""Extract official technical PDF text while preserving table layout."""
import json
import sys
from pypdf import PdfReader

reader=PdfReader(sys.argv[1])
pages=[p.extract_text(extraction_mode='layout') or '' for p in reader.pages]
print(json.dumps(pages,ensure_ascii=True))
