// Front end for the Raw and Aggregate dashboards.
// Loads the five panels in parallel and measures:
//   - per-panel query time reported by the server (query_ms)
//   - total time from requesting the refresh until all five panels finished rendering
(function () {
  const { mode, panels } = window.DASH;
  const charts = {};
  const palette = ["#1f77b4", "#ff7f0e", "#2ca02c", "#d62728", "#9467bd",
                   "#8c564b", "#e377c2", "#7f7f7f", "#bcbd22", "#17becf"];

  function currentQuery() {
    const f = new FormData(document.getElementById("filters"));
    return new URLSearchParams({ start: f.get("start"), end: f.get("end"), meter: f.get("meter") });
  }

  function draw(panel, data) {
    const ctx = document.getElementById("chart-" + panel);
    if (charts[panel]) charts[panel].destroy();
    let config;
    const rows = data.rows;
    const axis = (text) => ({ title: { display: true, text } });

    if (panel === "hourly_region") {
      const times = [...new Set(rows.map(r => r[0]))];
      const regions = [...new Set(rows.map(r => r[1]))];
      const lookup = new Map(rows.map(r => [r[0] + "|" + r[1], r[2]]));
      config = {
        type: "line",
        data: {
          labels: times.map(t => t.slice(5, 16).replace("T", " ")),
          datasets: regions.map((reg, i) => ({
            label: reg, borderColor: palette[i % palette.length], borderWidth: 1.2,
            pointRadius: 0, data: times.map(t => lookup.get(t + "|" + reg) ?? null),
          })),
        },
        options: { animation: false, scales: { y: axis("Energy (kWh)") } },
      };
    } else if (panel === "completeness") {
      config = {
        type: "bar",
        data: { labels: rows.map(r => r[0]),
                datasets: [{ label: "Completeness (%)", data: rows.map(r => r[3]), backgroundColor: "#2ca02c" }] },
        options: { animation: false, scales: { y: { ...axis("Completeness (%)"), min: 90, max: 100 } } },
      };
    } else {
      const label = panel === "weekly_network" ? (v) => "from " + v : (v) => v.slice(0, 10);
      config = {
        type: "bar",
        data: { labels: rows.map(r => label(r[0])),
                datasets: [{ label: "Energy (kWh)", data: rows.map(r => r[1]), backgroundColor: "#1f77b4" }] },
        options: { animation: false, scales: { y: axis("Energy (kWh)") } },
      };
    }
    charts[panel] = new Chart(ctx, config);
  }

  async function loadPanel(panel, query) {
    query.set("_", String(performance.now()) + Math.random());   // defeat any cache
    const res = await fetch(`/api/${mode}/${panel}/?${query}`, { cache: "no-store" });
    if (!res.ok) throw new Error(panel + ": " + (await res.text()));
    const data = await res.json();
    draw(panel, data);
    document.getElementById("ms-" + panel).textContent =
      `query ${data.query_ms.toFixed(1)} ms, ${data.rows.length} rows`;
    return data.query_ms;
  }

  // Returns {perPanel: {panel: ms}, total: ms}
  async function refreshAll() {
    const query = currentQuery();
    const t0 = performance.now();
    const times = await Promise.all(panels.map(p => loadPanel(p, new URLSearchParams(query))));
    await new Promise(r => requestAnimationFrame(() => requestAnimationFrame(r)));  // rendered
    const total = performance.now() - t0;
    const perPanel = {};
    panels.forEach((p, i) => perPanel[p] = times[i]);
    document.getElementById("total").textContent = `all panels rendered in ${total.toFixed(0)} ms`;
    return { perPanel, total };
  }

  const median = (a) => { const s = [...a].sort((x, y) => x - y), m = s.length >> 1;
                          return s.length % 2 ? s[m] : (s[m - 1] + s[m]) / 2; };

  async function runBenchmark() {
    const out = document.getElementById("bench");
    out.textContent = "Warm-up refresh...";
    await refreshAll();                              // 1 warm-up, not recorded
    const runs = [];
    for (let i = 1; i <= 10; i++) {
      out.textContent = `Measured refresh ${i} of 10...`;
      const start = new Date();
      const r = await refreshAll();
      runs.push({ i, start: start.toISOString(), ...r });
    }
    const keys = [...panels, "dashboard_total"];
    const series = (k) => runs.map(r => k === "dashboard_total" ? r.total : r.perPanel[k]);
    let html = `<h3>${mode} benchmark: 10 measured refreshes (ms)</h3>
      <table><tr><th>Item</th><th>Median</th><th>Min</th><th>Max</th></tr>`;
    for (const k of keys) {
      const s = series(k);
      html += `<tr><td>${k}</td><td>${median(s).toFixed(1)}</td><td>${Math.min(...s).toFixed(1)}</td><td>${Math.max(...s).toFixed(1)}</td></tr>`;
    }
    html += "</table><p><button id='csv'>Download per-run CSV</button></p>";
    out.innerHTML = html;
    document.getElementById("csv").onclick = () => {
      const head = ["run", "start_iso", ...panels, "dashboard_total"].join(",");
      const lines = runs.map(r => [r.i, r.start, ...panels.map(p => r.perPanel[p].toFixed(2)), r.total.toFixed(2)].join(","));
      const blob = new Blob([[head, ...lines].join("\n")], { type: "text/csv" });
      const a = document.createElement("a");
      a.href = URL.createObjectURL(blob);
      a.download = `benchmark_${mode}.csv`;
      a.click();
    };
  }

  document.getElementById("filters").addEventListener("submit", (e) => {
    e.preventDefault();
    refreshAll().catch(err => alert(err.message));
  });
  document.getElementById("runBench").addEventListener("click", () =>
    runBenchmark().catch(err => alert(err.message)));
  refreshAll().catch(err => alert(err.message));
})();
