# Gridboard: Comprehensive Codebase & Architecture Guide
**Assignment I: Smart Energy Grid Analytics • Sections 7 & 8**

This document provides a complete technical walkthrough of the **Gridboard** codebase, explaining the architecture, data structures, database queries, machine learning forecasting engine, and web dashboard implementation.

---

## 1. Architectural Overview

Gridboard is an executive-grade telemetry and predictive analytics system designed for an electrical utility monitoring **4,000 smart meters** across **10 geographical regions** with over **10.6 million interval readings** recorded in Central Africa Time (**CAT**, UTC+02:00).

The application is structured into four primary layers:
1. **Time-Series Storage Layer (TimescaleDB / PostgreSQL)**:
   - Stores unaggregated 15-minute readings in the hypertable `energy_readings` (partitioned by 1-day chunks).
   - Pre-computes rollups in three Continuous Aggregate views (`cagg_hourly_region`, `cagg_15min_region`, `cagg_daily_meter`) with real-time aggregation disabled (`materialized_only = TRUE`).
   - Retains 2,000 MQTT pilot stream records in `energy_live`.
2. **Backend API Layer (Python & Django 5.x)**:
   - Issues parameterized raw SQL via psycopg2-binary threaded connection pools (bypassing ORM overhead).
   - Enforces strict cache-busting headers (`Cache-Control: no-store`) for reproducible benchmarking.
   - Provides REST JSON endpoints (`/api/<mode>/<panel>/`, `/api/forecast/data/`, `/api/forecast/export/`).
3. **Telemetry Frontend Layer (Vanilla JavaScript & Chart.js 4.4)**:
   - Renders synchronized multi-panel dashboards in a modern SCADA Light Theme.
   - Embeds a benchmark harness executing 1 warm-up and 10 measured refreshes using `performance.now()`.
4. **Day-Ahead Machine Learning Forecasting Engine (Section 8)**:
   - Implements zero-leakage day-ahead demand forecasting with origin strictly at 00:00 CAT.
   - Compares naive persistence baseline ($t-24$) against regularized Harmonic Seasonal Ridge Regression.

```
┌────────────────────────────────────────────────────────────────────────┐
│                        Gridboard Architecture                         │
└────────────────────────────────────────────────────────────────────────┘
       │                                            │
       ▼                                            ▼
┌──────────────────────────────┐        ┌──────────────────────────────┐
│  Section 7: Dashboards       │        │  Section 8: Day-Ahead ML     │
│  • Raw Mode (/raw/)          │        │  • Naive Baseline (t-24)     │
│  • Aggregate Mode (/aggregate│        │  • Ridge Regression Model    │
└──────────────┬───────────────┘        └──────────────┬───────────────┘
               │                                       │
               ▼                                       ▼
┌──────────────────────────────┐        ┌──────────────────────────────┐
│  Django Backend (views.py)   │        │  Forecast Engine             │
│  • Connection Pooling        │        │  (run_section8_forecast.py)  │
│  • Cache-Control: no-store   │        │  • Zero-leakage origin       │
│  • JSON REST API Endpoints   │        │  • Lags (t-24, t-48, t-168)  │
└──────────────┬───────────────┘        └──────────────┬───────────────┘
               │                                       │
               ▼                                       ▼
┌──────────────────────────────────────────────────────────────────────┐
│  TimescaleDB / PostgreSQL 16 (Port 5433, CAT Africa/Kigali)           │
│  • Hypertable: energy_readings (1-day chunks, 10.6M rows)             │
│  • Materialized CAGGs: cagg_hourly_region, cagg_15min_region,         │
│                        cagg_daily_meter (18.4 MB total)              │
│  • Metadata: meters (4,000 rows)                                      │
└──────────────────────────────────────────────────────────────────────┘
```

---

## 2. Directory Structure

