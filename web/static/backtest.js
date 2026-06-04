const currencySelect = document.getElementById("currency");
const marketSelect = document.getElementById("market");
const stockPick = document.getElementById("stock-pick");
const symbolInput = document.getElementById("symbol");
const startInput = document.getElementById("start");
const endInput = document.getElementById("end");
const strategySelect = document.getElementById("strategy");
const initialCashInput = document.getElementById("initial-cash");
const runBtn = document.getElementById("run");
const compareBtn = document.getElementById("compare-all");
const scanPresetsBtn = document.getElementById("scan-presets");
const statusEl = document.getElementById("status");
const chartEl = document.getElementById("equity-chart");
const legendEl = document.getElementById("legend");
const strategyDescEl = document.getElementById("strategy-desc");
const singleResultsEl = document.getElementById("single-results");
const compareResultsEl = document.getElementById("compare-results");
const tradesSectionEl = document.getElementById("trades-section");

const STRATEGY_COLORS = {
  sma_crossover: "#2962ff",
  ma_cross_20_50: "#7e57c2",
  ma_trend_20_50: "#26a69a",
  rsi_mean_reversion: "#ab47bc",
  breakout_20: "#ff9800",
  trend_risk_control: "#00bcd4",
};

let japanStocks = [];
let usStocks = [];
let strategies = [];
let config = {};
let chart;
let chartSeries = [];

function effectiveCurrency() {
  const raw = currencySelect?.value || "auto";
  if (raw === "usd" || raw === "jpy") return raw;
  return marketSelect?.value === "jp" ? "jpy" : "usd";
}

function queryParams() {
  const p = new URLSearchParams();
  p.set("market", marketSelect?.value || "jp");
  p.set("currency", effectiveCurrency());
  return p;
}

