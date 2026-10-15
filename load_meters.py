import psycopg2
from psycopg2.extras import execute_values

import smart_meter_simulator as sim

conn = psycopg2.connect(
    dbname="smartgrid", user="postgres", password="password",
    host="127.0.0.1", port=5433,
)
try:
    with conn, conn.cursor() as cur:
        rows = [
            (m["meter_id"], m["region"], m["customer_type"],
             m["base_power_kw"], m["power_factor"])
            for m in sim.meter_metadata()
        ]
        execute_values(
            cur,
            """INSERT INTO meters
               (meter_id, region, customer_type, base_power_kw, power_factor)
               VALUES %s""",
            rows,
        )
        print(f"Loaded {len(rows)} meters")
        print(rows[:5])
finally:
    conn.close()