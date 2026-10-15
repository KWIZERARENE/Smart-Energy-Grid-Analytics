"""Section 7.3: compare the numbers behind every Raw and Aggregate panel.

Run from the gridboard folder (set PGPASSWORD first):
    python verify_match.py
Optional: python verify_match.py 2026-09-22 2026-09-29 1000000000

Requires identical keys and reading counts, energy differences <= 0.001 kWh,
and completeness differences <= 0.000001 percentage points.
"""
import os
import sys
from datetime import timedelta

import psycopg2

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "gridboard.settings")

from dashboard.db import cat_midnight  # noqa: E402
from dashboard.queries import AGG, PANELS, RAW  # noqa: E402

START = sys.argv[1] if len(sys.argv) > 1 else "2026-09-22"
END = sys.argv[2] if len(sys.argv) > 2 else "2026-09-29"
METER = int(sys.argv[3]) if len(sys.argv) > 3 else 1000000000

ENERGY_TOL = 0.001
PCT_TOL = 0.000001

conn = psycopg2.connect(
    dbname=os.environ.get("PGDATABASE", "smartgrid"),
    user=os.environ.get("PGUSER", "postgres"),
    password=os.environ.get("PGPASSWORD", "CHANGE_ME"),
    host=os.environ.get("PGHOST", "127.0.0.1"),
    port=int(os.environ.get("PGPORT", "5433")),
    options="-c timezone=Africa/Kigali",
)
conn.autocommit = True

s, e = cat_midnight(START), cat_midnight(END)
params = {"start": s, "end": e, "meter": METER, "days": (e - s) // timedelta(days=1)}


def fetch(sql):
    with conn.cursor() as cur:
        cur.execute(sql, params)
        return cur.fetchall()


def key_and_values(panel, row):
    """Split a row into (key, energy, readings_or_None, pct_or_None)."""
    if panel == "hourly_region":
        return (row[0], row[1]), float(row[2]), None, None
    if panel == "completeness":
        return (row[0],), None, int(row[1]), float(row[3])
    return (row[0],), float(row[1]), None, None


print(f"Range {START} to {END} (exclusive), meter {METER}\n")
print(f"{'panel':16} {'rows':>6} {'max |energy diff| kWh':>22} {'max |pct diff|':>16} {'counts':>8}  result")
all_ok = True
for panel in PANELS:
    raw_rows = {key_and_values(panel, r)[0]: key_and_values(panel, r) for r in fetch(RAW[panel])}
    agg_rows = {key_and_values(panel, r)[0]: key_and_values(panel, r) for r in fetch(AGG[panel])}
    same_keys = raw_rows.keys() == agg_rows.keys()
    max_e = max_p = 0.0
    counts_ok = True
    for k in raw_rows.keys() & agg_rows.keys():
        _, e1, c1, p1 = raw_rows[k]
        _, e2, c2, p2 = agg_rows[k]
        if e1 is not None:
            max_e = max(max_e, abs(e1 - e2))
        if p1 is not None:
            max_p = max(max_p, abs(p1 - p2))
            counts_ok &= (c1 == c2)
    ok = same_keys and max_e <= ENERGY_TOL and max_p <= PCT_TOL and counts_ok
    all_ok &= ok
    print(f"{panel:16} {len(raw_rows):>6} {max_e:>22.9f} {max_p:>16.9f} "
          f"{'equal' if counts_ok else 'DIFFER':>8}  {'PASS' if ok else 'FAIL'}"
          + ("" if same_keys else "  (keys differ)"))

# Reading counts per bucket for the regional panels (hourly and 15-minute views)
with conn.cursor() as cur:
    cur.execute("""
        SELECT time_bucket(INTERVAL '1 hour', r.event_time, 'Africa/Kigali') AS b, m.region, count(*)
        FROM energy_readings r JOIN meters m USING (meter_id)
        WHERE r.event_time >= %(start)s AND r.event_time < %(end)s GROUP BY 1, 2
    """, params)
    raw_counts = {(r[0], r[1]): r[2] for r in cur.fetchall()}
    cur.execute("""
        SELECT bucket, region, reading_count FROM cagg_hourly_region
        WHERE bucket >= %(start)s AND bucket < %(end)s
    """, params)
    agg_counts = {(r[0], r[1]): r[2] for r in cur.fetchall()}
counts_match = raw_counts == agg_counts
all_ok &= counts_match
print(f"\nhourly_region reading counts identical per bucket and region: {counts_match}")
print("\nOVERALL:", "PASS" if all_ok else "FAIL")
conn.close()
sys.exit(0 if all_ok else 1)