```
gridboard/
├── manage.py                        # Django administrative CLI
├── requirements.txt                 # Dependencies (Django, psycopg2-binary, numpy, pandas, matplotlib)
├── README.md                        # Quickstart instructions and command reference
├── CODE_EXPLANATION.md              # Technical code walkthrough (this document)
├── verify_match.py                  # Section 7.3 numerical parity verification script
├── run_section8_forecast.py         # Section 8 ML data preparation, baseline & model evaluation
├── generate_report.py               # Compiles complete Sections 7 & 8 report into Word (.docx)
├── section8_forecast_plot.png       # Matplotlib visualization of test week actuals vs. model
├── Gridboard_Assignment_I_Section_7_Report.docx # Formatted academic/executive report
│
├── gridboard/                       # Django project configuration
│   ├── settings.py                  # Database credentials, timezone (Africa/Kigali), cache disabled
│   ├── urls.py                      # Root URL configuration delegating to dashboard
│   └── wsgi.py                      # WSGI web server gateway
│
└── dashboard/                       # Core telemetry application
    ├── db.py                        # psycopg2 connection pool, timer helper, CAT midnight converter
    ├── queries.py                   # Parameterized SQL statements for RAW and AGG panels
    ├── urls.py                      # App URL routing (/raw/, /aggregate/, /forecast/, /api/...)
    ├── views.py                     # HTTP view handlers, JSON API, and CSV export logic
    ├── static/dashboard/
    │   ├── dashboard.css            # Executive SCADA theme styles, responsive 2x2 grid, dark/light vars
    │   └── dashboard.js             # Chart.js rendering, filters, 1+10 benchmark runner, CSV exporter
    └── templates/dashboard/
        ├── dashboard.html           # Main template for Raw and Aggregate telemetry views
        └── forecast.html            # Dedicated Section 8 interactive forecast dashboard
```

---

## 3. Deep-Dive: Database Layer & Queries (`dashboard/queries.py`)

All telemetry panels use raw, parameterized SQL queries to bypass Django ORM overhead and leverage native TimescaleDB functions (`time_bucket`).

Every query accepts four standardized parameters:
* `%(start)s`: Inclusive start timestamp (CAT midnight of first selected day, e.g. `2026-09-22 00:00:00+02:00`).
* `%(end)s`: Exclusive end timestamp (CAT midnight after last day, e.g. `2026-09-29 00:00:00+02:00`).
* `%(meter)s`: Selected smart meter ID (`BIGINT`, default `1000000000`).
* `%(days)s`: Integer count of whole 24-hour days in the selected range (e.g. `7`).

### 3.1 Five Telemetry Panels Breakdown

| Panel Key | Title & Metric | Raw Source Query | Aggregate Source View |
|---|---|---|---|
| `hourly_region` | Hourly Regional Energy (kWh) | `energy_readings` JOIN `meters` (`time_bucket('1 hour')`) | `cagg_hourly_region` (direct bucket read) |
| `daily_network` | Daily Network Energy (kWh) | `energy_readings` (`time_bucket('1 day')`) | `cagg_15min_region` rolled up to 1 day |
| `weekly_network`| 7-Day Period Energy (kWh) | Calendar-aligned formula over `energy_readings` | `cagg_15min_region` rolled up to 7-day blocks |
| `meter_daily`   | Selected Meter Daily (kWh) | `energy_readings` WHERE `meter_id = %(meter)s` | `cagg_daily_meter` WHERE `meter_id = %(meter)s` |
| `completeness`  | Regional Completeness (%) | CTE: observed rows / (meters × 96 × days) | CTE: `sum(reading_count)` from `cagg_15min_region` |

### 3.2 SQL Query Analysis

#### Panel 1: Hourly Regional Energy (`hourly_region`)
* **Raw SQL**:
  ```sql
  SELECT time_bucket(INTERVAL '1 hour', r.event_time, 'Africa/Kigali') AS bucket,
         m.region AS region,
         sum(r.energy_kwh) AS energy_kwh
  FROM energy_readings r
  JOIN meters m ON m.meter_id = r.meter_id
  WHERE r.event_time >= %(start)s AND r.event_time < %(end)s
  GROUP BY 1, 2 ORDER BY 1, 2;
  ```
  *Why Raw is slow*: Must scan 2.6M+ raw rows for a 7-day range, join on `meter_id`, and dynamically compute 1,680 time buckets.
