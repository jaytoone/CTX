// CTX Dashboard client — connects to /stream SSE and renders snapshots.
// All telemetry-sourced strings are escaped before insertion to prevent XSS
// (defense in depth — the telemetry source is trusted local hooks, but
// hooks may log user prompts in future extensions).
const $ = (id) => document.getElementById(id);

// Demo mode (2026-04-24): propagate ?demo=1 through all API fetches
// so the server-side overlay fires consistently. Also shows a badge.
const CTX_DEMO = new URLSearchParams(location.search).get("demo") === "1";
const demoQS = CTX_DEMO ? "&demo=1" : "";
const demoQSLead = CTX_DEMO ? "?demo=1" : "";
const demoQSJoin = (url) => CTX_DEMO ? (url.includes("?") ? url + "&demo=1" : url + "?demo=1") : url;
// Wrap fetch to auto-append ?demo=1 to /api/* calls when in demo mode
if (CTX_DEMO) {
  const origFetch = window.fetch;
  window.fetch = function(input, init) {
    if (typeof input === "string" && input.startsWith("/api/")) {
      input = demoQSJoin(input);
    }
    return origFetch(input, init);
  };
  // Add a subtle DEMO badge
  document.addEventListener("DOMContentLoaded", () => {
    const badge = document.createElement("div");
    badge.style.cssText = "position:fixed; top:8px; right:8px; z-index:9999; background:#ff9800; color:#fff; font-size:0.75em; font-weight:600; padding:3px 8px; border-radius:3px; letter-spacing:0.5px";
    badge.textContent = "DEMO";
    document.body.appendChild(badge);
  });
}

