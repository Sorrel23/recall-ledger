"""Offline test: normalize sample FDA/CPSC records, merge, build, check output.
Run: python3 tests/test_pipeline.py"""
import json
import os
import shutil
import subprocess
import sys
import tempfile

SRC = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

FDA = [
    {"status": "Ongoing", "city": "Totowa", "state": "NJ", "country": "United States", "classification": "Class I",
     "product_type": "Food", "event_id": "99684", "recalling_firm": "EURO FOODS GROUP USA NJ INC",
     "voluntary_mandated": "Voluntary: Firm initiated",
     "distribution_pattern": "The adulterated product was distributed to the following states: VA, NY, NJ, MI",
     "recall_number": "H-1331-2026",
     "product_description": "Crown Farms Dried Suri Cut, 200 gm, in plastic pack, 25 packages per box, keep frozen",
     "product_quantity": "53 boxes",
     "reason_for_recall": "The firm imported and distributed dried ribbon fish that was not properly eviscerated prior to drying.",
     "recall_initiation_date": "20260801", "center_classification_date": "20260904", "report_date": "20260916",
     "code_info": "BATCH NO: 130 EF, 146 EF", "more_code_info": ""},
    {"status": "Ongoing", "city": "Los Angeles", "state": "CA", "country": "United States", "classification": "Class II",
     "product_type": "Food", "event_id": "99675", "recalling_firm": "L-Nutra Inc",
     "distribution_pattern": "Product is sold exclusively from the recalling firm's online website nationwide.",
     "recall_number": "H-1335-2026",
     "product_description": "Prolon Everyday Apulian Almond & Cocoa Spread, NET WT: 8.47 OZ. UPC: 50040360530",
     "product_quantity": "8,529 jars", "reason_for_recall": "Undeclared allergen (tree nuts): hazelnut, cashew, and pistachio.",
     "recall_initiation_date": "20260807", "center_classification_date": "20260910", "report_date": "20260916",
     "code_info": "Lot code: L2755 Expiration: 02 Jan 2027", "more_code_info": ""},
]
CPSC = [{
    "RecallID": 11060, "RecallNumber": "27082", "RecallDate": "2026-11-12T00:00:00",
    "Title": "Allstar Recalls Sharper Image Tabletop and Infinity Fire Pits Due to Risk of Serious Injury from Burn and Fire Hazards",
    "Description": "This recall involves tabletop fire pits.", "URL": "https://www.cpsc.gov/Recalls/2027/example",
    "ConsumerContact": "Allstar toll-free at 855-215-5032", "LastPublishDate": "2026-11-12T00:00:00",
    "Products": [{"Name": "Sharper Image Tabletop Fire Pits", "NumberOfUnits": "About 265,000", "Model": ""}],
    "Images": [{"URL": "https://www.cpsc.gov/s3fs-public/example.jpg", "Caption": "Fire pit"}],
    "Injuries": [{"Name": "Four injuries, including third-degree burns."}],
    "Manufacturers": [], "Importers": [{"Name": "Allstar Marketing Group, LLC"}], "Distributors": [],
    "Retailers": [{"Name": "Target"}, {"Name": "Walmart"}], "ManufacturerCountries": [{"Country": "China"}],
    "ProductUPCs": [], "Hazards": [{"Name": "Ignited flammable liquid can escape from the fire pits."}],
    "Remedies": [{"Name": "Refund"}], "RemedyOptions": [{"Option": "Refund"}],
}]


def main():
    tmp = tempfile.mkdtemp()
    repo = os.path.join(tmp, "repo")
    shutil.copytree(SRC, repo, ignore=shutil.ignore_patterns("public", "data", ".git"))
    os.makedirs(os.path.join(repo, "data"))
    sys.path.insert(0, os.path.join(repo, "scripts"))
    import fetch  # noqa: E402
    from common import extract_states  # noqa: E402

    assert extract_states("distributed to the following states: VA, NY, NJ, MI")[0] == ["MI", "NJ", "NY", "VA"]
    assert extract_states("Distributed nationwide")[1] is True
    assert extract_states("AL, GA, TN and OR")[0] == ["AL", "GA", "OR", "TN"]
    assert extract_states("PRODUCT WAS SHIPPED IN OR AROUND TEXAS")[0] == ["TX"]
    assert extract_states("West Virginia and Arkansas")[0] == ["AR", "WV"]

    recs = [fetch.norm_fda("food", r) for r in FDA] + [fetch.norm_cpsc(r) for r in CPSC]
    new, changed, _ = fetch.merge(recs)
    assert (new, changed) == (3, 0), (new, changed)
    assert fetch.merge(recs)[:2] == (0, 0)  # idempotent

    cfg = json.load(open(os.path.join(repo, "config.json")))
    cfg["keep_days"] = 100000
    json.dump(cfg, open(os.path.join(repo, "config.json"), "w"))
    out = subprocess.run([sys.executable, os.path.join(repo, "scripts", "build.py")], capture_output=True, text=True)
    print(out.stdout, out.stderr)
    assert out.returncode == 0
    pub = os.path.join(repo, "public")
    for f in ["index.html", "llms.txt", "robots.txt", "sitemap.xml", "sitemap-1.xml", "feed.xml", "api/latest.json",
              "state/nj/index.html", "state/tx/index.html", "category/food/index.html",
              "category/consumer-product/index.html", "topic/tree-nuts/index.html", "retailer/walmart/index.html", "topic/fire-burn/index.html", f"{cfg['indexnow_key']}.txt", "404.html"]:
        assert os.path.exists(os.path.join(pub, f)), f
    pages = os.listdir(os.path.join(pub, "recalls"))
    assert len(pages) == 3, pages
    nj = open(os.path.join(pub, "state/nj/index.html")).read()
    assert "Crown Farms" in nj and "Prolon" in nj  # named + nationwide
    tx = open(os.path.join(pub, "state/tx/index.html")).read()
    assert "Crown Farms" not in tx and "Prolon" in tx
    page = open(os.path.join(pub, "recalls", [p for p in pages if "h-1331" in p][0], "index.html")).read()
    assert "Class I is the most serious" in page and "FAQPage" in page and "Michigan" in page
    data = json.load(open(os.path.join(pub, "api/latest.json")))
    assert data["count"] == 3
    print("ALL TESTS PASSED; sample output in", pub)


if __name__ == "__main__":
    main()
