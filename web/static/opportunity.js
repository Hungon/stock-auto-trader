const marketSelect = document.getElementById("market");
const customSymbolsInput = document.getElementById("custom-symbols");
const scanBtn = document.getElementById("scan");
const statusEl = document.getElementById("status");
const summaryCardsEl = document.getElementById("summary-cards");
const filterBarEl = document.getElementById("filter-bar");
const tableEl = document.getElementById("opp-table");
const tableBody = tableEl.querySelector("tbody");
const scanErrorsEl = document.getElementById("scan-errors");
const detailEmptyEl = document.getElementById("detail-empty");
const detailPanelEl = document.getElementById("detail-panel");

const TYPE_CLASS = {
  "Momentum Breakout": "type-breakout",
  "New High Candidate": "type-newhigh",
  "Trend Continuation": "type-trend",
  "MA Crossover Candidate": "type-cross",
  "Pullback Setup": "type-pullback",
  "High Volume Alert": "type-volume",
  "RSI Reversal Candidate": "type-reversal",
  "Momentum Watch": "type-momentum",
  "Oversold Rebound Watch": "type-oversold",
  "Neutral / Mixed": "type-neutral",
  "Weakness / Short-Watch": "type-weak",
  "Bearish Breakdown": "type-bearish",
};

const TYPE_LABEL = {
  "Momentum Breakout": "Breakout",
  "New High Candidate": "New High",
  "Trend Continuation": "Trend",
  "MA Crossover Candidate": "MA Cross",
  "Pullback Setup": "Pullback",
  "High Volume Alert": "High Vol",
  "RSI Reversal Candidate": "RSI Rev",
  "Momentum Watch": "Momentum",
  "Oversold Rebound Watch": "Oversold",
  "Neutral / Mixed": "Neutral",
  "Weakness / Short-Watch": "Weak",
  "Bearish Breakdown": "Bearish",
};

let allSignals = [];
let setupTypes = [];
let activeFilter = "all";
let currentMarket = "jp";
let selectedSymbol = null;
let sortKey = "rank";
let sortDir = "asc";

function fmtNum(value, digits = 2) {
  if (value == null || Number.isNaN(value)) return "—";
  return Number(value).toLocaleString(undefined, {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  });
}

function fmtPrice(value) {
  if (value == null) return "—";
  return currentMarket === "jp"
    ? `¥${Number(value).toLocaleString(undefined, { maximumFractionDigits: 0 })}`
    : `$${fmtNum(value, 2)}`;
}

function fmtPct(value) {
  if (value == null || Number.isNaN(value)) return "—";
  return `${value >= 0 ? "+" : ""}${Number(value).toFixed(2)}%`;
}

function scoreClass(score) {
  if (score >= 65) return "score-strong";
  if (score >= 50) return "score-good";
  if (score >= 35) return "score-weak";
  return "score-bad";
}

function renderSummary(summary) {
  if (!summary || !summary.count) {
    summaryCardsEl.innerHTML = "";
    return;
  }
  const top = summary.top_opportunity;
  const cards = [
    { label: "Market Bias", value: summary.market_bias, sub: `avg momentum ${fmtNum(summary.avg_momentum, 0)}` },
    { label: "Breakouts", value: String(summary.breakout_count), sub: "momentum setups" },
    { label: "High Volume", value: String(summary.high_volume_count), sub: "2x+ avg volume" },
    { label: "Bearish", value: String(summary.bearish_count), sub: "breakdown watch" },
    {
      label: "Top Opportunity",
      value: top ? top.symbol : "—",
      sub: top ? `${top.opportunity_type} · ${top.opportunity_score}` : "",
    },
  ];
  summaryCardsEl.innerHTML = cards
    .map(
      (c) => `<div class="summary-card">
        <div class="summary-label">${c.label}</div>
        <div class="summary-value">${c.value}</div>
        <div class="summary-sub">${c.sub}</div>
      </div>`
    )
    .join("");
}

function typesInResults() {
  // Preserve the server's canonical order, keeping only types actually present.
  const present = new Set(allSignals.map((s) => s.opportunity_type));
  const ordered = (setupTypes.length ? setupTypes : [...present]).filter((t) =>
    present.has(t)
  );
  return ordered;
}

