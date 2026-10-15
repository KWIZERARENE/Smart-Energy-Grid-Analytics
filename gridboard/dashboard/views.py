import csv
import io
import json
from datetime import timedelta
import numpy as np

from django.http import Http404, HttpResponse, HttpResponseBadRequest, JsonResponse
from django.shortcuts import redirect, render

from .db import cat_midnight, timed_query
from .queries import MODES, PANELS, TITLES

import run_section8_forecast

DEFAULT_START = "2026-09-22"
DEFAULT_END = "2026-09-29"      # exclusive
DEFAULT_METER = 1000000000

# In-memory cache for Section 8 forecast data to ensure instantaneous rendering
_FORECAST_CACHE = None

def get_forecast_cache():
    global _FORECAST_CACHE
    if _FORECAST_CACHE is None:
        df = run_section8_forecast.generate_hourly_regional_dataset()
        df_feat = run_section8_forecast.build_features(df)

        train_mask = (df_feat["day_of_month"] >= 8) & (df_feat["day_of_month"] <= 14)
        val_mask = (df_feat["day_of_month"] >= 15) & (df_feat["day_of_month"] <= 21)
        test_mask = (df_feat["day_of_month"] >= 22) & (df_feat["day_of_month"] <= 28)

        config1_cols = ["lag_24", "lag_48", "hour_sin", "hour_cos", "dow_sin", "dow_cos", "is_weekend"]
        config2_cols = ["lag_24", "lag_48", "lag_168", "prior_day_mean", "prior_day_max", "hour_sin", "hour_cos", "dow_sin", "dow_cos", "is_weekend"]

        y_train = df_feat.loc[train_mask, "energy_kwh"].values
        X_train_c1 = df_feat.loc[train_mask, config1_cols].values
        X_train_c2 = df_feat.loc[train_mask, config2_cols].values

        y_val = df_feat.loc[val_mask, "energy_kwh"].values
        X_val_c1 = df_feat.loc[val_mask, config1_cols].values
        X_val_c2 = df_feat.loc[val_mask, config2_cols].values

        _, val_pred_c1 = run_section8_forecast.run_ridge_regression(X_train_c1, y_train, X_val_c1, alpha=1.0)
        val_mae_c1, val_rmse_c1 = run_section8_forecast.evaluate_metrics(y_val, val_pred_c1)

        w_c2, val_pred_c2 = run_section8_forecast.run_ridge_regression(X_train_c2, y_train, X_val_c2, alpha=0.5)
        val_mae_c2, val_rmse_c2 = run_section8_forecast.evaluate_metrics(y_val, val_pred_c2)

        # Test inference
        test_df = df_feat[test_mask].copy().reset_index(drop=True)
        y_test = test_df["energy_kwh"].values
        baseline_pred = test_df["lag_24"].values

        X_test_c2 = test_df[config2_cols].values
        X_test_with_intercept = np.hstack([np.ones((X_test_c2.shape[0], 1)), X_test_c2])
        model_pred = X_test_with_intercept @ w_c2

        test_df["baseline_pred"] = baseline_pred
        test_df["model_pred"] = model_pred
        test_df["base_abs_err"] = np.abs(test_df["baseline_pred"] - test_df["energy_kwh"])
        test_df["model_abs_err"] = np.abs(test_df["model_pred"] - test_df["energy_kwh"])

        base_mae, base_rmse = run_section8_forecast.evaluate_metrics(y_test, baseline_pred)
        model_mae, model_rmse = run_section8_forecast.evaluate_metrics(y_test, model_pred)
        pct_mae_imp = 100.0 * (base_mae - model_mae) / base_mae
        pct_rmse_imp = 100.0 * (base_rmse - model_rmse) / base_rmse

        # Regional summary
        reg_summary = []
        for r_id in range(1, 11):
            r_name = f"Region {r_id}"
            sub = test_df[test_df["region"] == r_name]
            b_m, b_r = run_section8_forecast.evaluate_metrics(sub["energy_kwh"].values, sub["baseline_pred"].values)
            m_m, m_r = run_section8_forecast.evaluate_metrics(sub["energy_kwh"].values, sub["model_pred"].values)
            reg_summary.append({
                "region": r_name,
                "base_mae": round(b_m, 2),
                "base_rmse": round(b_r, 2),
                "model_mae": round(m_m, 2),
                "model_rmse": round(m_r, 2),
                "mae_reduction_pct": round(100.0 * (b_m - m_m) / b_m, 1)
            })

        # Peak summary
        peak_summary = []
        for r_id in range(1, 11):
            r_name = f"Region {r_id}"
            sub = test_df[test_df["region"] == r_name].sort_values(by=["energy_kwh", "event_time"], ascending=[False, True])
            top = sub.iloc[0]
            peak_summary.append({
                "region": r_name,
                "peak_hour": top["event_time"].strftime("%Y-%m-%d %H:00"),
                "actual_kwh": round(float(top["energy_kwh"]), 2),
                "base_pred_kwh": round(float(top["baseline_pred"]), 2),
                "base_err_kwh": round(float(top["base_abs_err"]), 2),
                "model_pred_kwh": round(float(top["model_pred"]), 2),
                "model_err_kwh": round(float(top["model_abs_err"]), 2)
            })

        # Serialized time series per region for frontend charting
        time_series = {}
        for r_id in range(1, 11):
            r_name = f"Region {r_id}"
            sub = test_df[test_df["region"] == r_name].sort_values(by="event_time")
            time_series[r_name] = {
                "timestamps": [t.strftime("%d %b %H:00") for t in sub["event_time"]],
                "actual": [round(float(v), 2) for v in sub["energy_kwh"]],
                "baseline": [round(float(v), 2) for v in sub["baseline_pred"]],
                "model": [round(float(v), 2) for v in sub["model_pred"]],
            }

        _FORECAST_CACHE = {
            "overall": {
                "base_mae": round(float(base_mae), 2),
                "base_rmse": round(float(base_rmse), 2),
                "model_mae": round(float(model_mae), 2),
                "model_rmse": round(float(model_rmse), 2),
                "mae_reduction_pct": round(float(pct_mae_imp), 1),
                "rmse_reduction_pct": round(float(pct_rmse_imp), 1),
                "test_rows": int(len(test_df)),
                "train_rows_retained": int(train_mask.sum()),
                "val_rows": int(val_mask.sum()),
            },
            "validation": [
                {
                    "config": "Config 1",
                    "desc": "Linear Autoregressive Lags (t-24, t-48) + Harmonics (α=1.0)",
                    "train_rows": int(train_mask.sum()),
                    "val_rows": int(val_mask.sum()),
                    "val_mae": round(float(val_mae_c1), 2),
                    "val_rmse": round(float(val_rmse_c1), 2),
                    "status": "Evaluated"
                },
                {
                    "config": "Config 2",
                    "desc": "Harmonic Seasonal AR (t-24, t-48, t-168) + Prior Day Stats (α=0.5)",
                    "train_rows": int(train_mask.sum()),
                    "val_rows": int(val_mask.sum()),
                    "val_mae": round(float(val_mae_c2), 2),
                    "val_rmse": round(float(val_rmse_c2), 2),
                    "status": "Selected & Frozen"
                }
            ],
            "regional_summary": reg_summary,
            "peak_summary": peak_summary,
            "time_series": time_series,
            "raw_test_df": test_df
        }
    return _FORECAST_CACHE


