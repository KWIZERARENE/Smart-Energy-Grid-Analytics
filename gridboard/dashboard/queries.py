"""Panel SQL for the Raw and Aggregate dashboards (Assignment I, 7.1 and 7.2).

Every query takes the same named parameters:
    %(start)s   inclusive start, timestamptz (CAT midnight of the first selected day)
    %(end)s     exclusive end, timestamptz (CAT midnight after the last selected day)
    %(meter)s   selected meter_id (BIGINT), used by the meter-history panel only
    %(days)s    number of whole days in the range, used for the planned-reading count

RAW queries read energy_readings directly (joining meters where needed).
AGG queries read only the continuous aggregates; they touch meters only for
registered meter counts (completeness denominator), as 7.2 allows.
"""

PANELS = ("hourly_region", "daily_network", "weekly_network", "meter_daily", "completeness")

TITLES = {
    "hourly_region": "Hourly regional energy (kWh)",
    "daily_network": "Daily network energy (kWh)",
    "weekly_network": "Seven-day period network energy (kWh)",
    "meter_daily": "Daily energy, selected meter (kWh)",
    "completeness": "Completeness by region (%)",
}

# Seven-day periods begin on 1, 8, 15 and 22 September (CAT dates).
_WEEK = "(DATE '2026-09-01' + 7 * (({d}::date - DATE '2026-09-01') / 7))::text"

RAW = {
    "hourly_region": """
        SELECT time_bucket(INTERVAL '1 hour', r.event_time, 'Africa/Kigali') AS bucket,
               m.region AS region,
               sum(r.energy_kwh) AS energy_kwh
        FROM energy_readings r
        JOIN meters m ON m.meter_id = r.meter_id
        WHERE r.event_time >= %(start)s AND r.event_time < %(end)s
        GROUP BY 1, 2
        ORDER BY 1, 2
    """,
    "daily_network": """
        SELECT time_bucket(INTERVAL '1 day', event_time, 'Africa/Kigali') AS bucket,
               sum(energy_kwh) AS energy_kwh
        FROM energy_readings
        WHERE event_time >= %(start)s AND event_time < %(end)s
        GROUP BY 1
        ORDER BY 1
    """,
    "weekly_network": """
        SELECT """ + _WEEK.format(d="(event_time AT TIME ZONE 'Africa/Kigali')") + """ AS period_start,
               sum(energy_kwh) AS energy_kwh
        FROM energy_readings
        WHERE event_time >= %(start)s AND event_time < %(end)s
        GROUP BY 1
        ORDER BY 1
    """,
    "meter_daily": """
        SELECT time_bucket(INTERVAL '1 day', event_time, 'Africa/Kigali') AS bucket,
               sum(energy_kwh) AS energy_kwh
        FROM energy_readings
        WHERE meter_id = %(meter)s
          AND event_time >= %(start)s AND event_time < %(end)s
        GROUP BY 1
        ORDER BY 1
    """,
    "completeness": """
        WITH obs AS (
            SELECT m.region, count(*) AS observed
            FROM energy_readings r
            JOIN meters m ON m.meter_id = r.meter_id
            WHERE r.event_time >= %(start)s AND r.event_time < %(end)s
            GROUP BY m.region
        ), reg AS (
            SELECT region, count(*) AS meters FROM meters GROUP BY region
        )
        SELECT reg.region,
               obs.observed AS observed_readings,
               reg.meters * 96 * %(days)s AS planned_readings,
               100.0 * obs.observed / (reg.meters * 96 * %(days)s) AS completeness_pct
        FROM reg JOIN obs USING (region)
        ORDER BY 1
    """,
}

AGG = {
    "hourly_region": """
        SELECT bucket, region, energy_kwh_sum AS energy_kwh
        FROM cagg_hourly_region
        WHERE bucket >= %(start)s AND bucket < %(end)s
        ORDER BY 1, 2
    """,
    "daily_network": """
        SELECT time_bucket(INTERVAL '1 day', bucket, 'Africa/Kigali') AS bucket,
               sum(energy_kwh_sum) AS energy_kwh
        FROM cagg_15min_region
        WHERE bucket >= %(start)s AND bucket < %(end)s
        GROUP BY 1
        ORDER BY 1
    """,
    "weekly_network": """
        SELECT """ + _WEEK.format(d="(bucket AT TIME ZONE 'Africa/Kigali')") + """ AS period_start,
               sum(energy_kwh_sum) AS energy_kwh
        FROM cagg_15min_region
        WHERE bucket >= %(start)s AND bucket < %(end)s
        GROUP BY 1
        ORDER BY 1
    """,
    "meter_daily": """
        SELECT bucket, energy_kwh_sum AS energy_kwh
        FROM cagg_daily_meter
        WHERE meter_id = %(meter)s
          AND bucket >= %(start)s AND bucket < %(end)s
        ORDER BY 1
    """,
    "completeness": """
        WITH obs AS (
            SELECT region, sum(reading_count) AS observed
            FROM cagg_15min_region
            WHERE bucket >= %(start)s AND bucket < %(end)s
            GROUP BY region
        ), reg AS (
            SELECT region, count(*) AS meters FROM meters GROUP BY region
        )
        SELECT reg.region,
               obs.observed AS observed_readings,
               reg.meters * 96 * %(days)s AS planned_readings,
               100.0 * obs.observed / (reg.meters * 96 * %(days)s) AS completeness_pct
        FROM reg JOIN obs USING (region)
        ORDER BY 1
    """,
}

MODES = {"raw": RAW, "aggregate": AGG}