function renderFilters() {
  const chips = [{ id: "all", label: "All", count: allSignals.length }];
  typesInResults().forEach((t) => {
    chips.push({
      id: t,
      label: TYPE_LABEL[t] || t,
      count: allSignals.filter((s) => s.opportunity_type === t).length,
    });
  });
  filterBarEl.innerHTML = chips
    .map((c) => {
      const active = c.id === activeFilter ? " active" : "";
      return `<button type="button" class="filter-chip${active}" data-filter="${c.id}">${c.label} <span class="chip-count">${c.count}</span></button>`;
    })
    .join("");
  filterBarEl.querySelectorAll(".filter-chip").forEach((btn) => {
    btn.addEventListener("click", () => {
      activeFilter = btn.dataset.filter;
      renderFilters();
      renderTable();
    });
  });
}

function visibleSignals() {
  let rows =
    activeFilter === "all"
      ? allSignals.slice()
      : allSignals.filter((s) => s.opportunity_type === activeFilter);

  const dir = sortDir === "asc" ? 1 : -1;
  const numeric = sortKey !== "symbol" && sortKey !== "name" && sortKey !== "opportunity_type";
  rows.sort((a, b) => {
    let av = a[sortKey];
    let bv = b[sortKey];
    if (numeric) {
      // Null/undefined numeric values always sort to the bottom.
      const an = av == null || Number.isNaN(av);
      const bn = bv == null || Number.isNaN(bv);
      if (an && bn) return 0;
      if (an) return 1;
      if (bn) return -1;
      return (av - bv) * dir;
    }
    av = (av || "").toString().toLowerCase();
    bv = (bv || "").toString().toLowerCase();
    return av < bv ? -dir : av > bv ? dir : 0;
  });
  return rows;
}

function renderSortIndicators() {
  tableEl.querySelectorAll("th.sortable").forEach((th) => {
    th.classList.remove("sort-asc", "sort-desc");
    if (th.dataset.sort === sortKey) {
      th.classList.add(sortDir === "asc" ? "sort-asc" : "sort-desc");
    }
  });
}

function renderTable() {
  renderSortIndicators();
  const rows = visibleSignals();
  if (!rows.length) {
    tableBody.innerHTML = `<tr><td colspan="9" class="empty-row">No matching opportunities.</td></tr>`;
    return;
  }
  tableBody.innerHTML = rows
    .map((s) => {
      const typeClass = TYPE_CLASS[s.opportunity_type] || "type-neutral";
      const sel = s.symbol === selectedSymbol ? " selected" : "";
      const chg = s.price_change_pct >= 0 ? "pos" : "neg";
      return `<tr class="opp-row${sel}" data-symbol="${s.symbol}">
        <td>${s.rank}</td>
        <td class="mono">${s.symbol}</td>
        <td class="name-cell">${s.name}</td>
        <td>${fmtPrice(s.price)}</td>
        <td class="${chg}">${fmtPct(s.price_change_pct)}</td>
        <td>${s.volume_ratio != null ? fmtNum(s.volume_ratio, 2) : "—"}</td>
        <td>${s.rsi != null ? fmtNum(s.rsi, 0) : "—"}</td>
        <td><span class="type-badge ${typeClass}">${s.opportunity_type}</span></td>
        <td><span class="score-pill ${scoreClass(s.opportunity_score)}">${s.opportunity_score}</span></td>
      </tr>`;
    })
    .join("");
  tableBody.querySelectorAll(".opp-row").forEach((tr) => {
    tr.addEventListener("click", () => selectSymbol(tr.dataset.symbol));
  });
}

function selectSymbol(symbol) {
  selectedSymbol = symbol;
  renderTable();
  const sig = allSignals.find((s) => s.symbol === symbol);
  if (sig) renderDetail(sig);
}

function fitBadge(fit) {
  const cls =
    fit === "strong" ? "fit-strong" : fit === "possible" ? "fit-possible" : "fit-weak";
  return `<span class="fit-badge ${cls}">${fit}</span>`;
}