def index(request):
    return redirect("raw")


def dashboard(request, mode):
    return render(request, "dashboard/dashboard.html", {
        "mode": mode,
        "name": "Raw" if mode == "raw" else "Aggregate",
        "panels": [(p, TITLES[p]) for p in PANELS],
        "start": request.GET.get("start", DEFAULT_START),
        "end": request.GET.get("end", DEFAULT_END),
        "meter": request.GET.get("meter", DEFAULT_METER),
    })


def forecast_view(request):
    data = get_forecast_cache()
    return render(request, "dashboard/forecast.html", {
        "mode": "forecast",
        "name": "Section 8 Day-Ahead Forecast",
        "overall": data["overall"],
        "validation": data["validation"],
        "regional_summary": data["regional_summary"],
        "peak_summary": data["peak_summary"],
    })


def forecast_data(request):
    cache = get_forecast_cache()
    region = request.GET.get("region", "Region 1")
    if region not in cache["time_series"]:
        region = "Region 1"

    response = JsonResponse({
        "selected_region": region,
        "overall": cache["overall"],
        "time_series": cache["time_series"][region],
        "regional_summary": cache["regional_summary"],
        "peak_summary": cache["peak_summary"]
    })
    response["Cache-Control"] = "no-store"
    return response


def forecast_export_csv(request):
    cache = get_forecast_cache()
    df = cache["raw_test_df"]
    response = HttpResponse(content_type="text/csv")
    response["Content-Disposition"] = 'attachment; filename="section8_forecast_predictions.csv"'
    
    writer = csv.writer(response)
    writer.writerow([
        "region", "event_time_cat", "hour_of_day", "actual_energy_kwh", 
        "baseline_pred_kwh", "baseline_abs_err_kwh", "model_pred_kwh", "model_abs_err_kwh"
    ])
    for _, row in df.iterrows():
        writer.writerow([
            row["region"],
            row["event_time"].strftime("%Y-%m-%d %H:00:00+02:00"),
            row["hour_of_day"],
            round(float(row["energy_kwh"]), 3),
            round(float(row["baseline_pred"]), 3),
            round(float(row["base_abs_err"]), 3),
            round(float(row["model_pred"]), 3),
            round(float(row["model_abs_err"]), 3)
        ])
    return response


def panel_params(request):
    start = cat_midnight(request.GET.get("start", DEFAULT_START))
    end = cat_midnight(request.GET.get("end", DEFAULT_END))
    if end <= start:
        raise ValueError("end must be after start")
    meter = int(request.GET.get("meter", DEFAULT_METER))
    days = (end - start) // timedelta(days=1)
    return {"start": start, "end": end, "meter": meter, "days": days}


def panel_data(request, mode, panel):
    if mode not in MODES or panel not in PANELS:
        raise Http404
    try:
        params = panel_params(request)
    except (ValueError, TypeError) as exc:
        return HttpResponseBadRequest(str(exc))
    columns, rows, query_ms = timed_query(MODES[mode][panel], params)
    response = JsonResponse({
        "mode": mode, "panel": panel, "title": TITLES[panel],
        "columns": columns, "rows": rows, "query_ms": query_ms,
    })
    response["Cache-Control"] = "no-store"
    return response
