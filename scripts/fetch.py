#!/usr/bin/env python3
"""Fetch recent recalls from openFDA (food, drug, device) and CPSC, normalize
them, and merge into data/<source>/<YYYY-MM>.json. Stdlib only.

First run (empty data/) backfills `backfill_days`; later runs re-pull the last
`update_days` so status changes and late reports get picked up.
"""
import datetime as dt
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
from common import load_config, slugify, extract_states  # noqa: E402

DATA = os.path.join(ROOT, "data")
UA = "RecallLedger/1.0 (+public recall data aggregator)"
FDA_KEY = os.environ.get("OPENFDA_API_KEY", "")


def get_json(url, tries=4):
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
            with urllib.request.urlopen(req, timeout=60) as r:
                return json.loads(r.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            if e.code == 404:  # openFDA: no matches
                return None
            if i == tries - 1:
                raise
        except Exception:
            if i == tries - 1:
                raise
        time.sleep(3 * (i + 1))


def ymd(s):
    """'20260916' -> '2026-09-16'; ISO strings pass through truncated."""
    if not s:
        return None
    s = str(s)
    if re.fullmatch(r"\d{8}", s):
        return f"{s[:4]}-{s[4:6]}-{s[6:]}"
    return s[:10]


# ---------------- FDA ----------------
FDA_CATS = {"food": "food", "drug": "drug", "device": "device"}


def fetch_fda(kind, since):
    start = since.strftime("%Y%m%d")
    end = dt.date.today().strftime("%Y%m%d")
    out, skip = [], 0
    while True:
        q = {
            "search": f"report_date:[{start} TO {end}]",
            "limit": "1000",
            "skip": str(skip),
            "sort": "report_date:desc",
        }
        if FDA_KEY:
            q["api_key"] = FDA_KEY
        url = f"https://api.fda.gov/{kind}/enforcement.json?" + urllib.parse.urlencode(q)
        data = get_json(url)
        if not data:
            break
        res = data.get("results", [])
        out.extend(res)
        total = data.get("meta", {}).get("results", {}).get("total", 0)
        skip += len(res)
        if not res or skip >= total or skip >= 25000:
            break
        time.sleep(0.5)
    return [norm_fda(kind, r) for r in out if r.get("recall_number")]


def norm_fda(kind, r):
    rn = r["recall_number"]
    product = (r.get("product_description") or "").strip()
    dist = (r.get("distribution_pattern") or "").strip()
    states, nationwide = extract_states(dist)
    loc = ", ".join(x for x in [r.get("city"), r.get("state"), r.get("country")] if x)
    return {
        "id": f"fda-{kind}-{rn}".lower(),
        "slug": slugify(f"{kind}-{rn}-{product[:70]}"),
        "source": "FDA",
        "category": FDA_CATS[kind],
        "recall_number": rn,
        "event_id": r.get("event_id"),
        "title": short_title(product, r.get("recalling_firm")),
        "product": product,
        "reason": (r.get("reason_for_recall") or "").strip(),
        "hazard_level": r.get("classification"),
        "company": (r.get("recalling_firm") or "").strip(),
        "company_location": loc,
        "date": ymd(r.get("recall_initiation_date")) or ymd(r.get("report_date")),
        "report_date": ymd(r.get("report_date")),
        "classified_date": ymd(r.get("center_classification_date")),
        "status": r.get("status"),
        "voluntary": r.get("voluntary_mandated"),
        "distribution": dist,
        "states": states,
        "nationwide": nationwide,
        "quantity": r.get("product_quantity"),
        "codes": " ".join(x for x in [r.get("code_info"), r.get("more_code_info")] if x).strip(),
        "remedy": None,
        "retailers": [],
        "images": [],
        "injuries": None,
        "source_url": f"https://api.fda.gov/{kind}/enforcement.json?search=recall_number:%22{urllib.parse.quote(rn)}%22",
    }


def short_title(product, firm):
    p = re.split(r"[,;(]|\bNET\b|\bUPC\b", product, maxsplit=1)[0].strip() or product[:80]
    if len(p) > 90:
        p = p[:87].rsplit(" ", 1)[0] + "..."
    return f"{p} recall" + (f" ({firm.strip()})" if firm else "")


# ---------------- CPSC ----------------
def fetch_cpsc(since):
    q = {"format": "json", "RecallDateStart": since.isoformat(), "RecallDateEnd": dt.date.today().isoformat()}
    data = get_json("https://www.saferproducts.gov/RestWebServices/Recall?" + urllib.parse.urlencode(q)) or []
    return [norm_cpsc(r) for r in data if r.get("RecallNumber")]


def names(lst, key="Name"):
    return [x.get(key) for x in (lst or []) if x and x.get(key)]


def norm_cpsc(r):
    rn = str(r["RecallNumber"])
    prods = r.get("Products") or []
    product = "; ".join(p.get("Name") or "" for p in prods if p.get("Name")) or r.get("Title", "")
    units = "; ".join(p.get("NumberOfUnits") or "" for p in prods if p.get("NumberOfUnits"))
    models = "; ".join(p.get("Model") or "" for p in prods if p.get("Model"))
    upcs = names(r.get("ProductUPCs"), "UPC")
    firms = names(r.get("Manufacturers")) or names(r.get("Importers")) or names(r.get("Distributors"))
    hazards = names(r.get("Hazards"))
    remedies = names(r.get("Remedies"))
    remedy_opts = names(r.get("RemedyOptions"), "Option")
    title = (r.get("Title") or product).strip()
    return {
        "id": f"cpsc-{rn}".lower(),
        "slug": slugify(f"product-{rn}-{title[:70]}"),
        "source": "CPSC",
        "category": "consumer-product",
        "recall_number": rn,
        "event_id": str(r.get("RecallID") or ""),
        "title": title,
        "product": product,
        "reason": " ".join(hazards) or (r.get("Description") or "").strip(),
        "hazard_level": None,
        "company": ", ".join(firms),
        "company_location": ", ".join(names(r.get("ManufacturerCountries"), "Country")),
        "date": ymd(r.get("RecallDate")),
        "report_date": ymd(r.get("LastPublishDate")) or ymd(r.get("RecallDate")),
        "classified_date": None,
        "status": "Announced",
        "voluntary": None,
        "distribution": "Sold in the United States" + (
            " at " + ", ".join(names(r.get("Retailers"))) if r.get("Retailers") else ""),
        "states": [],
        "nationwide": True,
        "quantity": units,
        "codes": "; ".join(x for x in [("Models: " + models) if models else "", ("UPCs: " + ", ".join(upcs)) if upcs else ""] if x),
        "remedy": " ".join(remedies + remedy_opts).strip() or None,
        "retailers": names(r.get("Retailers")),
        "images": [{"url": i.get("URL"), "caption": i.get("Caption")} for i in (r.get("Images") or []) if i.get("URL")],
        "injuries": " ".join(names(r.get("Injuries"))) or None,
        "description": (r.get("Description") or "").strip(),
        "consumer_contact": (r.get("ConsumerContact") or "").strip(),
        "source_url": r.get("URL") or "https://www.cpsc.gov/Recalls",
    }


# ---------------- storage ----------------
def month_path(rec):
    src = rec["id"].split("-")[0] + ("-" + rec["category"] if rec["source"] == "FDA" else "")
    m = (rec.get("date") or rec.get("report_date") or "unknown")[:7]
    return os.path.join(DATA, src, f"{m}.json")


def merge(records):
    buckets = {}
    for r in records:
        buckets.setdefault(month_path(r), []).append(r)
    new = changed = 0
    new_slugs = []
    for path, recs in buckets.items():
        os.makedirs(os.path.dirname(path), exist_ok=True)
        cur = {}
        if os.path.exists(path):
            with open(path) as f:
                cur = json.load(f)
        for r in recs:
            old = cur.get(r["id"])
            if old is None:
                new += 1
                new_slugs.append(r["slug"])
                r["first_seen"] = dt.date.today().isoformat()
            elif old != {**r, "first_seen": old.get("first_seen")}:
                changed += 1
                r["first_seen"] = old.get("first_seen")
            else:
                continue
            cur[r["id"]] = r
        with open(path, "w") as f:
            json.dump(dict(sorted(cur.items())), f, indent=1, ensure_ascii=False)
    return new, changed, new_slugs


def main():
    cfg = load_config()
    empty = not any(f.endswith(".json") for _, _, fs in os.walk(DATA) for f in fs if f != "status.json")
    days = cfg["backfill_days"] if empty else cfg["update_days"]
    since = dt.date.today() - dt.timedelta(days=days)
    print(f"Fetching since {since} ({'backfill' if empty else 'update'})")

    all_recs, errors = [], []
    for kind in FDA_CATS:
        try:
            recs = fetch_fda(kind, since)
            print(f"  FDA {kind}: {len(recs)}")
            all_recs += recs
        except Exception as e:  # keep going if one source is down
            errors.append(f"fda-{kind}: {e}")
    try:
        recs = fetch_cpsc(since)
        print(f"  CPSC: {len(recs)}")
        all_recs += recs
    except Exception as e:
        errors.append(f"cpsc: {e}")

    new, changed, new_slugs = merge(all_recs)
    status = {
        "last_run": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "fetched": len(all_recs), "new": new, "changed": changed, "errors": errors,
    }
    with open(os.path.join(DATA, "status.json"), "w") as f:
        json.dump(status, f, indent=1)
    with open(os.path.join(DATA, "new_slugs.txt"), "w") as f:
        f.write("\n".join(new_slugs))
    print(json.dumps(status))
    if errors and not all_recs:
        sys.exit(1)


if __name__ == "__main__":
    main()
