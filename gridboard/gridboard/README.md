# gridboard: Raw and Aggregate dashboards (Assignment I, Section 7)

A small Django app with two pages that show the same five panels:

| URL | Dashboard | Reads |
|---|---|---|
| `/raw/` | Raw | `energy_readings` (joined to `meters`) |
| `/aggregate/` | Aggregate | `cagg_hourly_region`, `cagg_15min_region`, `cagg_daily_meter` (plus `meters` for registered counts) |

## Structure

```
gridboard/
  manage.py
  requirements.txt
  verify_match.py              7.3 numerical comparison of the two dashboards
  gridboard/                   project settings (no cache, CAT time zone, DB from env vars)
  dashboard/
    queries.py                 all panel SQL, RAW and AGG side by side
    db.py                      connection pool + timed query helper
    views.py, urls.py          pages and JSON API (/api/<mode>/<panel>/)
    templates/dashboard/dashboard.html
    static/dashboard/dashboard.js    charts, filters, 1 warm-up + 10 refresh benchmark
```

## Run

```cmd
cd gridboard
pip install -r requirements.txt
set PGPASSWORD=<your database password>
set PGPORT=5433
python manage.py runserver 127.0.0.1:8000
```

Open http://127.0.0.1:8000/raw/ and http://127.0.0.1:8000/aggregate/.
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

## Notes

- Panel queries use raw SQL, not the ORM, because `time_bucket` and continuous aggregates need it.
- Completeness planned count = registered meters x 96 x number of whole days in the range.
- Keep the password in the `PGPASSWORD` environment variable; never commit it.
