import json
import time
from itertools import islice

import paho.mqtt.client as mqtt

import smart_meter_simulator as sim

N = 2000
acknowledged = 0

def on_publish(client, userdata, mid, reason_code, properties):
    global acknowledged
    acknowledged += 1

client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="pilot-publisher")
client.on_publish = on_publish
client.connect("127.0.0.1", 1883)
client.loop_start()

generated = 0
pending = []
for record in islice(sim.iter_readings(), N):   # only the first 2,000 records
    generated += 1
    topic = f"energy/meters/{record['meter_id']}"
    pending.append(client.publish(topic, json.dumps(record), qos=1))

for info in pending:
    info.wait_for_publish(timeout=60)
time.sleep(1)   # let the last acknowledgements arrive

print("\n--- Publisher summary ---")
print("Generated   :", generated)
print("Acknowledged:", acknowledged, "(QoS 1 PUBACKs)")

client.loop_stop()
client.disconnect()