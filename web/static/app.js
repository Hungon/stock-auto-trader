const chartEl = document.getElementById("chart");
const statusEl = document.getElementById("status");
const ohlcEl = document.getElementById("ohlc");
const currencySelect = document.getElementById("currency");
const marketSelect = document.getElementById("market");
const stockPick = document.getElementById("stock-pick");
const symbolInput = document.getElementById("symbol");
const startInput = document.getElementById("start");
const endInput = document.getElementById("end");
const loadBtn = document.getElementById("load");
const liveToggle = document.getElementById("live-toggle");
const liveDot = document.getElementById("live-dot");

let chart;
let candleSeries;
let volumeSeries;
let fastSeries;
let slowSeries;
let refreshSeconds = 15;
let chartTimer = null;
let tickTimer = null;
let lastChartData = null;
let fitOnNextLoad = true;
let japanStocks = [];
let usStocks = [];

function selectedCurrencyRaw() {
  return currencySelect?.value || "auto";
}

/** Resolved currency sent to API (never omit). */
function effectiveCurrency() {
  const raw = selectedCurrencyRaw();
  if (raw === "usd" || raw === "jpy") return raw;
  return marketSelect?.value === "jp" ? "jpy" : "usd";
}

function chartQueryParams() {
  const params = new URLSearchParams();
  params.set("market", marketSelect?.value || "jp");
  params.set("currency", effectiveCurrency());
  return params;
}

