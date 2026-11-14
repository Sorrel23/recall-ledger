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
import datetime as dt
import glob
import re

# Full resubmission on Sundays or when asked (manual run); otherwise only new pages.
full = os.environ.get("INDEXNOW_FULL") == "1" or dt.date.today().weekday() == 6
if full:
    urls = []
    for sm in sorted(glob.glob(os.path.join(ROOT, "public", "sitemap-*.xml"))):
        urls += re.findall(r"<loc>([^<]+)</loc>", open(sm).read())
else:
    path = os.path.join(ROOT, "data", "new_slugs.txt")
    slugs = [s for s in open(path).read().split() if s] if os.path.exists(path) else []
    urls = [f"{base}/recalls/{s}/" for s in slugs] + [f"{base}/", f"{base}/latest/"]
print("mode:", "full" if full else "new pages")
for i in range(0, len(urls), 9000):
    batch = urls[i:i + 9000]
    body = json.dumps({"host": base.split("//", 1)[1], "key": cfg["indexnow_key"],
                       "keyLocation": f"{base}/{cfg['indexnow_key']}.txt", "urlList": batch}).encode()
    req = urllib.request.Request("https://api.indexnow.org/indexnow", data=body,
                                 headers={"Content-Type": "application/json; charset=utf-8"})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            print("IndexNow:", r.status, len(batch), "urls")
    except Exception as ex:  # never fail the run over this
        print("IndexNow failed:", ex)