* **Aggregate SQL**:
  ```sql
  SELECT bucket, region, energy_kwh_sum AS energy_kwh
  FROM cagg_hourly_region
  WHERE bucket >= %(start)s AND bucket < %(end)s
  ORDER BY 1, 2;
  ```
  *Why Aggregate is fast*: Directly reads pre-computed rows from a small table (only 6,720 rows for the entire month). Execution drops from **1,248 ms to 14 ms** (88x speedup).

#### Panel 3: Seven-Day Period Network Energy (`weekly_network`)
The assignment requires 7-day periods beginning strictly on 1, 8, 15, and 22 September:
```python
_WEEK = "(DATE '2026-09-01' + 7 * (({d}::date - DATE '2026-09-01') / 7))::text"
```
* In Raw Mode: Scans the entire 10.6M row table to evaluate all 4 historical weeks (**2,877 ms**).
* In Aggregate Mode: Sums `energy_kwh_sum` from `cagg_15min_region` (**12.5 ms** $\to$ **230x speedup**).

#### Panel 5: Regional Completeness (`completeness`)
* Formula: $\text{Completeness (\%)} = 100.0 \times \frac{\text{Observed Readings}}{\text{Registered Meters} \times 96 \times \text{Days}}$.
* In Aggregate Mode, `cagg_15min_region` stores pre-calculated `reading_count`, allowing PostgreSQL to calculate completeness across 4,000 meters in **7.3 ms** instead of scanning raw rows for **842 ms** (115x speedup).

---

## 4. Connection Pooling & Instrumentation (`dashboard/db.py`)

```python
POOL = ThreadedConnectionPool(
    minconn=1, maxconn=10,
    dbname=os.environ.get("PGDATABASE", "smartgrid"),
    user=os.environ.get("PGUSER", "postgres"),
    password=os.environ.get("PGPASSWORD", "CHANGE_ME"),
    host=os.environ.get("PGHOST", "127.0.0.1"),
    port=int(os.environ.get("PGPORT", "5433")),
    options="-c timezone=Africa/Kigali",
)
```
1. **Threaded Connection Pool**: Reuses persistent database connections across asynchronous HTTP panel requests, eliminating connection handshake latency.
2. **Session Timezone**: Automatically sets `timezone=Africa/Kigali`, ensuring `time_bucket(..., 'Africa/Kigali')` aligns buckets to CAT midnight (+02:00).
3. **High-Precision Timing**:
   ```python
   def timed_query(sql, params):
       t0 = time.perf_counter()
       # execute and fetch
       ms = (time.perf_counter() - t0) * 1000.0
       return cols, rows, round(ms, 2)
   ```
   Captures pure database execution and row retrieval time to sub-millisecond precision.

---

## 5. Web Views & REST Endpoints (`dashboard/views.py`)

### 5.1 Telemetry Endpoints
* `dashboard(request, mode)`: Renders `dashboard.html` for either `raw` or `aggregate` mode.
* `panel_data(request, mode, panel)`:
  * Validates date boundaries (`end > start`).
  * Executes the selected panel query via `timed_query`.
  * Returns JSON containing column headers, data rows, and `query_ms`.
  * Injects `Cache-Control: no-store` to prevent proxy or browser response caching.

### 5.2 Section 8 Forecasting Endpoints
* `forecast_view(request)`: Renders the dedicated Section 8 web dashboard (`forecast.html`).
* `forecast_data(request)`:
  * Accepts `?region=Region+X` (defaults to `Region 1`).
  * Returns JSON with overall test metrics (MAE, RMSE, error reduction), 168-hour time series arrays for Chart.js, model validation results, and peak-hour analysis.
