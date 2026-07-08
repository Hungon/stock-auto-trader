// AI Opportunity Perspective — requests a natural-language explanation of the
// selected stock's computed signals. The engine scores; this only explains.
(function () {
  const btn = document.getElementById("ai-perspective");
  const out = document.getElementById("ai-perspective-output");
  if (!btn || !out) return;

  function list(items) {
    return (items || []).map((t) => `<li>${t}</li>`).join("");
  }

  function render(p) {
    out.classList.remove("hidden");
    const srcClass = p.source === "ai" ? "src-ai" : "src-template";
    const srcLabel = p.source === "ai" ? "AI" : "Template";
    out.innerHTML = `
      <div class="ai-head">
        <span class="source-chip ${srcClass}">${srcLabel}</span>
        <span class="ai-alignment">signals: ${p.signal_alignment}</span>
      </div>
      <p class="ai-summary">${p.summary}</p>
      <h3 class="detail-sub">Key drivers</h3>
      <ul class="detail-list">${list(p.key_drivers)}</ul>
      <h3 class="detail-sub">Risk factors</h3>
      <ul class="detail-list">${list(p.risk_factors)}</ul>
      <h3 class="detail-sub">Watch next</h3>
      <ul class="detail-list">${list(p.watch_next)}</ul>
      <p class="ai-disclaimer">${p.disclaimer || ""}</p>`;
  }

  btn.addEventListener("click", async () => {
    const sel = window.currentOpportunity;
    if (!sel || !sel.symbol) {
      out.classList.remove("hidden");
      out.textContent = "Select a stock first.";
      return;
    }
    const cacheKey = `ai_${sel.market}_${sel.symbol}`;
    const cached = sessionStorage.getItem(cacheKey);
    if (cached) {
      render(JSON.parse(cached));
      return;
    }
    btn.disabled = true;
    out.classList.remove("hidden");
    out.textContent = "Generating perspective…";
    try {
      const res = await fetch("/api/ai/opportunity-perspective", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          market: sel.market,
          symbol: sel.symbol,
          company_name: sel.name,
        }),
      });
      const body = await res.json().catch(() => ({}));
      if (!res.ok) {
        out.textContent = body.detail || res.statusText;
        return;
      }
      sessionStorage.setItem(cacheKey, JSON.stringify(body));
      render(body);
    } catch (err) {
      out.textContent = String(err);
    } finally {
      btn.disabled = false;
    }
  });
})();