function formatPrice(value, currency) {
  const n = Number(value);
  if (currency === "jpy") return `¥${n.toLocaleString(undefined, { maximumFractionDigits: 0 })}`;
  return `$${n.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

function formatPct(v) {
  if (v == null || Number.isNaN(v)) return "n/a";
  return `${v >= 0 ? "+" : ""}${Number(v).toFixed(2)}%`;
}

function renderDl(el, rows) {
  el.innerHTML = rows.map(([k, v]) => `<dt>${k}</dt><dd>${v}</dd>`).join("");
}

function defaultDates() {
  const end = new Date();
  end.setDate(end.getDate() - 1);
  const start = new Date(end);
  start.setFullYear(end.getFullYear() - 2);
  endInput.value = end.toISOString().slice(0, 10);
  startInput.value = start.toISOString().slice(0, 10);
}

function clearChartSeries() {
  chartSeries.forEach((s) => chart.removeSeries(s));
  chartSeries = [];
}

function initChart() {
  chart = LightweightCharts.createChart(chartEl, {
    width: chartEl.clientWidth || 800,
    height: chartEl.clientHeight || 480,
    layout: {
      background: { type: "solid", color: "#131722" },
      textColor: "#d1d4dc",
    },
    grid: {
      vertLines: { color: "#2a2e39" },
      horzLines: { color: "#2a2e39" },
    },
    rightPriceScale: { borderColor: "#2a2e39" },
    timeScale: { borderColor: "#2a2e39" },
  });
  new ResizeObserver(() => {
    chart.applyOptions({
      width: chartEl.clientWidth,
      height: chartEl.clientHeight,
    });
  }).observe(chartEl);
}

function setChartCurrency(ccy) {
  chart.applyOptions({
    localization: {
      priceFormatter: (p) =>
        ccy === "jpy"
          ? `¥${Math.round(p).toLocaleString()}`
          : `$${p.toFixed(2)}`,
    },
  });
}

function addEquitySeries(data, color, title, useArea = false) {
  let series;
  if (useArea) {
    series = chart.addAreaSeries({
      lineColor: color,
      topColor:
        color === "#2962ff" ? "rgba(41, 98, 255, 0.35)" : `${color}59`,
      bottomColor: "rgba(0,0,0,0)",
      lineWidth: 2,
      title,
    });
  } else {
    series = chart.addLineSeries({ color, lineWidth: 2, title });
  }
  series.setData(data.equity_curve || []);
  chartSeries.push(series);
  return series;
}

function fillStockPicker(market) {
  const list = market === "us" ? usStocks : japanStocks;
  stockPick.innerHTML = list
    .map((s) => `<option value="${s.symbol}">${s.symbol} — ${s.name}</option>`)
    .join("");
  if (list.length) symbolInput.value = list[0].symbol;
}

function fillStrategyPicker() {
  const supported = strategies.filter((s) => s.supported);
  strategySelect.innerHTML = supported
    .map(
      (s) =>
        `<option value="${s.id}" title="${s.description}">${s.name}</option>`
    )
    .join("");
  updateStrategyDescription();
}

function updateStrategyDescription() {
  const id = strategySelect?.value;
  const spec = strategies.find((s) => s.id === id);
  if (strategyDescEl && spec) {
    strategyDescEl.textContent = spec.description;
  }
}

function applyInitialCashForMarket(market) {
  if (!initialCashInput) return;
  if (market === "jp") {
    const jpy = config.backtest_initial_cash_jpy || 1_000_000;
    initialCashInput.min = 100000;
    initialCashInput.step = 100000;
    initialCashInput.placeholder = "Initial ¥";
    initialCashInput.value = Math.round(jpy);
  } else {
    const usd = config.backtest_initial_cash || 10_000;
    initialCashInput.min = 1000;
    initialCashInput.step = 1000;
    initialCashInput.placeholder = "Initial $";
    initialCashInput.value = Math.round(usd);
  }
}

async function loadConfig() {
  const [cfgRes, stratRes] = await Promise.all([
    fetch("/api/config"),
    fetch("/api/strategies"),
  ]);
  if (cfgRes.ok) {
    config = await cfgRes.json();
    japanStocks = config.japan_stocks || [];
    usStocks = config.us_stocks || [];
    if (config.market) marketSelect.value = config.market;
    if (config.symbol) symbolInput.value = config.symbol;
    fillStockPicker(marketSelect.value);
    const saved = localStorage.getItem("sat_currency");
    if (saved) currencySelect.value = saved;
    applyInitialCashForMarket(marketSelect.value);
  }
  if (stratRes.ok) {
    const data = await stratRes.json();
    strategies = data.strategies || [];
    fillStrategyPicker();
  }
}

function showSingleMode() {
  singleResultsEl?.classList.remove("hidden");
  compareResultsEl?.classList.add("hidden");
  tradesSectionEl?.classList.remove("hidden");
}

function showCompareMode() {
  singleResultsEl?.classList.add("hidden");
  compareResultsEl?.classList.remove("hidden");
  tradesSectionEl?.classList.add("hidden");
}

function renderConversion(data) {
  const convEl = document.getElementById("conversion");
  if (!data.conversion) {
    convEl.innerHTML = "";
    return;
  }
  const c = data.conversion;
  const rows = [
    ["You entered", data.input_symbol],
    ["Formula", c.formula || "—"],
    ["USD/JPY", c.fx_usdjpy ? c.fx_usdjpy.toFixed(2) : "—"],
  ];
  if (c.example) rows.push(["Example", c.example]);
  if (data.symbol_alias_note) rows.push(["Alias", data.symbol_alias_note]);
  renderDl(convEl, rows);
}

function renderSingleResults(data) {
  showSingleMode();
  const ccy = data.display_currency || "usd";
  setChartCurrency(ccy);
  clearChartSeries();
  addEquitySeries(data, STRATEGY_COLORS[data.strategy_id] || "#2962ff", data.strategy_name, true);
  chart.timeScale().fitContent();
  legendEl.innerHTML = `<span class="leg fast">${data.strategy_name}</span>`;

  const pf =
    data.profit_factor != null ? data.profit_factor.toFixed(2) : "n/a";
  const avgTrade =
    data.avg_trade_pnl != null ? formatPrice(data.avg_trade_pnl, ccy) : "n/a";
  const exposure =
    data.exposure_pct != null ? `${data.exposure_pct.toFixed(1)}%` : "n/a";

  renderDl(document.getElementById("metrics"), [
    ["Strategy", data.strategy_name],
    ["Symbol", data.data_symbol],
    ["Market", data.market === "jp" ? "Japan (TSE)" : "United States"],
    ["Period", `${data.start} → ${data.end}`],
    ["Initial", formatPrice(data.initial_cash, ccy)],
    ["Final equity", formatPrice(data.final_equity, ccy)],
    ["Strategy return", formatPct(data.total_return_pct)],
    ["Buy & hold", formatPct(data.buy_hold_return_pct)],
    ["Max drawdown", `${data.max_drawdown_pct.toFixed(2)}%`],
    ["Trades", String(data.num_trades)],
    ["Win rate", data.win_rate_pct != null ? `${data.win_rate_pct.toFixed(1)}%` : "n/a"],
    ["Profit factor", pf],
    ["Avg trade", avgTrade],
    ["Exposure", exposure],
    ["Sharpe (ann.)", data.sharpe_ratio != null ? data.sharpe_ratio.toFixed(2) : "n/a"],
  ]);

  renderConversion(data);

  const tradesEl = document.getElementById("trades");
  tradesEl.innerHTML = (data.trades || [])
    .slice()
    .reverse()
    .map(
      (t) =>
        `<li class="${t.side}">${t.time} ${t.side.toUpperCase()} ${t.qty} @ ${formatPrice(t.price, ccy)} · cash ${formatPrice(t.cash_after, ccy)}</li>`
    )
    .join("");

  statusEl.textContent = `${data.strategy_name} · ${data.data_symbol} · ${data.num_trades} trades`;
}

function renderCompareResults(payload) {
  showCompareMode();
  const ccy = payload.display_currency || "usd";
  setChartCurrency(ccy);
  clearChartSeries();

  const rows = payload.results || [];
  rows.sort((a, b) => b.total_return_pct - a.total_return_pct);

  legendEl.innerHTML = rows
    .map((r) => {
      const color = STRATEGY_COLORS[r.strategy_id] || "#888";
      return `<span class="leg" style="--leg-color:${color}">${r.strategy_name}</span>`;
    })
    .join("");

  rows.forEach((r, i) => {
    const color = STRATEGY_COLORS[r.strategy_id] || "#888";
    addEquitySeries(r, color, r.strategy_name, i === 0);
  });
  chart.timeScale().fitContent();

  const tbody = document.querySelector("#compare-table tbody");
  tbody.innerHTML = rows
    .map((r) => {
      const pf = r.profit_factor != null ? r.profit_factor.toFixed(2) : "—";
      const win = r.win_rate_pct != null ? `${r.win_rate_pct.toFixed(0)}%` : "—";
      const sharpe = r.sharpe_ratio != null ? r.sharpe_ratio.toFixed(2) : "—";
      return `<tr>
        <td>${r.strategy_name}</td>
        <td class="${r.total_return_pct >= 0 ? "pos" : "neg"}">${formatPct(r.total_return_pct)}</td>
        <td>${r.max_drawdown_pct.toFixed(1)}%</td>
        <td>${win}</td>
        <td>${r.num_trades}</td>
        <td>${sharpe}</td>
        <td>${pf}</td>
      </tr>`;
    })
    .join("");

  const errEl = document.getElementById("compare-errors");
  const errs = payload.errors || [];
  errEl.innerHTML = errs
    .map((e) => `<li>${e.strategy_name}: ${e.error}</li>`)
    .join("");

  renderConversion(rows[0] || {});

  const bh = payload.buy_hold_return_pct;
  statusEl.textContent = `Compared ${rows.length} strategies · ${payload.data_symbol} · B&H ${formatPct(bh)}`;
}

async function fetchBacktest(compare) {
  const symbol = symbolInput.value.trim().toUpperCase();
  if (!symbol) {
    statusEl.textContent = "Enter a symbol.";
    return null;
  }

  const params = queryParams();
  params.set("symbol", symbol);
  params.set("start", startInput.value);
  params.set("end", endInput.value);
  if (initialCashInput.value) params.set("initial_cash", initialCashInput.value);
  if (compare) {
    params.set("compare", "true");
  } else {
    params.set("strategy", strategySelect.value || "sma_crossover");
  }

  const res = await fetch(`/api/backtest?${params}`);
  const body = await res.json().catch(() => ({}));
  if (!res.ok) {
    statusEl.textContent = body.detail || res.statusText;
    return null;
  }
  return body;
}

async function runBacktest() {
  statusEl.textContent = "Running backtest…";
  runBtn.disabled = true;
  compareBtn.disabled = true;
  try {
    const body = await fetchBacktest(false);
    if (body) renderSingleResults(body);
  } catch (err) {
    statusEl.textContent = String(err);
  } finally {
    runBtn.disabled = false;
    compareBtn.disabled = false;
  }
}

async function runCompareAll() {
  statusEl.textContent = "Comparing strategies…";
  runBtn.disabled = true;
  compareBtn.disabled = true;
  try {
    const body = await fetchBacktest(true);
    if (body) renderCompareResults(body);
  } catch (err) {
    statusEl.textContent = String(err);
  } finally {
    runBtn.disabled = false;
    compareBtn.disabled = false;
  }
}

marketSelect.addEventListener("change", () => {
  fillStockPicker(marketSelect.value);
  applyInitialCashForMarket(marketSelect.value);
});
stockPick.addEventListener("change", () => {
  symbolInput.value = stockPick.value;
  if (stockPick.value.toUpperCase().endsWith(".T")) marketSelect.value = "jp";
});
currencySelect.addEventListener("change", () => {
  localStorage.setItem("sat_currency", currencySelect.value);
});
strategySelect.addEventListener("change", updateStrategyDescription);
runBtn.addEventListener("click", runBacktest);
compareBtn.addEventListener("click", runCompareAll);

async function runScanPresets() {
  const symbols = [...japanStocks, ...usStocks].map((s) => s.symbol).join(",");
  if (!symbols) {
    statusEl.textContent = "No preset symbols loaded.";
    return;
  }
  statusEl.textContent = "Scanning preset symbols (may take a minute)…";
  runBtn.disabled = true;
  compareBtn.disabled = true;
  scanPresetsBtn.disabled = true;
  const params = new URLSearchParams();
  params.set("symbols", symbols);
  params.set("start", startInput.value);
  params.set("end", endInput.value);
  if (initialCashInput.value) params.set("initial_cash", initialCashInput.value);
  try {
    const res = await fetch(`/api/backtest/scan?${params}`);
    const body = await res.json().catch(() => ({}));
    if (!res.ok) {
      statusEl.textContent = body.detail || res.statusText;
      return;
    }
    renderScanResults(body);
  } catch (err) {
    statusEl.textContent = String(err);
  } finally {
    runBtn.disabled = false;
    compareBtn.disabled = false;
    scanPresetsBtn.disabled = false;
  }
}

function renderScanResults(payload) {
  showCompareMode();
  singleResultsEl?.classList.add("hidden");
  compareResultsEl?.classList.remove("hidden");
  tradesSectionEl?.classList.add("hidden");
  clearChartSeries();
  legendEl.innerHTML = "<span class=\"leg\">Scan mode — see table</span>";

  const tbody = document.querySelector("#compare-table tbody");
  const rows = payload.rows || [];
  tbody.innerHTML = rows
    .filter((r) => !r.error)
    .map((r) => {
      const star = r.is_best_for_symbol ? " ★" : "";
      const ret = r.total_return_pct != null ? formatPct(r.total_return_pct) : "—";
      const win = r.win_rate_pct != null ? `${r.win_rate_pct.toFixed(0)}%` : "—";
      return `<tr>
        <td>${r.data_symbol}${star}</td>
        <td>${r.strategy_name}</td>
        <td class="${(r.total_return_pct || 0) >= 0 ? "pos" : "neg"}">${ret}</td>
        <td>${r.max_drawdown_pct != null ? r.max_drawdown_pct.toFixed(1) + "%" : "—"}</td>
        <td>${win}</td>
        <td>${r.num_trades ?? "—"}</td>
        <td>${r.sharpe_ratio != null ? r.sharpe_ratio.toFixed(2) : "—"}</td>
        <td>${r.profit_factor != null ? r.profit_factor.toFixed(2) : "—"}</td>
      </tr>`;
    })
    .join("");

  document.querySelector("#compare-table thead tr").innerHTML = `
    <th>Symbol</th><th>Strategy</th><th>Return</th><th>Max DD</th><th>Win%</th>
    <th>Trades</th><th>Sharpe</th><th>P.F.</th>`;

  const errEl = document.getElementById("compare-errors");
  errEl.innerHTML = rows
    .filter((r) => r.error)
    .map((r) => `<li>${r.symbol}: ${r.error}</li>`)
    .join("");

  statusEl.textContent = `Scan complete · ${rows.filter((r) => !r.error).length} rows · ★ = best per symbol`;
}

if (scanPresetsBtn) scanPresetsBtn.addEventListener("click", runScanPresets);

defaultDates();
initChart();
loadConfig();
