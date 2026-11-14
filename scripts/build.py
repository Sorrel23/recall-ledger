#!/usr/bin/env python3
"""Build the static site into public/ from data/. Stdlib only, so it runs in the
Cloudflare Pages build image and in GitHub Actions without installs."""
import datetime as dt
import glob
import html
import json
import os
import re
import shutil
import sys
from email.utils import format_datetime

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
from common import STATES, load_config, slugify  # noqa: E402

CFG = load_config()
OUT = os.path.join(ROOT, "public")
BASE = CFG["site_url"].rstrip("/")
NAME = CFG["site_name"]
TODAY = dt.date.today()
e = html.escape

CAT_LABEL = {"food": "Food", "drug": "Drug", "device": "Medical device", "consumer-product": "Consumer product"}
CAT_AGENCY = {"food": "U.S. Food and Drug Administration (FDA)", "drug": "U.S. Food and Drug Administration (FDA)",
              "device": "U.S. Food and Drug Administration (FDA)",
              "consumer-product": "U.S. Consumer Product Safety Commission (CPSC)"}
CLASS_TEXT = {
    "Class I": "Class I is the most serious level: FDA considers there is a reasonable probability that using or being exposed to this product will cause serious health problems or death.",
    "Class II": "Class II is the middle level: using or being exposed to this product may cause temporary or medically reversible health problems, and the chance of serious harm is remote.",
    "Class III": "Class III is the least serious level: using or being exposed to this product is not likely to cause health problems, but it breaks FDA rules.",
}
TOPICS = {
    "listeria": ("Listeria", r"listeria"), "salmonella": ("Salmonella", r"salmonella"),
    "e-coli": ("E. coli", r"e\.?\s?coli|STEC|O157"), "botulism": ("Botulism", r"botulism|botulinum"),
    "undeclared-allergens": ("Undeclared allergen", r"undeclared|allergen"),
    "peanut": ("Peanut allergen", r"peanut"), "milk": ("Milk allergen", r"undeclared[^.]*\bmilk\b|\bmilk allergen|dairy"),
    "egg": ("Egg allergen", r"undeclared[^.]*\begg"), "soy": ("Soy allergen", r"undeclared[^.]*\bsoy"),
    "wheat-gluten": ("Wheat or gluten", r"undeclared[^.]*\b(wheat|gluten)"), "tree-nuts": ("Tree nut allergen", r"tree nut|almond|cashew|walnut|pecan|hazelnut|pistachio"),
    "sesame": ("Sesame allergen", r"sesame"), "shellfish-fish": ("Fish or shellfish allergen", r"undeclared[^.]*\b(shellfish|shrimp|crab|fish|anchov)"),
    "foreign-material": ("Foreign material (metal, plastic, glass)", r"foreign (material|object|matter)|metal|plastic piece|glass"),
    "mold": ("Mold", r"\bmold\b|mould"), "lead": ("Lead", r"\blead\b"), "contamination": ("Microbial contamination", r"microbial|bacteria|contaminat"),
    "sterility": ("Sterility problems", r"steril"), "mislabeling": ("Mislabeling", r"mislabel|label(ing)? error|incorrect label"),
    "fire-burn": ("Fire and burn hazard", r"\bfire\b|burn"), "choking": ("Choking hazard", r"chok"),
    "fall-injury": ("Fall and injury hazard", r"\bfall\b|tip[- ]over|entrap"), "infants-children": ("Infant and children's products", r"infant|baby|child|toddler|crib"),
    "supplements": ("Dietary supplements", r"supplement"), "pet-food": ("Pet food", r"\bpet\b|dog|cat food|animal food"),
}
files_written = 0


# ---------------- helpers ----------------
def write(rel, content):
    global files_written
    path = os.path.join(OUT, rel)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    files_written += 1


def url(rel):
    return f"{BASE}/{rel}".rstrip("/") + ("/" if not rel.endswith((".xml", ".txt", ".json")) and rel else "")


def nice_date(d):
    try:
        return dt.date.fromisoformat(d).strftime("%B %-d, %Y")
    except Exception:
        return d or "unknown"


def month_label(m):
    try:
        return dt.date.fromisoformat(m + "-01").strftime("%B %Y")
    except Exception:
        return "an unknown month"