* `forecast_export_csv(request)`:
  * Streams a complete 1,681-line CSV file download (`section8_forecast_predictions.csv`) containing `region`, `event_time_cat`, `hour_of_day`, `actual_energy_kwh`, `baseline_pred_kwh`, `baseline_abs_err_kwh`, `model_pred_kwh`, and `model_abs_err_kwh`.
* **In-Memory Cache Singleton (`_FORECAST_CACHE`)**:
  * Trains the Ridge model and generates predictions once on server start.
  * Ensures subsequent browser page reloads and region tab clicks respond instantaneously ($< 2\text{ ms}$).

---

## 6. Frontend Telemetry & Benchmark Harness (`dashboard.js` & `dashboard.css`)

### 6.1 Benchmark Harness (Section 7.4 Protocol)
When the operator clicks **"Run benchmark (1 warm-up + 10)"**:
1. Executes **1 unrecorded warm-up refresh** to prime database buffer pools and network sockets.
2. Executes **10 recorded refreshes** sequentially.
3. On each run:
   - Measures end-to-end rendering time with `performance.now()`.
   - Fires parallel `fetch()` requests for all 5 panels with cache-busting timestamp parameters (`_t=Date.now()`).
   - Collects per-panel server query execution times.
4. Calculates **median, minimum, and maximum** latencies in milliseconds.
5. Displays an interactive summary table and provides a **"Download benchmark.csv"** export button.

### 6.2 Visual Styling System
* **SCADA Light Theme**: Clean `#f8fafc` canvas, `#ffffff` card surfaces, `#e2e8f0` subtle borders.
* **Top Wide Card**: Panel 1 (`hourly_region`) spans the full desktop width (330px canvas) so all 10 regional series over 168 hours are legible.
* **2x2 Grid**: Panels 2 through 5 are arranged in a balanced two-column grid that automatically collapses to a single column on tablet/mobile screens.
* **Region Legend Chips**: Clicking region badges toggles series visibility in the chart dynamically.

---

## 7. Numerical Parity Verification Script (`verify_match.py`)

Ensures mathematical equivalence between Raw and Aggregate modes before performance benchmarking:
* **Test Window**: 00:00 CAT 22 September to 00:00 CAT 29 September 2026 (exclusive), meter `1000000000`, 10 regions.
* **Row-by-Row Comparison**:
  * Compares row count and primary keys.
  * Checks that maximum absolute energy difference $\le 0.001\text{ kWh}$.
  * Checks that completeness percentage difference $\le 0.000001\%$.
  * Verifies reading count per bucket is identical.
* **Measured Result**:
  * Maximum energy discrepancy across all rollups: **$0.000000014\text{ kWh}$** (8 orders of magnitude below tolerance, attributable to IEEE 754 floating-point summation re-ordering).
  * Parity status: **PASS** (Zero parity errors).

---

## 8. Section 8 Day-Ahead Forecasting Engine (`run_section8_forecast.py`)

### 8.1 Chronological Splits & Zero-Leakage Origin Rule
* **Total Dataset**: 6,720 hourly regional observations ($28\text{ days} \times 24\text{ hours} \times 10\text{ regions}$).
* **Splits**:
  * Training: 1 to 14 September (3,360 rows before exclusion; 1,680 warmup rows excluded $\to$ **1,680 usable training rows**).
  * Validation: 15 to 21 September (**1,680 rows**).
  * Testing: 22 to 28 September (**1,680 rows**).
* **Origin Rule**: In day-ahead dispatch, forecasts for hours 00:00 through 23:00 are generated at 00:00 CAT of that day. No intra-day hours are used as predictors, eliminating temporal leakage.

### 8.2 Feature Engineering
* **Cyclic Harmonics**:
  $$\text{hour\_sin} = \sin\left(\frac{2\pi \cdot \text{hour}}{24}\right), \quad \text{hour\_cos} = \cos\left(\frac{2\pi \cdot \text{hour}}{24}\right)$$
  $$\text{dow\_sin} = \sin\left(\frac{2\pi \cdot \text{dow}}{7}\right), \quad \text{dow\_cos} = \cos\left(\frac{2\pi \cdot \text{dow}}{7}\right)$$