const ESC_MAP = {"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"};
function esc(s) {
  if (s == null) return "";
  return String(s).replace(/[&<>"']/g, c => ESC_MAP[c]);
}

// ─────────────────────────── i18n ───────────────────────────
// Single-dict design: no external library. Each key maps to {en, ko}.
// Dynamic renders call t(key) to get the current language's string.
// Static HTML uses data-i18n / data-i18n-title / data-i18n-html attrs,
// applyLanguage() scans the DOM and replaces textContent / attributes on toggle.
// Language persists in localStorage; default falls back to browser lang.

const I18N = {
  // Header + brand
  "brand.title":            { en: "CTX Telemetry", ko: "CTX 텔레메트리" },
  "footer.connected":       { en: "connected:", ko: "연결:" },
  "footer.live":            { en: "live", ko: "실시간" },
  // Panel titles + hints
  "panel.health":           { en: "System Health", ko: "시스템 상태" },
  "panel.activity":         { en: "Activity", ko: "활동" },
  "panel.activity.hint":    { en: "events / minute (last 2h)", ko: "이벤트 / 분 (최근 2시간)" },
  "panel.latency":          { en: "Latency distribution", ko: "지연시간 분포" },
  "panel.latency.hint":     { en: "bm25-memory hook", ko: "bm25-memory 후크" },
  "panel.utility":          { en: "Utility rate", ko: "활용률" },
  "panel.utility.hint":     { en: "share of injected items Claude actually referenced", ko: "주입된 항목 중 Claude가 실제로 참조한 비율" },
  "panel.utility.how":      { en: "how", ko: "방법" },
  "panel.utility.tip":      { en: "Measured on the Stop hook by matching each injected item's distinctive tokens against the assistant's response AND tool-use params. Stale events auto-excluded.", ko: "Stop 후크에서 주입된 각 항목의 고유 토큰을 assistant 응답 및 tool-use 파라미터와 매칭하여 측정. 오래된 이벤트는 자동 제외." },
  "panel.notices":          { en: "Quality notices", ko: "품질 알림" },
  "panel.notices.hint":     { en: "rate-based, informational", ko: "비율 기반, 안내용" },
  "panel.token_usage":      { en: "Token Usage", ko: "토큰 사용량" },
  "panel.token_usage.hint": { en: "CTX-injected tokens per turn", ko: "CTX가 턴당 주입한 토큰 수" },
  "panel.other":            { en: "Other signals", ko: "기타 신호" },
  "panel.graph":            { en: "Knowledge graph", ko: "지식 그래프" },
  "panel.graph.hint":       { en: "decisions · docs · prompts — coral = selected prompt, edges = retrieval + topic + temporal", ko: "결정 · 문서 · 프롬프트 — 산호색 = 선택된 프롬프트, 엣지 = 검색 + 토픽 + 시간" },
  "panel.samples":          { en: "Function proof — real samples", ko: "기능 증명 — 실제 샘플" },
  "panel.samples.hint":     { en: "recent prompts → actual hook outputs (eye-check relevance)", ko: "최근 프롬프트 → 실제 후크 출력 (관련성 직접 확인)" },
  "panel.events":           { en: "Recent events", ko: "최근 이벤트" },
  "panel.events.hint":      { en: "newest first, last 30", ko: "최신순, 최근 30개" },
  // Buttons / nav
  "btn.refresh":            { en: "refresh", ko: "새로고침" },
  "btn.loadmore":           { en: "Load 10 more", ko: "10개 더 보기" },
  "nav.prev":               { en: "Previous prompt (older)", ko: "이전 프롬프트 (더 오래된)" },
  "nav.next":               { en: "Next prompt (newer)", ko: "다음 프롬프트 (더 최근)" },
  "nav.signals":            { en: "electrical signals", ko: "전기 신호" },
  // Samples legend
  "samples.legend.head":    { en: "Per-prompt utility pill:", ko: "프롬프트별 활용률 배지:" },
  "legend.chip.ok":         { en: "CTX surfaced items Claude actually used", ko: "CTX가 꺼낸 항목 중 Claude가 실제 사용" },
  "legend.chip.mid":        { en: "partially used", ko: "일부 사용됨" },
  "legend.chip.low":        { en: "injected but not referenced — honest signal, not a bug", ko: "주입됐지만 미참조 — 정직한 신호, 버그 아님" },
  "legend.chip.pending":    { en: "reply not yet persisted (Stop hook fires ~30s after turn)", ko: "응답 미저장 — Stop 후크가 ~30초 후 실행됨" },
  "samples.legend.body":    {
    en: "= how much of what CTX <em>surfaced</em> was actually <em>used</em> in Claude's response. Blocks below show what CTX surfaced into context. A <b>filled block with 0% utility</b> = CTX injected items but Claude didn't reference them — honest signal, not a bug; usually means the prompt was about a different topic than what BM25 matched. <b>—</b> = the reply isn't persisted yet (lands on Stop hook ~30s after the turn); score fills in on next refresh. CM entries are project-scoped <em>history</em>, not this prompt's reply.",
    ko: "= CTX가 <em>꺼낸</em> 것 중 Claude 응답에서 <em>실제 사용된</em> 비율. 아래 블록은 CTX가 문맥에 주입한 것을 표시. <b>블록은 채워졌는데 활용률 0%</b> = CTX가 항목을 주입했지만 Claude가 참조하지 않음 — 버그가 아닌 정직한 신호, 보통 BM25가 매칭한 주제와 프롬프트 주제가 다를 때 발생. <b>—</b> = 응답이 아직 저장되지 않음 (Stop 후크가 턴 종료 ~30초 후 실행됨); 다음 새로고침에 점수 채워짐. CM 항목은 이 프롬프트 응답이 아닌 프로젝트 <em>히스토리</em>."
  },
  // Utility panel (dynamic)
  "util.overall":           { en: "Overall utility", ko: "전체 활용률" },
  "util.overallCI":         { en: "95% CI", ko: "95% 신뢰구간" },
  "util.nturns":            { en: "turns measured", ko: "측정된 턴" },
  "util.items":             { en: "items injected", ko: "주입된 항목" },
  "util.stale":             { en: "stale pre-fix events skipped", ko: "수정 이전 stale 이벤트 제외" },
  "util.empty":             { en: "No measurements yet. Complete a turn — CTX will log whether the assistant actually referenced injected context.", ko: "아직 측정값 없음. 턴을 완료하면 CTX가 assistant의 문맥 참조 여부를 기록함." },
  // Age-split
  "age.head":               { en: "Utility by item age", ko: "항목 연령별 활용률" },
  "age.hint":               { en: "cross-session memory signal", ko: "크로스-세션 메모리 신호" },
  "age.0-7d":               { en: "0–7 days", ko: "0–7일" },
  "age.7-30d":              { en: "7–30 days", ko: "7–30일" },
  "age.30d+":               { en: "30+ days", ko: "30일+" },
  "age.no_date":            { en: "no date", ko: "날짜 없음" },
  // Response-type split
  "rtype.head":             { en: "Utility by response type", ko: "응답 유형별 활용률" },
  "rtype.hint":             { en: "iter 2→3 discrepancy explained", ko: "iter 2→3 불일치 원인 설명" },
  "rtype.prose":            { en: "Prose responses", ko: "산문 응답" },
  "rtype.mixed":            { en: "Mixed (prose + tool_use)", ko: "혼합 (산문 + tool_use)" },
  "rtype.tool_heavy":       { en: "Tool-heavy (short prose, many tool_use)", ko: "Tool 중심 (짧은 산문, 많은 tool_use)" },
  // Text-vs-tool split (iter 3)
  "split.head":             { en: "How CTX was referenced", ko: "CTX 참조 방식" },
  "split.tooltip":          { en: "tool-aware turns", ko: "tool-인식 턴" },
  "split.text":             { en: "text", ko: "텍스트" },
  "split.both":             { en: "both", ko: "둘다" },
  "split.tool":             { en: "tool", ko: "tool" },
  "split.recovery":         { en: "Tool-use recovery:", ko: "Tool-use 복구:" },
  // A/B split
  "ab.head":                { en: "A/B split", ko: "A/B 분할" },
  "ab.hint":                { en: "CTX_AB_DISABLE env scaffold", ko: "CTX_AB_DISABLE 환경변수 스캐폴드" },
  "ab.control":             { en: "Control (CTX off)", ko: "대조군 (CTX 끔)" },
  "ab.treatment":           { en: "Treatment (CTX on)", ko: "실험군 (CTX 켬)" },
  "ab.na":                  { en: "Control arm has 0 injected items by design — utility rate is undefined; compare session counts or time-saved instead", ko: "대조군은 설계상 주입 항목이 0 — 활용률 정의 불가; 세션 수 또는 절감 시간으로 비교" },
  // Graph legend
  "legend.current":         { en: "current prompt", ko: "현재 프롬프트" },
  "legend.decision":        { en: "decision", ko: "결정" },
  "legend.doc":             { en: "doc", ko: "문서" },
  "legend.prompt":          { en: "past prompt", ko: "과거 프롬프트" },
  "legend.hot":             { en: "hot (referenced)", ko: "활성 (참조됨)" },
  "legend.dead":            { en: "cold (no recent use)", ko: "비활성 (최근 사용 없음)" },
  "legend.recall":          { en: "retrieval", ko: "검색" },
  "legend.topic":           { en: "topic (doc↔doc)", ko: "토픽 (문서↔문서)" },
  "legend.temporal":        { en: "temporal (decision↔decision)", ko: "시간 (결정↔결정)" },
  // Node-explain pane
  "explain.is_prompt":      { en: "This IS the selected prompt", ko: "이 노드는 선택된 프롬프트 자체입니다" },
  "explain.click_hint":     { en: "Click a decision/doc node to see why it was retrieved.", ko: "결정/문서 노드를 클릭하면 검색된 이유를 확인할 수 있습니다." },
  "explain.not_connected":  { en: "Not connected to selected prompt", ko: "선택된 프롬프트와 연결되지 않음" },
  "explain.no_path":        { en: "No retrieval path found from prompt → this node within 4 hops. It's in the graph but not in the cascade.", ko: "프롬프트 → 이 노드로의 4홉 이내 경로 없음. 그래프에는 있으나 캐스케이드에 포함되지 않음." },
  "explain.depth1":         { en: "depth 1 — direct retrieval", ko: "depth 1 — 직접 검색" },
  "explain.depth_n":        { en: "— via retrieval chain", ko: "— 검색 체인 경유" },
  "explain.rank":           { en: "rank:", ko: "순위:" },
  "explain.bm25":           { en: "bm25 score:", ko: "bm25 점수:" },
  "explain.matched":        { en: "matched tokens:", ko: "일치 토큰:" },
  "explain.arrival":        { en: "arrival:", ko: "도착:" },
  "explain.no_match":       { en: "no direct token match (retrieval via semantic/fuzzy)", ko: "직접 토큰 일치 없음 (의미/퍼지 검색)" },
  "explain.in_cone":        { en: "in retrieval cone", ko: "검색 콘에서" },
  "explain.direct":         { en: "direct retrieval", ko: "직접 검색" },
  "explain.topic_conn":     { en: "connected via shared keywords (Jaccard ≥ 0.08)", ko: "공유 키워드로 연결됨 (Jaccard ≥ 0.08)" },
  "explain.temporal_conn":  { en: "connected via same-day decisions (temporal cluster)", ko: "같은 날짜 결정으로 연결됨 (시간 클러스터)" },
  "explain.recall_conn":    { en: "connected via retrieval edge", ko: "검색 엣지로 연결됨" },
  "explain.selected_prompt":{ en: "selected prompt", ko: "선택된 프롬프트" },
  "explain.utility_hist":   { en: "utility history", ko: "활용 이력" },
  "explain.util_refs":      { en: "utility events touched", ko: "활용 이벤트가" },
  "explain.util_days":      { en: "block in the last 7 days", ko: "블록을 지난 7일 동안 건드림" },
  "explain.no_refs":        { en: "no recent utility events for this block type", ko: "이 블록 유형에 대한 최근 활용 이벤트 없음" },
  "explain.content":        { en: "content preview", ko: "콘텐츠 미리보기" },
  "explain.loading":        { en: "loading retrieval explanation…", ko: "검색 설명 로딩 중…" },
  "explain.no_prompt":      { en: "No prompt selected — cannot explain retrieval path.", ko: "선택된 프롬프트 없음 — 검색 경로를 설명할 수 없음." },
  "explain.load_fail":      { en: "Failed to load explanation — see console.", ko: "설명 로드 실패 — 콘솔 확인." },
  "explain.summary":        { en: "why retrieved", ko: "검색 이유" },
  "explain.breakdown":      { en: "score breakdown (per matched token)", ko: "점수 분해 (일치 토큰별)" },
  "explain.col_token":      { en: "token", ko: "토큰" },
  "explain.col_tf":         { en: "tf (in node)", ko: "tf (노드 내)" },
  "explain.col_idf":        { en: "idf", ko: "idf" },
  "explain.col_contrib":    { en: "contribution", ko: "기여도" },
  "explain.competitors":    { en: "top competitors in retrieval cone", ko: "검색 콘 내 상위 경쟁 노드" },
  "explain.missed":         { en: "prompt tokens NOT in this node", ko: "이 노드에 없는 프롬프트 토큰" },
  "explain.no_missed":      { en: "all prompt tokens present", ko: "모든 프롬프트 토큰이 존재" },
  "explain.prompt_from":    { en: "from project", ko: "출처 프로젝트" },
  "explain.prompt_at":      { en: "at", ko: "시각" },
  "explain.injected_as":    { en: "injected into context as", ko: "컨텍스트에 주입된 형식" },
  "explain.injected_block": { en: "block", ko: "블록" },
  "explain.ref_status":     { en: "used in response", ko: "응답에 사용됨" },
  "explain.ref_yes_text":   { en: "✓ referenced (text match)", ko: "✓ 참조됨 (텍스트 일치)" },
  "explain.ref_yes_tool":   { en: "✓ referenced (tool-use)", ko: "✓ 참조됨 (도구 사용)" },
  "explain.ref_yes_both":   { en: "✓✓ referenced (text + tool)", ko: "✓✓ 참조됨 (텍스트 + 도구)" },
  "explain.ref_no":         { en: "✗ not referenced in response", ko: "✗ 응답에 참조 안 됨" },
  "explain.ref_pending":    { en: "⟳ pending — assistant hasn't replied yet", ko: "⟳ 대기 중 — 응답 전" },
  "explain.ref_unknown":    { en: "? no telemetry for this prompt", ko: "? 이 프롬프트에 대한 텔레메트리 없음" },
};

function getLang() {
  const stored = localStorage.getItem("ctx-dashboard-lang");
  if (stored === "en" || stored === "ko") return stored;
  return (navigator.language || "en").toLowerCase().startsWith("ko") ? "ko" : "en";
}

function t(key, fallback) {
  const entry = I18N[key];
  if (!entry) return fallback != null ? fallback : key;
  return entry[getLang()] || entry.en || key;
}

function applyLanguage(lang) {
  localStorage.setItem("ctx-dashboard-lang", lang);
  document.documentElement.lang = lang;
  // data-i18n → textContent
  document.querySelectorAll("[data-i18n]").forEach(el => {
    const key = el.getAttribute("data-i18n");
    const entry = I18N[key];
    if (entry && entry[lang]) el.textContent = entry[lang];
  });
  // data-i18n-title → title attribute
  document.querySelectorAll("[data-i18n-title]").forEach(el => {
    const key = el.getAttribute("data-i18n-title");
    const entry = I18N[key];
    if (entry && entry[lang]) el.setAttribute("title", entry[lang]);
  });
  // data-i18n-html → innerHTML (for strings with <em>/<b> markup)
  document.querySelectorAll("[data-i18n-html]").forEach(el => {
    const key = el.getAttribute("data-i18n-html");
    const entry = I18N[key];
    if (entry && entry[lang]) el.innerHTML = entry[lang];
  });
  // Update language-toggle active segment
  document.querySelectorAll(".lang-seg").forEach(seg => {
    seg.classList.toggle("active", seg.dataset.lang === lang);
  });
  // Re-render dynamic panels (they use t() at render time)
  if (window._lastSnapshot) apply(window._lastSnapshot);
  if (graphNetwork) {
    renderGraphLegend(true);   // force re-render
    if (graphState && graphState.promptNodes.length) {
      updateNavLabel();
      applyPromptSelection();
    }
  }
}

function initLanguageToggle() {
  const btn = $("lang-toggle");
  if (!btn || btn.dataset.wired) return;
  btn.dataset.wired = "1";
  btn.addEventListener("click", () => {
    const next = getLang() === "en" ? "ko" : "en";
    applyLanguage(next);
  });
  // Apply current language on first load
  applyLanguage(getLang());
}

let activityPlot = null;
let graphNetwork = null;
let graphNodesSet = null;
let graphNodeById = {};
let lastEventCount = 0;   // used to detect new-event arrivals → refresh graph

function fmtThresholds(th) {
  return `Thresholds: CM ≥${th.cm_hybrid_min}%  |  g2_docs <${th.g2_docs_max}%  |  g2_grep <${th.g2_grep_max}%  |  p95 <${th.p95_max_ms}ms`;
}

// Human-readable labels for health row names (server sends code names)
const HEALTH_LABELS = {
  "CM hybrid":    { label: "Chat memory",    desc: "Accuracy of cross-session memory recall (BM25 + vector hybrid)" },
  "G1 fire rate": { label: "Decision recall", desc: "Share of prompts where past decisions were surfaced" },
  "g2_docs":      { label: "Docs search",     desc: "Share of prompts where relevant research docs were found" },
  "g2_grep":      { label: "Code search",     desc: "Share of prompts where codebase was searched" },
  "Latency p95":  { label: "Latency p95",     desc: "95th-percentile response time of the memory hook" },
};

function renderHealthRow(r) {
  const color = r.ok ? "green" : (r.critical ? "red" : "yellow");
  const sym = r.ok ? "✓" : (r.critical ? "!" : "~");
  const pct = Math.min(100, Math.max(2, Math.round((r.value || 0) * 100)));
  const meta = HEALTH_LABELS[r.name] || { label: r.name, desc: "" };
  return `
    <div class="row" title="${esc(meta.desc)}">
      <div class="label">${esc(meta.label)}</div>
      <div class="bar"><div class="bar-fill ${color}" style="width:${pct}%"></div></div>
      <div class="value">${esc(r.value_str)}</div>
      <div class="sym ${color}">${sym}</div>
      <div class="msg">${esc(r.msg)}</div>
    </div>`;
}

function renderLatencyBars(hist) {
  const total = hist.reduce((s, b) => s + b.count, 0) || 1;
  return hist.map(b => {
    const pct = (b.count / total) * 100;
    const danger = b.bucket === ">1s" || b.bucket === "500ms-1s";
    const fillColor = danger ? "red" : (b.bucket === "200-500ms" ? "yellow" : "green");
    return `
      <div class="b">
        <div class="bucket">${esc(b.bucket)}</div>
        <div class="bar"><div class="bar-fill ${fillColor}" style="width:${pct}%"></div></div>
        <div class="count">${esc(b.count)}</div>
      </div>`;
  }).join("");
}

// Wilson 95% confidence interval for a binomial proportion.
// Centralized so every rate label in the panel gets the same uncertainty
// treatment — iter 5 A1 (prior to this, only the age bar had CIs).
function wilsonCI(y, n, z = 1.96) {
  if (!n || n === 0) return [0, 0];
  const p = y / n;
  const d = 1 + z * z / n;
  const c = (p + z * z / (2 * n)) / d;
  const h = z * Math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d;
  return [Math.max(0, c - h), Math.min(1, c + h)];
}

// Formatter: "47% [44–51%] ±3.4pp"  — compact CI annotation for all rates.
// Returns just "—" if n is 0 (avoids misleading 0% ±0 display).
function fmtRateCI(referenced, total, opts = {}) {
  if (!total || total === 0) return { text: "—", hi: null, lo: null };
  const p = referenced / total;
  const [lo, hi] = wilsonCI(referenced, total);
  const pct = Math.round(p * 100);
  const halfwidth = ((hi - lo) * 50).toFixed(1);
  const short = opts.short
    ? `${pct}% <span class="ci-small">±${halfwidth}pp</span>`
    : `${pct}% <span class="ci-small">[${Math.round(lo*100)}–${Math.round(hi*100)}%]</span>`;
  return { text: short, pct, hi, lo, halfwidth };
}

function renderUtility(u) {
  const host = $("utility-body");
  if (!u || u.n_turns === 0) {
    host.innerHTML = `<div class="empty">${esc(t("util.empty"))}</div>`;
    return;
  }
  const overall = u.overall_rate;
  const pct = overall == null ? 0 : Math.round(overall * 100);
  const cls = pct >= 50 ? "" : (pct >= 25 ? "mid" : "low");
  // Pooled CI on the overall rate — n = total items across all turns
  const overallCI = fmtRateCI(
    Math.round((overall || 0) * (u.total_items || 0)),
    u.total_items || 0,
    { short: true }
  );
  const BLOCK_LABELS = {
    g1:          "Decisions",
    g2_docs:     "Research docs",
    g2_prefetch: "Code files",
  };
  const blocks = u.by_block || {};
  const blockRows = Object.keys(blocks).sort().map(name => {
    const b = blocks[name];
    const p = Math.round((b.rate || 0) * 100);
    const color = p >= 50 ? "green" : (p >= 25 ? "yellow" : "red");
    const pctFill = Math.max(3, p);
    const ci = fmtRateCI(b.referenced, b.total, { short: true });
    const displayName = BLOCK_LABELS[name] || name;
    return `<div class="row">
      <div class="name">${esc(displayName)}</div>
      <div class="bar"><div class="bar-fill ${color}" style="width:${pctFill}%"></div></div>
      <div class="count">${p}% (${esc(b.referenced)}/${esc(b.total)}) <span class="ci">${ci.halfwidth ? `±${ci.halfwidth}pp` : ""}</span></div>
    </div>`;
  }).join("");
  // A/B split panel — shown only when ≥2 groups or a control arm exists.
  // Delta row is computed when both control + treatment are present.
  const groups = u.by_group || {};
  const groupNames = Object.keys(groups);
  let abBlock = "";
  if (groupNames.length > 0) {
    const render = (name) => {
      const g = groups[name] || {};
      const rate = g.rate;
      const label = name === "control" ? t("ab.control")
                  : name === "treatment" ? t("ab.treatment")
                  : name.charAt(0).toUpperCase() + name.slice(1);
      const ci = fmtRateCI(g.referenced_items, g.total_items, { short: true });
      const rateDisplay = rate == null
        ? `<span class="ab-na" title="${esc(t("ab.na"))}">n/a</span>`
        : ci.text;
      const refDisplay = g.total_items
        ? `${g.referenced_items}/${g.total_items} items`
        : `${g.n_turns || 0} sessions, 0 injected`;
      return `<div class="ab-row">
        <div class="ab-label">${esc(label)}</div>
        <div class="ab-rate">${rateDisplay}</div>
        <div class="ab-sub">${esc(refDisplay)}</div>
      </div>`;
    };
    const ordered = ["control", "treatment", "ungrouped"].filter(n => groupNames.includes(n));
    let deltaLine = "";
    const c = groups.control, tr = groups.treatment;   // `t` would shadow i18n helper
    if (c && tr && tr.rate != null) {
      // Delta on utility alone is misleading when control rate is n/a — expose
      // session count contrast instead (the real A/B question: does treatment
      // deliver enough referenced items to justify the overhead?)
      deltaLine = `<div class="ab-delta">
        treatment: ${tr.n_turns} turns, ${tr.referenced_items} items used ·
        control: ${c.n_turns} sessions, CTX disabled
        <span class="hint">(time-saved comparison needs external timing — scaffold only)</span>
      </div>`;
    }
    abBlock = `<div class="ab-split">
      <div class="ab-head">${esc(t("ab.head"))} <span class="hint">${esc(t("ab.hint"))}</span></div>
      ${ordered.map(render).join("")}
      ${deltaLine}
    </div>`;
  }

  // Response-type stratification — iter 5 A2. Classifies each turn into
  // {prose, mixed, tool_heavy} via (response_len, tool_params_len). Rendered
  // only when ≥1 event has tool_params_len (iter 3+). The v1 32.5% vs v2 9.3%
  // discrepancy from iter 2 was primarily a response-type distribution artifact
  // — this makes the structure visible.
  let rtypeBlock = "";
  const rt = u.by_response_type;
  if (rt && rt.events_with_rtype > 0) {
    const label = { prose: t("rtype.prose"), mixed: t("rtype.mixed"),
                    tool_heavy: t("rtype.tool_heavy"),
                    unknown: "Unclassified" };
    const tooltip = {
      prose: "Mostly textual replies. CTX references are most visible here via substring/semantic match.",
      mixed: "Blend of prose and tool_use. CTX references split between text and tool-param channels.",
      tool_heavy: "Short prose with heavy tool_use. Textual-only scoring undercounts utility — tool-param match is the primary signal.",
      unknown: "Legacy events without tool_params_len field — response type cannot be determined.",
    };
    const row = (rtype) => {
      const b = rt[rtype];
      if (!b || b.n_turns === 0) return "";
      if (b.total === 0) {
        return `<div class="row" title="${esc(tooltip[rtype] || '')}">
          <div class="name">${esc(label[rtype] || rtype)}</div>
          <div class="bar"><div class="bar-fill" style="width:3%; background:var(--panel-border)"></div></div>
          <div class="count">— (${b.n_turns} turns, 0 items)</div>
        </div>`;
      }
      const p = Math.round(b.rate * 100);
      const color = p >= 50 ? "green" : (p >= 25 ? "yellow" : "red");
      const pctFill = Math.max(3, p);
      const ci = fmtRateCI(b.referenced, b.total);
      return `<div class="row" title="${esc(tooltip[rtype] || '')}">
        <div class="name">${esc(label[rtype] || rtype)}</div>
        <div class="bar"><div class="bar-fill ${color}" style="width:${pctFill}%"></div></div>
        <div class="count">${p}% (${esc(b.referenced)}/${esc(b.total)}) <span class="ci">±${ci.halfwidth}pp · ${esc(b.n_turns)}t</span></div>
      </div>`;
    };
    // Mixed first (highest citation rate = strongest CTX signal), then prose, then tool_heavy
    const rows = ["mixed", "prose", "tool_heavy"].map(row).filter(Boolean).join("");
    rtypeBlock = `<div class="rtype-split">
      <div class="rtype-head">${esc(t("rtype.head"))} <span class="hint">${esc(t("rtype.hint"))}</span></div>
      ${rows}
    </div>`;
  }

  // Age-stratified utility — iter 4. Visualizes the core "cross-session
  // memory" claim: are items 14+ days old actually getting used, or is utility
  // dominated by fresh items? Only rendered when ≥1 event carries by_age.
  let ageBlock = "";
  const ba = u.by_age;
  if (ba && ba.events_with_age > 0) {
    const row = (label, band, tooltip) => {
      const b = ba[band];
      if (!b || b.total === 0) return "";
      const p = Math.round(b.rate * 100);
      const color = p >= 50 ? "green" : (p >= 25 ? "yellow" : "red");
      const pctFill = Math.max(3, p);
      const ci = fmtRateCI(b.referenced, b.total);
      return `<div class="row" title="${esc(tooltip)}">
        <div class="name">${esc(label)}</div>
        <div class="bar"><div class="bar-fill ${color}" style="width:${pctFill}%"></div></div>
        <div class="count">${p}% (${esc(b.referenced)}/${esc(b.total)}) <span class="ci">±${ci.halfwidth}pp</span></div>
      </div>`;
    };
    const rows = [
      row(t("age.0-7d"),   "0-7d",    "Items surfaced from decisions within the last week"),
      row(t("age.7-30d"),  "7-30d",   "Cross-session recall zone — this is the core CTX claim"),
      row(t("age.30d+"),   "30d+",    "Deep memory — items that would otherwise be forgotten"),
      row(t("age.no_date"),"no_date", "Docs and code prefetches have no age attribution"),
    ].filter(Boolean).join("");
    ageBlock = `<div class="age-split">
      <div class="age-head">${esc(t("age.head"))} <span class="hint">${esc(t("age.hint"))}</span></div>
      ${rows}
    </div>`;
  }

  // Text-vs-tool split — new in iter 3. Only shown when we have events
  // emitted by tool-aware utility-rate.py (pre-iter-3 events don't carry
  // `referenced_by` so they're silently excluded from this breakdown).
  let splitBlock = "";
  const rs = u.referenced_split;
  if (rs && rs.events_with_split > 0) {
    const textPct = Math.round(rs.text_only_share * 100);
    const toolPct = Math.round(rs.tool_only_share * 100);
    const bothPct = Math.round(rs.both_share * 100);
    const recoveryPp = (rs.tool_only_recovery_pp * 100).toFixed(1);
    splitBlock = `<div class="util-split">
      <div class="util-split-head">${esc(t("split.head"))} <span class="hint">${esc(rs.events_with_split)} ${esc(t("split.tooltip"))}</span></div>
      <div class="util-split-bar">
        <div class="util-seg text" style="flex:${rs.text_only};">${textPct}% ${esc(t("split.text"))}</div>
        <div class="util-seg both" style="flex:${rs.both};">${bothPct}% ${esc(t("split.both"))}</div>
        <div class="util-seg tool" style="flex:${rs.tool_only};">${toolPct}% ${esc(t("split.tool"))}</div>
      </div>
      <div class="util-split-note">
        ${esc(t("split.recovery"))} <b>+${recoveryPp}pp</b>
      </div>
    </div>`;
  }

  const overallCITxt = overallCI.halfwidth
    ? `<span class="overall-ci">${esc(t("util.overallCI"))} ±${overallCI.halfwidth}pp</span>`
    : "";

  // Interpretation note: surface the mixed-turn rate up front (strongest CTX signal)
  let interpretNote = "";
  const rtMixed = (u.by_response_type || {}).mixed;
  if (rtMixed && rtMixed.n_turns > 0 && rtMixed.rate != null) {
    const mixedPct = Math.round(rtMixed.rate * 100);
    interpretNote = `<div class="util-interp-note" style="margin-top:6px; font-size:0.82em; color:var(--text-dim); font-style:italic">
      In multi-step turns (tool use), CTX context was cited ${mixedPct}% of the time — vs 0% baseline without CTX.
    </div>`;
  }

  host.innerHTML = `
    <div class="overall">
      <div class="big ${cls}">${pct}%</div>
      <div>
        <div>${esc(t("util.overall"))} ${overallCITxt} <span class="hint" style="font-size:0.8em; color:var(--text-dim)">(vs 0% baseline)</span></div>
        <div class="sub">${esc(u.n_turns)} ${esc(t("util.nturns"))} · ${esc(u.total_items)} ${esc(t("util.items"))}${u.stale_skipped ? ` · ${esc(u.stale_skipped)} ${esc(t("util.stale"))}` : ''}</div>
      </div>
    </div>
    ${interpretNote}
    ${blockRows}
    ${rtypeBlock}
    ${ageBlock}
    ${splitBlock}
    ${abBlock}
  `;
}

function renderNotices(notices) {
  if (!notices || notices.length === 0) {
    return `<div style="color:#2e7d32; font-family:var(--mono); font-size:12px; display:flex; align-items:center; gap:6px">
      <span style="font-size:1.1em">✓</span> No quality alerts — all metrics within normal ranges
    </div>`;
  }
  return notices.map(n => `
    <div class="notice">
      <div class="tilde">~</div>
      <div class="metric">${esc(n.metric)}</div>
      <div class="msg">${esc(n.msg)}</div>
    </div>`).join("");
}

// Human-readable labels for "other signals" event types
const OTHER_LABELS = {
  "CM daemon-down":   "Vector daemon offline",
  "decision-keyword": "Decision triggers",
  "grep-fallback":    "Search fallbacks",
};

function renderOther(other) {
  if (!other || other.length === 0) return `<span style="color:var(--text-dim); font-size:12px;">No additional signals this window</span>`;
  return other.map(o => {
    const label = OTHER_LABELS[o.label] || o.label;
    return `<span class="pill" title="${esc(o.label)}">${esc(label)} <span class="count">×${esc(o.count)}</span></span>`;
  }).join("");
}

function renderTokenUsage(tu) {
  const host = $("token-usage-body");
  if (!host) return;
  if (!tu) {
    host.innerHTML = `<span style="color:var(--text-dim);font-size:12px;font-family:var(--mono)">No token_usage events yet — inject CTX context to start tracking.</span>`;
    return;
  }
  const pct = tu.total_prompt_tokens > 0
    ? ((tu.total_injected_tokens / tu.total_prompt_tokens) * 100).toFixed(1)
    : null;
  const byBlock = tu.by_block && Object.keys(tu.by_block).length > 0
    ? Object.entries(tu.by_block)
        .sort((a, b) => b[1] - a[1])
        .map(([blk, toks]) => `<span class="pill" style="font-family:var(--mono);font-size:11px">${esc(blk)} <span class="count">${toks.toLocaleString()}</span></span>`)
        .join(" ")
    : null;
  host.innerHTML = `
    <div style="display:flex;flex-wrap:wrap;gap:18px;align-items:flex-start">
      <div style="min-width:160px">
        <div style="font-size:28px;font-weight:600;color:var(--accent);font-family:var(--mono);line-height:1">${tu.avg_injected_tokens.toLocaleString()}</div>
        <div style="font-size:11px;color:var(--text-dim);margin-top:3px">avg CTX tokens / turn</div>
      </div>
      ${pct !== null ? `<div style="min-width:120px">
        <div style="font-size:28px;font-weight:600;color:var(--text-soft);font-family:var(--mono);line-height:1">${pct}%</div>
        <div style="font-size:11px;color:var(--text-dim);margin-top:3px">of prompt tokens</div>
      </div>` : ''}
      <div style="min-width:120px">
        <div style="font-size:22px;font-weight:500;color:var(--text-soft);font-family:var(--mono);line-height:1">${tu.total_turns}</div>
        <div style="font-size:11px;color:var(--text-dim);margin-top:3px">turns tracked</div>
      </div>
    </div>
    ${byBlock ? `<div style="margin-top:12px"><div style="font-size:11px;color:var(--text-dim);margin-bottom:6px;text-transform:uppercase;letter-spacing:0.5px">by block (total tokens)</div><div class="pills">${byBlock}</div></div>` : ''}`;
}

function fmtTs(ts) {
  if (!ts) return "";
  // ts is ISO8601 (from vault.db) — take HH:MM
  try {
    const s = String(ts);
    const m = s.match(/T(\d\d:\d\d)/);
    return m ? m[1] : s.slice(0, 16);
  } catch { return String(ts).slice(0, 16); }
}

function renderBlock(name, tag, items, itemClass = "it") {
  const cls = items && items.length ? "" : "empty";
  // Method dot colors for G1/G2-DOCS items (when item is a {text, retrieval_method} dict)
  const methodDotColor = { semantic: '#7b1fa2', keyword: '#1565c0', cascade: '#555',
                           cm_hybrid: '#2e7d32', code_index: '#00695c' };
  const body = items && items.length
    ? items.map(i => {
        // Support both plain strings (g2_prefetch) and {text, retrieval_method} objects (g1, g2_docs)
        const text = typeof i === 'object' ? (i.text || '') : i;
        const method = typeof i === 'object' ? i.retrieval_method : null;
        const dotColor = method && methodDotColor[method];
        const dot = dotColor
          ? `<span style="color:${dotColor}; font-size:0.7em; margin-right:2px; flex-shrink:0" title="${method}">●</span>`
          : '';
        return `<div class="${itemClass}" title="${esc(text)}" style="display:flex; align-items:flex-start; gap:1px">${dot}<span>${esc(text)}</span></div>`;
      }).join("")
    : `<div class="it empty-block">nothing surfaced</div>`;
  return `
    <div class="block ${cls} ${name.toLowerCase()}">
      <div class="name"><span>${esc(name)}</span><span class="tag">${esc(tag)}</span></div>
      <div class="items">${body}</div>
    </div>`;
}

function renderCmBlock(cm) {
  const cls = cm && cm.length ? "" : "empty";
  const body = cm && cm.length
    ? cm.map(e => `
        <div class="cm-entry">
          <span class="who">${esc(e.role)}@${esc(e.project)}</span><span title="${esc(e.preview)}">${esc(e.preview)}</span>
        </div>`).join("")
    : `<div class="it empty-block">nothing surfaced</div>`;
  return `
    <div class="block cm ${cls}">
      <div class="name"><span>Chat history</span><span class="tag">past conversations</span></div>
      <div class="items">${body}</div>
    </div>`;
}

function renderGraphLegend(force) {
  const host = $("graph-legend");
  if (!force && host.childElementCount > 0) return;
  host.innerHTML = `
    <span class="lg current"><span class="swatch"></span>${esc(t("legend.current"))}</span>
    <span class="lg decision"><span class="swatch"></span>${esc(t("legend.decision"))}</span>
    <span class="lg doc"><span class="swatch"></span>${esc(t("legend.doc"))}</span>
    <span class="lg chatmem"><span class="swatch chatmem"></span>chat mem</span>
    <span class="lg code"><span class="swatch code"></span>codebase</span>
    <span class="lg prompt"><span class="swatch"></span>${esc(t("legend.prompt"))}</span>
    <span class="lg hot"><span class="swatch hot"></span>${esc(t("legend.hot"))}</span>
    <span class="lg dead"><span class="swatch dead"></span>${esc(t("legend.dead"))}</span>
    <span class="lg recall"><span class="line"></span>${esc(t("legend.recall"))}</span>
    <span class="lg topic"><span class="line"></span>${esc(t("legend.topic"))}</span>
    <span class="lg temporal"><span class="line"></span>${esc(t("legend.temporal"))}</span>
  `;
}

function nodeStyle(type, utilityHeat) {
  // Paper-canvas palette — deeper saturated colors so nodes pop on cream bg.
  // Current prompt = Claude coral (brand accent).
  // Decision = deep navy slate; Doc = deep plum; Prompt = warm grey.
  // Labels now dark (not light) since they read against paper, not dark.
  //
  // Iter 4 A3: decision/doc nodes get heat-modulated border and opacity.
  //   heat ≥ 0.67 → coral border (referenced multiple times recently)
  //   heat ≥ 0.34 → coral-tinted border
  //   heat  > 0   → normal
  //   heat == 0   → muted (dead weight signal)
  const heat = typeof utilityHeat === "number" ? utilityHeat : 0;
  const isHot = heat >= 0.67;
  const isWarm = heat >= 0.34;
  const isDead = heat === 0;

  switch (type) {
    case "current":  return {
      color: { background: "#cc785c", border: "#a34b2c",
               highlight: { background: "#e08562", border: "#b55a3c" },
               hover:     { background: "#e08562", border: "#b55a3c" } },
      size: 26, font: { color: "#faf9f6", size: 14, face: "ui-monospace" }, shape: "dot", borderWidth: 3,
    };
    case "decision": {
      const border = isHot ? "#cc785c" : (isWarm ? "#a34b2c" : "#25475e");
      const bg = isDead ? "#7a8a9a" : "#3b6a8a";
      return {
        color: { background: bg, border,
                 highlight: { background: "#5788a8", border: "#cc785c" },
                 hover:     { background: "#5788a8", border: "#cc785c" } },
        size: isHot ? 16 : (isWarm ? 14 : (isDead ? 11 : 13)),
        font: { color: isDead ? "#8a8278" : "#1f1c1a", size: 11 },
        shape: "dot",
        borderWidth: isHot ? 3 : (isWarm ? 2 : 1.5),
        opacity: isDead ? 0.55 : 1,
      };
    }
    case "doc": {
      const border = isHot ? "#cc785c" : (isWarm ? "#a34b2c" : "#553d63");
      const bg = isDead ? "#9a8aa0" : "#7a5c8a";
      return {
        color: { background: bg, border,
                 highlight: { background: "#9778a8", border: "#cc785c" },
                 hover:     { background: "#9778a8", border: "#cc785c" } },
        size: isHot ? 15 : (isWarm ? 13 : (isDead ? 10 : 12)),
        font: { color: isDead ? "#8a8278" : "#1f1c1a", size: 11 },
        shape: "dot",
        borderWidth: isHot ? 3 : (isWarm ? 2 : 1.5),
        opacity: isDead ? 0.55 : 1,
      };
    }
    case "chatmem":  return {
      // teal-green: chat memory recall
      color: { background: "#2e8b7a", border: "#1d6b5c",
               highlight: { background: "#3aaa97", border: "#2e8b7a" },
               hover:     { background: "#3aaa97", border: "#2e8b7a" } },
      size: 12, font: { color: "#1f1c1a", size: 11 }, shape: "diamond", borderWidth: 2,
    };
    case "code":     return {
      // olive-green: codebase prefetch
      color: { background: "#6b8c3a", border: "#4d6a28",
               highlight: { background: "#86a850", border: "#6b8c3a" },
               hover:     { background: "#86a850", border: "#6b8c3a" } },
      size: 12, font: { color: "#1f1c1a", size: 11 }, shape: "square", borderWidth: 2,
    };
    case "prompt":   return {
      color: { background: "#8a8278", border: "#6d655b",
               highlight: { background: "#a8a095", border: "#8a8278" },
               hover:     { background: "#a8a095", border: "#8a8278" } },
      size: 10, font: { color: "#4a4540", size: 10 }, shape: "dot", borderWidth: 1.5,
    };
    default: return { color: { background: "#8a8278", border: "#6d655b" }, size: 10, shape: "dot" };
  }
}

function edgeStyle(type, weight, isCurrent) {
  const base = {
    width: Math.max(0.6, Math.min(3.2, weight * 0.8)),
    smooth: { enabled: true, type: "continuous" },
  };
  // Paper-bg edges — deeper saturated tones. Current prompt edges get a
  // subtle coral glow; past-prompt edges are thinner and more transparent
  // so the current retrieval cone reads instantly.
  if (type === "recall-d" || type === "recall-w") {
    const isDoc = type === "recall-w";
    return Object.assign(base, {
      color: isCurrent
        ? { color: "#cc785c", highlight: "#a34b2c", opacity: 0.95 }
        : { color: isDoc ? "#7a5c8a" : "#3b6a8a", highlight: "#cc785c", opacity: 0.55 },
      width: isCurrent ? Math.max(2.6, weight * 0.65) : Math.max(0.9, weight * 0.35),
      shadow: isCurrent ? { enabled: true, color: "rgba(204,120,92,0.35)", size: 6, x: 0, y: 0 } : false,
    });
  }
  // CM recall (chatmem nodes) — teal threads
  if (type === "recall-cm") {
    return Object.assign(base, {
      color: isCurrent
        ? { color: "#2e8b7a", highlight: "#1d6b5c", opacity: 0.90 }
        : { color: "#2e8b7a", highlight: "#3aaa97", opacity: 0.45 },
      width: isCurrent ? 2.2 : 0.9,
      dashes: [6, 3],
    });
  }
  // Codebase prefetch (code nodes) — olive threads
  if (type === "recall-pre") {
    return Object.assign(base, {
      color: isCurrent
        ? { color: "#6b8c3a", highlight: "#4d6a28", opacity: 0.90 }
        : { color: "#6b8c3a", highlight: "#86a850", opacity: 0.45 },
      width: isCurrent ? 2.2 : 0.9,
      dashes: [4, 4],
    });
  }
  // Topic edges (doc ↔ doc) — plum threads, low opacity so clusters are
  // visible but don't dominate the current retrieval cone.
  if (type === "topic") {
    return Object.assign(base, {
      color: { color: "#7a5c8a", highlight: "#9778a8", opacity: 0.35 },
      width: Math.max(0.6, weight * 2.5),
    });
  }
  // Temporal edges (same-day decisions) — very subtle navy threads;
  // structural glue that shouldn't compete with retrieval edges.
  if (type === "temporal") {
    return Object.assign(base, {
      color: { color: "#3b6a8a", highlight: "#5788a8", opacity: 0.18 },
      width: 0.7,
    });
  }
  return base;
}

// Prompt navigation + signal animation state (module-level so nav buttons
// and rAF loop can reach it without re-fetching the graph on every tick).
let graphState = {
  promptNodes: [],      // [{id, label, ts, full}, ...] sorted newest-first
  selectedIdx: 0,       // 0 = newest
  rawNodes: [],         // full node list from last /api/graph
  rawEdges: [],         // full edge list from last /api/graph
  promptBM25: {},       // {prompt_id: {node_id: max_bm25_weight}} — iter 9
  signalOn: true,
  rafHandle: null,
};

function renderGraph(g) {
  if (!g || !g.nodes) return;
  renderGraphLegend();
  const canvas = $("graph-canvas");

  // Extract prompt nodes in display order (current/prompt types, newest first).
  // Server already prepends the "current" node; append remaining "prompt" nodes
  // in their emitted order (which is also newest-first from vault.db).
  const promptNodes = g.nodes
    .filter(n => n.type === "current" || n.type === "prompt")
    .map(n => ({ id: n.id, label: n.label, full: n.full, ts: n.ts, type: n.type }));
  graphState.rawNodes = g.nodes;
  graphState.rawEdges = g.edges;
  graphState.promptBM25 = g.prompt_bm25 || {};
  graphState.promptNodes = promptNodes;
  // Preserve selectedIdx across re-renders if it's still valid, else reset
  if (graphState.selectedIdx >= promptNodes.length) graphState.selectedIdx = 0;

  const visNodes = g.nodes.map(n => {
    const style = nodeStyle(n.type, n.utility_heat);
    graphNodeById[n.id] = n;
    // Enrich tooltip with utility heat signal
    const heatNote = (n.type === "decision" || n.type === "doc")
      ? `\n\nUtility heat (7d): ${(n.utility_heat || 0).toFixed(2)}`
      + (n.utility_heat >= 0.34 ? " — referenced in recent actions" : "")
      + (n.utility_heat === 0 ? " — no recent references (candidate for pruning)" : "")
      : "";
    return Object.assign({
      id: n.id,
      label: n.type === "current" ? n.label : "",
      title: n.full + heatNote,
      type: n.type,
    }, style);
  });
  const visEdges = g.edges.map((e, i) => Object.assign(
    { id: `e${i}`, from: e.from, to: e.to, type: e.type, current: !!e.current },
    edgeStyle(e.type, e.weight || 1, !!e.current),
  ));

  const stats = g.stats || {};
  const heatTxt = (stats.heat && stats.heat.pairs_scanned)
    ? ` · ${stats.heat.nodes_hot} hot nodes (${stats.heat.pairs_scanned} turns scanned)`
    : "";
  $("graph-stats").textContent = `${stats.decisions||0} decisions · ${stats.docs||0} docs · ${stats.prompts||0} prompts · ${stats.edges||0} edges${heatTxt}`;

  if (graphNetwork) {
    graphNetwork.setData({ nodes: visNodes, edges: visEdges });
    // Re-render path: re-init nav (prompt list may have changed) + restart signals
    initPromptNavigation();
    startSignalAnimation();
    return;
  }

  const data = {
    nodes: new vis.DataSet(visNodes),
    edges: new vis.DataSet(visEdges),
  };
  // Per-edge physics: temporal edges have short tight springs (cluster same-day
  // decisions together); topic edges medium; retrieval edges long (radial cone).
  visEdges.forEach(e => {
    if (e.type === "temporal")       { e.length = 55;  e.physics = true; }
    else if (e.type === "topic")     { e.length = 140; e.physics = true; }
    else if (e.type === "recall-d")  { e.length = 220; e.physics = true; }
    else if (e.type === "recall-w")  { e.length = 240; e.physics = true; }
    else if (e.type === "recall-cm") { e.length = 200; e.physics = true; }
    else if (e.type === "recall-pre"){ e.length = 190; e.physics = true; }
  });

  const options = {
    interaction: { hover: true, hoverConnectedEdges: true, tooltipDelay: 80, dragView: true, zoomView: true },
    physics: {
      enabled: true,
      solver: "forceAtlas2Based",
      forceAtlas2Based: {
        gravitationalConstant: -65,    // stronger node repulsion → sharper cluster gaps
        centralGravity: 0.004,         // let clusters drift apart
        springLength: 110,
        springConstant: 0.11,          // tighter springs within connected nodes
        damping: 0.55,
        avoidOverlap: 0.3,
      },
      stabilization: { iterations: 320, fit: true },
      maxVelocity: 60,
    },
    nodes: { borderWidth: 1.5, shadow: false },
    edges: { selectionWidth: 2.5 },
  };

  graphNetwork = new vis.Network(canvas, data, options);

  // First render: wire up navigation + signals now that the network exists
  initPromptNavigation();
  startSignalAnimation();

  graphNetwork.on("click", (params) => {
    const detail = $("graph-detail");
    if (params.nodes.length === 0) {
      detail.classList.add("empty");
      detail.innerHTML = "";
      return;
    }
    const id = params.nodes[0];
    const n = graphNodeById[id];
    if (!n) return;
    detail.classList.remove("empty");
    // Methodology change 2026-04-24: always show the ranked contributors list
    // for the selected prompt. If the clicked node is itself in the list, it
    // scrolls into view + expands. If the user clicked a non-contributor node,
    // the list still renders (as overview) and `renderNodeExplain` appears at
    // the top as a banner for the clicked node.
    const selectedPrompt = graphState.promptNodes[graphState.selectedIdx];
    if (selectedPrompt) {
      renderContributorsList(detail, selectedPrompt.id, n.id);
    } else {
      renderNodeExplain(detail, n);
    }
  });
}

// Highlight matched tokens inside an excerpt (case-insensitive, word-boundary-aware)
function highlightMatches(text, tokens) {
  if (!text || !tokens || !tokens.length) return esc(text || "");
  const matchSet = new Set(tokens.map(t => t.toLowerCase()).filter(t => t.length >= 3));
  if (!matchSet.size) return esc(text);
  return text.split(/(\s+|[.,;:!?()])/).map(w => {
    const clean = w.toLowerCase().replace(/[^\w-]/g, "");
    if (matchSet.has(clean)) return `<span class="match-tok">${esc(w)}</span>`;
    return esc(w);
  }).join("");
}

// ─────────────────── contributors list (2026-04-24 methodology) ───────────────────
// Shows ALL nodes contributing to the selected prompt, ranked by BM25 score.
// Each entry: rank + score bar + injection_preview + referenced chip.
// Click → highlight on graph + expand full detail inline.

function renderContributorsList(detail, promptId, highlightNodeId) {
  detail.innerHTML = `<div style="padding:12px; color:var(--text-dim); font-style:italic">
    ${esc(t("explain.loading") || "loading contributors...")}
  </div>`;
  fetch(`/api/prompt-contributors?prompt_id=${encodeURIComponent(promptId)}`)
    .then(r => r.json())
    .then(data => detail.innerHTML = buildContributorsHTML(data, highlightNodeId))
    .then(() => wireContributorClicks(detail, highlightNodeId))
    .catch(err => {
      console.error("prompt-contributors failed", err);
      detail.innerHTML = `<div class="node-info">Error loading contributors — see console.</div>`;
    });
}

function buildContributorsHTML(data, highlightNodeId) {
  if (data.error) return `<div class="node-info">Error: ${esc(data.error)}</div>`;

  const promptMeta = [];
  if (data.prompt_project) promptMeta.push(`<span class="label">${esc(t('explain.prompt_from'))}</span> <b>${esc(data.prompt_project)}</b>`);
  if (data.prompt_ts) {
    let ts = data.prompt_ts;
    try {
      const d = new Date(data.prompt_ts);
      if (!isNaN(d)) ts = d.toISOString().replace('T', ' ').slice(0, 16);
    } catch(e) {}
    promptMeta.push(`<span class="label">${esc(t('explain.prompt_at'))}</span> ${esc(ts)}`);
  }

  const contribs = data.contributors || [];
  const maxScore = contribs.length ? Math.max(...contribs.map(c => c.bm25_score || 0)) || 1 : 1;

  const refStatusMap = {
    yes_text: { label: "CITED", icon: "✓", color: "#2e7d32", bg: "#e8f5e9" },
    yes_tool: { label: "CITED", icon: "✓", color: "#2e7d32", bg: "#e8f5e9" },
    yes_both: { label: "CITED", icon: "✓✓", color: "#1b5e20", bg: "#c8e6c9" },
    no:       { label: "PROVIDED", icon: null, color: "#666", bg: "#f0f0f0" },
    pending:  { label: null, icon: null, color: null, bg: null },
    unknown:  { label: null, icon: null, color: null, bg: null },
  };

  const items = contribs.map(c => {
    const barPct = Math.max(5, (c.bm25_score / maxScore) * 100);
    const rs = refStatusMap[c.referenced_in_response] || refStatusMap.unknown;
    const tokens = (c.matched_tokens || []).slice(0, 4).map(t => `<span class="match-tok">${esc(t)}</span>`).join(" ");
    const isHighlight = c.node_id === highlightNodeId;
    const methodBadge = (() => {
      const m = c.retrieval_method || 'unknown';
      const cfg = {
        semantic:   { label: 'SEMANTIC',   color: '#7b1fa2', bg: '#f3e5f5' },
        keyword:    { label: 'KEYWORD',    color: '#1565c0', bg: '#e3f2fd' },
        cascade:    { label: 'CASCADE',    color: '#555',    bg: '#eeeeee' },
        cm_hybrid:  { label: 'CM',         color: '#2e7d32', bg: '#e8f5e9' },
        code_index: { label: 'CODE',       color: '#00695c', bg: '#e0f2f1' },
        hybrid:     { label: 'HYBRID',     color: '#e65100', bg: '#fff3e0' },
      }[m] || { label: m.toUpperCase(), color: '#888', bg: '#f5f5f5' };
      return `<span style="font-size:0.72em; font-weight:700; padding:1px 6px; border-radius:8px; color:${cfg.color}; background:${cfg.bg}; flex-shrink:0; letter-spacing:0.4px; border:1px solid ${cfg.color}40">${cfg.label}</span>`;
    })();
    return `
      <li class="contributor-item" data-node-id="${esc(c.node_id)}"
          style="padding:8px 10px; margin-bottom:6px; border-left:3px solid ${(c.retrieval_method === 'semantic') ? '#7b1fa2' : 'var(--accent, #4a90e2)'};
                 background:${isHighlight ? 'var(--bg-alt, rgba(74,144,226,0.08))' : 'var(--bg, #fff)'};
                 border-radius:4px; cursor:pointer; transition:background 0.15s">
        <div style="display:flex; align-items:center; gap:8px; font-size:0.9em">
          <span style="font-weight:600; color:var(--accent-deep, #4a90e2); min-width:24px">#${c.rank}</span>
          <span class="tag ${esc(c.node_type)}" style="flex-shrink:0">${esc(c.node_type)}</span>
          ${methodBadge}
          <span style="flex:1; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; font-size:0.95em">
            ${esc(c.node_label)}
          </span>
          ${rs.label ? `<span style="font-size:0.72em; font-weight:700; padding:1px 6px; border-radius:8px; color:${rs.color}; background:${rs.bg}; flex-shrink:0; letter-spacing:0.4px; border:1px solid ${rs.color}40">${rs.icon ? rs.icon + ' ' : ''}${rs.label}</span>` : ''}
        </div>
        <div style="display:flex; align-items:center; gap:6px; margin-top:4px; font-size:0.8em; color:var(--text-dim)">
          <div style="flex:1; height:4px; background:var(--bg-muted, #e5e5e5); border-radius:2px; overflow:hidden">
            <div style="height:100%; width:${barPct.toFixed(1)}%; background:linear-gradient(90deg, var(--accent, #4a90e2), var(--accent-deep, #2e7d32))"></div>
          </div>
          <span style="min-width:60px; text-align:right">bm25 ${(c.bm25_score || 0).toFixed(2)}</span>
          ${c.semantic_score != null ? (() => {
            const ss = c.semantic_score;
            const ssColor = ss >= 0.75 ? '#7b1fa2' : ss >= 0.55 ? '#1565c0' : '#888';
            return `<span style="color:${ssColor}; font-weight:600; min-width:62px; text-align:right" title="e5-small cosine similarity">sem ${ss.toFixed(3)}</span>`;
          })() : ''}
          ${tokens ? `<span style="min-width:80px">${tokens}</span>` : ''}
        </div>
        ${c.summary ? `<div style="margin-top:4px; font-size:0.85em; color:var(--text); font-style:italic">${esc(c.summary)}</div>` : ''}
        ${c.relevant_excerpt ? `
          <div style="margin-top:6px; padding:6px 8px; background:var(--bg-muted, rgba(0,0,0,0.04)); border-left:2px solid var(--accent, #4a90e2); border-radius:3px; font-size:0.85em; line-height:1.4">
            ${highlightMatches(c.relevant_excerpt, c.matched_tokens)}
          </div>
        ` : ''}
        ${c.injection_preview ? `
          <details style="margin-top:6px" ${isHighlight ? 'open' : ''}>
            <summary style="cursor:pointer; color:var(--text-dim); font-size:0.8em">
              ${esc(t('explain.injected_as'))} ${c.injection_block ? `<span class="tag ${esc(c.node_type)}">${esc(c.injection_block)}</span>` : ''}
            </summary>
            <pre style="margin:4px 0; padding:6px; background:var(--bg-code, rgba(0,0,0,0.03)); border-radius:3px; font-size:0.78em; white-space:pre-wrap; overflow-x:auto">${esc(c.injection_preview)}</pre>
          </details>
        ` : ''}
      </li>`;
  }).join('');

  const promptBlock = `
    <div style="padding:8px 10px; margin-bottom:10px; background:var(--bg-muted, rgba(0,0,0,0.03)); border-radius:4px">
      <div style="font-size:0.75em; color:var(--accent-deep, #4a90e2); letter-spacing:0.5px; text-transform:uppercase; margin-bottom:4px">selected prompt</div>
      ${promptMeta.length ? `<div style="font-size:0.8em; color:var(--text-dim); margin-bottom:4px">${promptMeta.join(' · ')}</div>` : ''}
      <div style="font-size:0.9em; max-height:80px; overflow-y:auto">${esc(data.prompt_text || '')}</div>
    </div>`;

  // ALL CTX BLOCKS section — shows every retrieval channel, not just BM25-graph nodes
  let allBlocksBar = "";
  if (data.retrieval_blocks) {
    const rb = data.retrieval_blocks;
    const blockRows = [];
    if (rb.cm_mode) {
      blockRows.push(`<tr>
        <td style="padding:3px 8px; font-weight:600">CM</td>
        <td style="padding:3px 8px; color:var(--text-dim); font-size:0.85em">chat memory</td>
        <td style="padding:3px 8px; font-style:italic; color:var(--accent-deep)">${esc(rb.cm_mode)}</td>
        <td style="padding:3px 8px; color:var(--text-dim)">—</td>
      </tr>`);
    }
    const blockDefs = [
      ["g1_decisions", "G1",          "recent decisions",   true],
      ["g2_docs",      "G2-DOCS",     "research docs",      true],
      ["g2_prefetch",  "G2-PREFETCH", "codebase functions", false],
      ["g2_grep",      "G2-GREP",     "hook grep",          false],
    ];
    for (const [key, label, desc, inGraph] of blockDefs) {
      const blk = rb[key];
      if (!blk) continue;
      const badge = inGraph
        ? `<span style="background:var(--accent-soft,#f5e6de); color:var(--accent-deep); font-size:0.7em; padding:1px 4px; border-radius:8px; margin-left:4px; vertical-align:middle">in list</span>`
        : `<span style="background:#e8f5e9; color:#2e7d32; font-size:0.7em; padding:1px 4px; border-radius:8px; margin-left:4px; vertical-align:middle">samples ↓</span>`;
      blockRows.push(`<tr>
        <td style="padding:3px 8px; font-weight:600; color:${inGraph ? 'var(--accent-deep)' : 'var(--text-soft)'}">${esc(label)}${badge}</td>
        <td style="padding:3px 8px; color:var(--text-dim); font-size:0.85em">${esc(desc)}</td>
        <td style="padding:3px 8px; font-weight:${inGraph ? '600' : '400'}">${blk.count} items</td>
        <td style="padding:3px 8px; color:var(--text-dim); font-size:0.85em">${blk.duration_ms}ms</td>
      </tr>`);
    }
    if (blockRows.length) {
      allBlocksBar = `<div style="margin-bottom:10px; background:var(--bg-deep,#f0ede7); border-radius:5px; padding:8px 10px; font-size:0.88em">
        <div style="font-size:0.72em; color:var(--accent-deep); letter-spacing:0.5px; text-transform:uppercase; margin-bottom:5px; font-weight:600">All CTX blocks fired for this prompt</div>
        <table style="width:100%; border-collapse:collapse">
          <thead><tr style="color:var(--text-dim); font-size:0.78em; border-bottom:1px solid var(--panel-border)">
            <th style="text-align:left; padding:2px 8px">Block</th>
            <th style="text-align:left; padding:2px 8px">Type</th>
            <th style="text-align:left; padding:2px 8px">Items</th>
            <th style="text-align:left; padding:2px 8px">Latency</th>
          </tr></thead>
          <tbody>${blockRows.join("")}</tbody>
        </table>
        <div style="margin-top:5px; font-size:0.76em; color:var(--text-dim); font-style:italic">
          "in list" = graph nodes ranked by BM25 below · "samples ↓" = retrieved but not graphed — visible in Samples panel
        </div>
      </div>`;
    }
  }

  const header = `<div style="font-size:0.75em; color:var(--accent-deep, #4a90e2); letter-spacing:0.5px; text-transform:uppercase; margin-bottom:6px">
    contributors (ranked by BM25 · ${contribs.length} total)
  </div>`;

  return promptBlock + allBlocksBar + header + `<ul style="list-style:none; padding:0; margin:0">${items || '<li style="color:var(--text-dim); font-style:italic; padding:8px">No contributors — this prompt had no direct BM25 matches.</li>'}</ul>`;
}

function wireContributorClicks(detail, highlightNodeId) {
  const items = detail.querySelectorAll('.contributor-item');
  items.forEach(li => {
    li.addEventListener('click', (ev) => {
      // Don't trigger when user clicks the <summary> toggle
      if (ev.target.tagName === 'SUMMARY' || ev.target.closest('summary')) return;
      const nodeId = li.dataset.nodeId;
      if (!nodeId) return;
      // Scroll to graph panel first, then focus the node inside it
      document.getElementById('graph-panel')?.scrollIntoView({ behavior: 'smooth', block: 'start' });
      if (graphNetwork && graphNetwork.getNodeAt) {
        try {
          graphNetwork.selectNodes([nodeId], true);
          setTimeout(() => {
            graphNetwork.focus(nodeId, { scale: 1.3, animation: { duration: 400, easingFunction: 'easeInOutQuad' } });
          }, 350);
        } catch (e) {
          console.warn('focus failed', e);
        }
      }
      // Visual feedback in the list
      detail.querySelectorAll('.contributor-item').forEach(el =>
        el.style.background = 'var(--bg, #fff)');
      li.style.background = 'var(--bg-alt, rgba(74,144,226,0.15))';
    });
  });
  // If a highlight was requested (e.g., user clicked a node that's in the list), scroll it into view
  if (highlightNodeId) {
    const target = detail.querySelector(`.contributor-item[data-node-id="${highlightNodeId}"]`);
    if (target) target.scrollIntoView({ behavior: 'smooth', block: 'center' });
  }
}

// ─────────────────── node-explain detail pane ───────────────────
// Legacy single-node view (kept for fallback when no prompt is selected).

function renderNodeExplain(detail, clickedNode) {
  // Loading state first — fetch is async, want instant feedback
  detail.innerHTML = `<div class="node-info">
    <span class="tag ${esc(clickedNode.type)}">${esc(clickedNode.type)}</span>
    <span class="full">${esc(clickedNode.full)}</span>
    <div class="meta" style="color:var(--text-dim); font-style:italic">
      ${esc(t("explain.loading"))}
    </div>
  </div>`;

  // Figure out which prompt we're explaining against. If the user clicked
  // the currently-selected prompt itself, show prompt-specific info.
  const selected = graphState.promptNodes[graphState.selectedIdx];
  const promptId = selected?.id;
  if (!promptId) {
    detail.innerHTML = `<div class="node-info">
      <span class="tag ${esc(clickedNode.type)}">${esc(clickedNode.type)}</span>
      <span class="full">${esc(clickedNode.full)}</span>
      <div class="meta">${esc(t("explain.no_prompt"))}</div>
    </div>`;
    return;
  }

  fetch(`/api/node-explain?node_id=${encodeURIComponent(clickedNode.id)}&prompt_id=${encodeURIComponent(promptId)}`)
    .then(r => r.json())
    .then(data => detail.innerHTML = buildExplainHTML(data, clickedNode))
    .catch(err => {
      console.error("node-explain fetch failed", err);
      detail.innerHTML = `<div class="node-info">
        <span class="tag ${esc(clickedNode.type)}">${esc(clickedNode.type)}</span>
        <span class="full">${esc(clickedNode.full)}</span>
        <div class="meta">${esc(t("explain.load_fail"))}</div>
      </div>`;
    });
}

function buildExplainHTML(data, clickedNode) {
  if (data.error) {
    return `<div class="node-info">
      <span class="tag ${esc(clickedNode.type)}">${esc(clickedNode.type)}</span>
      <span class="full">${esc(clickedNode.full)}</span>
      <div class="meta">Error: ${esc(data.error)}</div>
    </div>`;
  }

  // ── Channel badge ─────────────────────────────────────────────────────────
  // Shows the actual retrieval mechanism used for this node type
  const channelColors = {
    decision: "#3b6a8a", doc: "#7a5c8a", chatmem: "#2e8b7a",
    code: "#6b8c3a", prompt: "#8a8278", current: "#cc785c",
  };
  const channelBg = channelColors[data.node_type] || "#8a8278";
  const channelBadge = data.channel
    ? `<span style="display:inline-block; padding:2px 8px; border-radius:10px; font-size:0.75em; font-family:var(--mono,monospace); background:${channelBg}22; color:${channelBg}; border:1px solid ${channelBg}55; margin-left:6px; vertical-align:middle">${esc(data.channel)}</span>`
    : "";

  // ── Formula display ────────────────────────────────────────────────────────
  let formulaSection = "";
  if (data.retrieval_formula) {
    formulaSection = `<div style="padding:5px 10px; margin:6px 0 8px; background:var(--bg-deep,#f0ede7); border-radius:4px; font-family:var(--mono,monospace); font-size:0.78em; color:var(--text-dim); letter-spacing:0.01em">
      ${esc(data.retrieval_formula)}
    </div>`;
  }

  // ── CM hybrid score decomposition ─────────────────────────────────────────
  let cmScoreSection = "";
  if (data.cm_scores) {
    const cs = data.cm_scores;
    const hasVec = cs.vec_available && cs.cosine_sim !== null;
    const hasBM25 = cs.bm25_rank !== null;
    const alpha = cs.alpha ?? 0.5;

    const cosinePct = hasVec ? Math.round(cs.cosine_sim * 100) : null;
    const bm25Pct   = hasBM25 ? Math.round(cs.bm25_rank_norm * 100) : null;
    const hybridPct = cs.hybrid !== null ? Math.round(cs.hybrid * 100) : null;

    const vecRow = hasVec
      ? `<tr>
          <td style="padding:3px 8px; color:var(--text-dim); font-size:0.85em">cosine_sim</td>
          <td style="padding:3px 8px; font-family:var(--mono,monospace)"><b>${cs.cosine_sim.toFixed(4)}</b></td>
          <td style="padding:3px 8px">
            <div style="width:${cosinePct}%; height:6px; background:#2e8b7a; border-radius:3px; min-width:2px"></div>
          </td>
          <td style="padding:3px 8px; font-size:0.8em; color:var(--text-dim)">× α=${alpha}</td>
        </tr>`
      : `<tr><td colspan="4" style="padding:3px 8px; color:var(--text-dim); font-style:italic; font-size:0.85em">cosine: vec-daemon unavailable</td></tr>`;

    const bm25Row = hasBM25
      ? `<tr>
          <td style="padding:3px 8px; color:var(--text-dim); font-size:0.85em">BM25_rank_norm</td>
          <td style="padding:3px 8px; font-family:var(--mono,monospace)"><b>${cs.bm25_rank_norm.toFixed(4)}</b></td>
          <td style="padding:3px 8px">
            <div style="width:${bm25Pct}%; height:6px; background:#a34b2c; border-radius:3px; min-width:2px"></div>
          </td>
          <td style="padding:3px 8px; font-size:0.8em; color:var(--text-dim)">rank ${cs.bm25_rank}/${cs.fts5_total} × (1-α)</td>
        </tr>`
      : `<tr><td colspan="4" style="padding:3px 8px; color:var(--text-dim); font-style:italic; font-size:0.85em">BM25: item not in FTS5 results for this prompt</td></tr>`;

    const hybridRow = hybridPct !== null
      ? `<tr style="border-top:1px solid var(--panel-border)">
          <td style="padding:4px 8px; font-weight:600">hybrid score</td>
          <td style="padding:4px 8px; font-family:var(--mono,monospace); font-weight:700; color:var(--accent-deep)">${cs.hybrid.toFixed(4)}</td>
          <td style="padding:4px 8px">
            <div style="width:${hybridPct}%; height:8px; background:var(--accent); border-radius:3px; min-width:2px"></div>
          </td>
          <td style="padding:4px 8px; font-size:0.8em; color:var(--text-dim)">α·cos + (1-α)·bm25</td>
        </tr>`
      : "";

    cmScoreSection = `<div style="margin-bottom:10px; background:var(--bg-deep,#f0ede7); border-radius:5px; padding:8px 10px">
      <div style="font-size:0.78em; letter-spacing:0.4px; text-transform:uppercase; color:var(--text-dim); margin-bottom:6px">CM hybrid scoring</div>
      <table style="width:100%; border-collapse:collapse; font-size:0.88em">
        <tbody>${vecRow}${bm25Row}${hybridRow}</tbody>
      </table>
    </div>`;
  }

  // Header
  const metaParts = [];
  if (data.node_date) metaParts.push(`date: ${esc(data.node_date)}`);
  if (typeof data.utility_heat === "number") {
    metaParts.push(`heat: <b style="color:var(--accent-deep)">${data.utility_heat.toFixed(2)}</b>`);
  }

  // SUMMARY section — one-line natural-language explanation (new in Option C)
  let summarySection = "";
  if (data.summary) {
    summarySection = `<div class="explain-summary" style="padding:8px 10px; margin-bottom:10px; background:var(--bg-alt); border-left:3px solid var(--accent); border-radius:4px; font-style:italic; color:var(--text)">
      ${esc(data.summary)}
    </div>`;
  }

  // INJECTION section — the exact text block injected into Claude's context
  // and whether it actually got referenced in the response (2026-04-24)
  let injectionSection = "";
  if (data.injection_preview && data.depth === 1) {
    const blockLabel = data.injection_block ? `<span class="tag ${esc(data.node_type)}">${esc(data.injection_block)}</span>` : "";
    // Status chip maps referenced_in_response → colored label
    let statusChip = "";
    const refStatusMap = {
      yes_text: { key: "explain.ref_yes_text", color: "#4caf50" },
      yes_tool: { key: "explain.ref_yes_tool", color: "#4caf50" },
      yes_both: { key: "explain.ref_yes_both", color: "#2e7d32" },
      no:       { key: "explain.ref_no",       color: "#d32f2f" },
      pending:  { key: "explain.ref_pending",  color: "#ff9800" },
      unknown:  { key: "explain.ref_unknown",  color: "var(--text-dim)" },
    };
    const status = refStatusMap[data.referenced_in_response] || refStatusMap.unknown;
    statusChip = `<span style="color:${status.color}; font-weight:600">${esc(t(status.key))}</span>`;

    injectionSection = `<div class="explain-injection" style="padding:8px 10px; margin-bottom:10px; background:var(--bg-code, rgba(0,0,0,0.03)); border-left:3px solid var(--accent-deep, #4a90e2); border-radius:4px">
      <div class="explain-head" style="margin-bottom:4px">
        ${esc(t("explain.injected_as"))} ${blockLabel}
      </div>
      <pre style="margin:4px 0; padding:6px 8px; background:var(--bg, #fff); border-radius:3px; font-family:monospace; font-size:0.85em; white-space:pre-wrap; overflow-x:auto">${esc(data.injection_preview)}</pre>
      <div class="explain-row" style="margin-top:6px; font-size:0.9em">
        <span class="label">${esc(t("explain.ref_status"))}:</span> ${statusChip}
      </div>
    </div>`;
  }

  // WHY section — depth + rank + BM25 + matched tokens
  let whySection = "";
  if (data.depth === 0) {
    whySection = `<div class="explain-why">
      <div class="explain-head">${esc(t("explain.is_prompt"))}</div>
      <div class="explain-body">${esc(t("explain.click_hint"))}</div>
    </div>`;
  } else if (data.depth == null) {
    whySection = `<div class="explain-why">
      <div class="explain-head">${esc(t("explain.not_connected"))}</div>
      <div class="explain-body">${esc(t("explain.no_path"))}</div>
    </div>`;
  } else if (data.depth === 1) {
    const rankTxt = (data.rank_in_cone && data.total_in_cone)
      ? `<b>rank ${data.rank_in_cone} / ${data.total_in_cone}</b> ${esc(t("explain.in_cone"))}`
      : esc(t("explain.direct"));
    const matchTxt = data.matched_tokens.length
      ? data.matched_tokens.map(tok => `<span class="match-tok">${esc(tok)}</span>`).join(" ")
      : `<span style="color:var(--text-dim); font-style:italic">${esc(t("explain.no_match"))}</span>`;
    whySection = `<div class="explain-why">
      <div class="explain-head">${esc(t("explain.depth1"))}</div>
      <div class="explain-row"><span class="label">${esc(t("explain.rank"))}</span> ${rankTxt}</div>
      <div class="explain-row"><span class="label">${esc(t("explain.bm25"))}</span> ${data.bm25_score.toFixed(3)}</div>
      <div class="explain-row"><span class="label">${esc(t("explain.matched"))}</span> ${matchTxt}</div>
    </div>`;
  } else {
    // Depth 2+: render the parent chain
    const chainHTML = data.parent_chain.map((step, i) => {
      const isLast = i === data.parent_chain.length - 1;
      const arrow = i === 0 ? "" : ` <span class="chain-arrow">→ (${esc(step.via_edge_type || "?")})</span>`;
      const cls = i === 0 ? "chain-prompt"
                : isLast ? "chain-target"
                : "chain-mid";
      return `<div class="chain-step ${cls}">
        ${arrow}
        <span class="chain-label">${esc(step.label || step.node_id)}</span>
      </div>`;
    }).join("");
    const typeExplain = data.arrival_edge_type === "topic"  ? t("explain.topic_conn")
                      : data.arrival_edge_type === "temporal" ? t("explain.temporal_conn")
                      : t("explain.recall_conn");
    whySection = `<div class="explain-why">
      <div class="explain-head">depth ${data.depth} ${esc(t("explain.depth_n"))}</div>
      <div class="explain-chain">${chainHTML}</div>
      <div class="explain-row" style="margin-top:6px"><span class="label">${esc(t("explain.arrival"))}</span> ${esc(typeExplain)}</div>
    </div>`;
  }

  // PROMPT section — FULL text with matched tokens highlighted + project + timestamp
  let promptSection = "";
  if (data.prompt_text && data.depth !== 0) {
    const matchSet = new Set(data.matched_tokens.map(t => t.toLowerCase()));
    const highlighted = data.prompt_text.split(/(\s+)/).map(w => {
      const clean = w.toLowerCase().replace(/[^\w-]/g, "");
      if (matchSet.has(clean)) return `<span class="match-tok">${esc(w)}</span>`;
      return esc(w);
    }).join("");
    // Metadata line: project + timestamp (who + when)
    const metaBits = [];
    if (data.prompt_project) {
      metaBits.push(`<span class="label">${esc(t("explain.prompt_from"))}</span> <b>${esc(data.prompt_project)}</b>`);
    }
    if (data.prompt_ts) {
      // Format ISO → "2026-04-24 13:42"
      let tsDisplay = data.prompt_ts;
      try {
        const d = new Date(data.prompt_ts);
        if (!isNaN(d)) {
          tsDisplay = d.toISOString().replace("T", " ").slice(0, 16);
        }
      } catch (e) {}
      metaBits.push(`<span class="label">${esc(t("explain.prompt_at"))}</span> ${esc(tsDisplay)}`);
    }
    const metaRow = metaBits.length
      ? `<div class="meta" style="font-size:0.85em; color:var(--text-dim); margin-bottom:4px">${metaBits.join(" · ")}</div>`
      : "";
    promptSection = `<div class="explain-prompt">
      <div class="explain-head">${esc(t("explain.selected_prompt"))}</div>
      ${metaRow}
      <div class="explain-body prompt-text" style="white-space:pre-wrap; max-height:260px; overflow-y:auto">${highlighted}</div>
    </div>`;
  }

  // UTILITY section
  let utilitySection = "";
  if (data.node_type === "decision" || data.node_type === "doc") {
    const blockName = data.node_type === "decision" ? "g1" : "g2_docs";
    const refTxt = data.utility_refs_7d > 0
      ? `<b>${data.utility_refs_7d}</b> ${esc(t("explain.util_refs"))} ${blockName} ${esc(t("explain.util_days"))}`
      : `<span style="color:var(--text-dim)">${esc(t("explain.no_refs"))}</span>`;
    utilitySection = `<div class="explain-util">
      <div class="explain-head">${esc(t("explain.utility_hist"))}</div>
      <div class="explain-body">${refTxt}</div>
    </div>`;
  }

  // BREAKDOWN section — per-token BM25 contribution (Option C)
  let breakdownSection = "";
  if (data.token_contributions && data.token_contributions.length > 0 && data.depth === 1) {
    const rows = data.token_contributions.slice(0, 8).map(tc => `
      <tr>
        <td><span class="match-tok">${esc(tc.token)}</span></td>
        <td style="text-align:right; font-family:var(--mono,monospace)">${tc.tf}</td>
        <td style="text-align:right; font-family:var(--mono,monospace)">${tc.idf !== null ? tc.idf.toFixed(2) : "—"}</td>
        <td style="padding-left:6px; min-width:80px">
          <div style="display:flex; align-items:center; gap:5px">
            <div style="width:${tc.contribution_pct}%; max-width:60px; height:6px; background:${data.node_type==='decision'?'#3b6a8a':'#7a5c8a'}; border-radius:2px; min-width:2px"></div>
            <b style="font-family:var(--mono,monospace)">${tc.contribution_pct}%</b>
          </div>
        </td>
      </tr>`).join("");
    breakdownSection = `<div class="explain-breakdown">
      <div class="explain-head">${esc(t("explain.breakdown"))}</div>
      <table style="width:100%; font-size:0.85em; border-collapse:collapse; margin-top:4px">
        <thead><tr style="color:var(--text-dim); text-align:left; border-bottom:1px solid var(--border)">
          <th>${esc(t("explain.col_token"))}</th>
          <th style="text-align:right">${esc(t("explain.col_tf"))}</th>
          <th style="text-align:right">${esc(t("explain.col_idf"))}</th>
          <th style="text-align:right">${esc(t("explain.col_contrib"))}</th>
        </tr></thead>
        <tbody>${rows}</tbody>
      </table>
    </div>`;
  }

  // COMPETITORS section — top 2 ranked nodes in the same cone (Option C)
  let competitorsSection = "";
  if (data.top_competitors && data.top_competitors.length > 0 && data.depth === 1) {
    const compRows = data.top_competitors.map(c => `
      <div class="explain-row" style="font-size:0.9em">
        <span class="label">#${c.rank}</span>
        <span style="color:var(--text-dim)">bm25 ${c.bm25_score}</span>
        <span style="margin-left:6px">${esc(c.label)}</span>
      </div>`).join("");
    competitorsSection = `<div class="explain-competitors">
      <div class="explain-head">${esc(t("explain.competitors"))}</div>
      ${compRows}
    </div>`;
  }

  // MISSED section — prompt tokens NOT in this node (Option C)
  let missedSection = "";
  if (data.depth === 1 && data.missed_tokens !== undefined) {
    if (data.missed_tokens.length > 0) {
      const missedChips = data.missed_tokens.map(tok =>
        `<span class="match-tok" style="opacity:0.5; text-decoration:line-through">${esc(tok)}</span>`
      ).join(" ");
      missedSection = `<div class="explain-missed">
        <div class="explain-head">${esc(t("explain.missed"))}</div>
        <div class="explain-body">${missedChips}</div>
      </div>`;
    } else if (data.matched_tokens.length > 0) {
      missedSection = `<div class="explain-missed">
        <div class="explain-head" style="color:var(--text-dim); font-style:italic">
          ${esc(t("explain.no_missed"))}
        </div>
      </div>`;
    }
  }

  // CONTENT preview with symmetric match highlighting (Option C — was plain text before)
  let contentSection = "";
  if (data.preview) {
    const matchSet = new Set((data.matched_tokens || []).map(t => t.toLowerCase()));
    const highlightedPreview = data.preview.split(/(\s+)/).map(w => {
      const clean = w.toLowerCase().replace(/[^\w-]/g, "");
      if (matchSet.has(clean)) return `<span class="match-tok">${esc(w)}</span>`;
      return esc(w);
    }).join("");
    contentSection = `<div class="explain-content">
      <div class="explain-head">${esc(t("explain.content"))}</div>
      <div class="explain-body content-preview">${highlightedPreview}</div>
    </div>`;
  }

  // ④ FULL CTX CONTEXT — all blocks that fired for this prompt (CM / G1 / G2-DOCS / G2-PREFETCH / G2-GREP)
  // Shows every retrieval channel, not just the BM25-ranked node. The block that
  // surfaced THIS node is bolded; other channels show item counts + latency.
  let allBlocksSection = "";
  if (data.retrieval_blocks) {
    const rb = data.retrieval_blocks;
    const thisBlockKey = data.node_type === "decision" ? "g1_decisions"
                       : data.node_type === "doc"      ? "g2_docs"
                       : null;
    const blockDefs = [
      ["g1_decisions", "G1",          "recent decisions",                 "g1_decisions"],
      ["g2_docs",      "G2-DOCS",     "research docs",                    "g2_docs"],
      ["g2_prefetch",  "G2-PREFETCH", "codebase functions",               "g2_prefetch"],
      ["g2_grep",      "G2-GREP",     "hook grep",                        "g2_grep"],
    ];
    const rows = [];
    if (rb.cm_mode) {
      rows.push(`<tr>
        <td style="padding:2px 6px; font-weight:600; color:var(--accent-deep)">CM</td>
        <td style="padding:2px 6px; color:var(--text-dim)">chat memory</td>
        <td style="padding:2px 6px; font-style:italic">${esc(rb.cm_mode)}</td>
        <td style="padding:2px 6px; color:var(--text-dim)">—</td>
      </tr>`);
    }
    for (const [key, label, desc, logKey] of blockDefs) {
      const blk = rb[logKey];
      if (!blk) continue;
      const isThis = logKey === thisBlockKey;
      const highlight = isThis ? 'font-weight:700; color:var(--accent-deep)' : 'color:var(--text-soft)';
      const badge = isThis ? ` <span style="background:var(--accent-soft,#f5e6de); color:var(--accent-deep); font-size:0.75em; padding:1px 5px; border-radius:10px; margin-left:4px">this node</span>` : "";
      rows.push(`<tr>
        <td style="padding:2px 6px; ${highlight}">${esc(label)}${badge}</td>
        <td style="padding:2px 6px; color:var(--text-dim); font-size:0.85em">${esc(desc)}</td>
        <td style="padding:2px 6px; font-weight:${isThis ? '700' : '400'}">${blk.count} items</td>
        <td style="padding:2px 6px; color:var(--text-dim); font-size:0.85em">${blk.duration_ms}ms</td>
      </tr>`);
    }
    if (rows.length) {
      allBlocksSection = `<div class="explain-all-blocks" style="margin-bottom:10px; background:var(--bg-deep,#f0ede7); border-radius:5px; padding:8px 10px">
        <div class="explain-head" style="margin-bottom:6px; font-size:0.8em; letter-spacing:0.4px; text-transform:uppercase; color:var(--text-dim)">All CTX blocks fired</div>
        <table style="width:100%; font-size:0.88em; border-collapse:collapse">
          <thead><tr style="color:var(--text-dim); font-size:0.8em; border-bottom:1px solid var(--panel-border)">
            <th style="text-align:left; padding:2px 6px">Block</th>
            <th style="text-align:left; padding:2px 6px">Type</th>
            <th style="text-align:left; padding:2px 6px">Retrieved</th>
            <th style="text-align:left; padding:2px 6px">Latency</th>
          </tr></thead>
          <tbody>${rows.join("")}</tbody>
        </table>
        <div style="font-size:0.78em; color:var(--text-dim); margin-top:5px; font-style:italic">
          Bold = block that surfaced this node. G2-PREFETCH / G2-GREP items visible in Samples panel.
        </div>
      </div>`;
    }
  }

  // Layout: 1. FROM → 2. ALL CTX BLOCKS → 3. WHY (this node) → 4. WHAT USED → details
  const detailsBlock = (breakdownSection || competitorsSection || missedSection || contentSection || utilitySection)
    ? `<details class="explain-details" style="margin-top:12px">
         <summary style="cursor:pointer; color:var(--text-dim); font-size:0.9em; padding:4px 0">
           ${esc(data.lang === 'ko' ? '세부 근거 (점수 분해·경쟁 노드·미매칭 토큰·원문·이력)' : 'detailed evidence (breakdown · competitors · missed · content · history)')}
         </summary>
         <div style="margin-top:8px">
           ${breakdownSection}
           ${competitorsSection}
           ${missedSection}
           ${contentSection}
           ${utilitySection}
         </div>
       </details>`
    : "";

  return `
    <div class="node-info">
      <span class="tag ${esc(data.node_type)}">${esc(data.node_type)}</span>${channelBadge}
      <span class="full">${esc(data.node_label)}</span>
      ${metaParts.length ? `<div class="meta">${metaParts.join(" · ")}</div>` : ""}
    </div>
    ${formulaSection}
    <div class="explain-section-label" style="font-size:0.75em; color:var(--accent-deep, #4a90e2); letter-spacing:0.5px; text-transform:uppercase; margin-top:10px; margin-bottom:2px">① from — selected prompt</div>
    ${promptSection}
    <div class="explain-section-label" style="font-size:0.75em; color:var(--accent-deep, #4a90e2); letter-spacing:0.5px; text-transform:uppercase; margin-top:10px; margin-bottom:2px">② all ctx blocks — everything retrieved for this prompt</div>
    ${allBlocksSection}
    <div class="explain-section-label" style="font-size:0.75em; color:var(--accent-deep, #4a90e2); letter-spacing:0.5px; text-transform:uppercase; margin-top:10px; margin-bottom:2px">③ why — how this node matched</div>
    ${summarySection}
    ${cmScoreSection}
    ${whySection}
    <div class="explain-section-label" style="font-size:0.75em; color:var(--accent-deep, #4a90e2); letter-spacing:0.5px; text-transform:uppercase; margin-top:10px; margin-bottom:2px">④ what used — memory injected into context</div>
    ${injectionSection}
    ${detailsBlock}
  `;
}

function refreshGraph() {
  fetch("/api/graph").then(r => r.json()).then(renderGraph).catch(console.error);
}

// ───────────────────────── prompt navigation ─────────────────────────
// Step through past prompts to inspect each one's retrieval cone. The
// selected prompt becomes the visual anchor — its edges pulse, other
// prompts fade. This is the "explore past retrievals" affordance.

function initPromptNavigation() {
  const nav = $("graph-nav");
  const label = $("prompt-nav-label");
  const prev = $("prompt-prev");
  const next = $("prompt-next");
  const toggle = $("signal-toggle");
  if (!nav || !label || !prev || !next || !toggle) return;

  const prompts = graphState.promptNodes;
  if (prompts.length === 0) {
    nav.style.display = "none";
    return;
  }
  nav.style.display = "flex";

  // Clamp + render label
  if (graphState.selectedIdx >= prompts.length) graphState.selectedIdx = 0;
  updateNavLabel();

  // One-time event binding (avoid re-binding on every refresh)
  if (!prev.dataset.wired) {
    prev.addEventListener("click", () => stepPrompt(+1));   // "previous" = older = higher idx
    next.addEventListener("click", () => stepPrompt(-1));   // "next" = newer = lower idx
    toggle.addEventListener("change", () => {
      graphState.signalOn = toggle.checked;
      if (graphState.signalOn) startSignalAnimation();
      else stopSignalAnimation();
    });
    prev.dataset.wired = "1";
  }

  applyPromptSelection();

  // Auto-render contributors list for current prompt on initial load
  const p = graphState.promptNodes[graphState.selectedIdx];
  const detail = document.getElementById('graph-detail');
  if (p && detail) {
    detail.classList.remove('empty');
    renderContributorsList(detail, p.id);
  }
}

function updateNavLabel() {
  const prompts = graphState.promptNodes;
  const label = $("prompt-nav-label");
  const prev = $("prompt-prev");
  const next = $("prompt-next");
  if (!label || !prompts.length) return;
  const p = prompts[graphState.selectedIdx];
  const timeStr = p.ts ? fmtTs(p.ts) : "—";
  label.innerHTML = `<span style="color:var(--accent-deep); font-weight:500">prompt ${graphState.selectedIdx + 1}/${prompts.length}</span> · <span style="color:var(--text-dim)">${esc(timeStr)}</span> · <span style="color:var(--text)">${esc((p.full || p.label || "").slice(0, 60))}</span>`;
  // Button disable state — at idx 0 we can't go newer; at last idx we can't go older.
  if (prev) prev.disabled = (graphState.selectedIdx >= prompts.length - 1);
  if (next) next.disabled = (graphState.selectedIdx <= 0);
}

function stepPrompt(delta) {
  const prompts = graphState.promptNodes;
  if (!prompts.length) return;
  const newIdx = graphState.selectedIdx + delta;
  if (newIdx < 0 || newIdx >= prompts.length) return;
  graphState.selectedIdx = newIdx;
  updateNavLabel();
  applyPromptSelection();
  // Refresh the contributors list for the newly-selected prompt
  const detail = document.getElementById('graph-detail');
  const p = prompts[newIdx];
  if (detail && p) {
    detail.classList.remove('empty');
    renderContributorsList(detail, p.id);
  }
}

// Iter 9 trust-floor: compute gated heat for a decision/doc node given
// the currently-selected prompt. This is the same sigmoid gate the server
// applied for the initial current-prompt render, but re-applied per node
// as the user navigates prompts with ◀▶.
function _gatedHeat(nodeId, rawHeat, selectedPromptId) {
  const cone = graphState.promptBM25?.[selectedPromptId] || {};
  const hasCone = Object.keys(cone).length > 0;
  if (!hasCone) {
    return rawHeat * 0.15;   // uniform muting — prompt has no meaningful retrieval
  }
  const pbm25 = cone[nodeId] || 0;
  const gate = 1 / (1 + Math.exp(-5 * (pbm25 - 0.1)));
  return rawHeat * gate;
}

// Public: does the selected prompt have ANY retrieval cone? UI uses this
// to render the "no meaningful retrieval" empty state.
function _selectedPromptHasCone() {
  const p = graphState.promptNodes[graphState.selectedIdx];
  if (!p) return false;
  const cone = graphState.promptBM25?.[p.id] || {};
  return Object.keys(cone).length > 0;
}

function applyPromptSelection() {
  if (!graphNetwork) return;
  const prompts = graphState.promptNodes;
  if (!prompts.length) return;
  const selected = prompts[graphState.selectedIdx];
  const selectedId = selected.id;

  // Restyle nodes: selected prompt → "current" coral, others → muted "prompt"
  // ALSO: re-apply heat gate per selected prompt. Uses raw heat from server
  // (utility_heat_raw) + prompt_bm25 map to compute gated display heat.
  const nodeUpdates = [];
  prompts.forEach(p => {
    const baseStyle = nodeStyle(p.id === selectedId ? "current" : "prompt", 0);
    nodeUpdates.push(Object.assign({ id: p.id }, baseStyle,
      p.id === selectedId ? { label: p.label } : { label: "" }));
  });
  // Re-gate every decision/doc node's heat for the newly selected prompt
  graphState.rawNodes.forEach(n => {
    if (n.type !== "decision" && n.type !== "doc") return;
    const rawHeat = n.utility_heat_raw ?? n.utility_heat ?? 0;
    const gatedHeat = _gatedHeat(n.id, rawHeat, selectedId);
    // Mutate the cached graphNodeById so nodeStyle + tooltips see fresh heat
    if (graphNodeById[n.id]) graphNodeById[n.id].utility_heat = gatedHeat;
    const style = nodeStyle(n.type, gatedHeat);
    nodeUpdates.push(Object.assign({ id: n.id }, style));
  });
  graphNetwork.body.data.nodes.update(nodeUpdates);

  // Restyle edges: the SELECTED prompt's recall edges become the foreground
  // retrieval cone (coral, thick, shadowed). Other prompts' recall edges fade.
  // Temporal/topic edges left alone.
  const edgeUpdates = graphState.rawEdges.map((e, i) => {
    if (e.type !== "recall-d" && e.type !== "recall-w") return null;
    const isSelected = (e.from === selectedId);
    const style = edgeStyle(e.type, e.weight || 1, isSelected);
    return Object.assign({ id: `e${i}`, from: e.from, to: e.to }, style,
      { _selectedPrompt: isSelected });   // marker for signal-animation filter
  }).filter(Boolean);
  graphNetwork.body.data.edges.update(edgeUpdates);

  // Pan camera to the selected prompt node — NO zoom change (preserves user's
  // current scale), short animation so nav feels instant not laggy.
  try {
    const pos = graphNetwork.getPositions([selectedId])[selectedId];
    if (pos) {
      graphNetwork.moveTo({
        position: { x: pos.x, y: pos.y },
        animation: { duration: 150, easingFunction: "linear" },
        // NB: no `scale` key → zoom is untouched
      });
    }
  } catch (_) { /* moveTo fails if network not stabilized; fine to skip */ }

  // Restart the particle overlay so it tracks the new selection's edges
  startSignalAnimation();

  // Iter 9: empty-cascade UI state — when selected prompt has no retrieval
  // cone, render an explicit "nothing to surface" message in the detail
  // pane instead of leaving stale click state from a previous node.
  const detail = $("graph-detail");
  if (detail) {
    if (!_selectedPromptHasCone()) {
      detail.classList.remove("empty");
      detail.innerHTML = `<div class="node-info">
        <span class="tag" style="background:var(--panel-soft); color:var(--text-dim)">no retrieval</span>
        <span class="full">This prompt has no meaningful retrieval cone</span>
        <div class="meta" style="margin-top:8px; line-height:1.5">
          The prompt's distinctive tokens didn't clear CTX's BM25 relevance
          threshold against any decision or doc. Common causes:
          <ul style="margin:4px 0 0 20px; padding:0; color:var(--text-dim); font-size:11px">
            <li>URL-only or short prompts</li>
            <li>Prompt content unrelated to the indexed corpus</li>
            <li>Tokenizer mismatch (e.g., Unicode / BOM)</li>
          </ul>
          <span style="color:var(--text-dim); font-style:italic; display:inline-block; margin-top:6px">
            Nothing fabricated — CTX is honestly saying "I have nothing grounded here."
          </span>
        </div>
      </div>`;
    } else {
      // Clear stale detail from a prior prompt; let the user click to repopulate
      detail.classList.add("empty");
      detail.innerHTML = "";
    }
  }
}

// ───────────────────────── signal animation ──────────────────────────
// Traveling-particle effect on the selected prompt's retrieval edges.
// Draws bright coral dots that TRAVEL along each edge from prompt → target,
// like electrons flowing through a wire. Uses a canvas overlay stacked on
// top of vis-network's own canvas so we don't fight its rendering.

let signalOverlay = null;   // <canvas> element stacked over #graph-canvas
let signalCtx = null;

function ensureSignalOverlay() {
  const host = $("graph-canvas");
  if (!host) return null;
  if (signalOverlay && signalOverlay.isConnected) return signalOverlay;
  signalOverlay = document.createElement("canvas");
  signalOverlay.id = "signal-overlay";
  signalOverlay.style.cssText =
    "position:absolute; top:0; left:0; width:100%; height:100%; pointer-events:none; z-index:2;";
  host.appendChild(signalOverlay);
  signalCtx = signalOverlay.getContext("2d");
  // Size sync — rAF reads canvas size each frame to handle panel resize
  return signalOverlay;
}

// Build BFS cascade from the selected prompt across the graph: depth-1 edges
// are direct prompt→target retrievals; depth-2+ edges trace topic/temporal
// connections out from those targets. Cap total edges to keep the overlay
// readable and CPU cheap.
//
// Iter 9 trust-floor — two gates added:
//   (1) If root prompt has NO recall edges (URL/empty prompt) → return []
//       immediately. No fake cascades through topic/temporal clusters.
//   (2) Before enqueuing a topic/temporal neighbor, require that the target
//       has a non-zero prompt_bm25 score OR is a direct recall target. This
//       kills the "depth-3 chain to unrelated doc" trust bug.
function _buildCascadeEdges(rawEdges, rootId, maxDepth = 3, maxTotal = 40) {
  // Gate 1: no recall cone → no cascade
  const cone = graphState.promptBM25?.[rootId] || {};
  const hasCone = Object.keys(cone).length > 0;
  if (!hasCone) return [];

  const adj = new Map();
  const put = (k, v) => { if (!adj.has(k)) adj.set(k, []); adj.get(k).push(v); };
  rawEdges.forEach((e, i) => {
    const tagged = { ...e, _id: `e${i}` };
    if (e.type === "recall-d" || e.type === "recall-w" || e.type === "recall-cm" || e.type === "recall-pre") {
      put(e.from, { target: e.to, edge: tagged });
    } else if (e.type === "topic" || e.type === "temporal") {
      put(e.from, { target: e.to, edge: tagged });
      put(e.to,   { target: e.from, edge: tagged });   // undirected for expansion
    }
  });
  const visited = new Set([rootId]);
  const queue = [{ id: rootId, depth: 0 }];
  const out = [];
  while (queue.length && out.length < maxTotal) {
    const { id, depth } = queue.shift();
    if (depth >= maxDepth) continue;
    const neighbors = (adj.get(id) || []).slice(0, depth === 0 ? 99 : 4);
    for (const { target, edge } of neighbors) {
      if (visited.has(target)) continue;
      // Gate 2 (relaxed 2026-04-24): only block depth-1 topic/temporal edges
      // originating AT the root prompt — those would cross over to completely
      // unrelated clusters. For depth ≥ 2, trust the BFS path: the target was
      // reached via a chain that ALREADY passed through a BM25-matched node,
      // so topic/temporal neighbors of those nodes are semantically linked.
      if ((edge.type === "topic" || edge.type === "temporal")
          && depth === 0
          && (cone[target] || 0) < 0.05) {
        continue;
      }
      visited.add(target);
      out.push({ _id: edge._id, from: id, to: target, type: edge.type,
                 depth: depth + 1 });
      queue.push({ id: target, depth: depth + 1 });
      if (out.length >= maxTotal) break;
    }
  }
  return out;
}

function startSignalAnimation() {
  stopSignalAnimation();
  if (!graphState.signalOn || !graphNetwork) return;
  const overlay = ensureSignalOverlay();
  if (!overlay) return;

  const selected = graphState.promptNodes[graphState.selectedIdx];
  if (!selected) return;
  const selectedId = selected.id;

  // BFS cascade: depth 1 = direct retrieval, depth 2+ = neighbors via topic/temporal
  const travelEdges = _buildCascadeEdges(graphState.rawEdges, selectedId, 3, 40);
  if (!travelEdges.length) return;

  // Phase offset per edge so pulses in the same depth don't fire in unison
  travelEdges.forEach((e, i) => { e._phase = (i * 0.17) % 1; });

  const t0 = performance.now();
  const PERIOD_MS = 1400;     // one full traversal per edge takes 1.4s

  const step = (tNow) => {
    if (!graphState.signalOn) return;
    // Sync canvas backing size to displayed size (handles dashboard resize)
    const parent = overlay.parentElement;
    if (overlay.width !== parent.clientWidth || overlay.height !== parent.clientHeight) {
      overlay.width = parent.clientWidth;
      overlay.height = parent.clientHeight;
    }
    signalCtx.clearRect(0, 0, overlay.width, overlay.height);

    const elapsed = tNow - t0;
    for (const e of travelEdges) {
      const posFrom = graphNetwork.getPositions([e.from])[e.from];
      const posTo = graphNetwork.getPositions([e.to])[e.to];
      if (!posFrom || !posTo) continue;
      const a = graphNetwork.canvasToDOM(posFrom);
      const b = graphNetwork.canvasToDOM(posTo);

      // Depth-based time offset: depth-2 particles start PERIOD_MS later than
      // depth-1, depth-3 another PERIOD_MS later — so the pulse visibly hops
      // hop-by-hop outward. Modulo by max-cascade-time keeps the loop stable.
      const startDelay = (e.depth - 1) * PERIOD_MS;
      const cycleMs = PERIOD_MS * 3;   // full cascade cycle
      const localMs = ((elapsed + e._phase * PERIOD_MS) % cycleMs) - startDelay;
      if (localMs < 0 || localMs > PERIOD_MS) continue;   // particle not yet on this edge (or already past)
      const tRaw = localMs / PERIOD_MS;

      // Depth-based styling — kept visible through depth 3.
      // depth 1 → width 1.0, alpha 1.0   depth 2 → 0.80, 0.82   depth 3 → 0.66, 0.70
      // Previously 0.50/0.48 at depth 3 was nearly invisible; boosted for clarity.
      const widthFactor = Math.max(0.66, 1.0 - (e.depth - 1) * 0.18);
      const alphaFactor = Math.max(0.70, 1.0 - (e.depth - 1) * 0.16);

      // Edge-type color — coral for BM25 recall, teal for CM, olive for codebase
      const [glowRgb, coreRgb] =
        e.type === "recall-cm"  ? ["46,139,122",  "58,170,151"] :
        e.type === "recall-pre" ? ["107,140,58",  "134,168,80"] :
                                  ["204,120,92",  "244,156,120"];
      // 3-dot trailing comet at depth-scaled size
      for (let k = 0; k < 3; k++) {
        const tk = tRaw - k * 0.05;
        if (tk < 0 || tk > 1) continue;
        const x = a.x + (b.x - a.x) * tk;
        const y = a.y + (b.y - a.y) * tk;
        const headAlpha = (1 - k / 3) * 0.9 * alphaFactor;
        const baseRadius = (k === 0 ? 3.5 : (k === 1 ? 2.5 : 1.8)) * widthFactor;
        signalCtx.beginPath();
        signalCtx.arc(x, y, baseRadius * 2, 0, Math.PI * 2);
        signalCtx.fillStyle = `rgba(${glowRgb}, ${headAlpha * 0.25})`;
        signalCtx.fill();
        signalCtx.beginPath();
        signalCtx.arc(x, y, baseRadius, 0, Math.PI * 2);
        signalCtx.fillStyle = `rgba(${coreRgb}, ${headAlpha})`;
        signalCtx.fill();
      }
    }
    graphState.rafHandle = requestAnimationFrame(step);
  };
  graphState.rafHandle = requestAnimationFrame(step);

  // Static "wire" styling underneath the particles so each cascade edge is
  // visible as a coral-tinted line; opacity fades with depth so the depth-1
  // cone reads as the loudest signal and depth-3 feels like distant echo.
  const ds = graphNetwork.body.data.edges;
  const staticUpdates = travelEdges.map(e => {
    const depthOpacity = Math.max(0.22, 0.58 - (e.depth - 1) * 0.16);
    const depthWidth = Math.max(0.8, 1.8 - (e.depth - 1) * 0.4);
    return {
      id: e._id,
      color: { color: "#cc785c", opacity: depthOpacity },
      width: depthWidth,
      shadow: false,
    };
  });
  ds.update(staticUpdates);
}

function stopSignalAnimation() {
  if (graphState.rafHandle) {
    cancelAnimationFrame(graphState.rafHandle);
    graphState.rafHandle = null;
  }
  if (signalCtx && signalOverlay) {
    signalCtx.clearRect(0, 0, signalOverlay.width, signalOverlay.height);
  }
}

// Pause animation when tab is hidden (save CPU / battery on laptops)
document.addEventListener("visibilitychange", () => {
  if (document.hidden) stopSignalAnimation();
  else if (graphState.signalOn) startSignalAnimation();
});

function sampleCardHTML(p) {
  let score = "";
  if (p.utility) {
    const pct = Math.round(p.utility.rate * 100);
    const cls = pct >= 50 ? "ok" : (pct >= 25 ? "mid" : "low");
    score = `<span class="util ${cls}" title="${esc(p.utility.referenced)} of ${esc(p.utility.total)} injected items were referenced in Claude's response. Filled blocks below show what was surfaced; this pill shows what was actually used.">utility ${pct}% <span class="util-ratio">(${esc(p.utility.referenced)}/${esc(p.utility.total)})</span></span>`;
  } else if (p.has_response === false) {
    score = `<span class="util pending" title="Assistant response not yet persisted — score will appear once the reply lands">utility —</span>`;
  }
  return `
    <div class="sample">
      <div class="q">
        <span class="ts">${esc(fmtTs(p.ts))}</span>
        ${score}
        <span class="prompt">${esc(p.preview)}</span>
      </div>
      <div class="blocks">
        ${renderCmBlock(p.cm)}
        ${renderBlock("Decisions", "past decisions recalled", p.g1)}
        ${renderBlock("Research docs", "relevant docs surfaced", p.g2_docs)}
        ${renderBlock("Code files", "related code found", p.g2_prefetch)}
      </div>
    </div>`;
}

// Track how many additional samples we've already loaded via "Load more"
let extraOffset = 3;   // first 3 come from SSE snapshot
let loadedExtras = 0;

function renderSamples(samples) {
  const host = $("samples");
  const ageEl = $("samples-age");
  if (!samples || !samples.prompts || samples.prompts.length === 0) {
    host.innerHTML = `<div style="color:var(--text-dim); padding:12px; font-family:var(--mono); font-size:12px;">Computing samples… (first run can take ~1-2s)</div>`;
    ageEl.textContent = "";
    return;
  }
  const ageSec = Math.max(0, Math.round(Date.now()/1000 - samples.computed_at));
  ageEl.textContent = `computed ${ageSec}s ago`;
  // Live section replaces (keeps top-N current); extras stay appended below.
  const liveHTML = samples.prompts.map(sampleCardHTML).join("");
  const extraContainer = host.querySelector("#extras");
  const extraHTML = extraContainer ? extraContainer.outerHTML : `<div id="extras"></div>`;
  host.innerHTML = liveHTML + extraHTML;
}

function renderCodeFiles(cf) {
  const host = $("codefiles-body");
  if (!cf || !cf.files || cf.files.length === 0) {
    host.innerHTML = `<div style="color:var(--text-dim);font-size:12px;font-family:var(--mono)">No code files discovered yet — G2-PREFETCH / G2-GREP will populate this panel after a few turns.</div>`;
    return;
  }
  const METHOD_COLOR = {"G2-PREFETCH": "#cc785c", "G2-GREP": "#5c87cc"};
  const rows = cf.files.map(f => {
    const methodColor = METHOD_COLOR[f.method] || "#8a8278";
    const symbolPart = f.symbol ? `<span class="sym">${esc(f.symbol)}</span> ` : "";
    const pathEsc = esc(f.path);
    return `<div class="cf-row">
      <span class="cf-method" style="color:${methodColor}">${esc(f.method)}</span>
      <span class="cf-path">${symbolPart}<span class="path">${pathEsc}</span></span>
    </div>`;
  }).join("");
  host.innerHTML = `<div class="cf-list">${rows}</div>
    <div class="cf-footer" style="color:var(--text-dim);font-size:11px;font-family:var(--mono);margin-top:8px;">
      ${cf.files.length} file${cf.files.length !== 1 ? "s" : ""} · ${cf.total_turns} recent turn${cf.total_turns !== 1 ? "s" : ""}
    </div>`;
}

function renderEvents(evs) {
  if (!evs || evs.length === 0) return `<div style="color:var(--text-dim); padding:10px;">No recent events.</div>`;
  return evs.map(e => `
    <div class="ev">
      <div class="t">${esc(e.time)}</div>
      <div class="ty">${esc(e.type)}</div>
      <div class="hk">${esc(e.hook || "")}</div>
      <div class="bk">${esc(e.block || "")}</div>
      <div class="dur">${e.duration_ms != null ? esc(e.duration_ms) + "ms" : ""}</div>
    </div>`).join("");
}

function renderActivity(activity) {
  const xs = activity.map(a => a.ts);
  const ys = activity.map(a => a.count);
  const opts = {
    width: $("activity-chart").clientWidth,
    height: 160,
    scales: { x: { time: true } },
    axes: [
      { stroke: "#8a8278", grid: { stroke: "rgba(31,28,26,0.08)" } },
      { stroke: "#8a8278", grid: { stroke: "rgba(31,28,26,0.08)" } },
    ],
    series: [
      {},
      {
        label: "events/min",
        stroke: "#cc785c",
        fill: "rgba(204,120,92,0.15)",
        width: 2,
        points: { show: false },
      },
    ],
  };
  if (activityPlot) {
    activityPlot.setData([xs, ys]);
  } else {
    activityPlot = new uPlot(opts, [xs, ys], $("activity-chart"));
  }
}

function apply(snap) {
  window._lastSnapshot = snap;   // cached so language toggle can re-render
  if (snap.empty) {
    $("meta").textContent = snap.message || "no events";
    return;
  }
  $("meta").textContent = `${snap.total_events} events · window ${snap.window}`;
  $("updated").textContent = `Updated ${snap.updated}`;
  $("window").textContent = snap.window;
  const grade = $("grade");
  grade.textContent = snap.grade.label;
  grade.className = "grade " + snap.grade.style;
  $("health-rows").innerHTML = snap.rows.map(renderHealthRow).join("");
  renderActivity(snap.activity);
  $("latency-bars").innerHTML = renderLatencyBars(snap.latency_hist);
  renderUtility(snap.utility);
  renderCodeFiles(snap.code_files);
  renderTokenUsage(snap.token_usage);
  $("notices").innerHTML = renderNotices(snap.notices);
  $("other").innerHTML = renderOther(snap.other);
  $("events").innerHTML = renderEvents(snap.recent);
  renderSamples(snap.samples);
  $("thresholds").textContent = fmtThresholds(snap.thresholds);

  // Reactive graph refresh: when total_events grows, a new user prompt/hook
  // fired — re-fetch the graph so the current-prompt node and its retrieval
  // cone update in near-realtime (lag ≈ one SSE tick + one graph rebuild).
  if (snap.total_events > lastEventCount) {
    lastEventCount = snap.total_events;
    // Skip the very first call (initial load already triggered refreshGraph())
    if (lastEventCount > 0 && graphNetwork) {
      setTimeout(refreshGraph, 400);  // small delay so samples recompute in parallel
    }
  }
}

// Refresh buttons — samples + graph
document.addEventListener("click", async (e) => {
  if (!e.target) return;
  if (e.target.id === "refresh-samples") {
    const btn = e.target;
    btn.disabled = true; btn.textContent = "…";
    try { await fetch("/api/samples/refresh", { method: "POST" }); }
    catch (err) { console.error(err); }
    setTimeout(() => { btn.disabled = false; btn.textContent = "refresh"; }, 2000);
  } else if (e.target.id === "refresh-graph") {
    const btn = e.target;
    btn.disabled = true; btn.textContent = "…";
    try {
      await fetch("/api/graph/refresh", { method: "POST" });
      refreshGraph();
    } catch (err) { console.error(err); }
    setTimeout(() => { btn.disabled = false; btn.textContent = "refresh"; }, 2000);
  } else if (e.target.id === "load-more-samples") {
    const btn = e.target;
    const status = $("load-more-status");
    btn.disabled = true;
    btn.textContent = "loading…";
    status.textContent = "";
    try {
      const r = await fetch(`/api/samples?offset=${extraOffset}&limit=10`);
      const page = await r.json();
      const extras = $("extras") || (() => {
        const d = document.createElement("div");
        d.id = "extras";
        $("samples").appendChild(d);
        return d;
      })();
      const prompts = page.prompts || [];
      if (prompts.length === 0) {
        status.textContent = "no more history";
        btn.textContent = "Load 10 more";
        return;
      }
      extras.insertAdjacentHTML("beforeend", prompts.map(sampleCardHTML).join(""));
      extraOffset += prompts.length;
      loadedExtras += prompts.length;
      btn.disabled = false;
      btn.textContent = "Load 10 more";
      status.textContent = `showing +${loadedExtras} older`;
    } catch (err) {
      console.error(err);
      btn.disabled = false;
      btn.textContent = "Load 10 more";
      status.textContent = "load failed — retry";
    }
  }
});

function connect() {
  const status = $("conn-status");
  const es = new EventSource("/stream");
  es.onmessage = (e) => {
    status.textContent = "live"; status.className = "conn ok";
    try { apply(JSON.parse(e.data)); } catch (err) { console.error(err); }
  };
  es.onerror = () => {
    status.textContent = "reconnecting…"; status.className = "conn err";
  };
}

// Wire language toggle + apply persisted/default language BEFORE any data
// arrives, so the initial paint respects the user's lang choice.
initLanguageToggle();

// Initial fetch so the page is never blank while waiting for SSE
fetch("/api/snapshot").then(r => r.json()).then(apply).catch(console.error);
connect();

// Lazy-load vis-network (688KB) only when graph panel enters viewport.
// Falls back to immediate load if IntersectionObserver unavailable.
function loadVisNetworkThenRefresh() {
  if (typeof vis !== "undefined" && vis.Network) {
    refreshGraph(); return;
  }
  const s = document.createElement("script");
  s.src = "https://cdn.jsdelivr.net/npm/vis-network@9.1.9/standalone/umd/vis-network.min.js";
  s.onload = () => refreshGraph();
  s.onerror = () => console.error("vis-network failed to load");
  document.head.appendChild(s);
}
const graphPanel = $("graph-panel");
if (graphPanel && "IntersectionObserver" in window) {
  const io = new IntersectionObserver(entries => {
    for (const e of entries) {
      if (e.isIntersecting) { loadVisNetworkThenRefresh(); io.disconnect(); break; }
    }
  }, { rootMargin: "200px 0px" });   // start loading when panel is 200px away
  io.observe(graphPanel);
} else {
  loadVisNetworkThenRefresh();  // fallback for old browsers
}

// Wow-banner: show on load if a recent activation event exists, and auto-scroll
// to the knowledge graph so the user SEES the retrieval cone immediately.
function checkWow() {
  const dismissed = localStorage.getItem("ctxWowDismissedAt");
  fetch("/api/wow").then(r => r.json()).then(w => {
    if (!w.fired) return;
    const firedAtMs = (w.fired_at || 0) * 1000;
    if (dismissed && parseInt(dismissed) >= firedAtMs) return;  // user dismissed this one
    // Only show for events in the last 24h
    if ((w.age_hours || 0) > 24) return;
    const banner = $("wow-banner");
    banner.style.display = "flex";
    // Retrieval method annotation: "found by meaning, not keywords" for semantic rescues
    const isSemantic = w.retrieval_method === "semantic";
    const recallVerb = isSemantic
      ? `<strong>CTX semantically matched a decision from ${esc(w.age_days)} days ago</strong> — found by meaning, not keywords.`
      : `<strong>CTX keyword-matched a decision from ${esc(w.age_days)} days ago</strong> —`;
    const usedNote = `Claude used it (${Math.round(w.utility_rate * 100)}% of injected items referenced).`;
    banner.innerHTML = `
      <span class="dot"></span>
      <span class="text">
        ${recallVerb} ${usedNote}
        <em style="color:var(--text-dim)"> The retrieval cone is visible in the knowledge graph below ↓</em>
      </span>
      <button class="dismiss" id="wow-dismiss">dismiss</button>
    `;
    // Auto-scroll to the graph panel after 800ms — user sees the banner first, then the reveal
    setTimeout(() => {
      const graph = $("graph-panel");
      if (graph) graph.scrollIntoView({ behavior: "smooth", block: "start" });
    }, 800);
  }).catch(() => {});
}

document.addEventListener("click", (e) => {
  if (e.target && e.target.id === "wow-dismiss") {
    const banner = $("wow-banner");
    banner.style.display = "none";
    localStorage.setItem("ctxWowDismissedAt", String(Date.now()));
  }
});

checkWow();

// Retrieval method distribution widget (Change 1)
function fetchAndRenderRetrievalMethodStats() {
  fetch("/api/retrieval-method-stats").then(r => r.json()).then(data => {
    const host = $("retrieval-method-body");
    if (!host) return;
    const total = data.total || 0;
    if (total === 0) {
      host.innerHTML = `<div class="empty" style="color:var(--text-dim); font-size:12px; font-family:var(--mono)">No graph data yet.</div>`;
      return;
    }
    const counts = data.counts || {};
    // Show keyword, semantic, cascade — skip cm_hybrid/code_index/hybrid/unknown
    const display = [
      { key: "keyword",  label: "keyword",   color: "#1565c0", title: "BM25 direct match" },
      { key: "semantic", label: "semantic",  color: "#7b1fa2", title: "e5-small embedding rescue (BM25 missed)" },
      { key: "cascade",  label: "cascade",   color: "#555",    title: "BFS propagation via topic/temporal edges" },
    ];
    const rows = display.map(({ key, label, color, title }) => {
      const n = counts[key] || 0;
      if (n === 0) return "";
      const pct = Math.round(n / total * 100);
      const pctFill = Math.max(3, pct);
      const isRescue = key === "semantic";
      return `<div class="row" title="${esc(title)}" style="margin-bottom:4px">
        <div class="name" style="min-width:72px; color:${color}; font-weight:${isRescue ? '700' : '400'}">${esc(label)}</div>
        <div class="bar" style="flex:1; margin:0 8px">
          <div class="bar-fill" style="width:${pctFill}%; background:${color}; height:8px; border-radius:4px; opacity:0.75"></div>
        </div>
        <div class="count" style="min-width:90px; text-align:right; font-size:0.85em">
          ${pct}% <span style="color:var(--text-dim)">(${n})</span>${isRescue ? ' <span style="color:#7b1fa2; font-size:0.85em">← rescued</span>' : ''}
        </div>
      </div>`;
    }).filter(Boolean).join("");

    const rescueRate = data.semantic_rescue_rate || 0;
    const rescueNote = rescueRate > 0
      ? `<div style="margin-top:8px; font-size:0.82em; color:#7b1fa2; font-weight:600">
          ${Math.round(rescueRate * 100)}% of retrievals are semantic rescues — found by meaning, not keywords.
        </div>`
      : `<div style="margin-top:6px; font-size:0.8em; color:var(--text-dim)">
          No semantic rescues this window — all retrievals matched directly by keyword.
        </div>`;

    host.innerHTML = `
      <div class="rows" style="font-family:var(--mono)">${rows}</div>
      ${rescueNote}
      <div style="margin-top:4px; font-size:0.75em; color:var(--text-dim)">${total} recall edges · ${display.filter(d => counts[d.key] > 0).length} of 3 method types active</div>
    `;
  }).catch(() => {
    const host = $("retrieval-method-body");
    if (host) host.innerHTML = `<span style="color:var(--text-dim); font-size:12px">—</span>`;
  });
}

fetchAndRenderRetrievalMethodStats();

// Re-render chart on resize
window.addEventListener("resize", () => {
  if (activityPlot) {
    activityPlot.setSize({ width: $("activity-chart").clientWidth, height: 160 });
  }
});