CSS = """body{font:16px/1.55 system-ui,-apple-system,Segoe UI,Roboto,sans-serif;max-width:860px;margin:0 auto;padding:0 16px;color:#1b1b1b;background:#fff}
header{border-bottom:2px solid #b42318;padding:14px 0;margin-bottom:18px}header a{color:#1b1b1b;text-decoration:none;font-weight:700;font-size:20px}
nav a{margin-right:14px;font-size:14px}a{color:#0b57d0}h1{font-size:26px;line-height:1.25}h2{font-size:19px;margin-top:28px}
.tag{display:inline-block;font-size:12px;padding:2px 8px;border-radius:10px;background:#eee;margin-right:6px}
.c1{background:#fde2e1;color:#8a1c12}.c2{background:#fff1d6;color:#7a4b00}.c3{background:#e7f0e3;color:#2d5a1e}
table{border-collapse:collapse;width:100%;font-size:14px}td,th{border-bottom:1px solid #e5e5e5;padding:7px 6px;text-align:left;vertical-align:top}
.facts td:first-child{width:200px;color:#555}ul.list{padding-left:18px}ul.list li{margin:6px 0}
footer{margin:40px 0 30px;font-size:13px;color:#666;border-top:1px solid #eee;padding-top:12px}.pager a{margin-right:10px}"""


def page(title, desc, canon, body, jsonld=None):
    ld = "".join(f'<script type="application/ld+json">{json.dumps(j, ensure_ascii=False)}</script>' for j in (jsonld or []))
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{e(title)}</title><meta name="description" content="{e(desc[:300])}">
<link rel="canonical" href="{e(canon)}"><link rel="alternate" type="application/rss+xml" title="{e(NAME)}" href="{BASE}/feed.xml">
<style>{CSS}</style>{ld}</head><body>
<header><a href="/">{e(NAME)}</a><nav><a href="/latest/">Latest</a><a href="/category/food/">Food</a><a href="/category/drug/">Drugs</a><a href="/category/device/">Devices</a><a href="/category/consumer-product/">Products</a><a href="/state/">By state</a><a href="/topic/">By hazard</a><a href="/api/">Data API</a></nav></header>
<main>{body}</main>
<footer>{e(NAME)} republishes public recall records from the FDA (openFDA) and the CPSC, rewritten in plain English. It is not a government site. Always confirm details with the official source linked on each page. Updated {TODAY.isoformat()}.</footer>
</body></html>"""


def class_tag(r):
    hl = r.get("hazard_level")
    cls = {"Class I": "c1", "Class II": "c2", "Class III": "c3"}.get(hl, "")
    return f'<span class="tag {cls}">{e(hl)}</span>' if hl else ""


def clip(t, n):
    return t if len(t) <= n else t[:n].rsplit(" ", 1)[0].rstrip(",;:") + "..."


def row(r):
    return (f'<li><a href="/recalls/{r["slug"]}/">{e(r["title"])}</a><br>'
            f'<span class="tag">{e(CAT_LABEL[r["category"]])}</span>{class_tag(r)}'
            f'<small>Reported {e(nice_date(r.get("report_date") or r["date"]))} &middot; {e(clip(r["reason"] or "", 160))}</small></li>')


def listing(rel_base, title, desc, recs, intro=""):
    size = CFG["page_size"]
    pages = max(1, -(-len(recs) // size))
    for p in range(1, pages + 1):
        chunk = recs[(p - 1) * size: p * size]
        rel = rel_base if p == 1 else f"{rel_base}page/{p}/"
        pager = '<p class="pager">' + (f'<a href="/{rel_base}{"" if p == 2 else f"page/{p-1}/"}">&larr; Newer</a>' if p > 1 else "") + \
                (f'<a href="/{rel_base}page/{p+1}/">Older &rarr;</a>' if p < pages else "") + "</p>"
        t = title + (f" (page {p})" if p > 1 else "")
        body = f"<h1>{e(t)}</h1>{intro if p == 1 else ''}<p>{len(recs)} recalls.</p><ul class='list'>{''.join(row(r) for r in chunk)}</ul>{pager}"
        write(rel + "index.html", page(f"{t} | {NAME}", desc, url(rel), body))


# ---------------- record page ----------------
def what_to_do(r):
    if r.get("remedy"):
        return r["remedy"]
    if r["category"] == "drug":
        return ("Check the product name, lot number and expiration date on your package against the codes above. "
                "If they match, do not stop taking a prescription medicine without talking to your doctor or pharmacist first; "
                "ask them about a replacement. Return or dispose of the product as your pharmacy advises.")
    if r["category"] == "device":
        return ("Check the model, lot or serial numbers above against your device. If yours is affected, contact the "
                "manufacturer or your healthcare provider before you stop using a device you rely on.")
    return ("Check the product name and the codes above against what you have. If they match, do not eat or use it. "
            "Throw it away or return it to the store where you bought it, and contact the recalling company with questions.")


def record_page(r):
    cat = CAT_LABEL[r["category"]]
    where = r["distribution"] or "Not stated"
    if r["states"]:
        where += " (states named: " + ", ".join(STATES[s] for s in r["states"]) + ")"
    facts = [
        ("Recall number", r["recall_number"]), ("Category", cat), ("Agency", CAT_AGENCY[r["category"]]),
        ("Severity", r.get("hazard_level") or "Not classified"), ("Status", r.get("status")),
        ("Recall started", nice_date(r["date"])), ("Reported", nice_date(r.get("report_date"))),
        ("Company", r["company"]), ("Company location", r.get("company_location")),
        ("Initiated by", r.get("voluntary")), ("Quantity", r.get("quantity")),
        ("Sold at", ", ".join(r.get("retailers") or [])), ("Injuries reported", r.get("injuries")),
    ]
    facts_html = "".join(f"<tr><td>{e(k)}</td><td>{e(str(v))}</td></tr>" for k, v in facts if v)
    sev = CLASS_TEXT.get(r.get("hazard_level") or "", "")
    if r["category"] == "consumer-product":
        sev = "CPSC does not assign severity classes. Read the hazard and injury details above."
    company_link = f'<a href="/company/{slugify(r["company"])}/">{e(r["company"])}</a>' if r["company"] else "the company"
    summary = (f"{r['company'] or 'A company'} is recalling {r['product'][:300]}. "
               f"Reason: {(r['reason'] or 'not stated').rstrip('. ')}.")
    imgs = "".join(f'<figure><img src="{e(i["url"])}" alt="{e(i.get("caption") or r["title"])}" style="max-width:100%" loading="lazy"><figcaption>{e(i.get("caption") or "")}</figcaption></figure>'
                   for i in (r.get("images") or [])[:3])
    q1 = f"Is {r['title'].replace(' recall', '')} recalled?"
    a1 = (f"Yes. {summary} The recall started {nice_date(r['date'])} and its status is "
          f"{(r.get('status') or 'unknown').lower()}. Recall number {r['recall_number']}.")
    body = f"""<h1>{e(r['title'])}</h1>
