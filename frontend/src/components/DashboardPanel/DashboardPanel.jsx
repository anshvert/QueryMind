import {
  BarChart, Bar, CartesianGrid, XAxis, YAxis, Tooltip, ResponsiveContainer, Legend,
  LineChart, Line,
  PieChart, Pie, Cell,
} from "recharts";

const PALETTE = ["#3b82f6", "#10b981", "#f59e0b", "#ef4444", "#8b5cf6", "#06b6d4", "#f97316"];

// ── Helpers ────────────────────────────────────────────────────────────────────
// Normalize a series entry — LLM may return string OR {dataKey, name} object
const toKey = (s) =>
  !s ? "" : typeof s === "string" ? s : s?.dataKey || s?.key || s?.name || "";

// Round numbers to 2 dp in the data table
const fmt = (val) => {
  if (typeof val === "number") {
    return Number.isInteger(val) ? val.toLocaleString() : parseFloat(val.toFixed(2)).toLocaleString();
  }
  return String(val ?? "");
};

// Auto-detect chart spec from raw data rows
function autoDetectSpec(data, question = "") {
  if (!data?.length) return null;
  const keys    = Object.keys(data[0]);
  const numKeys = keys.filter((k) => typeof data[0][k] === "number");
  const txtKeys = keys.filter((k) => typeof data[0][k] !== "number");

  if (!numKeys.length) return null;

  // If only 1 row with multiple numeric keys → KPI cards, no chart
  if (data.length === 1) return null;

  // Pick the best x-axis (first text column) and series (numeric columns that are NOT the x-axis)
  const xAxis = txtKeys[0] || keys[0];
  const series = numKeys.filter((k) => k !== xAxis).slice(0, 3);

  if (!series.length) return null;

  const q = question.toLowerCase();
  const type = (q.includes("trend") || q.includes("over time") || q.includes("by year") || q.includes("by month"))
    ? "line"
    : (q.includes("pie") || q.includes("proportion") || q.includes("share"))
    ? "pie"
    : "bar";

  return {
    type,
    title: "Query Results",
    xAxis,
    yAxis: series[0],
    series,
  };
}

