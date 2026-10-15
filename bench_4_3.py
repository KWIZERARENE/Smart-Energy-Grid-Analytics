import os, socket, statistics, time, csv
from datetime import datetime
from zoneinfo import ZoneInfo
import psycopg2

CAT = ZoneInfo("Africa/Kigali")
DSN = dict(host="127.0.0.1", port=5433, dbname="smartgrid", user="postgres",
           password=os.environ["PGPASSWORD"], options="-c timezone=Africa/Kigali")
REF = "energy_readings"
TABLES = {"day": "energy_readings", "3h": "energy_readings_3h", "week": "energy_readings_week", "time_compressed": "energy_time_compressed", "meter_compressed": "energy_meter_compressed"}
MACHINE = socket.gethostname()

Q = {
 "Q1": """SELECT date_trunc('hour', event_time) AS hr, avg(power_kw)
          FROM {t} WHERE event_time >= '2026-09-21 00:00+02' AND event_time < '2026-09-22 00:00+02'
          GROUP BY 1 ORDER BY 1""",
 "Q2": """SELECT event_time, sum(power_kw) AS total_kw FROM {t}
          WHERE event_time >= '2026-09-22 00:00+02' AND event_time < '2026-09-29 00:00+02'
          GROUP BY event_time ORDER BY total_kw DESC, event_time ASC LIMIT 10""",
 "Q3": """SELECT meter_id, sum(energy_kwh) FROM {t} GROUP BY meter_id ORDER BY meter_id""",
 "Q4": """SELECT sum(energy_kwh), avg(power_kw), max(power_kw) FROM {t}
          WHERE meter_id = 1000000000
          AND event_time >= '2026-09-22 00:00+02' AND event_time < '2026-09-29 00:00+02'""",
 "Q5": """SELECT count(*), sum(energy_kwh), avg(power_kw), min(power_kw), max(power_kw) FROM {t}""",
}

def run_once(cur, sql):
    s = datetime.now(CAT); p0 = time.perf_counter()
    cur.execute(sql); rows = cur.fetchall()
    ms = (time.perf_counter() - p0) * 1000
    return rows, ms, s, datetime.now(CAT)

def same(a, b, tol=0.001):
    if len(a) != len(b): return False
    for ra, rb in zip(a, b):
        for x, y in zip(ra, rb):
            if isinstance(x, (int, float)) and isinstance(y, (int, float)):
                if abs(x - y) > tol: return False
            elif x != y: return False
    return True

def measure(cur, qn, label, sql, log):
    sess0 = time.perf_counter()
    run_once(cur, sql)                           # warm-up
    times, rows = [], None
    for i in range(1, 6):
        rows, ms, s, e = run_once(cur, sql)
        times.append(ms)
        log.append([qn, label, i, s.isoformat(), e.isoformat(), round(ms, 2), MACHINE])
    sess = time.perf_counter() - sess0
    return rows, times, sess

conn = psycopg2.connect(**DSN); conn.autocommit = True; cur = conn.cursor()
log, summary = [], []
for qn, tmpl in Q.items():
    # Baseline: uncompressed one-day table, measured in this same session
    ref_rows, btimes, bsess = measure(cur, qn, "day_baseline", tmpl.format(t=REF), log)
    bmed = statistics.median(btimes)
    summary.append([qn, "day_baseline", round(bmed, 2), round(min(btimes), 2), round(max(btimes), 2),
                    round(bsess, 2), round(bmed, 2), "", True])
    print(qn, "day_baseline median", round(bmed, 2), "min", round(min(btimes), 2),
          "max", round(max(btimes), 2), "ms")
    for label, tbl in TABLES.items():
        rows, times, sess = measure(cur, qn, label, tmpl.format(t=tbl), log)
        med = statistics.median(times)
        imp = 100 * (bmed - med) / bmed
        ok = same(rows, ref_rows)
        summary.append([qn, label, round(med, 2), round(min(times), 2), round(max(times), 2),
                        round(sess, 2), round(bmed, 2), round(imp, 1), ok])
        print(qn, label, "median", round(med, 2), "min", round(min(times), 2),
              "max", round(max(times), 2), "ms | baseline", round(bmed, 2),
              "| improvement %", round(imp, 1), "| match:", ok)

with open("bench_4_3_runs.csv", "w", newline="") as f:
    w = csv.writer(f)
    w.writerow(["query","table","run","start_cat","end_cat","ms","machine"])
    w.writerows(log)
with open("bench_4_3_summary.csv", "w", newline="") as f:
    w = csv.writer(f)
    w.writerow(["query","table","median_ms","min_ms","max_ms","session_s",
                "baseline_day_median_ms","improvement_pct","matches_day"])
    w.writerows(summary)

with open("plans_4_3.txt", "w") as f:
    for qn in ("Q1", "Q4"):
        for label, tbl in TABLES.items():
            cur.execute("EXPLAIN (ANALYZE, BUFFERS) " + Q[qn].format(t=tbl))
            f.write(f"===== {qn} {label} ({tbl}) =====\n")
            f.write("\n".join(r[0] for r in cur.fetchall()) + "\n\n")
print("Done. Client: Python + psycopg2, timer: time.perf_counter()")