<p><span class="tag">{e(cat)}</span>{class_tag(r)}<span class="tag">{e(r.get('status') or '')}</span></p>
<p><strong>Summary:</strong> {e(summary)}</p>
<h2>What is being recalled</h2><p>{e(r['product'])}</p>
<h2>Why</h2><p>{e(r['reason'] or 'Not stated.')}</p>
{f"<p>{e(r['description'])}</p>" if r.get('description') else ''}
<h2>How serious is it</h2><p>{e(sev) or 'Not classified yet.'}</p>
<h2>Where it was sold</h2><p>{e(where)}</p>
<h2>How to tell if yours is affected</h2><p>{e(r.get('codes') or 'No lot or model codes were published. Match the product description above.')}</p>
<h2>What to do</h2><p>{e(what_to_do(r))}</p>
{f"<p><strong>Contact:</strong> {e(r['consumer_contact'])}</p>" if r.get('consumer_contact') else ''}
{imgs}
<h2>Recall facts</h2><table class="facts">{facts_html}</table>
<p>More recalls from {company_link} &middot; <a href="/category/{r['category']}/">all {e(cat.lower())} recalls</a>
&middot; <a href="/month/{(r['date'] or 'unknown')[:7]}/">recalls from {e(month_label((r['date'] or 'unknown')[:7]))}</a></p>
<p><a href="{e(r['source_url'])}" rel="nofollow">Official {e(r['source'])} record</a></p>"""
    canon = url(f"recalls/{r['slug']}/")
    ld = [{
        "@context": "https://schema.org", "@type": "Article", "headline": r["title"][:110],
        "description": summary[:300], "datePublished": r.get("report_date") or r["date"],
        "dateModified": r.get("report_date") or r["date"], "url": canon,
        "about": {"@type": "Product", "name": r["product"][:200],
                  **({"manufacturer": {"@type": "Organization", "name": r["company"]}} if r["company"] else {})},
        "publisher": {"@type": "Organization", "name": NAME, "url": BASE},
        "isBasedOn": r["source_url"],
    }, {
        "@context": "https://schema.org", "@type": "FAQPage",
        "mainEntity": [
            {"@type": "Question", "name": q1, "acceptedAnswer": {"@type": "Answer", "text": a1}},
            {"@type": "Question", "name": "What should I do if I have this product?",
             "acceptedAnswer": {"@type": "Answer", "text": what_to_do(r)}},
        ],
    }]
    write(f"recalls/{r['slug']}/index.html",
          page(f"{r['title']} | {NAME}", summary, canon, body, ld))


# ---------------- data / bot files ----------------
def public_rec(r):
    keys = ["id", "source", "category", "recall_number", "title", "product", "reason", "hazard_level", "company",
            "company_location", "date", "report_date", "status", "distribution", "states", "nationwide", "quantity",
            "codes", "remedy", "retailers", "injuries", "source_url"]
    d = {k: r.get(k) for k in keys}
    d["url"] = url(f"recalls/{r['slug']}/")
    return d


def bot_files(recs, months, companies):
    latest = recs[:200]
    write("api/latest.json", json.dumps({"generated": TODAY.isoformat(), "count": len(latest),
                                         "recalls": [public_rec(r) for r in latest]}, ensure_ascii=False))
    for m, rs in months.items():
        write(f"api/month/{m}.json", json.dumps({"month": m, "count": len(rs), "recalls": [public_rec(r) for r in rs]}, ensure_ascii=False))
    write("api/index.html", page(f"Recall data API | {NAME}", "Free JSON files of U.S. recalls.", url("api/"),
          "<h1>Recall data (JSON)</h1><p>Static JSON files, regenerated daily.</p><ul class='list'>"
          "<li><a href='/api/latest.json'>/api/latest.json</a> &mdash; the 200 most recent recalls</li>"
          + "".join(f"<li><a href='/api/month/{m}.json'>/api/month/{m}.json</a> ({len(rs)})</li>" for m, rs in months.items())
          + "</ul>"))

    # RSS
    items = "".join(
        f"<item><title>{e(r['title'])}</title><link>{url('recalls/' + r['slug'] + '/')}</link>"
        f"<guid>{url('recalls/' + r['slug'] + '/')}</guid>"
        f"<pubDate>{format_datetime(dt.datetime.combine(dt.date.fromisoformat(r['report_date'] or r['date']), dt.time(12), dt.timezone.utc))}</pubDate>"
        f"<description>{e((r['reason'] or '')[:400])}</description></item>"
        for r in recs[:100] if (r.get('report_date') or r.get('date')))
    write("feed.xml", f'<?xml version="1.0" encoding="UTF-8"?><rss version="2.0"><channel><title>{e(NAME)}</title>'
                      f"<link>{BASE}/</link><description>{e(CFG['tagline'])}</description>{items}</channel></rss>")

    # llms.txt — a map for AI agents
    cats = "\n".join(f"- [{CAT_LABEL[c]} recalls]({url('category/' + c + '/')})" for c in CAT_LABEL)
    write("llms.txt", f"""# {NAME}

