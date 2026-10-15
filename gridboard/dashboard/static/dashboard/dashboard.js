// Front end for the Raw and Aggregate dashboards (Assignment I, Section 7)
// High-performance light theme data visualization with Chart.js
(function () {
  const { mode, panels } = window.DASH;
  const charts = {};

  // Harmonious, distinct palette for the 10 regions on clean light backgrounds
  const palette = [
    "#0284c7", // Sky blue (Region 1)
    "#ea580c", // Orange (Region 2)
    "#16a34a", // Emerald (Region 3)
    "#dc2626", // Red (Region 4)
    "#8b5cf6", // Purple (Region 5)
    "#ca8a04", // Dark Yellow/Gold (Region 6)
    "#0d9488", // Teal (Region 7)
    "#db2777", // Pink (Region 8)
    "#4f46e5", // Indigo (Region 9)
    "#65a30d"  // Lime (Region 10)
  ];

  function fmtNum(val, decimals = 2) {
    if (val === null || val === undefined || isNaN(val)) return "-";
    return Number(val).toLocaleString(undefined, {
      minimumFractionDigits: decimals,
      maximumFractionDigits: decimals
    });
  }

  function fmtCompact(val) {
    if (Math.abs(val) >= 1e6) return (val / 1e6).toFixed(1) + "M";
    if (Math.abs(val) >= 1e3) return (val / 1e3).toFixed(0) + "k";
    return val;
  }

  function formatWeekLabel(dateStr) {
    const d = dateStr.slice(0, 10);
    const weekMap = {
      "2026-09-01": "Week 1 (1–7 Sep)",
      "2026-09-08": "Week 2 (8–14 Sep)",
      "2026-09-15": "Week 3 (15–21 Sep)",
      "2026-09-22": "Week 4 (22–28 Sep)"
    };
    return weekMap[d] || `Week of ${d}`;
  }

  function formatDayLabel(dateStr) {
    try {
      const parts = dateStr.slice(0, 10).split("-");
      if (parts.length === 3) {
        const monthNames = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
        const day = parseInt(parts[2], 10);
        const m = monthNames[parseInt(parts[1], 10) - 1];
        return `${day} ${m}`;
      }
    } catch (_) {}
    return dateStr.slice(0, 10);
  }

  function currentQuery() {
    const f = new FormData(document.getElementById("filters"));
    return new URLSearchParams({
      start: f.get("start"),
      end: f.get("end"),
      meter: f.get("meter")
    });
  }

  function draw(panel, data) {
    const canvas = document.getElementById("chart-" + panel);
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (charts[panel]) charts[panel].destroy();

    const rows = data.rows;
    const axisColor = "#64748b";
    const gridColor = "#f1f5f9";

    const commonAxis = (text) => ({
      title: { display: true, text, color: axisColor, font: { size: 11, weight: "600" } },
      ticks: {
        color: axisColor,
        font: { size: 10 },
        callback: (v) => fmtCompact(v)
      },
      grid: { color: gridColor }
    });

    let config;

    if (panel === "hourly_region") {
      const times = [...new Set(rows.map(r => r[0]))];
      const regions = [...new Set(rows.map(r => r[1]))];
      const lookup = new Map(rows.map(r => [r[0] + "|" + r[1], r[2]]));

      config = {
        type: "line",
        data: {
          labels: times.map(t => {
            // E.g. "2026-09-22T14:00:00+02:00" -> "22 Sep 14:00"
            const day = t.slice(8, 10);
            const time = t.slice(11, 16);
            return `${day} Sep ${time}`;
          }),
          datasets: regions.map((reg, i) => ({
            label: reg,
            borderColor: palette[i % palette.length],
            borderWidth: 1.5,
            pointRadius: 0,
            pointHoverRadius: 4,
            tension: 0.2,
            data: times.map(t => lookup.get(t + "|" + reg) ?? null),
          })),
        },
        options: {
          responsive: true,
          maintainAspectRatio: false,
          animation: false,
          interaction: { mode: "nearest", intersect: false },
          plugins: {
            legend: {
              position: "top",
              align: "center",
              labels: {
                color: "#334155",
                font: { size: 10, weight: "600" },
                boxWidth: 8,
                boxHeight: 8,
                padding: 8
              }
            },
            tooltip: {
              callbacks: {
                title: (items) => items.length ? items[0].label : "",
                label: (ctx) => ` ${ctx.dataset.label}: ${fmtNum(ctx.parsed.y)} kWh`
              }
            }
          },
          scales: {
            x: {
              ticks: {
                color: axisColor,
                font: { size: 10 },
                maxTicksLimit: 7,
                maxRotation: 0,
                callback: function(val, idx) {
                  const lbl = this.getLabelForValue(val);
                  return lbl.split(" ")[0] + " " + lbl.split(" ")[1]; // E.g. "22 Sep"
                }
              },
              grid: { color: gridColor }
            },
            y: commonAxis("Energy (kWh)")
          },
        },
      };
    } else if (panel === "weekly_network") {
      // Seven-day period network energy (kWh) - Displays all 4 weeks from Section 5.1
      const currentStart = document.querySelector('input[name="start"]')?.value || "";
      const bgColors = rows.map(r => {
        // Highlight active week if matched, else clean indigo
        return r[0] === currentStart ? "#4f46e5" : "#6366f1";
      });

      config = {
        type: "bar",
        data: {
          labels: rows.map(r => formatWeekLabel(r[0])),
          datasets: [{
            label: "Weekly Energy (kWh)",
            data: rows.map(r => r[1]),
            backgroundColor: bgColors,
            borderRadius: 5,
            maxBarThickness: 50
          }]
        },
        options: {
          responsive: true,
          maintainAspectRatio: false,
          animation: false,
          plugins: {
            legend: { display: false },
            tooltip: {
              callbacks: {
                label: (ctx) => ` Network Total: ${fmtNum(ctx.parsed.y, 2)} kWh`
              }
            }
          },
          scales: {
            x: {
              ticks: { color: axisColor, font: { size: 11, weight: "600" } },
              grid: { display: false }
            },
            y: {
              beginAtZero: true,
              ...commonAxis("Total Energy (kWh)")
            }
          },
        },
      };
    } else if (panel === "daily_network") {
      // Daily network energy (kWh)
      config = {
        type: "bar",
        data: {
          labels: rows.map(r => formatDayLabel(r[0])),
          datasets: [{
            label: "Daily Network Energy (kWh)",
            data: rows.map(r => r[1]),
            backgroundColor: "#2563eb",
            borderRadius: 4,
            maxBarThickness: 40
          }]
        },
        options: {
          responsive: true,
          maintainAspectRatio: false,
          animation: false,
          plugins: {
            legend: { display: false },
            tooltip: {
              callbacks: {
                label: (ctx) => ` Network Energy: ${fmtNum(ctx.parsed.y, 2)} kWh`
              }
            }
          },
          scales: {
            x: {
              ticks: { color: axisColor, font: { size: 11 } },
              grid: { display: false }
            },
            y: {
              beginAtZero: true,
              ...commonAxis("Energy (kWh)")
            }
          },
        },
      };
    } else if (panel === "meter_daily") {
      // Daily energy, selected meter (kWh)
      config = {
        type: "bar",
        data: {
          labels: rows.map(r => formatDayLabel(r[0])),
          datasets: [{
            label: "Meter Energy (kWh)",
            data: rows.map(r => r[1]),
            backgroundColor: "#d97706",
            borderRadius: 4,
            maxBarThickness: 40
          }]
        },
        options: {
          responsive: true,
          maintainAspectRatio: false,
          animation: false,
          plugins: {
            legend: { display: false },
            tooltip: {
              callbacks: {
                label: (ctx) => ` Meter Energy: ${fmtNum(ctx.parsed.y, 3)} kWh`
              }
            }
          },
          scales: {
            x: {
              ticks: { color: axisColor, font: { size: 11 } },
              grid: { display: false }
            },
            y: {
              beginAtZero: true,
              ...commonAxis("Energy (kWh)")
            }
          },
        },
      };
    } else {
      // Completeness by region (%)
      config = {
        type: "bar",
        data: {
          labels: rows.map(r => r[0]),
          datasets: [{
            label: "Completeness (%)",
            data: rows.map(r => r[3]),
            backgroundColor: "#16a34a",
            borderRadius: 4,
            maxBarThickness: 32
          }]
        },
        options: {
          responsive: true,
          maintainAspectRatio: false,
          animation: false,
          plugins: {
            legend: { display: false },
            tooltip: {
              callbacks: {
                label: (ctx) => {
                  const r = rows[ctx.dataIndex];
                  return [
                    ` Completeness: ${fmtNum(r[3], 2)}%`,
                    ` Observed: ${Number(r[1]).toLocaleString()} readings`,
                    ` Planned: ${Number(r[2]).toLocaleString()} readings`
                  ];
                }
              }
            }
          },
          scales: {
            x: {
              ticks: { color: axisColor, font: { size: 10 } },
              grid: { display: false }
            },
            y: {
              min: 98,
              max: 100,
              title: { display: true, text: "Completeness (%)", color: axisColor, font: { size: 11, weight: "600" } },
              ticks: {
                color: axisColor,
                font: { size: 10 },
                callback: (v) => `${v}%`
              },
              grid: { color: gridColor }
            }
          },
        },
      };
    }

    charts[panel] = new Chart(ctx, config);
  }

  async function loadPanel(panel, query) {
    const msEl = document.getElementById("ms-" + panel);
    if (msEl) msEl.textContent = "loading...";

    // For weekly_network: Always load all 4 weeks (1 to 29 Sep) as requested
    const q = new URLSearchParams(query);
    if (panel === "weekly_network") {
      q.set("start", "2026-09-01");
      q.set("end", "2026-09-29");
    }

    q.set("_", String(performance.now()) + Math.random()); // defeat cache
    try {
      const res = await fetch(`/api/${mode}/${panel}/?${q}`, { cache: "no-store" });
      if (!res.ok) throw new Error(panel + ": " + (await res.text()));
      const data = await res.json();
      draw(panel, data);
      if (msEl) {
        msEl.textContent = `query ${data.query_ms.toFixed(1)} ms, ${data.rows.length} rows`;
      }
      return data.query_ms;
    } catch (err) {
      if (msEl) msEl.textContent = "error: " + err.message;
      throw err;
    }
  }

  // Returns {perPanel: {panel: ms}, total: ms}
  async function refreshAll() {
    const query = currentQuery();
    const t0 = performance.now();
    const times = await Promise.all(panels.map(p => loadPanel(p, query)));
    await new Promise(r => requestAnimationFrame(() => requestAnimationFrame(r))); // rendered
    const total = performance.now() - t0;
    const perPanel = {};
    panels.forEach((p, i) => perPanel[p] = times[i]);
    const totalEl = document.getElementById("total");
    if (totalEl) {
      totalEl.textContent = `All panels rendered in ${total.toFixed(0)} ms`;
    }
    return { perPanel, total };
  }

  const median = (a) => {
    const s = [...a].sort((x, y) => x - y), m = s.length >> 1;
    return s.length % 2 ? s[m] : (s[m - 1] + s[m]) / 2;
  };

  async function runBenchmark() {
    const out = document.getElementById("bench");
    out.textContent = "Warm-up refresh...";
    await refreshAll(); // 1 warm-up, not recorded
    const runs = [];
    for (let i = 1; i <= 10; i++) {
      out.textContent = `Measured refresh ${i} of 10...`;
      const start = new Date();
      const r = await refreshAll();
      runs.push({ i, start: start.toISOString(), ...r });
    }
    const keys = [...panels, "dashboard_total"];
    const series = (k) => runs.map(r => k === "dashboard_total" ? r.total : r.perPanel[k]);
    let html = `<h3>${mode.toUpperCase()} Benchmark: 10 measured refreshes (ms)</h3>
      <table><thead><tr><th>Item</th><th>Median</th><th>Min</th><th>Max</th></tr></thead><tbody>`;
    for (const k of keys) {
      const s = series(k);
      html += `<tr><td>${k}</td><td>${median(s).toFixed(1)}</td><td>${Math.min(...s).toFixed(1)}</td><td>${Math.max(...s).toFixed(1)}</td></tr>`;
    }
    html += "</tbody></table><p><button id='csv'>Download per-run CSV</button></p>";
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
    refreshAll().catch(err => console.error(err));
  });
  document.getElementById("runBench").addEventListener("click", () =>
    runBenchmark().catch(err => console.error(err)));
  refreshAll().catch(err => console.error(err));
})();
