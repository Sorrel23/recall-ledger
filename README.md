# Recall Ledger

A static site of every recent U.S. food, drug, medical device and consumer product recall, written in plain English for people and AI agents. AI crawlers are charged per page through Cloudflare's pay-per-crawl.

- **Data:** openFDA enforcement reports (food, drug, device) and the CPSC recall API.
- **Runs itself:** a GitHub Action runs every morning. It fetches new recalls, commits them to `data/`, and Cloudflare Pages rebuilds the site. IndexNow is then pinged so Bing (which feeds ChatGPT search and Copilot) crawls the new pages.
- **Cost:** $0 hosting and about $10–11/year for a domain.

## One-time setup (about 30 minutes)

1. **GitHub**
   - Create an account and a new **public** repository named `recall-ledger`.
   - Leave it empty. Claude pushes the code once the repo exists and is connected to Claude.
2. **Domain**
   - In Cloudflare, go to *Domains → Register*. Buy a short `.com` such as `recallledger.com` or `recallcheck.org`.
   - Pay-per-crawl needs your own domain on Cloudflare. It doesn't work on a `pages.dev` address.
3. **Cloudflare Pages**
   - Go to *Workers & Pages → Create → Pages → Connect to Git* and pick `recall-ledger`.
   - Framework preset: **None**. Build command: `python3 scripts/build.py`. Output directory: `public`.
   - Then go to *Custom domains*, add your domain, and send Claude the domain name.
4. **Charge AI crawlers**
   - Open your domain in Cloudflare, then *AI Crawl Control*.
   - Allow **Googlebot** and **Bingbot** for free, so the site gets found.
   - Set the other AI crawlers to **Charge**: start at **$0.01 per page** and request pay-per-crawl access if prompted.
   - Turn on payouts.
5. **Search engines** (5 minutes, after the first deploy)
   - Add the site to Bing Webmaster Tools and Google Search Console, and submit `https://YOURDOMAIN/sitemap.xml`.
6. **Optional:** get a free openFDA API key at https://open.fda.gov/apis/authentication/. Add it to the repo under *Settings → Secrets → Actions* as `OPENFDA_API_KEY`.

## Files

- `config.json`: site name, domain, how far back to keep data.
- `scripts/fetch.py`: pulls recalls and merges them into `data/<source>/<YYYY-MM>.json`.
- `scripts/build.py`: generates `public/`. It builds one page per recall, plus pages by category, state, company and month. It also writes `llms.txt`, JSON files under `/api/`, an RSS feed and the sitemap.
- `scripts/ping_indexnow.py`: tells search engines about new pages.
- `tests/test_pipeline.py`: an offline test, which the Action runs first.

## Limits

- The Cloudflare Pages free plan allows 20,000 files. The build warns at 18,000. If it does, lower `keep_days`.
