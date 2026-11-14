#!/usr/bin/env python3
"""Tell Bing/Yandex/Seznam/Naver (IndexNow) about new pages so they get crawled
fast. Bing's index also feeds ChatGPT search and Copilot. Skips if the site URL
is still the placeholder."""
import json
import os
import sys
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
from common import load_config  # noqa: E402

cfg = load_config()
base = cfg["site_url"].rstrip("/")
if base.endswith("example.com"):
    print("site_url not set; skipping IndexNow")
    sys.exit(0)
path = os.path.join(ROOT, "data", "new_slugs.txt")
slugs = [s for s in open(path).read().split() if s] if os.path.exists(path) else []
urls = [f"{base}/recalls/{s}/" for s in slugs][:9000] + [f"{base}/", f"{base}/latest/"]
body = json.dumps({"host": base.split("//", 1)[1], "key": cfg["indexnow_key"],
                   "keyLocation": f"{base}/{cfg['indexnow_key']}.txt", "urlList": urls}).encode()
req = urllib.request.Request("https://api.indexnow.org/indexnow", data=body,
                             headers={"Content-Type": "application/json; charset=utf-8"})
try:
    with urllib.request.urlopen(req, timeout=30) as r:
        print("IndexNow:", r.status, len(urls), "urls")
except Exception as ex:  # never fail the run over this
    print("IndexNow failed:", ex)