function renderDetail(sig) {
  detailEmptyEl.classList.add("hidden");
  detailPanelEl.classList.remove("hidden");

  document.getElementById("detail-title").textContent = `${sig.symbol} · ${sig.name}`;
  const typeClass = TYPE_CLASS[sig.opportunity_type] || "type-neutral";
  document.getElementById("detail-score").innerHTML = `
    <span class="score-pill big ${scoreClass(sig.opportunity_score)}">${sig.opportunity_score}</span>
    <span class="type-badge ${typeClass}">${sig.opportunity_type}</span>
    <span class="confidence">confidence: ${sig.confidence}</span>`;

  renderDl(document.getElementById("detail-signals"), [
    ["Price", fmtPrice(sig.price)],
    ["Change", fmtPct(sig.price_change_pct)],
    ["Volume ratio", sig.volume_ratio != null ? `${fmtNum(sig.volume_ratio, 2)}×` : "—"],
    ["RSI", sig.rsi != null ? fmtNum(sig.rsi, 1) : "—"],
    ["SMA20", sig.sma20 != null ? fmtPrice(sig.sma20) : "—"],
    ["SMA50", sig.sma50 != null ? fmtPrice(sig.sma50) : "—"],
    ["From 20d high", sig.dist_from_high20_pct != null ? fmtPct(sig.dist_from_high20_pct) : "—"],
  ]);

  renderDl(document.getElementById("detail-breakdown"), [
    ["Momentum", `${sig.momentum_score}`],
    ["Volume", `${sig.volume_score}`],
    ["Technical", `${sig.technical_score}`],
    ["Setup", `${sig.setup_score}`],
  ]);

  document.getElementById("detail-why").innerHTML = (sig.explanation || [])
    .map((t) => `<li>${t}</li>`)
    .join("");
  document.getElementById("detail-watch").innerHTML = (sig.watch_next || [])
    .map((t) => `<li>${t}</li>`)
    .join("");
  document.getElementById("detail-fit").innerHTML = (sig.strategy_fit || [])
    .map((f) => `<li>${f.name} ${fitBadge(f.fit)}</li>`)
    .join("");

  const params = `market=${sig.market}&symbol=${encodeURIComponent(sig.symbol)}`;
  document.getElementById("open-chart").href = `/?${params}`;
  document.getElementById("run-backtest").href = `/backtest?${params}`;
}

function renderDl(el, rows) {
  el.innerHTML = rows.map(([k, v]) => `<dt>${k}</dt><dd>${v}</dd>`).join("");
}

function setupSortHandlers() {
  tableEl.querySelectorAll("th.sortable").forEach((th) => {
    th.addEventListener("click", () => {
      const key = th.dataset.sort;
      if (sortKey === key) {
        sortDir = sortDir === "asc" ? "desc" : "asc";
      } else {
        sortKey = key;
        // Numeric columns default to descending (best first); text to ascending.
        sortDir = th.dataset.type === "num" && key !== "rank" ? "desc" : "asc";
      }
      renderTable();
    });
  });
}

async function runScan() {
  currentMarket = marketSelect.value || "jp";
  const custom = (customSymbolsInput.value || "").trim();
  statusEl.textContent = "Scanning (fetching bars per symbol)…";
  scanBtn.disabled = true;
  try {
    const params = new URLSearchParams({ market: currentMarket });
    if (custom) params.set("symbols", custom);
    const res = await fetch(`/api/opportunities?${params}`);
    const body = await res.json().catch(() => ({}));
    if (!res.ok) {
      statusEl.textContent = body.detail || res.statusText;
      return;
    }
    allSignals = body.signals || [];
    setupTypes = body.setup_types || [];
    selectedSymbol = null;
    activeFilter = "all";
    sortKey = "rank";
    sortDir = "asc";
    detailEmptyEl.classList.remove("hidden");
    detailPanelEl.classList.add("hidden");
    renderSummary(body.summary);
    renderFilters();
    renderTable();
    scanErrorsEl.innerHTML = (body.errors || [])
      .map((e) => `<li>${e.symbol}: ${e.error}</li>`)
      .join("");
    const errNote = body.errors && body.errors.length ? ` · ${body.errors.length} skipped` : "";
    statusEl.textContent = `Scanned ${allSignals.length} symbols · ${body.start} → ${body.end}${errNote}`;
    if (allSignals.length) selectSymbol(allSignals[0].symbol);
  } catch (err) {
    statusEl.textContent = String(err);
  } finally {
    scanBtn.disabled = false;
  }
}

scanBtn.addEventListener("click", runScan);
marketSelect.addEventListener("change", runScan);
customSymbolsInput.addEventListener("keydown", (e) => {
  if (e.key === "Enter") runScan();
});

setupSortHandlers();
runScan();