> {CFG['tagline']} Each recall has its own page with the product, reason, severity, where it was sold, lot codes, and what to do, plus a link to the official FDA or CPSC record.

Data covers {len(recs)} recalls that started between {min((r['date'] for r in recs if r.get('date')), default='')} and {max((r['date'] for r in recs if r.get('date')), default='')}. Sources: openFDA enforcement reports (food, drugs, medical devices) and the CPSC recall database.

## Browse
- [Latest recalls]({url('latest/')})
{cats}
- [Recalls by U.S. state]({url('state/')})
- [Recalls by month]({url('month/')})

## Machine-readable
- [Latest 200 recalls as JSON]({url('api/latest.json')})
- [Monthly JSON files]({url('api/')})
- [RSS feed]({url('feed.xml')})
- [Sitemap]({url('sitemap.xml')})

## Page URL pattern
- Recall: {BASE}/recalls/<slug>/
- Company: {BASE}/company/<company-slug>/
- State: {BASE}/state/<two-letter-code>/
""")

    write("robots.txt", f"User-agent: *\nAllow: /\n\nSitemap: {BASE}/sitemap.xml\n")
    write(f"{CFG['indexnow_key']}.txt", CFG["indexnow_key"])
    write("_headers", "/*\n  X-Robots-Tag: all\n/api/*\n  Access-Control-Allow-Origin: *\n  Cache-Control: public, max-age=3600\n")


def sitemap(urls):
    chunks = [urls[i:i + 40000] for i in range(0, len(urls), 40000)] or [[]]
    names = []
    for i, ch in enumerate(chunks):
        n = f"sitemap-{i + 1}.xml"
        names.append(n)
        write(n, '<?xml version="1.0" encoding="UTF-8"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
              + "".join(f"<url><loc>{e(u)}</loc>{f'<lastmod>{lm}</lastmod>' if lm else ''}</url>" for u, lm in ch) + "</urlset>")
    write("sitemap.xml", '<?xml version="1.0" encoding="UTF-8"?><sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
          + "".join(f"<sitemap><loc>{BASE}/{n}</loc><lastmod>{TODAY.isoformat()}</lastmod></sitemap>" for n in names) + "</sitemapindex>")


# ---------------- main ----------------
def load():
    recs = {}
    for path in glob.glob(os.path.join(ROOT, "data", "*", "*.json")):
        with open(path) as f:
            for r in json.load(f).values():
                recs[r["id"]] = r
    cutoff = (TODAY - dt.timedelta(days=CFG["keep_days"])).isoformat()
    out = [r for r in recs.values() if (r.get("date") or "") >= cutoff]
    out.sort(key=lambda r: (r.get("report_date") or r.get("date") or "", r["id"]), reverse=True)
    # unique slugs
    seen = {}
    for r in out:
        s = r["slug"]
        if s in seen:
            seen[s] += 1
            r["slug"] = f"{s}-{seen[s]}"
        else:
            seen[s] = 1
    return out


def main():
    if BASE.endswith("example.com"):
        print("WARNING: site_url in config.json is still the placeholder.")
    if os.path.exists(OUT):
        shutil.rmtree(OUT)
    recs = load()
    urls = []

    for r in recs:
        record_page(r)
        urls.append((url(f"recalls/{r['slug']}/"), r.get("report_date")))

    by_cat, by_state, by_co, months = {}, {}, {}, {}
    for r in recs:
        by_cat.setdefault(r["category"], []).append(r)
        for s in r["states"]:
            by_state.setdefault(s, []).append(r)
        if r["company"]:
            by_co.setdefault(slugify(r["company"]), (r["company"], []))[1].append(r)
        months.setdefault((r.get("date") or "unknown")[:7], []).append(r)
    nationwide = [r for r in recs if r["nationwide"]]

    listing("latest/", "Latest U.S. recalls", CFG["tagline"], recs[:500])
    urls.append((url("latest/"), TODAY.isoformat()))
    for c, rs in by_cat.items():
        listing(f"category/{c}/", f"{CAT_LABEL[c]} recalls", f"All recent {CAT_LABEL[c].lower()} recalls in plain English.", rs)
        urls.append((url(f"category/{c}/"), TODAY.isoformat()))

    st_links = []
    for code, sname in STATES.items():
        rs = by_state.get(code, [])
        combined = sorted({r["id"]: r for r in rs + nationwide}.values(),
                          key=lambda r: r.get("report_date") or r.get("date") or "", reverse=True)
        intro = (f"<p>Recalls of products that were distributed in {e(sname)}: {len(rs)} name {e(sname)} directly, "
                 f"and {len(nationwide)} were distributed nationwide.</p>")
        listing(f"state/{code.lower()}/", f"Recalls in {sname}", f"Food, drug, device and product recalls affecting {sname}.",
                combined, intro)
        urls.append((url(f"state/{code.lower()}/"), TODAY.isoformat()))
        st_links.append(f'<li><a href="/state/{code.lower()}/">{e(sname)}</a> ({len(rs)} named + nationwide)</li>')
    write("state/index.html", page(f"Recalls by state | {NAME}", "Recalls by U.S. state.", url("state/"),
                                   f"<h1>Recalls by state</h1><ul class='list'>{''.join(st_links)}</ul>"))
    urls.append((url("state/"), TODAY.isoformat()))

    for cs, (cname, rs) in by_co.items():
        listing(f"company/{cs}/", f"{cname} recalls", f"Every recent recall by {cname}.", rs)
        urls.append((url(f"company/{cs}/"), rs[0].get("report_date")))

    # Topic pages: match how people phrase questions ("listeria recalls", "peanut allergy recalls", "Walmart recalls")
    tlinks = []
    for tslug, (label, pattern) in TOPICS.items():
        rs = [r for r in recs if re.search(pattern, (r.get("reason") or "") + " " + (r.get("product") or ""), re.I)]
        if not rs:
            continue
        listing(f"topic/{tslug}/", f"{label} recalls", f"Recent U.S. recalls involving {label.lower()}.", rs)
        urls.append((url(f"topic/{tslug}/"), TODAY.isoformat()))
        tlinks.append(f'<li><a href="/topic/{tslug}/">{e(label)}</a> ({len(rs)})</li>')
    by_ret = {}
    for r in recs:
        for ret in r.get("retailers") or []:
            by_ret.setdefault(slugify(ret), (ret, []))[1].append(r)
    for rs_slug, (rname, rs) in by_ret.items():
        listing(f"retailer/{rs_slug}/", f"Products recalled at {rname}", f"Recalled products that were sold at {rname}.", rs)
        urls.append((url(f"retailer/{rs_slug}/"), TODAY.isoformat()))
        tlinks.append(f'<li><a href="/retailer/{rs_slug}/">Sold at {e(rname)}</a> ({len(rs)})</li>')
    write("topic/index.html", page(f"Recalls by topic | {NAME}", "Recalls by hazard, allergen and retailer.", url("topic/"),
                                   f"<h1>Recalls by hazard, allergen and store</h1><ul class='list'>{''.join(tlinks)}</ul>"))
    urls.append((url("topic/"), TODAY.isoformat()))

    mlinks = []
    for m in sorted(months, reverse=True):
        label = month_label(m)
        listing(f"month/{m}/", f"Recalls in {label}", f"All U.S. recalls that started in {label}.", months[m])
        urls.append((url(f"month/{m}/"), None))
        mlinks.append(f'<li><a href="/month/{m}/">{e(label)}</a> ({len(months[m])})</li>')
    write("month/index.html", page(f"Recalls by month | {NAME}", "Archive of recalls by month.", url("month/"),
                                   f"<h1>Recalls by month</h1><ul class='list'>{''.join(mlinks)}</ul>"))

    counts = " &middot; ".join(f'<a href="/category/{c}/">{e(CAT_LABEL[c])}: {len(rs)}</a>' for c, rs in by_cat.items())
    class1 = [r for r in recs if r.get("hazard_level") == "Class I"][:20]
    home = (f"<h1>{e(NAME)}</h1><p>{e(CFG['tagline'])}</p><p>{counts}</p>"
            f"<h2>Most serious recent recalls (FDA Class I)</h2><ul class='list'>{''.join(row(r) for r in class1)}</ul>"
            f"<h2>Latest recalls</h2><ul class='list'>{''.join(row(r) for r in recs[:40])}</ul>"
            f"<p><a href='/latest/'>See all latest recalls &rarr;</a></p>")
    write("index.html", page(f"{NAME}: U.S. recalls in plain English", CFG["tagline"], BASE + "/", home,
                             [{"@context": "https://schema.org", "@type": "WebSite", "name": NAME, "url": BASE + "/"}]))
    urls.insert(0, (BASE + "/", TODAY.isoformat()))
    write("404.html", page(f"Not found | {NAME}", "Page not found.", BASE + "/", "<h1>Page not found</h1><p><a href='/'>Go to the home page</a></p>"))

    bot_files(recs, {m: months[m] for m in sorted(months, reverse=True) if m != "unknown"}, by_co)
    sitemap(urls)

    print(f"Built {len(recs)} recalls, {files_written} files -> public/")
    if files_written > CFG["max_files_warning"]:
        print(f"WARNING: {files_written} files is close to the Cloudflare Pages free limit (20,000). Lower keep_days.")


if __name__ == "__main__":
    main()