function formatPrice(value, currency) {
  const n = Number(value);
  if (currency === "jpy") return `¥${n.toLocaleString(undefined, { maximumFractionDigits: 0 })}`;
  return `$${n.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

function formatOhlc(bar, symbol, currency) {
  return `${symbol}  O ${formatPrice(bar.open, currency)}  H ${formatPrice(bar.high, currency)}  L ${formatPrice(bar.low, currency)}  C ${formatPrice(bar.close, currency)}`;
}

function defaultDates() {
  const end = new Date();
  const start = new Date();
  start.setFullYear(end.getFullYear() - 2);
  endInput.value = end.toISOString().slice(0, 10);
  startInput.value = start.toISOString().slice(0, 10);
}

function initChart() {
  if (typeof LightweightCharts === "undefined") {
    statusEl.textContent = "Chart library failed to load. Check your internet connection.";
    return;
  }
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
    crosshair: { mode: LightweightCharts.CrosshairMode.Normal },
    rightPriceScale: { borderColor: "#2a2e39" },
    timeScale: { borderColor: "#2a2e39", timeVisible: true },
  });

  candleSeries = chart.addCandlestickSeries({
    upColor: "#26a69a",
    downColor: "#ef5350",
    borderVisible: false,
    wickUpColor: "#26a69a",
    wickDownColor: "#ef5350",
  });

  volumeSeries = chart.addHistogramSeries({
    color: "#26a69a",
    priceFormat: { type: "volume" },
    priceScaleId: "",
  });
  volumeSeries.priceScale().applyOptions({
    scaleMargins: { top: 0.85, bottom: 0 },
  });

  fastSeries = chart.addLineSeries({
    color: "#2196f3",
    lineWidth: 2,
    title: "SMA fast",
  });
  slowSeries = chart.addLineSeries({
    color: "#ff9800",
    lineWidth: 2,
    title: "SMA slow",
  });

  chart.subscribeCrosshairMove((param) => {
    if (!param.time || !param.seriesData.size) return;
    const bar = param.seriesData.get(candleSeries);
    if (!bar) return;
    const ccy = lastChartData?.display_currency || "usd";
    ohlcEl.textContent = formatOhlc(bar, lastChartData?.symbol || "", ccy);
  });

  const ro = new ResizeObserver(() => {
    chart.applyOptions({
      width: chartEl.clientWidth,
      height: chartEl.clientHeight,
    });
  });
  ro.observe(chartEl);
}

function renderDl(el, rows) {
  el.innerHTML = rows.map(([k, v]) => `<dt>${k}</dt><dd>${v}</dd>`).join("");
}

function formatFetchedAt(iso) {
  if (!iso) return "";
  const d = new Date(iso);
  return d.toLocaleTimeString();
}

function setLiveIndicator(on) {
  liveDot.classList.toggle("on", on);
}

function stopTimers() {
  if (chartTimer) clearInterval(chartTimer);
  if (tickTimer) clearInterval(tickTimer);
  chartTimer = null;
  tickTimer = null;
  setLiveIndicator(false);
}

function startTimers() {
  stopTimers();
  if (!liveToggle.checked) return;
  setLiveIndicator(true);
  chartTimer = setInterval(() => loadChart({ silent: true }), refreshSeconds * 1000);
  tickTimer = setInterval(fetchTick, Math.max(5, Math.floor(refreshSeconds / 2)) * 1000);
}

function fillStockPicker(market) {
  const list = market === "us" ? usStocks : japanStocks;
  stockPick.innerHTML = list
    .map(
      (s) =>
        `<option value="${s.symbol}">${s.symbol} — ${s.name}</option>`
    )
    .join("");
  if (list.length) {
    symbolInput.value = list[0].symbol;
  }
}

async function loadConfig() {
  try {
    const res = await fetch("/api/config");
    if (!res.ok) return;
    const cfg = await res.json();
    refreshSeconds = cfg.chart_refresh_seconds || 15;
    liveToggle.title = `Refresh chart every ${refreshSeconds}s`;
    japanStocks = cfg.japan_stocks || [];
    usStocks = cfg.us_stocks || [];
    if (cfg.market) marketSelect.value = cfg.market;
    fillStockPicker(marketSelect.value);
    if (cfg.symbol) symbolInput.value = cfg.symbol;
    const saved = localStorage.getItem("sat_currency");
    if (saved) currencySelect.value = saved;
    else if (cfg.display_currency && cfg.display_currency !== "auto") {
      currencySelect.value = cfg.display_currency;
    }
  } catch (_) {
    /* ignore */
  }
}

marketSelect.addEventListener("change", () => {
  fillStockPicker(marketSelect.value);
  fitOnNextLoad = true;
  loadChart();
  loadAccount();
});

stockPick.addEventListener("change", () => {
  symbolInput.value = stockPick.value;
  if (stockPick.value.toUpperCase().endsWith(".T")) {
    marketSelect.value = "jp";
  }
  fitOnNextLoad = true;
  loadChart();
  loadAccount();
});

currencySelect.addEventListener("change", () => {
  localStorage.setItem("sat_currency", currencySelect.value);
  fitOnNextLoad = true;
  loadChart();
  loadAccount();
});

async function loadAccount() {
  try {
    const q = chartQueryParams();
    const res = await fetch(`/api/account?${q}`);
    if (!res.ok) return;
    const data = await res.json();
    const mode = data.demo_mode ? "demo (add .env for live)" : data.trading_mode;
    const ccy = data.display_currency || "usd";
    const fx = data.fx_usdjpy ? ` (USD/JPY ${data.fx_usdjpy.toFixed(2)})` : "";
    renderDl(document.getElementById("account"), [
      ["Currency", ccy.toUpperCase() + fx],
      ["Mode", mode],
      ["Symbol", data.symbol],
      ["Market", data.market_open ? "Open" : "Closed"],
      ["Position", String(data.position_qty)],
      ["Equity", formatPrice(data.equity, ccy)],
      ["Cash", formatPrice(data.cash, ccy)],
    ]);
  } catch (_) {
    /* optional */
  }
}

function applyChartData(data, { silent = false } = {}) {
  if (!chart || !candleSeries) return;
  lastChartData = data;
  symbolInput.value = data.symbol;

  if (!data.candles?.length) {
    statusEl.textContent = "No candle data for this symbol/range.";
    return;
  }

  candleSeries.setData(data.candles);
  volumeSeries.setData(data.volume);
  fastSeries.setData(data.fast_sma);
  slowSeries.setData(data.slow_sma);
  candleSeries.setMarkers(data.markers);

  document.getElementById("legend").querySelector(".leg.fast").textContent =
    `SMA ${data.fast_period}`;
  document.getElementById("legend").querySelector(".leg.slow").textContent =
    `SMA ${data.slow_period}`;

  const ccy = data.display_currency || effectiveCurrency();
  const native = data.native_currency || ccy;
  chart.applyOptions({
    localization: {
      priceFormatter: (price) =>
        ccy === "jpy"
          ? `¥${Math.round(price).toLocaleString()}`
          : `$${price.toFixed(2)}`,
    },
  });
  if (data.last) {
    ohlcEl.textContent = formatOhlc(data.last, data.symbol, ccy);
  }
  if (data.native_currency && data.display_currency && data.native_currency !== data.display_currency) {
    ohlcEl.textContent += ` · native ${data.native_currency.toUpperCase()}`;
  }

  const convEl = document.getElementById("conversion");
  if (data.conversion) {
    const c = data.conversion;
    const rows = [
      ["You entered", data.input_symbol || data.symbol],
      ["Data symbol", data.data_symbol || data.symbol],
      ["Native", c.native_currency?.toUpperCase()],
      ["Display", c.display_currency?.toUpperCase()],
      ["USD/JPY", c.fx_usdjpy ? c.fx_usdjpy.toFixed(2) : "—"],
      ["Formula", c.formula],
    ];
    if (c.native_close != null) {
      rows.push([
        "Native close",
        formatPrice(c.native_close, c.native_currency),
      ]);
    }
    if (c.display_close != null) {
      rows.push([
        "Display close",
        formatPrice(c.display_close, c.display_currency),
      ]);
    }
    if (c.example) rows.push(["Example", c.example]);
    if (data.symbol_alias_note) rows.push(["Alias", data.symbol_alias_note]);
    renderDl(convEl, rows);
  } else {
    convEl.innerHTML = "";
  }

  const statsEl = document.getElementById("stats");
  if (data.stats) {
    renderDl(statsEl, [
      ["Return", `${data.stats.total_return_pct}%`],
      ["Buy & hold", `${data.stats.buy_hold_return_pct}%`],
      ["Max DD", `${data.stats.max_drawdown_pct}%`],
      ["Trades", String(data.stats.num_trades)],
    ]);
  } else {
    statsEl.innerHTML = "<dd>Not enough bars</dd>";
  }

  const tradesEl = document.getElementById("trades");
  tradesEl.innerHTML = (data.trades || [])
    .slice()
    .reverse()
    .map(
      (t) =>
        `<li class="${t.side}">${t.time} ${t.side.toUpperCase()} ${t.qty} @ ${formatPrice(t.price, ccy)}</li>`
    )
    .join("");

  if (fitOnNextLoad) {
    chart.timeScale().fitContent();
    fitOnNextLoad = false;
  }

  const demo = data.demo_mode ? " · DEMO" : "";
  const live = liveToggle.checked ? " · LIVE" : "";
  const mkt = data.market === "jp" ? " · Japan" : "";
  const note = data.trading_note ? ` · ${data.trading_note}` : "";
  const at = formatFetchedAt(data.fetched_at);
  const fx =
    data.currency_converted && data.fx_usdjpy
      ? ` · FX ${data.fx_usdjpy.toFixed(2)}`
      : "";
  const ccyLabel =
    native !== ccy
      ? `${ccy.toUpperCase()} (from ${native.toUpperCase()})`
      : ccy.toUpperCase();
  const warn = data.currency_warning ? ` · ${data.currency_warning}` : "";
  statusEl.textContent = `${data.symbol} · ${ccyLabel} · ${data.bar_timeframe} · ${data.candles.length} bars${mkt}${demo}${live}${fx} · updated ${at}${warn}${note}`;
}

async function loadChart({ silent = false } = {}) {
  const symbol = symbolInput.value.trim().toUpperCase() || "SPY";
  const start = startInput.value;
  const end = endInput.value;
  if (!silent) {
    statusEl.textContent = "Loading…";
    fitOnNextLoad = true;
  }

  const params = chartQueryParams();
  params.set("symbol", symbol);
  params.set("start", start);
  params.set("end", end);
  const res = await fetch(`/api/chart?${params}`);
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    statusEl.textContent = err.detail || res.statusText;
    return;
  }

  const data = await res.json();
  applyChartData(data, { silent });
}

async function fetchTick() {
  if (!candleSeries || !volumeSeries) return;
  const symbol = symbolInput.value.trim().toUpperCase() || "SPY";
  try {
    const params = chartQueryParams();
    params.set("symbol", symbol);
    const res = await fetch(`/api/tick?${params}`);
    if (!res.ok) return;
    const tick = await res.json();
    const b = tick.bar;
    const up = b.close >= b.open;
    candleSeries.update(b);
    volumeSeries.update({
      time: b.time,
      value: b.volume,
      color: up ? "rgba(38,166,154,0.5)" : "rgba(239,83,80,0.5)",
    });
    const quote = tick.quote;
    const ccy = tick.display_currency || "usd";
    ohlcEl.textContent = `${tick.symbol}  bid ${formatPrice(quote.bid, ccy)}  ask ${formatPrice(quote.ask, ccy)}  C ${formatPrice(b.close, ccy)}`;
    const demo = tick.demo_mode ? " · DEMO" : "";
    const at = formatFetchedAt(tick.fetched_at);
    statusEl.textContent = `${tick.symbol} · tick ${at}${demo} · LIVE`;
  } catch (_) {
    /* ignore transient errors */
  }
}

loadBtn.addEventListener("click", () => {
  fitOnNextLoad = true;
  loadChart();
  loadAccount();
  startTimers();
});

liveToggle.addEventListener("change", () => {
  if (liveToggle.checked) startTimers();
  else stopTimers();
});

function boot() {
  defaultDates();
  initChart();
  loadConfig()
    .then(async () => {
      await loadChart();
      await loadAccount();
      startTimers();
    })
    .catch((err) => {
      statusEl.textContent = `Startup error: ${err.message}`;
      console.error(err);
    });
}

if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", boot);
} else {
  boot();
}
