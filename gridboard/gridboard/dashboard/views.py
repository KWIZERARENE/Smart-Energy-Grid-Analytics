from datetime import timedelta

from django.http import Http404, HttpResponseBadRequest, JsonResponse
from django.shortcuts import redirect, render

from .db import cat_midnight, timed_query
from .queries import MODES, PANELS, TITLES

DEFAULT_START = "2026-09-22"
DEFAULT_END = "2026-09-29"      # exclusive
DEFAULT_METER = 1000000000


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
