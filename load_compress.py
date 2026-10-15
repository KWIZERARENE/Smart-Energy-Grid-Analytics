import os, csv, time
import psycopg2

conn = psycopg2.connect(host="127.0.0.1", port=5433, dbname="smartgrid", user="postgres",
                        password=os.environ["PGPASSWORD"], options="-c timezone=Africa/Kigali")
conn.autocommit = True
cur = conn.cursor()
cur.execute("SELECT cutoff FROM exp_cutoff")
cutoff = cur.fetchone()[0]
cur.execute("SELECT range_start, range_end FROM timescaledb_information.chunks "
            "WHERE hypertable_name='energy_readings' ORDER BY range_start")
ranges = cur.fetchall()
out = []
for tbl in ("energy_time_compressed", "energy_meter_compressed"):
    for rs, re_ in ranges:
        t0 = time.perf_counter()
        cur.execute(f"INSERT INTO {tbl} SELECT * FROM energy_readings "
                    "WHERE event_time >= %s AND event_time < %s", (rs, re_))
        n = cur.rowcount
        load_s = time.perf_counter() - t0
        comp_s = None
        if re_ <= cutoff:
            cur.execute("SELECT chunk_schema, chunk_name FROM timescaledb_information.chunks "
                        "WHERE hypertable_name=%s AND range_start=%s", (tbl, rs))
            sch, name = cur.fetchone()
            ident = '"' + sch + '"."' + name + '"'
            t1 = time.perf_counter()
            cur.execute("SELECT compress_chunk(%s::regclass)", (ident,))
            comp_s = time.perf_counter() - t1
        out.append([tbl, rs.isoformat(), re_.isoformat(), n, round(load_s, 3),
                    None if comp_s is None else round(comp_s, 3)])
        print(tbl, rs, n, "load_s", round(load_s, 2), "compress_s",
              None if comp_s is None else round(comp_s, 2))

with open("load_compress_log.csv", "w", newline="") as f:
    w = csv.writer(f)
    w.writerow(["table", "range_start", "range_end", "rows", "load_s", "compress_s"])
    w.writerows(out)
print("compression total s:", round(sum(r[5] for r in out if r[5] is not None), 2))