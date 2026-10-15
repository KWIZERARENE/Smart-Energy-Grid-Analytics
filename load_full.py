import csv
import os
import sys
import time
from itertools import islice

import psycopg2

import smart_meter_simulator as sim

BATCH_ROWS = 500_000
EXPECTED = sim.dataset_info()["expected_counts"]["emitted_readings"]
FIELDS = ("meter_id", "event_time", "received_time", "power_kw",
          "voltage_v", "current_a", "frequency_hz", "energy_kwh")
COPY_SQL = ("COPY energy_readings (meter_id, event_time, received_time, power_kw, "
            "voltage_v, current_a, frequency_hz, energy_kwh) "
            "FROM STDIN WITH (FORMAT csv)")

conn = psycopg2.connect(dbname="smartgrid", user="postgres", password="password",
                        host="127.0.0.1", port=5433)
cur = conn.cursor()

# Safety check: refuse to load on top of existing data (prevents doubled rows)
cur.execute("SELECT count(*) FROM energy_readings")
if cur.fetchone()[0] != 0:
    sys.exit("energy_readings is not empty. Run TRUNCATE energy_readings; first.")

os.makedirs("batches", exist_ok=True)
log = open("load_log.csv", "w", newline="")
log_writer = csv.writer(log)
log_writer.writerow(["batch", "rows_file", "rows_loaded", "generate_write_sec", "copy_sec"])

stream = sim.iter_readings()
generated = loaded = batch_no = 0
t_start = time.time()
gen_total = copy_total = 0.0

while True:
    batch_no += 1
    path = os.path.join("batches", f"batch_{batch_no:04d}.csv")

    t0 = time.time()
    n_file = 0
    with open(path, "w", newline="") as f:
        writer = csv.writer(f)
        for rec in islice(stream, BATCH_ROWS):
            writer.writerow([rec[k] for k in FIELDS])
            n_file += 1
    t1 = time.time()

    if n_file == 0:
        os.remove(path)
        break

    with open(path, "r", newline="") as f:
        cur.copy_expert(COPY_SQL, f)
    n_loaded = cur.rowcount
    conn.commit()
    t2 = time.time()

    os.remove(path)
    generated += n_file
    loaded += n_loaded
    gen_total += t1 - t0
    copy_total += t2 - t1
    log_writer.writerow([batch_no, n_file, n_loaded, round(t1 - t0, 2), round(t2 - t1, 2)])
    log.flush()
    print(f"batch {batch_no:3d}: file={n_file:,} loaded={n_loaded:,} "
          f"total={loaded:,}  ({(t2 - t_start) / 60:.1f} min elapsed)")

total_sec = time.time() - t_start
log.close()

print("\n--- Load summary ---")
print(f"Generated (rows written to files) : {generated:,}")
print(f"Loaded by COPY                    : {loaded:,}")
print(f"Expected emitted_readings         : {EXPECTED:,}")
print("Three-way match                   :", generated == loaded == EXPECTED)
print(f"Generate + write time             : {gen_total / 60:.1f} min")
print(f"COPY time                         : {copy_total / 60:.1f} min")
print(f"Total time                        : {total_sec / 60:.1f} min")

cur.execute("ANALYZE energy_readings")
conn.commit()
conn.close()