* **Autoregressive Lags**:
  * $t-24$: Same hour previous calendar day (persistence benchmark).
  * $t-48$: Same hour 2 days prior.
  * $t-168$: Same hour 7 days prior (captures weekly seasonal demand patterns).
* **Prior Completed-Day Statistics**: Rolling 24-hour mean and maximum consumption from the preceding day.

### 8.3 Model Architecture & Closed-Form Solver
We implement **Ridge Regression (L2 regularized OLS)**:
$$\mathbf{w} = \left(\mathbf{X}^T \mathbf{X} + \alpha \mathbf{I}\right)^{-1} \mathbf{X}^T \mathbf{y}$$
* Solved directly via `np.linalg.solve` without regularizing the bias/intercept term.
* Prevents collinearity issues among multi-day lags and requires zero external C-dependencies.

### 8.4 Model Selection & Test Results
* **Config 1** (Linear Lags $t-24, t-48$ + Harmonics, $\alpha=1.0$): Validation MAE = $18.54\text{ kWh}$, RMSE = $23.86\text{ kWh}$.
* **Config 2** (Seasonal Lags $t-24, t-48, t-168$ + Prior Day Stats + Harmonics, $\alpha=0.5$): Validation MAE = **$14.21\text{ kWh}$**, RMSE = **$18.72\text{ kWh}$** (**Winner - Frozen for test**).

#### Test Split Evaluation (1,680 Hourly Observations)
* **Overall Baseline ($t-24$)**: MAE = $32.19\text{ kWh}$, RMSE = $45.87\text{ kWh}$.
* **Overall Model (Config 2)**: MAE = **$14.83\text{ kWh}$** (**$53.9\%$ Error Reduction**), RMSE = **$19.21\text{ kWh}$** (**$58.1\%$ Error Reduction**).
* **Peak Hour Analysis**: Captures evening peak (18:00 CAT) across all 10 regions, reducing peak forecasting error in Region 3 to $0.35\text{ kWh}$ and Region 10 to $2.16\text{ kWh}$.

---

## 9. Word Report Generator (`generate_report.py`)

A Python script using `python-docx` that compiles the official **Assignment I Report** (`Gridboard_Assignment_I_Section_7_Report.docx`):
* Formats margins, headings, callout boxes, and metadata tables according to executive and academic presentation standards.
* Generates all required tables:
  * Raw and Aggregate SQL query mappings
  * Section 7.3 numerical parity results
  * Section 7.4 benchmark timing statistics (Median, Min, Max, Speedup)
  * Section 6.1 continuous aggregate storage (18.4 MB) and initial refresh costs (42.1s)
  * Section 8.1 lookback accounting and feature dictionary
  * Section 8.3 model validation comparison
  * Section 8.4 regional error comparison and peak-hour analysis
* Insets Figure placeholders with desktop taskbar and CAT system clock context.
* Embeds the high-resolution test week forecast chart (`section8_forecast_plot.png`).

---

## 10. Execution Quickstart

```cmd
:: 1. Navigate to directory
cd unzipped\gridboard

:: 2. Set database environment variables
set PGPASSWORD=your_database_password
set PGPORT=5433

:: 3. Run Section 7.3 Numerical Parity Verification
python verify_match.py 2026-09-22 2026-09-29 1000000000

:: 4. Run Section 8 Machine Learning Forecasting Pipeline
python run_section8_forecast.py

:: 5. Compile the complete Word Report (.docx)
python generate_report.py

:: 6. Launch the Web Application
python manage.py runserver 127.0.0.1:8000
```
Open your browser to:
- **Raw Telemetry**: `http://127.0.0.1:8000/raw/`
- **Aggregate Telemetry**: `http://127.0.0.1:8000/aggregate/`
- **Section 8 Demand Forecast**: `http://127.0.0.1:8000/forecast/`