// ── Chart Component ────────────────────────────────────────────────────────────
function Chart({ spec, data }) {
  if (!spec || !data?.length) return (
    <div style={{ color: "var(--text-muted)", fontSize: 12, padding: 20, textAlign: "center" }}>
      No data available for this chart.
    </div>
  );

  const type = (spec.type || "bar").toLowerCase();

  // Resolve keys — always strings
  const xKey = toKey(spec.xAxis) || Object.keys(data[0] || {})[0];
  const rawSeries = spec.series || [spec.yAxis || spec.valueKey];
  const seriesKeys = rawSeries.map(toKey).filter((k) => k && k !== xKey);

  // Fallback: pick first numeric column that isn't the x-axis
  const finalSeries = seriesKeys.length
    ? seriesKeys
    : Object.keys(data[0] || {}).filter((k) => k !== xKey && typeof data[0][k] === "number").slice(0, 3);

  const tooltipStyle = { background: "#0c1628", border: "1px solid #1e3a5f", borderRadius: 8, fontSize: 12 };

  if (type === "line") return (
    <ResponsiveContainer width="100%" height={240}>
      <LineChart data={data}>
        <CartesianGrid strokeDasharray="3 3" stroke="#1e3a5f" />
        <XAxis dataKey={xKey} tick={{ fill: "#64748b", fontSize: 11 }} />
        <YAxis tick={{ fill: "#64748b", fontSize: 11 }} />
        <Tooltip contentStyle={tooltipStyle} />
        <Legend />
        {finalSeries.map((key, i) => (
          <Line key={key} type="monotone" dataKey={key} stroke={PALETTE[i % PALETTE.length]} dot={false} strokeWidth={2} />
        ))}
      </LineChart>
    </ResponsiveContainer>
  );

  if (type === "pie" || type === "donut") {
    const valueKey = finalSeries[0] || Object.keys(data[0] || {}).find(k => typeof data[0][k] === "number") || "value";
    return (
      <ResponsiveContainer width="100%" height={260}>
        <PieChart>
          <Pie
            data={data}
            dataKey={valueKey}
            nameKey={xKey}
            cx="50%" cy="50%"
            outerRadius={type === "donut" ? 90 : 100}
            innerRadius={type === "donut" ? 55 : 0}
            label={({ name, percent }) => `${name} (${(percent * 100).toFixed(0)}%)`}
            labelLine={false}
          >
            {data.map((_, i) => <Cell key={i} fill={PALETTE[i % PALETTE.length]} />)}
          </Pie>
          <Tooltip contentStyle={tooltipStyle} />
        </PieChart>
      </ResponsiveContainer>
    );
  }

  // Default: bar
  return (
    <ResponsiveContainer width="100%" height={240}>
      <BarChart data={data} margin={{ top: 4, right: 8, left: 0, bottom: 4 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="#1e3a5f" />
        <XAxis dataKey={xKey} tick={{ fill: "#64748b", fontSize: 11 }} />
        <YAxis tick={{ fill: "#64748b", fontSize: 11 }} />
        <Tooltip contentStyle={tooltipStyle} />
        <Legend />
        {finalSeries.map((key, i) => (
          <Bar key={key} dataKey={key} fill={PALETTE[i % PALETTE.length]} radius={[3, 3, 0, 0]} />
        ))}
      </BarChart>
    </ResponsiveContainer>
  );
}

// ── KPI Cards ──────────────────────────────────────────────────────────────────
function KPICards({ data }) {
  if (!data?.length) return null;
  const keys = Object.keys(data[0]);
  const numKeys = keys.filter((k) => typeof data[0][k] === "number");
  if (!numKeys.length) return null;

  // Show KPI cards when result is 1 row with multiple numeric columns
  if (data.length === 1) {
    return (
      <div className="kpi-grid">
        {numKeys.map((k) => (
          <div className="kpi-card" key={k}>
            <div className="kpi-title">{k.replace(/_/g, " ")}</div>
            <div className="kpi-value">{fmt(data[0][k])}</div>
          </div>
        ))}
      </div>
    );
  }
  return null;
}

// ── Data Table ─────────────────────────────────────────────────────────────────
function DataTable({ data }) {
  if (!data?.length) return null;
  const cols = Object.keys(data[0]);
  const rows = data.slice(0, 50);

  const downloadCSV = () => {
    const header = cols.join(",");
    const body = rows.map((r) => cols.map((c) => JSON.stringify(r[c] ?? "")).join(",")).join("\n");
    const blob = new Blob([header + "\n" + body], { type: "text/csv" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a"); a.href = url; a.download = "results.csv"; a.click();
  };

  return (
    <div className="data-table-wrap">
      <div className="data-table-title" style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <span>Raw Results — {data.length} row{data.length !== 1 ? "s" : ""}</span>
        <button className="sql-toggle-btn" onClick={downloadCSV}>↓ CSV</button>
      </div>
      <div className="data-table-scroll">
        <table className="data-table">
          <thead>
            <tr>{cols.map((c) => <th key={c}>{c.replace(/_/g, " ")}</th>)}</tr>
          </thead>
          <tbody>
            {rows.map((row, i) => (
              <tr key={i}>
                {cols.map((c) => <td key={c}>{fmt(row[c])}</td>)}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

// ── Dashboard Panel ────────────────────────────────────────────────────────────
export default function DashboardPanel({ dashboardSpec, data, loading }) {
  // Normalise spec — backend may return {charts:[...], kpis:[...]} or a single chart object
  let charts = [];
  let kpis   = [];

  if (dashboardSpec) {
    if (Array.isArray(dashboardSpec.charts)) {
      charts = dashboardSpec.charts;
      kpis   = dashboardSpec.kpis || [];
    } else if (dashboardSpec.type) {
      charts = [dashboardSpec];
    }
  }

  // Fallback auto-detect from raw data
  if (!charts.length && data?.length) {
    const auto = autoDetectSpec(data);
    if (auto) charts = [auto];
  }

  const showKPIs = data?.length === 1;
  const hasContent = Boolean((charts.length > 0 && data?.length > 1) || showKPIs || data?.length > 0);

  return (
    <section className="dashboard-panel">
      <div className="dashboard-header">
        <div className="panel-title">Live Dashboard</div>
        {data?.length > 0 && (
          <span style={{ fontSize: 11, color: "var(--text-muted)" }}>
            {data.length} row{data.length !== 1 ? "s" : ""}
          </span>
        )}
      </div>

      <div className="dashboard-content">
        {/* Loading skeleton */}
        {loading && (
          <div className="dashboard-skeleton">
            <div className="skeleton-kpi" />
            <div className="skeleton-chart" />
          </div>
        )}

        {!loading && !hasContent && (
          <div className="empty-state">
            <div className="empty-icon">📊</div>
            <p>Ask a question to generate a live chart.<br />Dashboard will appear here automatically.</p>
          </div>
        )}

        {!loading && hasContent && (
          <>
            {/* KPI row for manual spec */}
            {kpis.length > 0 && (
              <div className="kpi-grid">
                {kpis.map((kpi, i) => (
                  <div className="kpi-card" key={i}>
                    <div className="kpi-title">{kpi.title || kpi.label}</div>
                    <div className="kpi-value">{fmt(kpi.value)}</div>
                  </div>
                ))}
              </div>
            )}

            {/* Auto KPI cards for single-row results */}
            <KPICards data={data} />

            {/* Charts */}
            <div className="chart-grid">
              {charts.map((spec, i) => (
                <div className="chart-card" key={i}>
                  <div className="chart-title">{spec.title || `Chart ${i + 1}`}</div>
                  <Chart spec={spec} data={data} />
                </div>
              ))}
            </div>

            {/* Raw data table */}
            <DataTable data={data} />
          </>
        )}
      </div>
    </section>
  );
}
