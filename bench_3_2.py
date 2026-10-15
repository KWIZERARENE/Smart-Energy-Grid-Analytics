import os, socket, statistics, time, csv
from datetime import datetime
from zoneinfo import ZoneInfo
import psycopg2

CAT = ZoneInfo("Africa/Kigali")
DSN = dict(host="127.0.0.1", port=5433, dbname="smartgrid", user="postgres",
           password=os.environ.get("PGPASSWORD", "YOUR_PASSWORD"),
           options="-c timezone=Africa/Kigali")
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

conn = psycopg2.connect(**DSN); conn.autocommit = True; cur = conn.cursor()
log, summary, ref = [], [], {}
for qn, tmpl in Q.items():
    for label, tbl in TABLES.items():
        sql = tmpl.format(t=tbl)
        sess0 = time.perf_counter()
        run_once(cur, sql)                       # warm-up
        times = []
        for i in range(1, 6):
            rows, ms, s, e = run_once(cur, sql)
            times.append(ms)
            log.append([qn, label, i, s.isoformat(), e.isoformat(), round(ms, 2), MACHINE])
        sess = time.perf_counter() - sess0
        if label == "day": ref[qn] = rows
        ok = same(rows, ref[qn]) if qn in ref else None
        summary.append([qn, label, round(statistics.median(times), 2), round(min(times), 2),
                        round(max(times), 2), round(sess, 2), ok])
        print(qn, label, "median", round(statistics.median(times), 2), "min", round(min(times), 2),
              "max", round(max(times), 2), "ms | session", round(sess, 1), "s | match:", ok)

with open("bench_3_2_runs.csv", "w", newline="") as f:
    w = csv.writer(f); w.writerow(["query","table","run","start_cat","end_cat","ms","machine"]); w.writerows(log)
with open("bench_3_2_summary.csv", "w", newline="") as f:
    w = csv.writer(f); w.writerow(["query","table","median_ms","min_ms","max_ms","session_s","matches_day"]); w.writerows(summary)

with open("plans_3_2.txt", "w") as f:
    for label, tbl in TABLES.items():
        cur.execute("EXPLAIN (ANALYZE, BUFFERS) " + Q["Q4"].format(t=tbl))
        f.write(f"===== {label} ({tbl}) =====\n")
        f.write("\n".join(r[0] for r in cur.fetchall()) + "\n\n")
print("Done. Client: Python + psycopg2, timer: time.perf_counter()")