import json
import queue
import threading
import time

import paho.mqtt.client as mqtt
import psycopg2

BROKER, MQTT_PORT = "127.0.0.1", 1883
TOPIC = "energy/meters/+"
IDLE_STOP_SECONDS = 60   # stop after this long with no new message

db = psycopg2.connect(dbname="smartgrid", user="postgres", password="password",
                      host="127.0.0.1", port=5433)
db.autocommit = True
cur = db.cursor()

counts = {"received": 0, "redelivered": 0, "inserted": 0, "failed": 0}
last_message = time.time()
work = queue.Queue()

INSERT = """
INSERT INTO energy_live
 (meter_id, event_time, received_time, power_kw, voltage_v,
  current_a, frequency_hz, energy_kwh)
VALUES
 (%(meter_id)s, %(event_time)s, %(received_time)s, %(power_kw)s, %(voltage_v)s,
  %(current_a)s, %(frequency_hz)s, %(energy_kwh)s)
"""

def inserter():
    while True:
        record = work.get()
        if record is None:
            break
        try:
            cur.execute(INSERT, record)
            counts["inserted"] += 1
        except Exception as exc:
            counts["failed"] += 1
            print("Insert failed:", exc)

worker = threading.Thread(target=inserter)
worker.start()

def on_connect(client, userdata, flags, reason_code, properties):
    print("Connected to broker:", reason_code)
    client.subscribe(TOPIC, qos=1)

def on_subscribe(client, userdata, mid, reason_codes, properties):
    print("Subscribed. READY: start the publisher now.")

def on_message(client, userdata, msg):
    global last_message
    last_message = time.time()
    counts["received"] += 1
    if msg.dup:
        counts["redelivered"] += 1
    work.put(json.loads(msg.payload))   # return immediately; insert happens in the worker
    if counts["received"] % 500 == 0:
        print(counts)

client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="pilot-subscriber")
client.on_connect = on_connect
client.on_subscribe = on_subscribe
client.on_message = on_message
client.connect(BROKER, MQTT_PORT)
client.loop_start()

try:
    while True:
        time.sleep(1)
        if (counts["received"] > 0 and work.empty()
                and time.time() - last_message > IDLE_STOP_SECONDS):
            break
except KeyboardInterrupt:
    pass

client.loop_stop()
client.disconnect()

work.put(None)      # tell the worker to finish
worker.join()

cur.execute("SELECT count(*) FROM energy_live")
stored = cur.fetchone()[0]
print("\n--- Subscriber summary ---")
print("Received     :", counts["received"])
print("Redelivered  :", counts["redelivered"], "(MQTT dup flag)")
print("Insert OK    :", counts["inserted"])
print("Insert failed:", counts["failed"])
print("Stored (rows in energy_live):", stored)
db.close()