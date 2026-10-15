import os
import psycopg2
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

conn = psycopg2.connect(host="127.0.0.1", port=5433, dbname="smartgrid", user="postgres",
                        password=os.environ["PGPASSWORD"], options="-c timezone=Africa/Kigali")
cur = conn.cursor()
TZ = "Africa/Kigali"

# 1. Energy per CAT day (kWh)
cur.execute("SELECT date_trunc('day', event_time) AS day, sum(energy_kwh) AS kwh "
            "FROM energy_readings GROUP BY 1 ORDER BY 1")
daily = pd.DataFrame(cur.fetchall(), columns=["day", "kwh"])
daily["day"] = pd.to_datetime(daily["day"], utc=True).dt.tz_convert(TZ)
assert len(daily) == 28, len(daily)
daily["label"] = daily["day"].dt.strftime("%d %b")
print("\nDaily network energy (kWh)")
print(daily[["label", "kwh"]].to_string(index=False))

# 2. Seven-day periods beginning 1, 8, 15 and 22 September
periods = ["1-7 Sep", "8-14 Sep", "15-21 Sep", "22-28 Sep"]
weekly = daily.groupby(daily.index // 7)["kwh"].sum()
weekly.index = periods
print("\nSeven-day network energy (kWh)")
print(weekly.round(1).to_string())

# 3. Network demand per 15-minute interval (kW)
cur.execute("SELECT event_time, sum(power_kw) AS kw, count(*) AS readings "
            "FROM energy_readings GROUP BY event_time ORDER BY event_time")
iv = pd.DataFrame(cur.fetchall(), columns=["event_time", "kw", "readings"])
iv["event_time"] = pd.to_datetime(iv["event_time"], utc=True).dt.tz_convert(TZ)
print("\nIntervals:", len(iv))
top3 = iv.nlargest(3, "kw")
print("\nThree highest 15-minute network demand intervals")
print(top3.to_string(index=False))

# Average demand by CAT hour of day, for explaining the pattern
iv["hour"] = iv["event_time"].dt.hour
profile = iv.groupby("hour")["kw"].mean()

# Charts
fig, ax = plt.subplots(figsize=(12, 5))
ax.bar(daily["label"], daily["kwh"], color="#2b6cb0")
ax.set_title("Total network energy per CAT day, 1-28 Sep 2026")
ax.set_ylabel("Energy (kWh)"); ax.tick_params(axis="x", rotation=60)
fig.tight_layout(); fig.savefig("chart_5_1_daily.png", dpi=120); plt.close(fig)

fig, ax = plt.subplots(figsize=(8, 5))
ax.bar(periods, weekly.values, color="#2b6cb0")
ax.set_title("Network energy per seven-day period")
ax.set_ylabel("Energy (kWh)")
fig.tight_layout(); fig.savefig("chart_5_1_weekly.png", dpi=120); plt.close(fig)

fig, ax = plt.subplots(figsize=(10, 5))
ax.plot(profile.index, profile.values, marker="o", color="#2b6cb0")
ax.set_title("Average network demand by CAT hour of day")
ax.set_xlabel("Hour (CAT)"); ax.set_ylabel("Average demand (kW per 15-min interval)")
ax.set_xticks(range(0, 24))
fig.tight_layout(); fig.savefig("chart_5_1_hourly.png", dpi=120); plt.close(fig)
print("\nSaved: chart_5_1_daily.png, chart_5_1_weekly.png, chart_5_1_hourly.png")