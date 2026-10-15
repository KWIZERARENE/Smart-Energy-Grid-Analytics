# gridboard: Raw, Aggregate & Section 8 Forecast dashboards (Assignment I)

A Django app with three pages that show:

| URL | Dashboard | Description | Reads |
|---|---|---|---|
| `/raw/` | Raw | Section 7.1 baseline dashboard | `energy_readings` (joined to `meters`) |
| `/aggregate/` | Aggregate | Section 7.2 continuous aggregate dashboard | `cagg_hourly_region`, `cagg_15min_region`, `cagg_daily_meter` (plus `meters` for registered counts) |
| `/forecast/` | Forecast | Section 8 Day-Ahead Regional Demand Forecasting | Zero-leakage Harmonic Seasonal Ridge ML Model vs. Naive Persistence Baseline |

## Structure

```
gridboard/
  manage.py
  requirements.txt
  verify_match.py              7.3 numerical comparison of the two dashboards
  run_section8_forecast.py     Section 8 data prep, persistence baseline, ML training & evaluation
  generate_report.py           Word report generator (.docx) for Sections 7 & 8
  gridboard/                   project settings (no cache, CAT time zone, DB from env vars)
  dashboard/
    queries.py                 all panel SQL, RAW and AGG side by side
    db.py                      connection pool + timed query helper
    views.py, urls.py          pages and JSON API (/api/<mode>/<panel>/, /api/forecast/data/)
    templates/dashboard/dashboard.html
    templates/dashboard/forecast.html
    static/dashboard/dashboard.js    charts, filters, 1 warm-up + 10 refresh benchmark
    static/dashboard/dashboard.css
```

## Run

```cmd
cd gridboard
pip install -r requirements.txt
set PGPASSWORD=<your database password>
set PGPORT=5433
python manage.py runserver 127.0.0.1:8000
```

Open:
- http://127.0.0.1:8000/raw/
- http://127.0.0.1:8000/aggregate/
- http://127.0.0.1:8000/forecast/
Defaults: 22 September to 29 September (exclusive), meter 1000000000.
The browser needs internet access once to load Chart.js from a CDN.

## 7.3 Verify matching results

```cmd
python verify_match.py 2026-09-22 2026-09-29 1000000000
```

Prints rows compared and the maximum absolute differences per panel and an overall PASS or FAIL.
Fix any FAIL before timing.

## 7.4 Timing

1. Pause the assignment background jobs and any loaders:
   `SELECT alter_job(job_id, scheduled => false) FROM timescaledb_information.jobs WHERE proc_name = 'policy_refresh_continuous_aggregate';`
2. Close other programs. Use the same browser, machine and connection pool for both modes.
3. Caching is disabled: no Django cache backend, `Cache-Control: no-store` on every API response, cache-busting parameter on every request, `fetch(..., {cache: "no-store"})`.
4. On `/raw/` click **Run benchmark**. It does 1 warm-up refresh and 10 measured refreshes, then shows
   median, min and max per panel (server query time) and for the whole dashboard
   (from requesting refresh until all five panels are rendered). Download the per-run CSV.
5. Repeat on `/aggregate/`.
6. Resume the jobs: same `alter_job` call with `scheduled => true`.

Measurement tool to name in the report: this app's built-in timer
(server `time.perf_counter()` per query, browser `performance.now()` for the dashboard total).

## Notes & Enhanced Features

- **Executive Telemetry UI / UX**:
  - Dark SCADA theme by default with clean Light mode toggle (persisted in localStorage).
  - Modern typography with Google Fonts (*Plus Jakarta Sans* & *JetBrains Mono*).
  - Telemetry HUD summary cards (Total Energy, Daily Average, Selected Meter Total, Completeness %, and Live Render Latency).
  - Filter toolbar with quick presets (7.3 Default 22-29 Sep, Week 1, Week 2, Week 3, Full 28-day September).
  - Multi-region line chart with interactive region filter chips (Region 1 to Region 10).
  - Individual panel controls: Toggle between interactive Chart and raw Data Table, and export panel CSV.
- **Section 7.3 Interactive Verification**:
  - Click **Verify 7.3 Parity** in the top bar to run live numerical parity verification between Raw and Aggregate modes directly from the UI, or run `python verify_match.py`.
- **Section 1.3 & 7.2 Pilot Stream Monitor**:
  - Collapsible live stream monitor panel inspecting `energy_live` (2,000 ingested pilot records). Excluded from Section 7.4 benchmark timing as specified.
- **Section 7.4 Benchmark Runner**:
  - Click **Run Benchmark (1+10)** to execute 1 warm-up refresh followed by 10 measured refreshes with animated progress, summary statistics table, and one-click per-run CSV download.
- **Database & Architecture**:
  - Panel queries use raw SQL, not the ORM, because `time_bucket` and continuous aggregates need it.
  - Completeness planned count = registered meters x 96 x number of whole days in the range.
  - Keep the password in the `PGPASSWORD` environment variable; never commit it.

