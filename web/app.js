// 취약 돌보미 화면 — 스토리보드 v1.3: 로그인(COM-01) → 비서 · 대시보드(DSH) · 시뮬레이션(SIM)
// 【판단】 색과 종이 느낌은 하늘 + 흰 종이접기 시안, 구성과 순서는 스토리보드 장 그대로
// 【판단】 계산이 아직 화면에 붙지 않은 칸은 지어내지 않고 "준비 중" · "예시"라고 적는다

const state = { region: null, member: null, meta: null, board: null, geo: null, sel: null, chartKey: null, onlySel: false, mapMode: "now", ref: null };
const view = document.getElementById("view");
const nav = document.getElementById("nav");
const dlg = document.getElementById("dlg");
const ICON = (name) => `assets/icons/${name}.png`;
const GRADES = ["위험", "경고", "주의", "관심", "평상"];
const GCOLOR = { 위험: "var(--g4)", 경고: "var(--g3)", 주의: "var(--g2)", 관심: "var(--g1)", 평상: "var(--g0)" };

// ── 공통 ─────────────────────────────────────────────
async function api(path) {
  const res = await fetch(path);
  if (res.status === 401) throw loginGone();
  if (!res.ok) throw new Error((await res.json().catch(() => ({}))).detail || res.statusText);
  return res.json();
}
// 【기능】 대시보드가 고른 기준일(YYYY-MM-DD)을 주소에 붙인다. ""(빈 글자)면 붙이지 않아 자료 마지막 날
// 【판단】 자료의 마지막 주는 전부 평상이라, 처음 열 때는 등급이 켜진 주를 보여 준다. 고른 날은 이 탭에서만 기억한다
const DEFAULT_REF = { 강남구: "2025-08-29" };
const refKey = () => "salpim_ref:" + state.region;
function curRef() {
  // 【기능】 지금 기준일 — 처음 한 번만 정한다: 이 탭에서 고른 날 → 지역 기본 날
  if (state.ref === null) {
    let saved = null;
    try { saved = sessionStorage.getItem(refKey()); } catch { /* 저장이 막힌 창 */ }
    state.ref = saved || DEFAULT_REF[state.region] || "";
  }
  return state.ref;
}
const refQ = () => (curRef() ? "&ref=" + curRef() : "");
const refP = () => (curRef() ? "?ref=" + curRef() : "");
function setRef(v) {
  state.ref = v || "";
  try { v ? sessionStorage.setItem(refKey(), v) : sessionStorage.removeItem(refKey()); } catch { /* 저장이 막힌 창이면 이 화면에서만 */ }
}
async function post(path, body) {
  // 【기능】 POST 로 JSON 을 보내고 JSON 을 받는다. 서버가 422 로 돌려준 고칠 목록은 e.problems 에 담는다
  const res = await fetch(path, { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify(body) });
  if (res.status === 401) throw loginGone();
  if (!res.ok) {
    const detail = (await res.json().catch(() => ({}))).detail;
    const e = new Error(detail?.problems ? detail.problems.join(" ") : detail || res.statusText);
    e.problems = detail?.problems ?? null;
    e.status = res.status;
    throw e;
  }
  return res.json();
}
const fmt = (n) => (n == null ? "–" : Math.round(n).toLocaleString("ko-KR"));
const pct = (x, d = 1) => (x == null ? "–" : (x * 100).toFixed(d) + "%");
const esc = (s) => String(s ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" })[c]);
const chip = (g) => `<span class="chip g-${esc(g ?? "평상")}">${esc(g ?? "등급 없음")}</span>`;
const read = (html) => `<div class="read"><b>읽는 법</b> · ${html}</div>`;
const day = (iso) => {
  const d = new Date(iso + "T00:00:00");
  return `${d.getFullYear()}년 ${d.getMonth() + 1}월 ${d.getDate()}일(${"일월화수목금토"[d.getDay()]})`;
};

// 접힌 종이 띠 — 하늘 머리 아래에 깔리는 로우폴리. seed 로 모양을 고정한다
function folds(seed = 7, h = 60) {
  let s = seed;
  const rnd = () => ((s = (s * 9301 + 49297) % 233280) / 233280);
  const shades = ["oklch(0.975 0.01 245)", "oklch(0.95 0.015 245)", "oklch(0.92 0.02 245)", "oklch(0.97 0.012 245)"];
  const pts = [];
  for (let x = -40; x <= 1480; x += 60 + rnd() * 70) pts.push([x, h * (0.25 + rnd() * 0.55)]);
  let p = "";
  for (let i = 0; i < pts.length - 1; i++) {
    const [x1, y1] = pts[i], [x2, y2] = pts[i + 1], mx = (x1 + x2) / 2, my = Math.min(y1, y2) - rnd() * h * 0.25;
    p += `<polygon points="${x1},${h} ${x1},${y1} ${mx},${my}" fill="${shades[i % 4]}"/>`;
    p += `<polygon points="${x1},${y1} ${mx},${my} ${x2},${y2} ${x2},${h} ${x1},${h}" fill="${shades[(i + 2) % 4]}"/>`;
  }
  return `<svg class="folds" viewBox="0 0 1440 ${h}" preserveAspectRatio="none" aria-hidden="true">${p}</svg>`;
}
const pageHead = (crumb, title, sub = "", extra = "") => `<section class="page-head">
  <div class="crumb">${esc(crumb)}</div><h1>${title}</h1>${sub ? `<p>${sub}</p>` : ""}${extra}${folds()}</section>`;

function openDialog(html) {
  dlg.innerHTML = html + `<div class="acts" style="justify-content:flex-end"><button class="btn" data-close>닫기</button></div>`;
  dlg.querySelectorAll("[data-close]").forEach((b) => b.addEventListener("click", () => dlg.close()));
  dlg.showModal();
}

// ── COM-100 ~ 161 로그인 · 회원가입 · 아이디/비밀번호 찾기 ─────
// 【판단】 10-25 팀장: 체험 계정 대신 진짜 로그인(src/auth · web/auth.js) — 그리기는 auth.js 가 한다
const AUTH_PAGES = ["login", "signup", "find"];
function authPage() {
  nav.hidden = true;
  SalpimAuth.render(location.hash.replace(/^#\//, "") || "login");
}
// 【기능】 API 가 401(로그인 없음 · 끝남)이면 세션 만료 안내(CHT-SESS) → 로그인하면 이 화면으로 돌아온다
function loginGone() {
  state.member = null;
  SalpimAuth.expired(location.hash.replace(/^#\//, "") || "dashboard");
  const e = new Error("로그인 시간이 지났어요. 다시 로그인해 주세요.");
  e.status = 401;
  return e;
}

// ── CHT 비서 홈 (팀장 화면을 그대로 연다) ───────────
async function assistant() {
  // 【판단】 10-25 비서 서버도 로그인 쿠키를 읽는다 — 쿠키는 호스트가 같아야 같이 가서(포트는 상관없음),
  //   이 화면을 연 주소(localhost · 127.0.0.1)와 같은 호스트로 비서를 연다
  // 【판단】 반대로 비서 주소가 Tailscale(https://…ts.net:8020)인데 이 화면을 localhost 로 열었으면,
  //   쿠키가 localhost 에만 있어 비서가 '로그인이 필요합니다'로 막힌다(10-27). 그때는 이 화면의
  //   주소(http://localhost)에 비서 포트만 붙인다 — 비서 서버도 이 컴퓨터 127.0.0.1:포트 에 떠 있다
  const LOCAL = ["127.0.0.1", "localhost", "[::1]"];
  const au = new URL(state.meta.assistant_url);
  // 【판단】 http/https 도 이 화면을 따른다 — https 화면 안에 http 비서를 넣으면 브라우저가 막는다
  if (LOCAL.includes(au.hostname) || LOCAL.includes(location.hostname)) { au.protocol = location.protocol; au.hostname = location.hostname; }
  const url = au.toString().replace(/\/$/, "");
  view.innerHTML = pageHead("홈 > 비서", "비서 홈", `${esc(state.region)} 담당 · 오늘 챙길 일과 대화는 비서가 맡아요`) +
    `<div class="wrap page-body"><div id="aBox"><div class="paper empty">비서를 여는 중…</div></div></div>`;
  const box = view.querySelector("#aBox");
  try {
    await fetch(url, { mode: "no-cors" });
    box.innerHTML = `<iframe class="assistant-frame" src="${esc(url)}" title="AI 비서"></iframe>`;
  } catch {
    box.innerHTML = `<div class="paper fold empty"><img src="${ICON("people")}" alt="" width="80">
      <p>비서가 꺼져 있어요. 비서는 따로 켜요(주소 ${esc(url)}).</p>
      <code>uv run --env-file ../big-contest/.env uvicorn src.api.assistant:app --port ${esc(new URL(url).port || "80")}</code></div>`;
  }
}

// ── DSH 대시보드 ────────────────────────────────────
async function dashboard() {
  const boardOf = () => api("/api/board?region=" + encodeURIComponent(state.region) + refQ());
  const [B, G] = await Promise.all([
    // 【판단】 기억해 둔 날 · 기본 날이 고를 수 있는 범위 밖이면(자료가 바뀜) 마지막 날로 다시 부른다
    boardOf().catch(() => { setRef(""); return boardOf(); }),
    api("/api/geo?region=" + encodeURIComponent(state.region)),
  ]);
  state.board = B; state.geo = G;
  if (!state.sel || !B.dongs.some((d) => d.dong_cd === state.sel)) {
    state.sel = (B.dongs.find((d) => d.grade && d.grade !== "평상") || B.dongs[0]).dong_cd;
  }
  const C = B.counts, L = B.last_week;
  const trend = (g) => {
    if (!L) return "";
    const diff = C[g] - L[g];
    return `지난주 ${L[g]} · ${diff > 0 ? `<span class="up">▲${diff}</span>` : diff < 0 ? `<span class="down">▼${-diff}</span>` : "–"}`;
  };
  const head = B.ref_date
    ? `<div class="ref refpick"><label for="refPick">기준일</label>
         <input type="date" id="refPick" min="${B.ref_min}" max="${B.ref_max}" value="${B.ref_date}">
         <span>${day(B.ref_date)} 기준 · ${B.ref_date === B.ref_max ? "나우캐스트 자료의 마지막 주" : B.ref_date === DEFAULT_REF[state.region] ? `처음 보여 주는 날 — 등급이 가장 많이 켜진 주(자료 끝 ${day(B.ref_max)})` : `지난 날을 되돌아보는 중(자료 끝 ${day(B.ref_max)})`}</span>
         ${B.ref_date === B.ref_max ? "" : `<button class="help" id="refLatest">마지막 날로</button>`}</div>
       <div style="display:flex;gap:14px;align-items:baseline;flex-wrap:wrap;margin-top:6px"><h1 style="margin:0">${esc(state.region)} 이번 주</h1>
       <button class="help" id="helpBtn">등급은 어떻게 정하나요? ›</button></div>
       <div class="gcards">${["위험", "경고", "주의", "관심"].map((g) => `<div class="paper fold gcard"><div class="g"><span class="dot" style="background:${GCOLOR[g]}"></span>${g}</div>
         <div class="c">${C[g]}곳</div><div class="w">${trend(g)}</div>${weekBars(B.trend, g)}</div>`).join("")}</div>`
    : `<h1>${esc(state.region)} 이번 주</h1><p>카드 결제 자료가 없어 등급을 매기지 않았어요. 고립 위험 바탕 인원은 아래에 그대로 보여요.</p>`;
  const quiet = C && C["위험"] + C["경고"] === 0;
  view.innerHTML = `<section class="page-head"><div class="crumb">홈 > 대시보드</div>${head}${folds()}</section>
  <div class="wrap page-body">
    ${C ? `<div class="paper">
      ${quiet ? `<div class="banner ok"><i class="ti ti-circle-check"></i><div><b>이번 주는 위험·경고 동이 없습니다.</b><br>주의·관심 동은 아래 목록에서 볼 수 있습니다.</div></div>` : ""}
      <div class="notice"><b>이번 주 안내</b><span>${B.holidays_this_week.length ? `${esc(B.holidays_this_week.join(", "))}이 있는 주예요. 공휴일은 원래 씀씀이가 달라서 '평소보다 크게 적은 날'로 세지 않았어요.` : "평소 기준 그대로 계산했어요."}</span>
        <b>다음 주 예상</b><span>${nextText(B.next_week)}</span></div></div>` : ""}

    <section class="sec" id="sMap"><div class="sec-head"><h2 class="sec-title">지도</h2>
      <span class="seg2" id="mapMode"><button data-m="now" class="${state.mapMode !== "next" ? "on" : ""}">지금</button><button data-m="next" class="${state.mapMode === "next" ? "on" : ""}" ${B.next_week ? "" : "disabled"}>다음 주 예상</button><button data-m="youth" class="${state.mapMode === "youth" ? "on" : ""}">청년 은둔 어림</button></span></div>
      <div class="map-wrap"><div class="paper">${mapSvg()}<div class="legend" id="mapLegend">${mapLegend()}</div></div>
        <div class="paper fold" id="summary"></div></div></section>

    <section class="sec" id="sList"><div class="grid g2">
      <div class="paper"><h2>방문 순서</h2>
        <p class="order-how">1번부터 차례로 가 보세요. 등급이 높은 동이 먼저이고, 같은 등급이면 <b>① 오래 이어진 동</b> → <b>② 고립 위험 인원이 많은 동</b> 순이에요.</p>
        <div id="list"></div></div>
      <div class="paper"><div style="display:flex;justify-content:space-between;align-items:center;gap:8px"><h2 style="margin:0">줄어든 사람들 (나이 · 업종)</h2>
        <label style="font-size:13px;color:var(--sub)"><input type="checkbox" id="onlySel" ${state.onlySel ? "checked" : ""}> 고른 동만</label></div>
        <div class="groups" id="groups" style="margin-top:10px"></div>
        <p class="privacy">카드 자료는 구 단위 자료라서, 동 값은 그 나이 인구 비율이 높은 동에 나눠 붙인 추정이에요.</p></div></div></section>

    <section class="sec" id="sChart"><div class="paper"><h2>평소 수준과 실제 카드 이용 수준</h2><div class="tabs2" id="ctabs"></div><div id="chart"></div>
      <div class="legend"><span>━ 실제 카드 이용 수준</span><span>┅ 평소 수준(지난 4주)</span><span><span class="dot" style="background:oklch(0.86 0.06 245)"></span> 평소 범위(열에 여덟)</span><span><span class="dot" style="background:oklch(0.93 0.03 245)"></span> 스물에 열아홉</span><span><span class="dot" style="background:var(--g4)"></span> 예상보다 많이 낮은 날</span></div></div></section>

    <section class="sec" id="sDong"><div id="dongBox"></div></section>
  </div>`;

  // 【판단】 날짜 칸은 연 · 월 · 일을 한 칸씩 칠 때마다 change 가 난다. 바로 화면을 다시 그리면
  //   입력칸이 새로 만들어져 나머지 숫자가 사라지므로(10-27 '날짜를 넣어도 안 바뀜'), 범위 안의
  //   날짜만 받고 0.7초 동안 더 안 바뀌면 그때 다시 그린 뒤 입력칸에 커서를 돌려준다
  const pick = view.querySelector("#refPick");
  pick?.addEventListener("change", () => {
    clearTimeout(dashboard.timer);
    const v = pick.value;
    if (!v || v < B.ref_min || v > B.ref_max || v === B.ref_date) return;
    dashboard.timer = setTimeout(async () => {
      const typing = document.activeElement === pick;
      setRef(v); state.board = null; await dashboard();
      if (typing) view.querySelector("#refPick")?.focus();
    }, 700);
  });
  view.querySelector("#refLatest")?.addEventListener("click", async () => { setRef(B.ref_max); state.board = null; await dashboard(); });
  view.querySelector("#helpBtn")?.addEventListener("click", async () => {
    openDialog(`<h2>등급은 이렇게 정합니다</h2>
    ${GRADES.map((g) => `<div class="rule"><span>${chip(g)}</span><span>${esc(B.rules[g])}</span></div>`).join("")}
    <div class="terms"><div><b>무엇을 보나</b> 그 나이 분들의 카드 이용 수준(나우캐스트, 구 전체, 주 단위. 건수가 아니라 기준 시점 대비 수준이에요)</div>
      <div><b>평소 수준</b> 지난 4주 값의 가운데값</div>
      <div><b>크게 적은 날</b> 실제 수준이 평소 범위 아래로 내려간 날(평소엔 40일에 1번꼴인 수준). 공휴일은 세지 않음</div>
      <div><b>절반도 안 된 날</b> 실제 수준이 평소 수준의 절반이 안 된 날</div></div>
    <h3 style="margin:14px 0 4px;font-size:15px">이 기준이 잘 잡나요 — 줄어듦을 일부러 심어 본 결과</h3><div id="detTable" class="muted">계산 중…</div>`);
    // 【기능】 규칙 성능(만약에 ③) — 줄 4개 × 기준일 22개에 줄어듦을 심고 찾아낸 몫
    try {
      const rows = await api("/api/detection");
      const pc = (v) => `${Math.round(v * 100)}%`;
      const box = dlg.querySelector("#detTable");
      if (box) box.outerHTML = `<table class="ytable sv-table"><thead><tr><th>줄어듦</th><th>기간</th><th>관심 이상</th><th>주의 이상</th><th>경고 이상</th></tr></thead><tbody>
        ${rows.filter((r) => !(r["줄어듦"] === "0%" && r["며칠"] === 14)).map((r) => `<tr><td>${r["줄어듦"] === "0%" ? "없음(대조)" : r["줄어듦"]}</td><td>${r["줄어듦"] === "0%" ? "–" : `${r["며칠"]}일`}</td><td>${pc(r["관심 이상"])}</td><td>${pc(r["주의 이상"])}</td><td>${pc(r["경고 이상"])}</td></tr>`).join("")}</tbody></table>
        <p class="privacy">각 줄 ${rows[0]["건수"]}건(줄 4개 × 기준일 22개). '없음' 줄은 아무것도 안 심었는데 뜬 등급 = 잘못 울림이에요(관심 ${pc(rows[0]["관심 이상"])}).</p>`;
    } catch (e) {
      const box = dlg.querySelector("#detTable");
      if (box) box.textContent = `규칙 성능을 계산하지 못했어요(${e.message})`;
    }
  });
  view.querySelector("#onlySel").addEventListener("change", (e) => { state.onlySel = e.target.checked; drawGroups(); });
  view.querySelectorAll("#mapMode button").forEach((b) => b.addEventListener("click", () => {
    state.mapMode = b.dataset.m;
    view.querySelectorAll("#mapMode button").forEach((x) => x.classList.toggle("on", x === b));
    select(state.sel);
  }));
  view.querySelectorAll(".map path").forEach((p) => p.addEventListener("click", () => select(p.dataset.cd)));
  drawList(); drawGroups(); drawSummary(); drawChartTabs(); await drawDong();
}

function weekBars(trend, g) {
  // 【기능】 4주 흐름 막대(DSH-100 ②) — 3주 전 → 이번 주, 그 등급 동 수
  if (!trend?.length) return "";
  const vals = trend.map((w) => w.counts[g]), max = Math.max(1, ...vals);
  return `<div class="wbars" role="img" aria-label="${g} 4주 흐름 ${vals.join(", ")}">${vals.map((v, i) => `<span title="${trend[i].ref.slice(5).replace("-", "/")} ${v}곳"><i style="height:${Math.max(2, (v / max) * 22)}px;background:${GCOLOR[g]}"></i></span>`).join("")}<em>4주</em></div>`;
}

function nextText(nw) {
  // 【기능】 다음 주 예상 한 줄 — 두 가정(이어짐 · 반쯤 회복)의 범위로만 말한다
  if (!nw) return "카드 결제 자료가 없어 계산하지 않았어요.";
  const md = (iso) => `${+iso.slice(5, 7)}/${+iso.slice(8, 10)}`;
  const parts = ["위험", "경고", "주의", "관심"].filter((g) => nw.counts_range[g][1] > 0)
    .map((g) => { const [a, b] = nw.counts_range[g]; return `${g} ${a === b ? a : `${a}~${b}`}곳`; });
  return `${md(nw.from)}~${md(nw.to)} · ${parts.join(" · ") || "위험 · 경고 · 주의 · 관심 0곳"} (이번 주 줄어든 카드 이용 수준이 그대로 이어지는 경우 ~ 반쯤 돌아오는 경우)${nw.holidays.length ? ` · ${esc(nw.holidays.join(", "))}` : ""}. 날씨는 넣지 않았어요.`;
}

// 【판단】 청년 은둔 어림은 한 가지 색의 진하기(많을수록 진함) — 등급 색과 섞이지 않게 파랑 계열
const YCOLOR = ["oklch(0.94 0.03 250)", "oklch(0.85 0.07 250)", "oklch(0.72 0.11 252)", "oklch(0.58 0.14 255)"];
const youthCuts = () => {
  const his = state.board.dongs.map((d) => d.youth?.homebound?.hi).filter((v) => v != null).sort((a, b) => a - b);
  return [0.25, 0.5, 0.75].map((q) => his[Math.floor(q * (his.length - 1))] ?? 0);
};
const youthBin = (v) => youthCuts().filter((c) => v > c).length;

function mapLegend() {
  if (state.mapMode !== "youth") {
    return GRADES.map((g) => `<span><span class="dot" style="background:${GCOLOR[g]}"></span> ${g}</span>`).join("")
      + `<span><span class="dot" style="background:var(--paper-2);border:1px solid var(--line)"></span> 등급 없음</span>`;
  }
  const c = youthCuts();
  const labels = [`${fmt(c[0])}명 이하`, `~${fmt(c[1])}명`, `~${fmt(c[2])}명`, `${fmt(c[2])}명 넘음`];
  return labels.map((t, i) => `<span><span class="dot" style="background:${YCOLOR[i]}"></span> ${t}</span>`).join("")
    + `<span class="muted">거의 집에만 있는 청년 어림(위 끝 값) · 청년의 삶 실태조사 2024 비율로 어림</span>`;
}

function mapSvg() {
  // 【기능】 동 경계(경도 · 위도)를 화면 좌표로 — 위도에 맞춰 가로를 줄여 모양이 눌리지 않게
  const feats = state.geo.features;
  let minX = 1e9, minY = 1e9, maxX = -1e9, maxY = -1e9;
  const each = (f, fn) => (f.geometry.type === "Polygon" ? [f.geometry.coordinates] : f.geometry.coordinates).forEach((poly) => poly.forEach((ring) => ring.forEach(fn)));
  feats.forEach((f) => each(f, ([x, y]) => { minX = Math.min(minX, x); maxX = Math.max(maxX, x); minY = Math.min(minY, y); maxY = Math.max(maxY, y); }));
  const k = Math.cos(((minY + maxY) / 2) * Math.PI / 180), W = 640, sc = W / ((maxX - minX) * k), H = (maxY - minY) * sc;
  const P = ([x, y]) => [((x - minX) * k * sc).toFixed(1), ((maxY - y) * sc).toFixed(1)];
  const byCd = Object.fromEntries(state.board.dongs.map((d) => [d.dong_cd, d]));
  // 【판단】 다음 주 예상은 "이번 주 낮은 만큼이 이어지면"의 등급 — 점선 테두리로 지금과 구분(DSH-101 ③)
  const next = state.mapMode === "next" && state.board.next_week;
  const youthMode = state.mapMode === "youth";
  const labels = [];
  const out = feats.map((f) => {
    const d0 = byCd[f.properties.dong_cd] || {};
    const d = next ? { ...d0, grade: state.board.next_week.dong_grade[d0.dong] ?? d0.grade } : d0;
    const polys = f.geometry.type === "Polygon" ? [f.geometry.coordinates] : f.geometry.coordinates;
    const path = polys.map((poly) => poly.map((ring) => "M" + ring.map(P).join("L") + "Z").join("")).join("");
    const sel = state.sel === f.properties.dong_cd;
    const strong = (d.grade && !["평상", "관심"].includes(d.grade)) || sel;
    const rank = sel ? -1 : d.grade ? GRADES.indexOf(d.grade) : GRADES.length;
    labels.push({ name: f.properties.dong, strong, rank, ...labelPoint(polys, P) });
    // 【판단】 청년 모드는 등급이 아니라 '거의 집에만 있는 청년 어림'(위 끝 값) 많고 적음으로 칠한다
    const hb = d0.youth?.homebound;
    const fill = youthMode ? (hb ? YCOLOR[youthBin(hb.hi)] : "var(--paper-2)") : d.grade ? GCOLOR[d.grade] : "var(--paper-2)";
    const tip = youthMode ? `청년 은둔 어림 ${hb ? `${fmt(hb.lo)}~${fmt(hb.hi)}명` : "–"}` : `${next ? "다음 주 예상 " : ""}${d.grade ?? "등급 없음"}`;
    return `<path d="${path}" data-cd="${f.properties.dong_cd}" fill="${fill}" class="${sel ? "sel" : ""}${next ? " next" : ""}"><title>${esc(f.properties.dong)} · ${esc(tip)}</title></path>`;
  }).join("");
  return `<svg class="map" viewBox="0 0 ${W} ${H.toFixed(0)}" role="img" aria-label="${esc(state.region)} 동 지도${next ? " · 다음 주 예상" : ""}">${out}${placeLabels(labels)}${next ? `<text x="${W - 8}" y="18" text-anchor="end" class="map-tag">예상 · 이번 주 줄어든 만큼 이어지면</text>` : ""}</svg>`;
}

function labelPoint(polys, P) {
  // 【기능】 동 이름을 놓을 자리 — 가장 넓은 조각의 무게중심 높이에서, 경계 안쪽 가로 구간 중 가장 긴 곳의 가운데
  // 【판단】 꼭짓점 평균은 꼭짓점이 몰린 쪽으로 쏠려 이름이 경계 위에 걸렸다(10-27 춘천 남산면)
  const rings = polys.map((poly) => poly[0].map((pt) => P(pt).map(Number)));
  const area = (r) => r.reduce((s, [x, y], i) => { const [x2, y2] = r[(i + 1) % r.length]; return s + x * y2 - x2 * y; }, 0) / 2;
  const ring = rings.reduce((a, b) => (Math.abs(area(b)) > Math.abs(area(a)) ? b : a));
  const A = area(ring) || 1;
  let cx = 0, cy = 0;
  ring.forEach(([x, y], i) => { const [x2, y2] = ring[(i + 1) % ring.length], c = x * y2 - x2 * y; cx += (x + x2) * c; cy += (y + y2) * c; });
  cx /= 6 * A; cy /= 6 * A;
  // 【기능】 가로선 y = cy 가 경계와 만나는 x 들 → 둘씩 짝지은 구간이 '안쪽'
  const xs = [];
  ring.forEach(([x, y], i) => { const [x2, y2] = ring[(i + 1) % ring.length]; if ((y > cy) !== (y2 > cy)) xs.push(x + ((cy - y) * (x2 - x)) / (y2 - y)); });
  xs.sort((a, b) => a - b);
  let best = null;
  for (let i = 0; i + 1 < xs.length; i += 2) if (!best || xs[i + 1] - xs[i] > best[1] - best[0]) best = [xs[i], xs[i + 1]];
  const inside = best && cx > best[0] && cx < best[1];
  return { x: inside ? cx : best ? (best[0] + best[1]) / 2 : cx, y: cy, room: best ? best[1] - best[0] : 0, size: Math.abs(A) };
}

function placeLabels(labels) {
  // 【기능】 이름끼리 겹치지 않게 — 고른 동 → 등급 높은 동 → 넓은 동 순서로 놓고, 이미 놓인 이름과 겹치면 뺀다
  // 【판단】 빠진 동은 지도에서 눌러 보거나(이름이 뜸) 옆 동 목록에서 찾는다. 겹친 글자보다 읽힌다
  const placed = [];
  labels.sort((a, b) => a.rank - b.rank || b.size - a.size);
  return labels.map((l) => {
    const fs = l.strong ? 12 : 10.5, w = l.name.length * fs * 0.95 + 4, h = fs + 3;
    const box = [l.x - w / 2, l.y - h / 2, l.x + w / 2, l.y + h / 2];
    const hit = placed.some((p) => box[0] < p[2] && box[2] > p[0] && box[1] < p[3] && box[3] > p[1]);
    if (hit && l.rank !== -1) return "";
    placed.push(box);
    return `<text x="${l.x.toFixed(1)}" y="${l.y.toFixed(1)}" dy="0.35em" text-anchor="middle" class="${l.strong ? "strong" : ""}">${esc(l.name)}</text>`;
  }).join("");
}

function select(cd) {
  state.sel = cd;
  view.querySelector("#sMap .paper").firstElementChild.outerHTML = mapSvg();
  view.querySelectorAll(".map path").forEach((p) => p.addEventListener("click", () => select(p.dataset.cd)));
  const lg = view.querySelector("#mapLegend");
  if (lg) lg.innerHTML = mapLegend();
  drawList(); drawGroups(); drawSummary(); drawDong();
}

const whyText = (w) => (w ? (w.source === "SKT" ? `SKT 유동 경보: ${w.rule}` : `${w.age} ${w.group} 카드 이용 수준 — ${w.rule}`) : "");

async function drawSummary() {
  const d = state.board.dongs.find((x) => x.dong_cd === state.sel);
  const box = view.querySelector("#summary");
  box.innerHTML = `<h2>${esc(d.dong)} ${chip(d.grade)}${d.weeks ? ` <span class="muted">${d.weeks}주째</span>` : ""}</h2>
    <div style="font-size:14px;color:var(--sub)">${d.why ? esc(whyText(d.why)) : d.grade ? "카드 이용 수준이 평소 범위 안이에요." : "카드 결제 자료가 없어 등급을 매기지 않았어요."}</div>
    <div id="evid"></div>
    <div class="kv" style="display:grid;grid-template-columns:auto 1fr;gap:4px 12px;margin-top:10px;font-size:14px">
      <span class="muted">고립 위험 바탕</span><b>${fmt(d.est_n)}명 (${pct(d.rate)})</b>
      <span class="muted">80세 이상 혼자</span><b>${d.solo80 == null ? "–" : "약 " + fmt(d.solo80) + "명"}</b>
      <span class="muted">도와줄 기관</span><b>${d.helpers}곳</b></div>
    <div class="acts"><button class="btn" id="bMore">아래 자세히 보기 ›</button></div>`;
  view.querySelector("#bMore").addEventListener("click", () => view.querySelector("#sDong").scrollIntoView({ behavior: "smooth" }));
  // 【기능】 근거 세 줄(DSH-102) — 얼마나 줄었나 · 예상과 비교 · 며칠째
  const x = await api("/api/dongs/" + d.dong_cd + refP());
  const ev = x.evidence;
  if (ev && state.sel === d.dong_cd) box.querySelector("#evid").innerHTML = evidenceRow(ev);
}

function evidenceRow(ev) {
  return `<div class="evid"><div><span class="muted">${esc(ev.age)} ${esc(ev.group)} 카드 이용 수준</span><b>${ev.drop_pct > 0 ? "+" : ""}${ev.drop_pct}%</b><span class="muted">지난 7일, 평소와 비교</span></div>
    <div><span class="muted">평소와 비교</span><b>${esc(ev.label)}</b></div>
    <div><span class="muted">며칠째</span><b>${ev.days}일</b><span class="muted">평소보다 적은 날이 이어짐</span></div></div>`;
}

function orderWhy(d) {
  // 【기능】 이 동이 이 자리에 온 까닭 한 줄 — 순서를 정한 기준(신호 수 → 몇 주째 → 인원) 가운데 이 동에 해당하는 첫째
  if (d.signals?.length > 1) return "카드 결제와 SKT 외출 신호가 둘 다 켜졌어요";
  if (d.weeks > 1) return `${d.grade} 등급이 ${d.weeks}주째 이어지고 있어요`;
  return `${d.grade} 동 가운데 고립 위험 인원이 ${fmt(d.est_n)}명이에요`;
}

function drawList() {
  // 【판단】 같은 등급 안은 방문 순서(visit_rank) 순 — 신호 수 → 몇 주째 → 인원. 순서가 없는 평상 · 등급 없음은 서버 순서(인원 많은 순) 그대로
  const by = (g) => state.board.dongs.filter((d) => (d.grade ?? "등급 없음") === g)
    .sort((a, b) => (a.visit_rank ?? Infinity) - (b.visit_rank ?? Infinity));
  const first = [...GRADES, "등급 없음"].find((g) => by(g).length && g !== "평상") ?? "평상";
  // 【판단】 '방문 순서'로 읽히게 맨 위에 먼저 갈 3곳을 길처럼 잇고, 자리마다 까닭을 한 줄씩 붙인다(10-27 사용자 "방문 우선순위로 안 느껴짐")
  const ranked = state.board.dongs.filter((d) => d.visit_rank).sort((a, b) => a.visit_rank - b.visit_rank);
  const route = ranked.length
    ? `<ol class="route">${ranked.slice(0, 3).map((d) => `<li data-cd="${d.dong_cd}" class="${d.dong_cd === state.sel ? "sel" : ""}">
        <span class="rk top">${d.visit_rank}</span><div><b>${esc(d.dong)}</b> ${chip(d.grade)}<p>${esc(orderWhy(d))}</p></div></li>`).join("")}</ol>
      ${ranked.length > 3 ? `<p class="route-more">나머지 ${ranked.length - 3}곳은 아래 등급별 목록의 번호 순서대로예요.</p>` : ""}`
    : `<p class="route-more">이 기준일에는 먼저 갈 동이 없어요. 모든 동이 평상이에요.</p>`;
  view.querySelector("#list").innerHTML = route + [...GRADES, "등급 없음"].filter((g) => by(g).length).map((g) => `
    <details class="acc" ${g === first || by(g).some((d) => d.dong_cd === state.sel) ? "open" : ""}><summary><span class="dot" style="background:${GCOLOR[g] ?? "var(--paper-2)"}"></span>${g}<span class="n">${by(g).length}곳 <i class="caret" aria-hidden="true">▾</i></span></summary>
      <ul>${by(g).map((d) => `<li data-cd="${d.dong_cd}" class="${d.dong_cd === state.sel ? "sel" : ""}"><span class="nm">${d.visit_rank ? `<span class="rk${d.visit_rank <= 3 ? " top" : ""}" title="방문 순서 ${d.visit_rank}번">${d.visit_rank}</span>` : ""}${esc(d.dong)}${d.signals?.length > 1 ? `<span class="wk sg" title="카드 결제와 SKT 외출 신호가 둘 다 켜짐">카드·SKT</span>` : ""}${d.weeks && d.grade !== "평상" ? `<span class="wk">${d.weeks}주째</span>` : ""}</span><span class="muted num">고립 위험 ${fmt(d.est_n)}명</span></li>`).join("")}</ul></details>`).join("");
  view.querySelectorAll("#list li").forEach((li) => li.addEventListener("click", () => select(li.dataset.cd)));
}

function drawGroups() {
  const d = state.board.dongs.find((x) => x.dong_cd === state.sel);
  let gs = state.board.groups;
  if (state.onlySel) gs = gs.filter((g) => (g.exposed ?? g.dongs).includes(d.dong));
  view.querySelector("#groups").innerHTML = gs.length ? gs.slice(0, 6).map((g) => `<div class="grp"><div class="grp-h">${chip(g.grade)}<b><span>${esc(g.age)} ·</span> <span>${esc(g.group)}</span></b></div>
    <div class="r">${esc(g.rule)}</div><div class="r">${g.grade === "평상" ? "" : "그 나이 어르신이 많은 동: "}${g.grade === "평상" ? "" : esc(g.dongs.join(" · "))}</div></div>`).join("")
    : `<div class="muted">고른 동에 걸린 묶음이 없어요.</div>`;
}

function drawChartTabs() {
  const gs = state.board.groups.slice(0, 4);
  if (!gs.length) return (view.querySelector("#sChart").hidden = true);
  if (!state.chartKey) state.chartKey = `${gs[0].age}|${gs[0].group}`;
  const tabs = [["60대 이상", "전체", "전체"], ...gs.map((g) => [g.age, g.group, `${g.age} ${g.group}`])];
  view.querySelector("#ctabs").innerHTML = tabs.map(([a, g, label]) => `<button data-k="${esc(a)}|${esc(g)}" class="${state.chartKey === `${a}|${g}` ? "on" : ""}">${esc(label)}</button>`).join("");
  view.querySelectorAll("#ctabs button").forEach((b) => b.addEventListener("click", () => { state.chartKey = b.dataset.k; drawChartTabs(); }));
  drawChart();
}

async function lineChart(age, group, { w = 680, h = 240, mini = false } = {}) {
  const past = await api(`/api/chart?region=${encodeURIComponent(state.region)}&age=${encodeURIComponent(age)}&group=${encodeURIComponent(group)}${refQ()}`);
  // 【기능】 오늘 선 오른쪽 = 앞으로 1주 예상선 · 범위(DSH-104 ②). 실제 값은 아직 없다
  const fut = mini ? [] : (state.board?.next_week?.lines?.[`${age}|${group}`] ?? []);
  const rows = [...past, ...fut];
  const lo = Math.min(...rows.map((r) => Math.min(r.actual ?? Infinity, r.lo95))), hi = Math.max(...rows.map((r) => Math.max(r.actual ?? -Infinity, r.hi95)));
  // 【판단】 왼쪽 여백은 세로 눈금 숫자 길이만큼 — 30px 고정이면 '1,849' 의 앞자리가 잘렸다
  const pad = mini ? 4 : Math.max(30, fmt(hi).length * 7 + 10), X = (i) => pad + (i * (w - pad - 10)) / (rows.length - 1), Y = (v) => 10 + ((hi - v) * (h - 40)) / (hi - lo || 1);
  const band = (a, b, fill) => `<polygon fill="${fill}" points="${rows.map((r, i) => `${X(i)},${Y(r[a])}`).join(" ")} ${rows.map((r, i) => `${X(rows.length - 1 - i)},${Y(rows[rows.length - 1 - i][b])}`).join(" ")}"/>`;
  const line = (k, attrs, n = rows.length) => `<polyline fill="none" ${attrs} points="${rows.slice(0, n).map((r, i) => `${X(i)},${Y(r[k])}`).join(" ")}"/>`;
  const today = fut.length ? `<line x1="${X(past.length - 1)}" x2="${X(past.length - 1)}" y1="6" y2="${h - 26}" stroke="var(--sub)" stroke-dasharray="2 3"/><text x="${X(past.length - 1) - 4}" y="16" font-size="11" text-anchor="end" fill="var(--sub)">오늘 · 오른쪽은 다음 1주 예상 →</text>` : "";
  const dots = rows.map((r, i) => (r.low ? `<circle cx="${X(i)}" cy="${Y(r.actual)}" r="${mini ? 2.5 : 4}" fill="var(--g4)"/>` : "")).join("");
  const ticks = mini ? "" : [0, Math.floor(rows.length / 2), rows.length - 1].map((i) => `<text x="${X(i)}" y="${h - 6}" font-size="11" text-anchor="middle" fill="var(--faint)">${rows[i].day.slice(5).replace("-", "/")}</text>`).join("")
    + [lo, (lo + hi) / 2, hi].map((v) => `<text x="${pad - 6}" y="${Y(v) + 4}" font-size="11" text-anchor="end" fill="var(--faint)">${fmt(v)}</text>`).join("");
  return `<svg viewBox="0 0 ${w} ${h}" width="100%" role="img" aria-label="${esc(age)} ${esc(group)} 주 단위 카드 이용">${band("hi95", "lo95", "oklch(0.93 0.03 245)")}${band("hi80", "lo80", "oklch(0.86 0.06 245)")}
    ${line("expected", 'stroke="var(--blue)" stroke-width="1.5" stroke-dasharray="5 4"')}${line("actual", 'stroke="var(--ink)" stroke-width="2"', past.length)}${dots}${today}${ticks}</svg>`;
}

async function drawChart() {
  const [age, group] = state.chartKey.split("|");
  const box = view.querySelector("#chart");
  box.innerHTML = `<div class="muted">${esc(age === "60대 이상" && group === "전체" ? "60대 이상 합계" : `${age} ${group}`)} · 카드 이용 수준 · 최근 8주</div>` + await lineChart(age, group);
}

function youthBlock(y) {
  // 【기능】 동별 칸의 청년(19~34세) — 인구 · 1인세대 · 거의 집에만 있는 청년 어림 · 연결 창구
  const h = y.homebound ?? {};
  return `<div class="youth"><h2>청년(19~34세) · 고립 · 은둔</h2>
    <div class="kv" style="display:grid;grid-template-columns:auto 1fr;gap:4px 12px;font-size:14px">
      <span class="muted">청년</span><b>${fmt(y.total)}명 <span class="muted">(19~24세 ${fmt(y.bands["19-24"])} · 25~29세 ${fmt(y.bands["25-29"])} · 30~34세 ${fmt(y.bands["30-34"])})</span></b>
      <span class="muted">혼자 사는 청년</span><b>${fmt(y.solo)}명</b>
      <span class="muted">거의 집에만 있는 청년</span><b>${h.under10 ? "10명 미만" : `약 ${fmt(h.lo)} ~ ${fmt(h.hi)}명`} <span class="muted">${h.per100_lo ? `(100명에 ${h.per100_lo}~${h.per100_hi}명꼴)` : ""}</span></b></div>
    <p class="privacy">어림 = 청년의 삶 실태조사 2024(전국)의 나이별 비율을 이 동의 나이 구성에 곱한 값이에요. 실제로 센 수가 아니에요.</p>
    ${y.desk?.length ? `<details class="acc"><summary>연결할 곳 ▾</summary><ul style="padding-left:18px;font-size:14px">${y.desk.map((t) => `<li>${esc(t)}</li>`).join("")}</ul></details>` : ""}
  </div>`;
}

async function drawDong() {
  const box = view.querySelector("#dongBox");
  const x = await api("/api/dongs/" + state.sel + refP());
  const minis = await Promise.all(["70대 이상", "60대"].map(async (a) => state.board.ref_date ? `<div><div class="muted">${a} 카드 이용</div>${await lineChart(a, "전체", { w: 300, h: 90, mini: true })}</div>` : ""));
  const why = x.why ? (x.why.source === "SKT" ? `SKT 유동 경보: ${x.why.rule}` : `${x.why.age} ${x.why.group} 카드 이용 수준 — ${x.why.rule}`) : x.grade === "평상" ? "이번 주 카드 이용 수준은 평소 범위 안이에요." : "카드 결제 자료가 없어 등급을 매기지 않았어요.";
  const nextG = x.next_grade == null ? "계산 안 함" : x.next_grade === x.next_grade_recover ? `${x.next_grade} 예상` : `${x.next_grade_recover} ~ ${x.next_grade} 예상`;
  box.innerHTML = `<div class="paper fold">
    <div style="display:flex;gap:10px;align-items:center;flex-wrap:wrap"><h2 style="margin:0;font-size:22px">${esc(x.dong)}</h2>${chip(x.grade)}<span class="muted">${x.weeks ? `${x.weeks}주째 · ` : ""}다음 주 ${esc(nextG)}</span></div>
    <p style="color:var(--sub);margin:8px 0 0">${esc(why)}</p>${x.evidence ? evidenceRow(x.evidence) : ""}
    ${state.board.ref_date ? `<div class="grid g3" style="margin-top:12px">${minis.join("")}</div>` : ""}
    <div class="grid g2" style="margin-top:16px">
      <div><h2>고립 위험 바탕 — 지역사회건강조사</h2><div class="big">${fmt(x.est_n)}명<small>어른 ${fmt(x.adult)}명 중 ${pct(x.rate)}</small></div>
        ${x.standout.length ? `<div style="margin-top:8px">${x.standout.map((s) => `<div style="font-size:14px;margin:4px 0">· <b>${esc(s.reason)}</b> <span class="muted">${esc(s.group)} · 이 동 고립자의 ${s.pct}% · 전국의 ${s.lift}배</span></div>`).join("")}</div>` : ""}</div>
      <div><h2>이 동에서 할 일</h2>
        <div class="kv" style="display:grid;grid-template-columns:auto 1fr;gap:4px 12px;font-size:14px">
          <span class="muted">도와줄 기관</span><b>${x.helpers}곳 <span class="muted">(경로당 · 급식소 · 복지관)</span></b>
          <span class="muted">80세 이상 혼자 사는 분</span><b>${x.solo80 == null ? "–" : "약 " + fmt(x.solo80) + "명"}</b>
          <span class="muted">1억 방문 · 3년</span><b>${x.visit_fewer_random == null ? "–" : `${x.visit_fewer_random.toFixed(1)} ~ ${x.visit_fewer_upper.toFixed(1)}명 줄어듦`}</b></div>
        <div class="acts"><button class="btn primary" id="bBrief"><i class="ti ti-file-text"></i>현장 브리핑 만들기</button>
          <button class="btn" id="bAsk"><i class="ti ti-message-chatbot"></i>비서에게 묻기</button>
          <button class="btn" id="bDone"><i class="ti ti-check"></i>했어요</button></div>
        <p class="privacy">개인 이름 · 연락처는 받지 않습니다. 동과 집단 단위로만 기록합니다.</p></div></div>
    ${x.youth ? youthBlock(x.youth) : ""}</div>`;
  const ask = `${x.dong}은 왜 ${x.grade ?? "등급이 없"}${x.grade ? "이야" : "어"}?`;
  box.querySelector("#bAsk").addEventListener("click", () => openDialog(`<h2>비서에게 묻기</h2><p>비서 대화에 이 질문을 먼저 보내요.</p><div class="para">${esc(ask)}</div>
    <div class="acts"><a class="btn primary" href="#/assistant" data-close>비서 열기</a></div>`));
  box.querySelector("#bBrief").addEventListener("click", () => openDialog(`<h2>현장 브리핑</h2><p>현장 브리핑(BRF-100)은 비서가 새 창으로 만들어요. 비서에게 이렇게 요청해요.</p>
    <div class="para">${esc(x.dong)} 현장 브리핑 만들어 줘</div><div class="acts"><a class="btn primary" href="#/assistant" data-close>비서 열기</a></div>`));
  box.querySelector("#bDone").addEventListener("click", () => openDialog(`<h2>했어요 · ${esc(x.dong)}</h2><p class="muted">비서 카드와 같은 기록(CHT-105)으로 이어 붙일 자리예요(준비 중).</p>
    <div class="form"><label>결과</label><select><option>문제 있음</option><option>문제 없음</option><option>못 만남</option></select>
    <label>메모</label><textarea placeholder="이름 · 연락처는 쓰지 마세요"></textarea></div>`));
}

// ── SIM 시뮬레이션 ──────────────────────────────────
const KINDS = ["찾아가서 살피기(방문)", "안부 확인(전화 · IoT)", "함께 모이는 활동", "생활 지원", "청년 관계 회복(사례관리)"];
const WHO = ["80세 이상 혼자 사는 분", "65세 이상 혼자 사는 분", "기초수급 어르신", "고립·은둔 청년(19~34세)"];
const isYouth = (who) => who.includes("청년");
// 【기능】 청년만의 비교 순서(엔진 APPLY) — 손을 든 청년 중에서 만난다
const APPLY = "알려서 신청받기";

async function simulation() {
  const B = state.board?.region === state.region ? state.board : await api("/api/board?region=" + encodeURIComponent(state.region) + refQ());
  state.board = B;
  const top = B.dongs.filter((d) => d.visit_fewer_upper != null).sort((a, b) => b.visit_fewer_upper - a.visit_fewer_upper).slice(0, 2);
  const picked = new Set((top.length ? top : B.dongs.slice(0, 2)).map((d) => d.dong));
  view.innerHTML = pageHead("홈 > 시뮬레이션", "정책을 넣으면 고립 위험이 어떻게 달라질지 미리 계산", `${esc(state.region)} · 칸으로 고를 것은 고르고, 나머지는 설명글로 써요`) + `
  <div class="wrap page-body"><div class="sim">
    <div class="paper fold form">
      <label for="sKind">정책 종류</label><select id="sKind">${KINDS.map((k) => `<option>${k}</option>`).join("")}</select>
      <label for="sWho">누구에게</label><select id="sWho">${WHO.map((k) => `<option>${k}</option>`).join("")}</select>
      <label>어디에</label><div class="chips" id="sDongs"></div>
      <select id="sAdd" style="margin-top:6px"><option value="">+ 동 고르기</option>${B.dongs.map((d) => `<option>${esc(d.dong)}</option>`).join("")}</select>
      <div class="row"><div><label for="sMoney">돈 (1년 · 만원)</label><input id="sMoney" type="number" min="0" step="100" placeholder="비워 두면 AI가 채움"></div>
        <div><label for="sYears">기간 · 횟수</label><div class="row"><select id="sYears"><option>1년</option><option selected>2년</option><option>3년</option></select><select id="sFreq"><option>주 1회</option><option selected>주 2회</option><option>주 3회</option></select></div></div></div>
      <label for="sText">설명글</label><textarea id="sText"></textarea>
      <ul class="err-list" id="sErr" hidden></ul>
      <div class="acts"><button class="btn primary" id="sRun"><i class="ti ti-player-play"></i>실행</button></div>
      <p class="privacy">개인 이름 · 연락처는 받지 않아요(비서와 같은 규칙).</p>
    </div>
    <div id="sOut"><div class="paper empty"><img src="${ICON("chart")}" alt="" width="80"><p>결과 자리 — 실행하면 진행 기록 → 결과가 여기에 떠요.</p></div></div>
  </div></div>`;
  const chips = view.querySelector("#sDongs");
  const VERB = { [KINDS[0]]: "찾아가 안부를 살피고 병원 동행을 돕는다", [KINDS[1]]: "전화 · IoT 로 안부를 확인한다",
    [KINDS[2]]: "함께 모이는 활동을 연다", [KINDS[3]]: "생활 지원을 한다",
    [KINDS[4]]: "찾아가 관계 회복을 돕는 사례관리를 한다" };
  const text = () => `${[...picked].join("·")} ${view.querySelector("#sWho").value}께 ${view.querySelector("#sFreq").value} ${VERB[view.querySelector("#sKind").value]}.`;
  const drawChips = () => {
    chips.innerHTML = [...picked].map((d) => `<span>${esc(d)} <button aria-label="${esc(d)} 빼기" data-d="${esc(d)}">✕</button></span>`).join("") || `<span class="muted">동을 고르세요</span>`;
    chips.querySelectorAll("button").forEach((b) => b.addEventListener("click", () => { picked.delete(b.dataset.d); drawChips(); }));
    view.querySelector("#sText").value = text();
  };
  drawChips();
  view.querySelector("#sAdd").addEventListener("change", (e) => { if (e.target.value) picked.add(e.target.value); e.target.value = ""; drawChips(); });
  ["#sWho", "#sKind", "#sFreq"].forEach((id) => view.querySelector(id).addEventListener("change", () => (view.querySelector("#sText").value = text())));
  view.querySelector("#sRun").addEventListener("click", () => { state.simOverrides = {}; runSim([...picked]); });
}

function askDialog(qs) {
  // 【기능】 칸과 설명글이 다른 것(최대 2개)을 나란히 보여 주고 고른 쪽을 돌려준다(SIM-102 · 103)
  //   돌려주는 값: 질문마다 "form"(칸대로) 또는 "text"(설명글대로)
  return new Promise((resolve) => {
    const show = (q, v) => esc(q.field === "money" ? `${fmt(v)}만원` : typeof v === "number" ? `${v}년` : String(v));
    dlg.innerHTML = `<h2>칸과 설명글이 달라요</h2>
      <p class="muted">계산을 잠깐 멈췄어요. 어느 쪽으로 할지 골라 주세요.</p>
      ${qs.map((q, i) => `<fieldset class="ask"><legend>${esc(q.label)}${q.field === "kind" ? " · 설명글은 이 종류에 가까워요" : ""}</legend>
        <label><input type="radio" name="q${i}" value="form" checked> 칸대로 <b>${show(q, q.form)}</b></label>
        <label><input type="radio" name="q${i}" value="text"> 설명글대로 <b>${show(q, q.text)}</b></label></fieldset>`).join("")}
      <div class="acts" style="justify-content:flex-end"><button class="btn primary" id="askOk">이대로 계산</button></div>`;
    let done = false;
    const finish = (pick) => { if (!done) { done = true; resolve(pick); } };
    dlg.querySelector("#askOk").addEventListener("click", () => {
      finish(qs.map((_, i) => dlg.querySelector(`input[name=q${i}]:checked`).value));
      dlg.close();
    });
    // 【판단】 Esc 로 닫으면 칸대로 — 사람이 고르지 않은 것은 바꾸지 않는다
    dlg.addEventListener("close", () => finish(qs.map(() => "form")), { once: true });
    dlg.showModal();
  });
}

function setChoice(sel, value) {
  // 【기능】 고르기 칸에 value 가 없으면 하나 더해서라도 고른다(예: 설명글의 "주 5회")
  if (![...sel.options].some((o) => o.value === value)) sel.add(new Option(value, value));
  sel.value = value;
}

async function readText() {
  // 【기능】 [실행] 전에 설명글을 서버가 읽게 하고, 칸과 다르면 묻고, 고른 쪽으로 칸을 바꾼다
  //   돌려주는 값: 진행 기록에 적을 줄 목록
  const $ = (id) => view.querySelector(id);
  const form = { freq: $("#sFreq").value, years: parseInt($("#sYears").value, 10), kind: $("#sKind").value, who: $("#sWho").value,
    money: +$("#sMoney").value || null };
  const r = await post("/api/simulation/read", { text: $("#sText").value, form });
  const notes = [];
  const found = Object.entries(r.found).map(([k, v]) => `${{ freq: "횟수", years: "기간", kind: "종류", who: "대상", money: "돈" }[k]} ${k === "money" ? fmt(v) + "만원" : typeof v === "number" ? v + "년" : v}`);
  notes.push(`설명글에서 읽은 것 · ${found.join(" · ") || "칸과 견줄 낱말 없음"}`);
  // 【판단】 돈 칸이 비었고 설명글에 돈이 있으면 묻지 않고 글의 돈으로 채운다 — 비워 둔 칸은 'AI가 채움'이라서
  if (form.money == null && r.found.money != null) {
    $("#sMoney").value = Math.round(r.found.money);
    notes.push(`돈: 칸이 비어 설명글대로(${fmt(r.found.money)}만원)`);
  }
  if (r.questions.length) {
    const pick = await askDialog(r.questions);
    r.questions.forEach((q, i) => {
      const unit = (v) => (q.field === "money" ? `${fmt(v)}만원` : v);
      if (pick[i] !== "text") return notes.push(`${q.label}: 칸대로(${unit(q.form)})`);
      if (q.field === "money") $("#sMoney").value = Math.round(q.text);
      if (q.field === "freq") setChoice($("#sFreq"), q.text);
      if (q.field === "years") setChoice($("#sYears"), `${Math.min(3, q.text)}년`);
      if (q.field === "kind") setChoice($("#sKind"), q.text);
      if (q.field === "who") setChoice($("#sWho"), q.text);
      notes.push(`${q.label}: 설명글대로(${unit(q.text)}${q.field === "years" && q.text > 3 ? " → 3년까지만 계산" : ""})`);
    });
  }
  r.assumed.forEach((q) => notes.push(`${q.label}: 더 묻지 않고 칸대로(${q.field === "money" ? `${fmt(q.form)}만원` : q.form}) — 한 번에 2개까지만 물어요`));
  if (r.guess) notes.push(`설명글에서 종류를 못 찾아 '${r.guess}'의 효과 값을 빌려 써요`);
  return notes;
}

async function runSim(picked, { again = false } = {}) {
  const B = state.board, err = view.querySelector("#sErr"), run = view.querySelector("#sRun");
  const who = view.querySelector("#sWho").value;
  const target = picked.reduce((s, n) => s + (B.dongs.find((d) => d.dong === n)?.solo80 ?? 0), 0);
  const problems = [];
  if (!picked.length) problems.push("동을 하나 이상 고르세요.");
  if (who.startsWith("80세") && picked.length && target === 0) problems.push("고른 조건에 맞는 분이 0명입니다. 대상이나 동을 넓혀 주세요.");
  err.hidden = !problems.length;
  err.innerHTML = problems.map((p) => `<li>${esc(p)}</li>`).join("");
  if (problems.length) return;
  run.disabled = true;
  let read = again ? ["고친 값으로 다시 계산(설명글은 앞에서 고른 대로)"] : [];
  try {
    if (!again) read = await readText();
  } catch (e) {
    read = [`설명글을 읽지 못해 칸대로 계산해요(${e.message})`];
  }
  const moneyIn = +view.querySelector("#sMoney").value || null;
  const money = moneyIn ?? 800;
  const out = view.querySelector("#sOut");
  const found = state.region === "강남구"
    ? ["이미 하는 사업 · 강남구 사회적 고립가구 고독사 예방사업 1.47억(2025)", "규정 · 강남구 홀로 사는 노인 고독사 예방 및 지원 조례(2017)"] : ["이미 하는 사업 · 지방재정365 연결 중"];
  const steps = [
    ["정리", "입력과 설명글을 읽고 필요한 자료를 찾음", [...found, ...read]],
    ["판단", "종류가 맞는지, 돈 · 시작 시기를 정함", [moneyIn ? `돈 ${fmt(money)}만원(입력)` : "돈 칸이 비어 800만원으로 채움(비슷한 사업 22건 가운데 값)"]],
    ["계산", "가상 주민 만들기 → 정책 얹어 보기 → 여러 번 돌려 보기", []],
    ["설명", "결과를 글로 쓰고 숫자와 맞는지 확인", []],
  ];
  const draw = (k) => (out.innerHTML = `<div class="paper"><h2>진행 기록</h2><ol class="steps4">${steps.map(([t, s, f], i) => `
    <li class="${i < k ? "done" : i === k ? "doing" : ""}"><span class="st">${i < k ? "✓" : i === k ? "⋯" : "○"}</span>
      <div><b>${i + 1}. ${t}</b> <span class="muted">${s}</span>${i < k && f.length ? `<div class="found">${f.map(esc).join("<br>")}</div>` : ""}</div></li>`).join("")}</ol></div>`);
  // 【판단】 계산을 먼저 걸어 두고 진행 기록을 그린다 — 기록이 도는 동안 서버가 계산한다
  const $ = (id) => view.querySelector(id);
  const body = { region: state.region, dongs: picked, who: $("#sWho").value, kind: $("#sKind").value,
    money: moneyIn, years: parseInt($("#sYears").value, 10), order: "무작위", overrides: state.simOverrides ?? {} };
  const job = post("/api/simulation/run", body).then((r) => ({ r }), (e) => ({ e }));
  for (let k = 0; k <= 2; k++) { draw(k); await new Promise((r) => setTimeout(r, 450)); }
  const { r, e } = await job;
  if (e?.problems) {
    // 【기능】 서버가 막은 입력(SIM-100E2) — 결과 자리를 비우고 입력 칸 아래에 고칠 것을 적는다
    err.hidden = false;
    err.innerHTML = e.problems.map((p) => `<li>${esc(p)}</li>`).join("");
    out.innerHTML = "";
    run.disabled = false;
    return;
  }
  steps[2][2] = r ? [`가상 주민으로 ${fmt(r.plan.runs)}번 돌림 · ${r.seconds}초`, `대상 ${fmt(r.target_n)}명 중 1년에 약 ${fmt(r.meet_n)}명을 만남`] : [];
  steps[3][2] = r ? [r.paragraph ? "설명글 속 숫자가 계산 결과와 모두 같음" : `설명글 숫자가 달라 숫자만 보여 줌(${r.paragraph_bad_numbers.join(", ")})`] : [];
  for (let k = 3; k <= steps.length; k++) { draw(k); await new Promise((res) => setTimeout(res, 350)); }
  try {
    // 【판단】 재료 파일이 없는 컴퓨터(404)에서는 노트북 예시 결과로 돈다
    const s = r ? toView(r) : await api("/api/simulation/demo");
    if (!r && e) s.fallback = e.message;
    const used = r ? r.input.money : money;
    out.innerHTML = results(s, picked, used, r ? r.input.money_filled : moneyIn == null);
    drawSimCharts(out, s, picked, used);
    state.sim = { out, s, picked, money: used };
    if (r) wireResult(out, r, picked);
  } catch (e2) {
    out.innerHTML = `<div class="paper"><div class="banner warn"><i class="ti ti-alert-triangle"></i><div><b>계산 중 문제가 생겼습니다.</b><br>입력한 내용은 그대로 있습니다. ${esc(e2.message)}</div></div></div>`;
  }
  out.querySelector("#copy")?.addEventListener("click", () => navigator.clipboard?.writeText(out.querySelector("#para").textContent));
  run.disabled = false;
}

// ── SIM 결과 — 그래프 · 표 ──────────────────────────
// 【판단】 두 안의 색은 dataviz 기준 팔레트 1 · 2번(파랑 · 주황) — 색약 검사 통과(ΔE 24.7)
const SER = { A: "#2a78d6", B: "#eb6834" };
const GRAY = "oklch(0.86 0.02 255)";
// 【기능】 토네이도 칸 이름 → 쉬운 말 · 낮은 쪽 / 높은 쪽 가정 값 (노트북 34단계 RANGES 순서)
const TORN = {
  "평균 머무는 달 (가정)": ["고립이 이어지는 기간", "가정", "12달", "36달"],
  "효과 NNT (근거)": ["몇 명 도와야 1명 나아지나", "연구", "14.4명", "10.3명"],
  "1인당 비용 (근거)": ["1인당 1년 비용", "조사", "107만원", "98만원"],
  "사업 기간 (선택)": ["사업 기간", "고를 수 있음", "1년", "3년"],
  "누구부터 (선택)": ["누구부터 만나나", "고를 수 있음", "무작위", "고립자 먼저"],
};
const n1 = (v) => (Math.round(v * 10) / 10).toFixed(1);
const niceMax = (v, step) => Math.ceil(v / step) * step;

function toView(r) {
  // 【기능】 /api/simulation/run 결과를 결과 화면이 그리는 모양(A · B 두 안)으로 바꾼다
  const x = r.input, A = r.plan, B = r.compare;
  const name = (o) => `${o === "모델 위험 순" ? "위험 높은 분 먼저" : o} ${x.years}년`;
  // 【판단】 청년의 비교 안은 '알려서 신청받기'(10-29) — 머리글도 그 말로 쓴다
  const bWay = B.order === APPLY ? "알려서 신청받은 청년을 만나는 쪽" : "위험이 높은 분부터 만나는 쪽";
  const a = A.final.median, b = B.final.median;
  const headline = b > a + 0.4 ? `같은 돈이면 ${bWay}이 3년 뒤 더 줄인다(${n1(b)}명 대 ${n1(a)}명)`
    : a > b + 0.4 ? `같은 돈이면 지금 안(${x.order})이 3년 뒤 더 줄인다(${n1(a)}명 대 ${n1(b)}명)`
    : `두 방법의 차이가 작다 — 3년 뒤 ${n1(a)}명 대 ${n1(b)}명`;
  return {
    live: r, dong: x.dongs.join("·"), years: 3, headline,
    plans: { A: { desc: name(x.order), ...A.final }, B: { desc: name(B.order), ...B.final }, prob_b_better: r.prob_compare_better },
    path: { months: [...Array(37).keys()], A: A.path, B: B.path },
    yearly: { A: A.yearly, B: B.yearly },
    stop: x.years * 12 < 36 ? x.years * 12 : null,
    tornado: r.tornado.rows, tornadoBase: r.tornado.base,
  };
}

function costRow(s) {
  // 【기능】 결과 표 맨 아래 '1인당 1년 비용' 줄 — 계산에 실제로 쓴 값(고친 값 포함)과 그 종류의 범위
  // 【판단】 10-25 이 줄이 종류와 상관없이 100 · 102 · 105만원으로 고정이었다(함께 모이는 활동은
  //        14 ~ 35만원). 엔진은 해마다 같은 비용으로 계산하므로 해마다 나누지 않고 한 칸으로 쓴다
  const used = s.live?.used;
  const range = used ? used.cost_range : s.assumptions?.cost_won;
  const cost = used ? used.cost : range && (range[0] + range[1]) / 2;
  if (cost == null) return "";
  const span = range ? ` (범위 ${fmt(range[0] / 10_000)} ~ ${fmt(range[1] / 10_000)}만원)` : "";
  return `<tr><td class="sv-row">1인당 1년 비용</td><td colspan="3">${fmt(cost / 10_000)}만원 · 3년 같게 둠${span}</td></tr>`;
}

function results(s, picked, money, filled) {
  const A = s.plans.A, B = s.plans.B, star = s.tornado.slice().sort((a, b) => b.swing - a.swing)[0];
  const youthWho = s.live && isYouth(s.live.input.who);
  const order = picked.map((n) => state.board.dongs.find((d) => d.dong === n)).filter(Boolean)
    .sort((a, b) => youthWho ? (b.youth?.homebound?.hi ?? 0) - (a.youth?.homebound?.hi ?? 0) : (b.visit_fewer_upper ?? 0) - (a.visit_fewer_upper ?? 0));
  const y1 = s.yearly;
  const early = y1 && y1.B[0] > y1.A[0]
    ? `1년째에는 B 가 ${n1(y1.B[0])}명으로 A(${n1(y1.A[0])}명)보다 많이 줄이지만, 1년 반에 멈춘 뒤 효과가 빠져 3년 뒤에는 A 가 앞서요.` : "";
  const tile = (label, color, v, sub) => `<div class="sv-stat"><div class="sv-k">${color ? `<i class="sv-sw" style="background:${color}"></i>` : ""}${label}</div>
    <div class="sv-v">${v}</div><div class="sv-s">${sub}</div></div>`;
  const L = s.live;
  const banner = L
    ? `<div class="banner ok" style="margin-bottom:14px"><i class="ti ti-circle-check"></i><div>고른 <b>${esc(s.dong)}</b> · ${esc(L.input.who)} · ${esc(L.input.kind)} · 1년 ${man(money)}으로 계산했어요${Object.keys(L.input.overrides ?? {}).length ? " · <b>고친 값 있음</b>" : ""}. 모르는 값을 바꿔 가며 ${fmt(L.plan.runs)}번 돌렸어요(${L.seconds}초).${isYouth(L.input.who) ? `<br>청년 ${fmt(L.target_n)}명 중 고립(은둔)은 <b>거의 집에만 있는 청년 어림 ${fmt(L.plan.target_isolated_n)}명</b>으로 맞췄어요(청년의 삶 실태조사 2024 비율). 누가 은둔인지는 몰라 청년 중에서 고르게 골랐어요.<br>그래서 B 는 점수 순이 아니라 <b>알려서 신청받기</b>예요 — 손을 든 청년 중에서 만나요. 한 해 신청은 은둔 · 고립 청년의 0.87 ~ 3.6%, 신청자 중 대상은 40 ~ 57%(서울 2024 · 2025, 복지부 2023 실적)로 두고 바꿔 가며 돌렸어요. 돈이 많아도 신청한 사람보다 많이 만나지는 못해요.` : ""}</div></div>`
    : `<div class="banner warn" style="margin-bottom:14px"><i class="ti ti-info-circle"></i><div>이 컴퓨터에 시뮬레이션 재료가 없어 노트북에서 계산한 <b>${esc(s.dong)} · 방문 1억 · ${s.years}년</b> 예시를 보여요.${s.fallback ? ` (${esc(s.fallback)})` : ""}</div></div>`;
  const few = L ? A.median < 1 : money < 3000;
  return `${banner}
  ${few ? `<div class="paper" style="margin-bottom:14px"><h2>${man(money)}이면 고립 위험이 거의 그대로입니다</h2>
    <p style="color:var(--sub)">${L ? `${man(money)} ÷ 1인당 1년 ${fmt(L.used.cost / 10_000)}만원 = 1년에 약 ${fmt(L.meet_n)}명을 만나요. 대상 ${fmt(L.target_n)}명 중 ${pct(L.meet_n / Math.max(L.target_n, 1), 0)}예요.` : `${fmt(money)}만원 ÷ 1인당 1년 100만원 = 약 ${Math.floor(money / 100)}명을 만날 수 있어요.`} 동 하나를 바꾸기에는 적어요.${L ? " 아래 '목표에서 거꾸로'로 얼마가 필요한지 볼 수 있어요." : ""}</p></div>` : ""}

  <div class="paper fold"><h2>${esc(s.headline)}</h2>
    <p class="sv-lead">같은 돈 · 같은 동에서 ${L ? "누구부터 만나느냐만 다른" : ""} 두 가지 방법을 비교했어요. 숫자는 <b>사업을 안 했을 때보다 고립 위험인 사람이 몇 명 줄었나</b>예요.</p>
    <div class="sv-stats">
      ${tile("A · " + esc(A.desc), SER.A, `${n1(A.median)}명`, `3년 뒤 · 범위 ${n1(A.p10)} ~ ${n1(A.p90)}명`)}
      ${tile("B · " + esc(B.desc), SER.B, `${n1(B.median)}명`, `3년 뒤 · 범위 ${n1(B.p10)} ~ ${n1(B.p90)}명`)}
      ${tile("B 가 A 보다 나을 확률", "", `${Math.round(s.plans.prob_b_better * 100)}%`, `모르는 값을 ${L ? 50 : 100}번 바꿔 돌린 결과`)}
    </div>
    ${s.path ? `<h3 class="sv-h">달마다 몇 명 줄었나</h3>
    <div class="sv-legend"><span><i class="sv-sw" style="background:${SER.A}"></i>A ${esc(A.desc)}</span><span><i class="sv-sw" style="background:${SER.B}"></i>B ${esc(B.desc)}</span><span><i class="sv-band"></i>옅은 띠 = 10 ~ 90% 범위</span></div>
    <div class="sv-viz" id="vPath"></div>
    ${read(`가로는 시작부터 지난 달, 세로는 줄어든 사람 수예요. 0 선이 정책이 없을 때예요. 선 위에 마우스를 올리면 그 달의 값이 보여요. ${L ? "" : early}`)}
    <table class="ytable sv-table"><thead><tr><th>줄어든 고립 위험</th><th>1년째</th><th>2년째</th><th>3년째</th></tr></thead><tbody>
      ${["A", "B"].map((k) => `<tr><td class="sv-row"><i class="sv-sw" style="background:${SER[k]}"></i>${k} ${esc(s.plans[k].desc)}</td>${y1[k].map((v) => `<td>${n1(v)}명</td>`).join("")}</tr>`).join("")}
      ${costRow(s)}</tbody></table>` : ""}
  </div>

  <div class="paper" style="margin-top:14px"><h2>무엇이 결과를 가장 크게 흔드나</h2>
    <p class="sv-lead">값 하나만 낮은 쪽 · 높은 쪽으로 바꾸고 나머지는 그대로 둔 채 3년 뒤 줄어든 사람 수를 다시 셌어요. 막대가 길수록 그 값에 따라 결과가 크게 달라져요.</p>
    <div class="sv-viz" id="vTorn"></div>
    ${read(`가운데 세로선은 기본 가정(${n1(s.tornadoBase ?? 3.6)}명)이에요. <b>'${esc(TORN[star.name]?.[0] ?? star.name)}'</b>이 가장 크게 흔들어요. '고를 수 있음' 값은 정책으로 정할 수 있는 것이에요.`)}
  </div>

  <div class="paper" style="margin-top:14px"><h2>같은 1억, 어느 동에서 가장 많이 줄까</h2>
    <p class="sv-lead">동마다 1억으로 3년 동안 찾아갔을 때 줄어드는 사람 수예요. <b>진한 막대</b>는 무작위로 만날 때, <b>옅은 끝</b>은 고립인 분을 먼저 만날 때(상한)예요.</p>
    <div class="sv-legend"><span><i class="sv-sw" style="background:${SER.A}"></i>고른 동</span><span><i class="sv-sw" style="background:${GRAY}"></i>다른 동</span></div>
    <div class="sv-viz" id="vDong"></div>
    ${read(`고른 동: ${order.map((d) => `${esc(d.dong)} ${n1(d.visit_fewer_random)} ~ ${n1(d.visit_fewer_upper)}명`).join(" · ") || "–"}${order.find((d) => d.helpers === 0) ? ` · ${esc(order.find((d) => d.helpers === 0).dong)}은 도와줄 기관이 없어 연결부터 필요해요` : ""}`)}
  </div>

  <div class="grid g2" style="margin-top:14px">
    <div class="paper"><h2>돈 비교 (1년)</h2><div class="sv-viz" id="vMoney"></div>
      ${read(`가운데 값 800만원은 전국 방문 · 안부 사업 22건의 가운데예요${filled ? " · <b>돈 칸이 비어 이 값으로 채웠어요</b>" : ""}.`)}</div>
    <div class="paper"><h2>계산에 쓴 값</h2>
      ${L ? usedTable(L) : `<table class="ytable sv-table sv-left"><thead><tr><th>값</th><th>쓴 값</th><th>어디서</th></tr></thead><tbody>
        <tr><td>1인당 1년 비용</td><td>100만원</td><td>노인맞춤돌봄 98 ~ 107만원(조사)</td></tr>
        <tr><td>몇 명 도와야 1명 나아지나</td><td>12.3명</td><td>안부확인 연구 10.3 ~ 14.4명</td></tr>
        <tr><td>고립이 이어지는 기간</td><td>24달</td><td>우리 가정 · 12 ~ 36달로 흔듦</td></tr>
        <tr><td>여러 번 돌리기</td><td>100번 × 20</td><td>모르는 값 100번 × 주사위 20번</td></tr></tbody></table>`}</div>
  </div>

  ${L ? `<div class="paper" style="margin-top:14px" id="reverseBox"><h2>목표에서 거꾸로 — 얼마면 되나</h2>
    <p class="sv-lead">3년 뒤 줄이고 싶은 사람 수를 넣으면, 같은 동 · 대상 · 종류로 1년에 최소 얼마가 드는지 찾아요.</p>
    <div class="form goal-form"><label for="goal">목표 (3년 뒤 줄일 사람, 명)</label>
      <div class="goal-row"><input id="goal" type="number" min="0.5" step="0.5" value="${Math.max(1, Math.ceil(A.median + 1))}">
      <button class="btn primary" id="goalRun"><i class="ti ti-calculator"></i>계산</button></div></div>
    <div id="goalOut" style="margin-top:10px"></div></div>` : ""}

  <div class="paper" style="margin-top:14px"><h2>AI 제안</h2><div class="grid g2">
    <div><b>돈은 보통 얼마</b><p style="color:var(--sub);margin:4px 0">찾아가서 살피기 · 1년 800만원(전국 22건 가운데 값), 많이 쓰는 곳 5,600만원</p></div>
    <div><b>어느 동부터</b><p style="color:var(--sub);margin:4px 0">${order.map((d) => esc(d.dong)).join(" → ") || "–"} (${youthWho ? "거의 집에만 있는 청년 어림이 많은 순서" : "1억 효과가 큰 순서"})</p></div>
    <div><b>언제 시작</b><p style="color:var(--sub);margin:4px 0">10월 · 효과가 나기까지 3개월(가정). 한파 전에 자리 잡게</p></div>
    <div><b>${L ? "누구부터" : "얼마나 오래"}</b><p style="color:var(--sub);margin:4px 0">${L ? `${L.compare?.order === APPLY ? "알려서 신청받은 청년을 만나면" : "위험이 높은 분부터 만나면"} 3년 뒤 ${n1(B.median)}명(지금 안 ${n1(A.median)}명) · 더 나을 확률 ${Math.round(s.plans.prob_b_better * 100)}%` : `끊지 말고 3년 · 1년 반에 멈추면 3년 뒤 효과가 ${n1(A.median - B.median)}명 작아요`}</p></div></div>
    <h2 style="margin-top:14px">설명글</h2>
    <div class="para" id="para">${L ? (L.paragraph ? esc(L.paragraph) : `숫자만: 3년 뒤 ${n1(A.p10)}~${n1(A.p90)}명(가운데 ${n1(A.median)}명)`) : `${esc(picked.join("·"))} ${esc(view.querySelector("#sWho").value)}께 ${esc(view.querySelector("#sFreq").value)} 찾아가면, ${esc(s.dong)} 예시 계산 기준으로 3년 뒤 고립 위험이 ${n1(A.p10)} ~ ${n1(A.p90)}명(가운데 ${n1(A.median)}명) 줄 것으로 보입니다. 결과를 가장 크게 흔드는 값은 '${esc(TORN[star.name]?.[0] ?? star.name)}'입니다. 한계: 카드 자료는 구 단위라 동 값은 추정이고, 효과 값은 다른 지역 연구에서 빌렸습니다.`}</div>
    <div class="acts"><button class="btn" id="copy"><i class="ti ti-copy"></i>복사</button></div>
    <p class="privacy">이 결과는 추정입니다. 실제로 해 보면 다를 수 있고, 위 값을 어떻게 두느냐에 따라 달라집니다.</p></div>`;
}

const FIX = {
  cost: { label: "1인당 1년 비용", unit: "만원", toApi: (v) => v * 10_000, fromApi: (v) => v / 10_000 },
  nnt: { label: "몇 명 도와야 1명 나아지나", unit: "명", toApi: (v) => v, fromApi: (v) => v },
  base_stay: { label: "고립이 이어지는 기간", unit: "달", toApi: (v) => v, fromApi: (v) => v },
};

function wireResult(out, r, picked) {
  // 【기능】 결과 화면의 버튼들 — [고치기](SIM-106) · 되돌리기 · 거꾸로 계산(SIM-108)
  out.querySelectorAll("[data-fix]").forEach((b) => b.addEventListener("click", () => {
    const key = b.dataset.fix, f = FIX[key], now = f.fromApi(r.used[key]);
    const [lo, hi] = (key === "cost" ? r.used.cost_range : key === "nnt" ? r.used.nnt_range : r.used.stay_range).map(f.fromApi);
    openDialog(`<h2>${f.label} 고치기</h2><p class="muted">이 값 하나만 바꿔 다시 계산해요. 지금 ${n1(now)}${f.unit} · 근거 범위 ${n1(lo)} ~ ${n1(hi)}${f.unit}</p>
      <div class="form"><label for="fixVal">새 값 (${f.unit})</label><input id="fixVal" type="number" min="0.1" step="0.1" value="${n1(now)}"></div>
      <ul class="err-list" id="fixErr" hidden></ul>
      <div class="acts"><button class="btn primary" id="fixGo"><i class="ti ti-refresh"></i>이 값으로 다시 계산</button></div>`);
    dlg.querySelector("#fixGo").addEventListener("click", () => {
      const v = parseFloat(dlg.querySelector("#fixVal").value);
      if (!(v > 0)) {
        const e = dlg.querySelector("#fixErr");
        e.hidden = false;
        e.innerHTML = "<li>0보다 큰 숫자를 넣어 주세요.</li>";
        return;
      }
      state.simOverrides = { ...(state.simOverrides ?? {}), [key]: f.toApi(v) };
      dlg.close();
      runSim(picked, { again: true });
    });
  }));
  out.querySelector("#fixReset")?.addEventListener("click", () => { state.simOverrides = {}; runSim(picked, { again: true }); });
  out.querySelector("#goalRun")?.addEventListener("click", async () => {
    const goal = parseFloat(out.querySelector("#goal").value), box = out.querySelector("#goalOut");
    if (!(goal > 0)) return (box.innerHTML = `<p class="err">0보다 큰 목표를 넣어 주세요.</p>`);
    box.innerHTML = `<p class="muted">돈을 바꿔 가며 찾는 중…</p>`;
    try {
      const x = r.input;
      const g = await post("/api/simulation/reverse", { region: x.region, dongs: x.dongs, who: x.who, kind: x.kind, goal, years: x.years, order: x.order, overrides: x.overrides ?? {} });
      if (g.budget == null) {
        box.innerHTML = `<div class="banner warn"><i class="ti ti-alert-triangle"></i><div>대상 ${fmt(r.target_n)}명을 모두 만나도(1년 약 ${man(g.all_budget / 10_000)}) 3년 뒤 약 ${n1(g.best)}명까지예요. 목표 ${n1(goal)}명은 돈만으로는 안 돼요 — 대상이나 종류를 바꿔 보세요.</div></div>`;
        return;
      }
      box.innerHTML = `<div class="sv-stats" style="grid-template-columns:repeat(2,minmax(0,1fr))">
          <div class="sv-stat"><div class="sv-k">1년에 최소</div><div class="sv-v">${man(g.budget / 10_000)}</div><div class="sv-s">가운데 값 기준 · 100만원 단위 올림</div></div>
          <div class="sv-stat"><div class="sv-k">대상을 모두 만나면</div><div class="sv-v">${n1(g.best)}명</div><div class="sv-s">1년 약 ${man(g.all_budget / 10_000)}</div></div></div>
        ${state.region === "강남구" ? `<p class="privacy">강남구가 지금 쓰는 고독사 예방사업은 1년 1.47억이에요.</p>` : ""}
        <div class="acts"><button class="btn primary" id="goalUse"><i class="ti ti-player-play"></i>이 금액으로 다시 계산</button></div>`;
      box.querySelector("#goalUse").addEventListener("click", () => {
        view.querySelector("#sMoney").value = Math.round(g.budget / 10_000);
        runSim(picked, { again: true });
        view.querySelector("#sOut").scrollIntoView({ behavior: "smooth" });
      });
    } catch (e) {
      box.innerHTML = `<p class="err">${esc(e.message)}</p>`;
    }
  });
}

const man = (v) => (v >= 10_000 ? `${(v / 10_000).toFixed(v % 10_000 ? 2 : 0)}억` : `${fmt(v)}만원`);

function usedTable(L) {
  // 【기능】 계산에 쓴 값(SIM-106) — 이번 계산의 가운데 값 · 흔든 범위 · 출처
  const u = L.used, over = L.input.overrides ?? {};
  const fix = (key) => `<button class="pill fix" data-fix="${key}" aria-label="${FIX[key].label} 고치기"><i class="ti ti-pencil"></i><span>고치기</span></button>${key in over ? ` <span class="wk">고친 값</span>` : ""}`;
  const range = (key, txt) => (key in over ? "이 값 하나로 고정해 계산" : txt);
  return `<table class="ytable sv-table sv-left"><thead><tr><th>값</th><th>쓴 값</th><th>흔든 범위 · 어디서</th><th></th></tr></thead><tbody>
    <tr><td>1인당 1년 비용</td><td>${fmt(u.cost / 10_000)}만원</td><td>${range("cost", `${fmt(u.cost_range[0] / 10_000)} ~ ${fmt(u.cost_range[1] / 10_000)}만원`)}</td><td>${fix("cost")}</td></tr>
    <tr><td>몇 명 도와야 1명 나아지나</td><td>${n1(u.nnt)}명</td><td>${range("nnt", `${u.nnt_range[0]} ~ ${u.nnt_range[1]}명`)}</td><td>${fix("nnt")}</td></tr>
    <tr><td>고립이 이어지는 기간</td><td>${fmt(u.base_stay)}달</td><td>${range("base_stay", `${u.stay_range[0]} ~ ${u.stay_range[1]}달 · 우리 가정`)}</td><td>${fix("base_stay")}</td></tr>
    <tr><td>보수적으로(효과 절반)</td><td>${n1(L.safe.median)}명</td><td>전후 비교 연구 → 무작위 대조 연구로 보면 효과 약 절반</td><td></td></tr>
    <tr><td>여러 번 돌리기</td><td>50번 × 20</td><td>모르는 값 50번 × 주사위 20번</td><td></td></tr></tbody></table>
    ${Object.keys(over).length ? `<div class="acts"><button class="btn" id="fixReset"><i class="ti ti-arrow-back-up"></i>고친 값 모두 되돌리기</button></div>` : ""}
    <p class="privacy">${esc(L.kind_src)}</p>`;
}

function drawSimCharts(out, s, picked, money) {
  // 【판단】 그래프는 들어갈 칸의 실제 너비로 그린다 → 폰에서도 글자가 작아지지 않는다
  const W = (id) => Math.max(300, out.querySelector(id)?.clientWidth || 600);
  if (s.path) pathChart(out.querySelector("#vPath"), s, W("#vPath"));
  tornadoChart(out.querySelector("#vTorn"), s, W("#vTorn"));
  dongChart(out.querySelector("#vDong"), picked, W("#vDong"));
  moneyChart(out.querySelector("#vMoney"), money, W("#vMoney"));
}

function pathChart(box, s, w) {
  // 【기능】 달마다 줄어든 사람 수 — 두 안의 가운데 선 + 10~90% 띠, B 가 멈추는 18달에 세로 점선
  const P = s.path, h = 260, L = 40, R = 76, T = 14, Bm = 30;
  const stop = s.live ? s.stop : 18;
  const top = niceMax(Math.max(...P.A.p90, ...P.B.p90), 3);
  const X = (m) => L + (m * (w - L - R)) / 36, Y = (v) => T + ((top - v) * (h - T - Bm)) / top;
  const pts = (arr) => arr.map((v, m) => `${X(m).toFixed(1)},${Y(v).toFixed(1)}`).join(" ");
  const band = (k) => `<polygon fill="${SER[k]}" fill-opacity=".13" points="${pts(P[k].p90)} ${P[k].p10.map((v, m) => [X(m), Y(v)]).reverse().map(([x, y]) => `${x.toFixed(1)},${y.toFixed(1)}`).join(" ")}"/>`;
  const grid = [0, top / 3, (2 * top) / 3, top].map((v) => `<line x1="${L}" x2="${w - R}" y1="${Y(v)}" y2="${Y(v)}" stroke="var(--line)"/>
    <text x="${L - 8}" y="${Y(v) + 4}" font-size="12" text-anchor="end" fill="var(--faint)">${v}</text>`).join("");
  const xt = [[0, "시작"], [12, "1년"], [24, "2년"], [36, "3년"]].map(([m, t]) => `<text x="${X(m)}" y="${h - 8}" font-size="12" text-anchor="middle" fill="var(--faint)">${t}</text>`).join("");
  const endA = P.A.median[36], endB = P.B.median[36];
  const [ya, yb] = Math.abs(Y(endA) - Y(endB)) < 16 ? [Y(endA) - 8, Y(endB) + 8] : [Y(endA), Y(endB)];
  box.innerHTML = `<svg viewBox="0 0 ${w} ${h}" width="${w}" height="${h}" role="img" aria-label="달마다 줄어든 고립 위험 인원 — A 와 B">
    ${grid}${xt}${band("A")}${band("B")}
    ${stop == null ? "" : `<line x1="${X(stop)}" x2="${X(stop)}" y1="${T}" y2="${h - Bm}" stroke="var(--sub)" stroke-dasharray="3 4"/>
    <text x="${X(stop) + 6}" y="${T + 12}" font-size="12" fill="var(--sub)">${s.live ? "사업 끝" : "B 멈춤(1년 반)"}</text>`}
    <text x="${L + 6}" y="${Y(0) - 6}" font-size="11" fill="var(--faint)">0 = 정책 없을 때</text>
    <polyline fill="none" stroke="${SER.A}" stroke-width="2" stroke-linejoin="round" points="${pts(P.A.median)}"/>
    <polyline fill="none" stroke="${SER.B}" stroke-width="2" stroke-linejoin="round" points="${pts(P.B.median)}"/>
    <text x="${X(36) + 8}" y="${ya + 4}" font-size="13" font-weight="700" fill="var(--ink)">A ${n1(endA)}명</text>
    <text x="${X(36) + 8}" y="${yb + 4}" font-size="13" font-weight="700" fill="var(--ink)">B ${n1(endB)}명</text>
    <g class="sv-cross" style="opacity:0"><line y1="${T}" y2="${h - Bm}" stroke="var(--ink)" stroke-opacity=".35"/>
      <circle r="4.5" fill="${SER.A}" stroke="var(--paper)" stroke-width="2"/><circle r="4.5" fill="${SER.B}" stroke="var(--paper)" stroke-width="2"/></g>
    <rect x="${L}" y="${T}" width="${w - L - R}" height="${h - T - Bm}" fill="transparent" class="sv-hit"/></svg><div class="sv-tip" hidden></div>`;
  const svg = box.querySelector("svg"), cross = svg.querySelector(".sv-cross"), tip = box.querySelector(".sv-tip");
  const [line, ca, cb] = cross.children;
  const show = (ev) => {
    const r = svg.getBoundingClientRect(), x = ((ev.clientX - r.left) * w) / r.width;
    const m = Math.max(0, Math.min(36, Math.round(((x - L) * 36) / (w - L - R))));
    line.setAttribute("x1", X(m)); line.setAttribute("x2", X(m));
    ca.setAttribute("cx", X(m)); ca.setAttribute("cy", Y(P.A.median[m]));
    cb.setAttribute("cx", X(m)); cb.setAttribute("cy", Y(P.B.median[m]));
    cross.style.opacity = 1;
    tip.hidden = false;
    tip.innerHTML = `<b>${m === 0 ? "시작" : m + "달째"}</b>${["A", "B"].map((k) => `<div><i class="sv-sw" style="background:${SER[k]}"></i>${k} ${n1(P[k].median[m])}명 <span class="muted">(${n1(P[k].p10[m])} ~ ${n1(P[k].p90[m])})</span></div>`).join("")}`;
    const left = (X(m) * r.width) / w;
    tip.style.left = `${Math.min(left + 12, r.width - tip.offsetWidth - 4)}px`;
    tip.style.top = "8px";
  };
  const hide = () => { cross.style.opacity = 0; tip.hidden = true; };
  const hit = svg.querySelector(".sv-hit");
  hit.addEventListener("pointermove", show);
  hit.addEventListener("pointerdown", show);
  hit.addEventListener("pointerleave", hide);
}

function hbars(rows, w, { labelW = 120, valueW = 120, max, ref } = {}) {
  // 【기능】 가로 막대 공통 — rows: {label, sub, from, to, ext, color, title, right, short}
  // 【판단】 폭이 좁으면(폰) 이름을 막대 위 한 줄로 올리고, 오른쪽 글은 짧은 것(short)을 쓴다
  const narrow = w < 520;
  if (narrow) { labelW = 0; valueW = 78; }
  const rowH = narrow ? 44 : 34, h = rows.length * rowH + 22, x0 = narrow ? 4 : labelW, x1 = w - valueW;
  const X = (v) => x0 + ((x1 - x0) * v) / max;
  const ticks = [0, max / 2, max].map((v) => `<line x1="${X(v)}" x2="${X(v)}" y1="0" y2="${h - 20}" stroke="var(--line)"/>
    <text x="${X(v)}" y="${h - 4}" font-size="12" text-anchor="middle" fill="var(--faint)">${fmt(v)}</text>`).join("");
  const body = rows.map((r, i) => {
    const y = i * rowH + (narrow ? 2 : 6), by = narrow ? y + 20 : y + 4, a = X(r.from ?? 0), b = X(r.to);
    const label = narrow
      ? `<text x="${x0}" y="${y + 12}" font-size="13" fill="var(--ink)" font-weight="${r.bold ? 700 : 500}">${esc(r.label)}${r.sub ? `<tspan font-size="11" font-weight="400" fill="var(--faint)"> · ${esc(r.sub)}</tspan>` : ""}</text>`
      : `<text x="${labelW - 10}" y="${y + 13}" font-size="13" text-anchor="end" fill="var(--ink)" font-weight="${r.bold ? 700 : 500}">${esc(r.label)}</text>
      ${r.sub ? `<text x="${labelW - 10}" y="${y + 27}" font-size="11" text-anchor="end" fill="var(--faint)">${esc(r.sub)}</text>` : ""}`;
    return `<g><title>${esc(r.title ?? "")}</title>${label}
      ${r.ext != null ? `<rect x="${b}" y="${by}" width="${Math.max(0, X(r.ext) - b)}" height="14" rx="4" fill="${r.color}" fill-opacity=".35"/>` : ""}
      <rect x="${a}" y="${by}" width="${Math.max(2, b - a)}" height="14" rx="4" fill="${r.color}"/>
      <text x="${x1 + 8}" y="${by + 11}" font-size="12" fill="var(--sub)">${narrow ? (r.short ?? r.right) : r.right}</text></g>`;
  }).join("");
  // 【판단】 좁을 때는 기준선을 막대 높이에만 긋는다 — 막대 위 이름 글자를 가로지르지 않게
  const refLine = ref == null ? "" : narrow
    ? rows.map((_, i) => `<line x1="${X(ref)}" x2="${X(ref)}" y1="${i * rowH + 18}" y2="${i * rowH + 40}" stroke="var(--ink)" stroke-dasharray="3 3"/>`).join("")
    : `<line x1="${X(ref)}" x2="${X(ref)}" y1="0" y2="${h - 20}" stroke="var(--ink)" stroke-dasharray="3 3"/>`;
  return `<svg viewBox="0 0 ${w} ${h}" width="${w}" height="${h}" role="img">${ticks}${body}${refLine}</svg>`;
}

function tornadoChart(box, s, w) {
  // 【기능】 토네이도 — 값 하나씩 낮은 쪽 · 높은 쪽으로 바꿨을 때 3년 뒤 결과의 폭, 흔드는 순서대로
  const rows = s.tornado.slice().sort((a, b) => b.swing - a.swing).map((t, i) => {
    // 【판단】 서버 결과는 행마다 이름 · 출처 · 양 끝 값 글을 이미 준다. 노트북 예시는 TORN 표로 바꾼다
    const [name, src, lo, hi] = TORN[t.name] ?? [t.name, t.src ?? "", t.lo_label ?? "낮게", t.hi_label ?? "높게"];
    const narrow = w < 520;
    return { label: name, sub: narrow ? `${lo} ↔ ${hi}` : src, from: Math.min(t.lo, t.hi), to: Math.max(t.lo, t.hi), bold: i === 0,
      color: src === "고를 수 있음" ? SER.A : "oklch(0.62 0.05 255)",
      right: `${n1(t.lo)}명(${lo}) ~ ${n1(t.hi)}명(${hi})`, short: `${n1(Math.min(t.lo, t.hi))}~${n1(Math.max(t.lo, t.hi))}명`, title: `${name}: ${lo} → ${n1(t.lo)}명, ${hi} → ${n1(t.hi)}명` };
  });
  const max = niceMax(Math.max(...s.tornado.map((t) => Math.max(t.lo, t.hi))), 2);
  box.innerHTML = hbars(rows, w, { labelW: Math.min(190, w * 0.36), valueW: Math.min(210, w * 0.36), max, ref: s.tornadoBase ?? 3.6 })
    + `<div class="sv-legend"><span><i class="sv-sw" style="background:${SER.A}"></i>정책으로 고를 수 있는 값</span><span><i class="sv-sw" style="background:oklch(0.62 0.05 255)"></i>모르는 값(연구 · 조사 · 가정)</span><span><i class="sv-dash"></i>기본 가정 ${n1(s.tornadoBase ?? 3.6)}명</span></div>`;
}

function dongChart(box, picked, w) {
  // 【기능】 동마다 1억 효과 — 효과 큰 동 8곳 + 고른 동(8곳 밖이어도 넣는다)
  const all = state.board.dongs.filter((d) => d.visit_fewer_random != null).sort((a, b) => b.visit_fewer_random - a.visit_fewer_random);
  if (!all.length) return (box.innerHTML = `<p class="muted">동별 1억 효과 자료가 없어요(노트북 36단계).</p>`);
  const show = [...all.slice(0, 8), ...all.slice(8).filter((d) => picked.includes(d.dong))];
  const max = niceMax(Math.max(...show.map((d) => d.visit_fewer_upper)), 2);
  // 【판단】 상한(고립자 먼저)이 무작위보다 낮게 나온 동이 있다(도곡2동 4.7 > 4.3) — 주사위 20번의 흔들림.
  //   그때는 옅은 끝을 그리지 않고 숫자는 작은 쪽 ~ 큰 쪽으로 적는다
  const rows = show.map((d) => ({ label: `${all.indexOf(d) + 1}. ${d.dong}`, from: 0, to: d.visit_fewer_random,
    ext: d.visit_fewer_upper > d.visit_fewer_random ? d.visit_fewer_upper : null,
    color: picked.includes(d.dong) ? SER.A : GRAY, bold: picked.includes(d.dong),
    right: `${n1(Math.min(d.visit_fewer_random, d.visit_fewer_upper))} ~ ${n1(Math.max(d.visit_fewer_random, d.visit_fewer_upper))}명`, title: `${d.dong}: 무작위 ${n1(d.visit_fewer_random)}명 · 고립자 먼저 ${n1(d.visit_fewer_upper)}명` }));
  box.innerHTML = hbars(rows, w, { labelW: Math.min(130, w * 0.34), valueW: 104, max });
}

function moneyChart(box, money, w) {
  // 【기능】 1년 돈 — 이 정책 · 전국 가운데 · 많이 쓰는 곳 · (강남) 지금 사업
  const items = [["이 정책", money, SER.A], ["전국 가운데", 800, GRAY], ["많이 쓰는 곳", 5600, GRAY]];
  if (state.region === "강남구") items.push(["강남구 지금 사업", 14700, GRAY]);
  const max = niceMax(Math.max(...items.map((i) => i[1])), 5000);
  const rows = items.map(([label, v, color]) => ({ label, to: v, color, bold: label === "이 정책",
    right: v >= 10000 ? `${(v / 10000).toFixed(2)}억` : `${fmt(v)}만원`, title: `${label} ${fmt(v)}만원` }));
  box.innerHTML = hbars(rows, w, { labelW: 104, valueW: 76, max });
}

// ── 길 찾기 ─────────────────────────────────────────
const ROUTES = { login: authPage, signup: authPage, find: authPage, assistant, dashboard, simulation };
function go(path) { location.hash = "#/" + path; }
async function whoAmI() {
  const res = await fetch("/api/auth/me");
  return res.ok ? (await res.json()).member : null;
}
async function render() {
  const name = (location.hash.replace(/^#\//, "").split("/")[0]) || "dashboard";
  if (AUTH_PAGES.includes(name)) return authPage();
  // 【판단】 10-25 팀장 "로그인해야지만 가능하게" — 회원이 아니면 로그인 화면으로, 로그인하면 이 화면으로
  state.member = state.member || (await whoAmI());
  if (!state.member) {
    sessionStorage.setItem("salpim_return", JSON.stringify(location.hash.replace(/^#\//, "") || "dashboard"));
    return go("login");
  }
  if (!state.meta) await loadMeta();
  // 【기능】 담당 지역은 회원 정보(가입할 때 고른 동의 시군구) — 스토리보드 COM-150
  const mine = state.member.regions.map((r) => r.sgg);
  state.region = mine.find((r) => state.meta.regions.includes(r)) || state.meta.regions[0];
  nav.hidden = false;
  document.getElementById("who").textContent = `${state.region} 담당 · ${state.member.name}`;
  document.querySelectorAll(".menu a").forEach((a) => a.classList.toggle("on", a.dataset.route === name));
  view.innerHTML = `<div class="empty" style="padding-top:140px">불러오는 중…</div>`;
  try { await (ROUTES[name] || dashboard)(); } catch (e) { view.innerHTML = pageHead("오류", "화면을 불러오지 못했어요") + `<div class="wrap empty err">${esc(e.message)}</div>`; }
  window.scrollTo(0, 0);
}

// 【기능】 창 너비가 바뀌면 시뮬레이션 그래프를 새 너비로 다시 그린다
let resizeTimer;
window.addEventListener("resize", () => {
  clearTimeout(resizeTimer);
  resizeTimer = setTimeout(() => {
    const v = state.sim;
    if (v && document.body.contains(v.out)) drawSimCharts(v.out, v.s, v.picked, v.money);
  }, 150);
});

async function loadMeta() {
  state.meta = await api("/api/meta");
  document.getElementById("dataNote").textContent = "공개 자료만으로 만든 화면이에요 · 카드 이용은 나우캐스트 주 단위" + " · 아이콘 3dicons(CC0) · Fluent Emoji(MIT)";
}

async function start() {
  // 【기능】 로그인하면 auth.js 가 부른다 — 회원을 바꾸고 전 회원의 대시보드 값은 버린다
  window.SALPIM_AUTH.onLogin = (m) => { state.member = m; state.board = null; };
  window.addEventListener("scroll", () => nav.classList.toggle("solid", window.scrollY > 40), { passive: true });
  document.getElementById("logout").addEventListener("click", async () => {
    await fetch("/api/auth/logout", { method: "POST" });
    state.member = null; state.board = null;
    go("login");
  });
  window.addEventListener("hashchange", render);
  await render();
}
start().catch((e) => (view.innerHTML = `<div class="empty err" style="padding-top:140px">${esc(e.message)}</div>`));
