# Permit Watch

One self-contained local web app that periodically collects public notices from approved websites, stores a local history, optionally summarizes new results with OpenRouter, and serves a reviewable dashboard.

## Architecture

```text
Configured public sources → requests + parser → SQLite (mounted dataset)
                                           ↘ dedupe + relevance → OpenRouter (optional)
Browser ← Nginx ← Gunicorn/Flask ← APScheduler (single app process)
```

Nginx terminates HTTP and serves the Flask UI. Gunicorn runs exactly **one worker**, because the embedded scheduler must exist only once. APScheduler triggers a safe sequential scrape at startup and at the configured interval. SQLite, source configuration, and logs are held under `/data`, which must be a persistent TrueNAS dataset mount.

## TrueNAS 26 deployment

TrueNAS 26 documentation is for **SCALE**, not the legacy FreeBSD-based CORE. In **Apps → Discover → more menu → Install via YAML**, create a dedicated dataset (for example `tank/apps/permit-watch`) and use `docker-compose.yml` after changing the host-path volume and published port as needed. The same image also runs on any normal Docker host.

Set `OPENROUTER_API_KEY` as a secret/environment value in the TrueNAS app form (or an untracked `.env` for local Docker), never in `sources.json`. To improve map placement, also set `GEOAPIFY_API_KEY` to a Geoapify key. After each scrape, Watcher geocodes and permanently caches up to `GEOCODING_BATCH_LIMIT` new public locations (default 100, maximum 500), so previously resolved locations do not consume another request. Expose the service only to a trusted LAN, or put it behind an authenticated reverse proxy/VPN. This starter intentionally has no application login.

### Recommended: automatic GitHub builds

For a TrueNAS deployment that does not require Docker Desktop or manual image uploads, use the included GitHub Actions workflow. It builds and publishes `ghcr.io/mrkorvo/permit-watch:stable` whenever the GitHub project changes. Follow [`GITHUB-SETUP.md`](GITHUB-SETUP.md) once, then use [`truenas-ghcr.compose.yaml`](truenas-ghcr.compose.yaml) in TrueNAS. Keep `OPENROUTER_API_KEY` in TrueNAS only.

## Configure sources

After the first start, edit `/mnt/tank/apps/permit-watch/sources.json` based on [`sources.example.json`](sources.example.json), then restart the app. Each source needs a stable public URL, a CSS selector that identifies individual results, and optional filters. RSS/Atom feeds are also supported and are generally preferable to scraping HTML.

For Ottawa's JavaScript-based Development Applications Search, add the `ottawa_devapps` entry shown in `sources.example.json`. It monitors active **Site Plan Control** and **Plan of Condominium** records using the City's public data service; no URL selector or API key is required.

```json
{
  "sources": [{
    "name": "Example municipality notices",
    "url": "https://example.gov/public-notices",
    "type": "html",
    "item_selector": ".notice-card",
    "title_selector": "h2, h3",
    "link_selector": "a",
    "date_selector": "time",
    "keywords": ["permit", "development", "zoning"],
    "enabled": true,
    "min_request_interval_seconds": 5
  }]
}
```

The built-in MERX connector reviews Canada-wide open opportunities and scores them for physical-security integration work such as access control, CCTV, intrusion detection, installation, commissioning, and maintenance. The CanadaBuys connector downloads the official federal Open tender notices CSV, retains each notice hyperlink, and applies the same scoring without scraping or paginating the website. Matching bids are shown by default; each procurement tab can also display all of its collected bids.

The tab-specific Run action reloads this file and starts a non-overlapping run for the active source. It does not alter source settings through the UI.

### Ottawa active site plans and condominiums

Replace `/data/sources.json` with the contents of `ottawa.sources.json`, then restart the app or select **Run now**. This connector intentionally uses only the City's public application data, filters it to Site Plan Control and Plan of Condominium records, and labels every result with its official source page.

## Safety and operating rules

- Only add sources you are authorized to access. Review a site’s terms, robots.txt, and any published API/feed first.
- Prefer official APIs, RSS feeds, and downloadable public records over HTML scraping.
- Do not bypass authentication, CAPTCHAs, access controls, rate limits, or anti-bot protections.
- Keep intervals conservative (hours, not minutes); this app identifies itself with a clear User-Agent and backs off after errors.
- Verify every enriched summary against its linked source. Model output is stored as a draft aid, not a finding of fact.
- Back up the mounted dataset. Database and raw excerpts can contain public-but-sensitive planning information.

## Development

```sh
cp sources.example.json data/sources.json
docker compose up --build
```

Open `http://localhost:8080`. The health endpoint is `/healthz`.
