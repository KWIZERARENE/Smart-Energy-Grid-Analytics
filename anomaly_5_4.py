import os
import psycopg2
import smart_meter_simulator as sim

K = 6.0   # robust standard deviations; fixed from the distribution below, not tuned on labels

conn = psycopg2.connect(host="127.0.0.1", port=5433, dbname="smartgrid", user="postgres",
                        password=os.environ["PGPASSWORD"], options="-c timezone=Africa/Kigali")
conn.autocommit = True
cur = conn.cursor()

def slot(a): return f"(extract(hour from {a}.event_time)*4 + extract(minute from {a}.event_time)/15)::int"
def wknd(a): return f"(extract(isodow from {a}.event_time) >= 6)"

print("1. Per-meter baseline: median power by meter, 15-min slot and weekday/weekend")
cur.execute("DROP TABLE IF EXISTS meter_slot_median")
cur.execute(f"""CREATE TABLE meter_slot_median AS
  SELECT meter_id, {wknd('energy_readings')} AS weekend, {slot('energy_readings')} AS slot,
         percentile_cont(0.5) WITHIN GROUP (ORDER BY power_kw) AS med
  FROM energy_readings GROUP BY 1, 2, 3""")
cur.execute("CREATE INDEX ON meter_slot_median (meter_id, weekend, slot)")
cur.execute("ANALYZE meter_slot_median")

print("2. Ratio of every reading to its baseline")
cur.execute(f"""CREATE TEMP TABLE tmp_ratio AS
  SELECT r.meter_id, r.event_time, r.power_kw, r.power_kw / m.med AS ratio
  FROM energy_readings r JOIN meter_slot_median m
    ON m.meter_id = r.meter_id AND m.weekend = {wknd('r')} AND m.slot = {slot('r')}
  WHERE m.med > 0""")
cur.execute("SELECT count(*), percentile_cont(0.5) WITHIN GROUP (ORDER BY ratio) FROM tmp_ratio")
n, center = cur.fetchone()
cur.execute("SELECT percentile_cont(0.5) WITHIN GROUP (ORDER BY abs(ratio - %s)) FROM tmp_ratio", (center,))
mad = cur.fetchone()[0]
sigma = 1.4826 * mad
lo, hi = center - K * sigma, center + K * sigma
cur.execute("SELECT percentile_cont(ARRAY[0.99,0.999,0.9999,0.99999]) WITHIN GROUP "
            "(ORDER BY abs(ratio - %s) / %s) FROM tmp_ratio", (center, sigma))
q = cur.fetchone()[0]
print(f"   readings scored: {n:,}")
print(f"   typical ratio (median): {center:.4f}   MAD: {mad:.4f}   robust sigma: {sigma:.4f}")
print(f"   deviation quantiles in sigmas, 99%/99.9%/99.99%/99.999%: {[round(x, 2) for x in q]}")
print(f"   rule: flag if ratio < {lo:.4f} or ratio > {hi:.4f}   (K = {K})")

cur.execute("CREATE TEMP TABLE tmp_flags AS SELECT meter_id, event_time, power_kw, ratio "
            "FROM tmp_ratio WHERE ratio < %s OR ratio > %s", (lo, hi))
cur.execute("SELECT count(*), count(DISTINCT meter_id) FROM tmp_flags")
nflags, nmeters = cur.fetchone()
print(f"3. Flags raised: {nflags:,} readings on {nmeters:,} meters")

with open("flagged_readings.csv", "w", newline="") as f:
    cur.copy_expert("COPY (SELECT meter_id, event_time, power_kw, ratio FROM tmp_flags "
                    "ORDER BY meter_id, event_time) TO STDOUT WITH CSV HEADER", f)
print("   all flagged readings saved to flagged_readings.csv")

cur.execute("SELECT meter_id, event_time, round(power_kw::numeric, 3), round(ratio::numeric, 3) "
            "FROM tmp_flags ORDER BY abs(ratio - %s) DESC LIMIT 10", (center,))
print("   ten strongest flags (meter_id, event_time, power_kw, ratio):")
for r in cur.fetchall():
    print("   ", r[0], r[1].strftime("%Y-%m-%d %H:%M"), r[2], r[3])

print("4. Evaluation against the injected events (labels used only now)")
events = sim.anomaly_events()
cur.execute("CREATE TEMP TABLE tmp_labels (meter_id bigint, start_time timestamptz, "
            "end_time timestamptz, event_type text)")
for e in events:
    cur.execute("INSERT INTO tmp_labels VALUES (%s, %s, %s, %s)",
                (e["meter_id"], e["start_time"], e["end_time"], e["event_type"]))
cur.execute("""SELECT l.meter_id, l.start_time, l.end_time, l.event_type,
   (SELECT count(*) FROM tmp_flags f WHERE f.meter_id = l.meter_id
      AND f.event_time >= l.start_time AND f.event_time < l.end_time) AS flags
   FROM tmp_labels l ORDER BY l.start_time""")
rows = cur.fetchall()
detected = sum(1 for r in rows if r[4] > 0)
print(f"   events: {len(rows)}   detected: {detected}   missed: {len(rows) - detected}")
for r in rows:
    print("   ", "DETECTED" if r[4] > 0 else "MISSED  ", r[0], r[3], r[1], "->", r[2], "flags:", r[4])

cur.execute("""SELECT count(*), count(DISTINCT f.meter_id) FROM tmp_flags f
   WHERE NOT EXISTS (SELECT 1 FROM tmp_labels l WHERE l.meter_id = f.meter_id
     AND f.event_time >= l.start_time AND f.event_time < l.end_time)""")
false_n, false_meters = cur.fetchone()
cur.execute("""SELECT count(*) FROM energy_readings r WHERE EXISTS (SELECT 1 FROM tmp_labels l
   WHERE l.meter_id = r.meter_id AND r.event_time >= l.start_time AND r.event_time < l.end_time)""")
inside = cur.fetchone()[0]
cur.execute("SELECT count(*) FROM energy_readings")
total = cur.fetchone()[0]
outside = total - inside
print(f"   observed readings: {total:,}   inside injected intervals: {inside:,}   outside: {outside:,}")
print(f"   false flags: {false_n:,} = {100 * false_n / outside:.4f}% of readings outside injected intervals")
print(f"   meters with at least one false flag: {false_meters:,} = {100 * false_meters / 4000:.2f}% of meters affected by false flags")