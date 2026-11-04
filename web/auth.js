/* 취약 돌보미 회원 화면 — 로그인 · 회원가입 5단계 · 아이디/비밀번호 찾기 · 비로그인 안내 · 세션 만료.
   스토리보드 v1.3 COM-100 ~ 161 · CHT-AUTH · CHT-SESS. 판정은 서버(/api/auth/*)가 하고,
   화면은 칸을 벗어나는 순간 같은 규칙으로 미리 알려 준다.
   【판단】 옮길 때 팀원 app.js 와 부딪히지 않게 한 덩어리(즉시 실행 함수)로, 밖에는 window.SalpimAuth 만
   【판단】 팀 화면에 끼울 때는 그 앞에 window.SALPIM_AUTH = { embed: true, home, onLogin } 을 두면
          길 나누기(hashchange)는 팀 화면이 하고, 여기서는 SalpimAuth.render(이름)로 그리기만 한다 */
(() => {
  "use strict";

  const view = document.getElementById("view");
  const $ = (s, r = document) => r.querySelector(s);
  const $$ = (s, r = document) => [...r.querySelectorAll(s)];
  const ESC = { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" };
  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ESC[c]);
  const go = (path) => { location.hash = "#/" + path; };
  const store = {
    get(k, area = sessionStorage) { try { return JSON.parse(area.getItem(k)); } catch { return null; } },
    set(k, v, area = sessionStorage) { try { area.setItem(k, JSON.stringify(v)); } catch { /* 저장 못 해도 화면은 돈다 */ } },
    del(k, area = sessionStorage) { try { area.removeItem(k); } catch { /* 위와 같음 */ } },
  };

  // 【기능】 서버 부르기 — 실패해도 {ok:false, error} 모양으로 돌려준다
  async function api(path, body) {
    const opt = body === undefined ? {} : {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
    };
    let r;
    // 【판단】 10-28 사이트 점검: 서버 · DB가 멈추면 요청이 끝나지 않아 [인증번호 받기]가 눌린 채
    //        아무 글도 없었다 → 25초가 지나면 끊고 알린다(메일 서버 시간 15초보다 길게)
    const ctl = new AbortController();
    const timer = setTimeout(() => ctl.abort(), 25000);
    try {
      r = await fetch(path, { credentials: "same-origin", signal: ctl.signal, ...opt });
    } catch (e) {
      return {
        ok: false, status: 0,
        error: e && e.name === "AbortError"
          ? "서버가 응답하지 않아요. 잠시 뒤 다시 해 주세요."
          : "서버에 닿지 않아요. 잠시 뒤 다시 해 주세요.",
      };
    } finally {
      clearTimeout(timer);
    }
    let j = {};
    try { j = await r.json(); } catch { /* 빈 응답 */ }
    if (j && j.detail && typeof j.detail === "object") j = j.detail;
    return { ...j, ok: r.ok && j.ok !== false, status: r.status };
  }

  // ── 그리는 부품 ──
  const LOGO = `<svg viewBox="0 0 40 40" aria-hidden="true"><path d="M4 22 36 6 26 34 19 25Z" fill="#fff"/>
    <path d="M19 25 36 6 15 27Z" fill="#DCE8F7"/><path d="M15 27 19 25 17 33Z" fill="#B9CFEA"/></svg>`;
  const page = (inner, wide = false) => `<div class="au-page"><div class="au-wrap ${wide ? "wide" : ""}">
    <a class="au-logo" href="#/login">${LOGO}<span><b>취약 돌보미</b><small>우리 동네 고립 살핌</small></span></a>
    <section class="au-paper">${inner}</section></div></div>`;
  // 【정함 10-25 팀장】 회원 유형(공공 · 민간)과 기관 코드를 없앴다 — 누구나 이메일 인증만으로 가입(4단계)
  const STEPS = ["약관 동의", "본인 확인", "정보 입력", "완료"];
  const steps = (n) => `<ol class="au-steps">${STEPS.map((s, i) =>
    `<li class="${i + 1 === n ? "on" : i + 1 < n ? "done" : ""}">${i + 1}. ${s}</li>`).join("")}</ol>`;
  const req = `<span class="au-req">*</span>`;

  function msg(el, text, kind = "") {
    if (!el) return;
    el.innerHTML = text ? `<p class="au-msg ${kind}">${text}</p>` : "";
  }
  function mark(input, bad) { input.classList.toggle("bad", !!bad); input.setAttribute("aria-invalid", bad ? "true" : "false"); }

  // COM-100 ①: [보기]를 누르는 동안만 보인다
  function peek(btn, input) {
    const show = (on) => { input.type = on ? "text" : "password"; };
    btn.addEventListener("pointerdown", () => show(true));
    ["pointerup", "pointerleave", "blur"].forEach((e) => btn.addEventListener(e, () => show(false)));
    btn.addEventListener("keydown", (e) => { if (e.key === " " || e.key === "Enter") { e.preventDefault(); show(true); } });
    btn.addEventListener("keyup", () => show(false));
  }

  function dialog(html) {
    let d = $("#auDlg");
    if (!d) {
      d = document.createElement("dialog");
      d.id = "auDlg"; d.className = "au-dlg";
      document.body.append(d);
    }
    d.innerHTML = html;
    $$("[data-close]", d).forEach((b) => b.addEventListener("click", () => d.close()));
    if (!d.open) d.showModal();
    return d;
  }

  // 남은 시간(04:52)과 [다시 받기] 1분 막기
  function countdown(el, secs, onEnd) {
    clearInterval(el._t);
    const end = Date.now() + secs * 1000;
    const tick = () => {
      const left = Math.max(0, Math.round((end - Date.now()) / 1000));
      el.textContent = `${String(Math.floor(left / 60)).padStart(2, "0")}:${String(left % 60).padStart(2, "0")}`;
      if (!left) { clearInterval(el._t); onEnd && onEnd(); }
    };
    tick();
    el._t = setInterval(tick, 500);
  }
  function cooldown(btn, secs) {
    const label = btn.dataset.label || btn.textContent;
    btn.dataset.label = label;
    clearInterval(btn._t);
    let left = secs;
    btn.disabled = true;
    const tick = () => {
      btn.textContent = left > 0 ? `${label} (${left}초)` : label;
      if (left-- <= 0) { clearInterval(btn._t); btn.disabled = false; }
    };
    tick();
    btn._t = setInterval(tick, 1000);
  }

  // 비밀번호 조건 넷(서버 rules.password_checks 와 같다)
  function pwChecks(pw, id) {
    return {
      length: pw.length >= 9 && pw.length <= 20,
      kinds: /[A-Za-z]/.test(pw) && /\d/.test(pw) && /[^A-Za-z0-9]/.test(pw),
      no_id: !(id && pw.toLowerCase().includes(id.toLowerCase())),
      no_repeat: !/(.)\1\1/.test(pw),
    };
  }
  const PW_WORDS = { length: "9~20자", kinds: "영문 · 숫자 · 특수문자", no_id: "아이디 없음", no_repeat: "같은 글자 3번 연속 없음" };
  function pwView(el, pw, id) {
    const c = pwChecks(pw, id);
    el.innerHTML = Object.entries(PW_WORDS).map(([k, w]) =>
      `<span class="${pw ? (c[k] ? "ok" : "bad") : ""}">${pw ? (c[k] ? "✓" : "×") : "·"} ${w}</span>`).join("");
    return Object.values(c).every(Boolean);
  }

  // ── COM-100 로그인 · E1 틀림 · E2 잠김 ──
  function login() {
    const saved = store.get("salpim_saved_id", localStorage) || "";
    const flash = store.get("salpim_flash");
    store.del("salpim_flash");
    view.innerHTML = page(`<h1>로그인</h1><p class="au-lead">담당자 계정으로 로그인하세요</p>
      ${flash ? `<p class="au-msg ok">${esc(flash)}</p>` : ""}
      <form id="f" novalidate>
        <div class="au-field"><label for="lid">아이디</label>
          <input class="au-input" id="lid" autocomplete="username" placeholder="아이디를 입력하세요" value="${esc(saved)}"></div>
        <div class="au-field"><label for="lpw">비밀번호</label>
          <div class="au-row"><input class="au-input" id="lpw" type="password" autocomplete="current-password" placeholder="비밀번호를 입력하세요">
          <button type="button" class="au-btn" id="peek">보기</button></div></div>
        <label class="au-check"><input type="checkbox" id="save" ${saved ? "checked" : ""}> 아이디 저장</label>
        <div id="err" aria-live="polite"></div>
        <div class="au-acts"><button class="au-btn primary block" id="go">로그인</button></div>
      </form>
      <nav class="au-links"><a href="#/find/id">아이디 찾기</a><span>|</span><a href="#/find/pw">비밀번호 재설정</a><span>|</span><a href="#/signup/1">회원가입</a></nav>
      <div class="au-note"><p>· 비밀번호를 5번 틀리면 30분 동안 로그인할 수 없습니다.</p>
      <p>· 공용 PC에서는 [아이디 저장]을 끄고, 다 쓰면 로그아웃하세요.</p></div>`);
    const id = $("#lid"), pw = $("#lpw"), err = $("#err");
    peek($("#peek"), pw);
    (saved ? pw : id).focus();
    $("#f").addEventListener("submit", async (e) => {
      e.preventDefault();
      mark(id, !id.value.trim()); mark(pw, !pw.value);
      if (!id.value.trim() || !pw.value) {
        err.innerHTML = `<div class="au-alert"><p>아이디와 비밀번호를 모두 넣어 주세요.</p></div>`;
        return;
      }
      $("#go").disabled = true;
      const r = await api("/api/auth/login", { login_id: id.value.trim(), password: pw.value });
      $("#go").disabled = false;
      if (r.ok) {
        if ($("#save").checked) store.set("salpim_saved_id", id.value.trim().toLowerCase(), localStorage);
        else store.del("salpim_saved_id", localStorage);
        const cfg = window.SALPIM_AUTH || {};
        const back = store.get("salpim_return") || cfg.home || "home";
        store.del("salpim_return");
        if (cfg.onLogin) cfg.onLogin(r.member);
        go(back);
        return;
      }
      pw.value = ""; mark(pw, true); pw.focus();   // E1 ①: 비밀번호만 비우고 아이디는 둔다
      if (r.locked) { err.innerHTML = ""; lockedDialog(r.until); return; }
      err.innerHTML = `<div class="au-alert"><p>${esc(r.error)}</p>${r.left
        ? `<p>${r.left}번 더 틀리면 30분 동안 로그인할 수 없습니다.</p>` : ""}</div>`;
    });
  }

  function lockedDialog(until) {
    const d = dialog(`<h3>로그인이 잠겼습니다</h3><p>비밀번호를 5번 잘못 입력했습니다.</p>
      <p>30분 동안 로그인할 수 없습니다.</p><p>다시 로그인할 수 있는 시각 <span class="big">${esc(until)}</span></p>
      <p>바로 풀려면 이메일 인증 뒤 비밀번호를 새로 정하세요.</p>
      <div class="au-acts"><button class="au-btn" data-close>닫기</button><button class="au-btn primary" id="toReset">비밀번호 재설정</button></div>`);
    $("#toReset", d).addEventListener("click", () => { d.close(); go("find/pw"); });
  }

  // ── 회원가입 단계에서 쓰는 값(새로고침해도 이어지게 sessionStorage) ──
  const S = () => store.get("salpim_signup") || { terms: {} };
  const saveS = (patch) => store.set("salpim_signup", { ...S(), ...patch });

  // COM-120 약관 동의
  let TERMS = null;
  async function signup2() {
    TERMS = TERMS || await api("/api/auth/terms");
    const t = S().terms || {};
    const body = (it) => {
      if (it.code !== "privacy") return it.lines.map((l) => `<p>${esc(l)}</p>`).join("");
      const rows = it.lines.filter((l) => l.includes(": ")).map((l) => {
        const [k, ...v] = l.split(": ");
        return `<tr><th>${esc(k)}</th><td>${esc(v.join(": "))}</td></tr>`;
      }).join("");
      const rest = it.lines.filter((l) => !l.includes(": ")).map((l) => `<p>${esc(l)}</p>`).join("");
      return `<table class="au-table">${rows}</table>${rest}`;
    };
    view.innerHTML = page(steps(1) + `<h2>약관에 동의해 주세요</h2><p class="au-lead">약관 판 ${esc(TERMS.version)}</p>
      <div class="au-terms">
        <div class="au-term"><label class="au-check"><input type="checkbox" id="all"> <b>전체 동의</b> (선택 항목 포함)</label></div>
        ${TERMS.items.map((it) => `<div class="au-term"><div class="au-row">
          <label class="au-check"><input type="checkbox" data-t="${it.code}" ${t[it.code] ? "checked" : ""}>
          ${it.required ? "[필수]" : "[선택]"} ${esc(it.title)}</label>
          <button type="button" class="link" data-open="${it.code}" aria-expanded="${it.code === "privacy"}">${it.code === "privacy" ? "접기 ˄" : "보기 ›"}</button></div>
          <div class="au-term-body" id="tb-${it.code}" ${it.code === "privacy" ? "" : "hidden"}>${body(it)}</div></div>`).join("")}
      </div>
      <div class="au-acts"><a class="au-btn" href="#/login">이미 회원이신가요? 로그인</a><button class="au-btn primary" id="next">다음</button></div>`, true);
    const boxes = $$("[data-t]");
    const sync = () => {
      const terms = Object.fromEntries(boxes.map((b) => [b.dataset.t, b.checked]));
      saveS({ terms });
      $("#all").checked = boxes.every((b) => b.checked);
      $("#next").disabled = !TERMS.items.filter((i) => i.required).every((i) => terms[i.code]);
    };
    $("#all").addEventListener("change", (e) => { boxes.forEach((b) => { b.checked = e.target.checked; }); sync(); });
    boxes.forEach((b) => b.addEventListener("change", sync));
    $$("[data-open]").forEach((b) => b.addEventListener("click", () => {
      const el = $("#tb-" + b.dataset.open);
      el.hidden = !el.hidden;
      b.textContent = el.hidden ? "보기 ›" : "접기 ˄";
      b.setAttribute("aria-expanded", !el.hidden);
    }));
    sync();
    $("#next").addEventListener("click", () => go("signup/2"));
  }

  // 인증번호 받기 · 확인(가입 · 아이디 찾기 · 비밀번호 재설정이 같이 쓴다)
  function codeBlock() {
    return `<div class="au-field" id="codeBox" hidden><label for="cd">인증번호${req}</label>
      <div class="au-row"><input class="au-input" id="cd" inputmode="numeric" maxlength="6" autocomplete="one-time-code" placeholder="6자리">
      <span class="au-timer" id="tm" aria-label="남은 시간"></span><button type="button" class="au-btn" id="ok">확인</button>
      <button type="button" class="au-btn" id="again">다시 받기</button></div><div id="cdMsg" aria-live="polite"></div></div>`;
  }
  function wireCode({ purpose, fields, onSent, onVerified }) {
    const cd = $("#cd"), cdMsg = $("#cdMsg");
    async function send(btn) {
      const f = fields();
      if (!f) return;
      btn.disabled = true;
      const r = await api("/api/auth/code/send", { purpose, ...f });
      // 10-28: 답이 늦게 와서 그사이 다른 화면으로 갔으면 아무것도 하지 않는다(없는 칸을 고치다 멈춤)
      const box = $("#codeBox");
      if (!box || !document.body.contains(btn)) return;
      btn.disabled = false;
      if (!r.ok) {
        if (r.wait) {
          cooldown($("#again"), r.wait);
          cooldown($("#send"), r.wait);
          // 10-28 사이트 점검: 인증번호 칸이 아직 숨어 있으면 그 칸의 글도 안 보였다
          //        ('1분에 한 번만 …'이 사라짐) → 칸이 숨어 있으면 이메일 칸 아래에
          if (box.hidden) onSent && onSent(r);
          else msg(cdMsg, esc(r.error), "bad");
          return;
        }
        onSent && onSent(r);
        return;
      }
      onSent && onSent(r);
      box.hidden = false;
      cd.value = ""; cd.disabled = false; $("#ok").disabled = false; cd.focus();
      // 10-26: 시험 모드(메일을 실제로 보내지 않음)면 그렇다고 알리고 시험 메일함 링크를 준다
      const sentText = esc(r.message || "인증번호를 보냈습니다. 5분 안에 넣어 주세요.");
      msg(cdMsg, r.dev_outbox
        ? `${sentText} <a href="${esc(r.dev_outbox)}" target="_blank" rel="noopener">시험 메일함 열기</a>`
        : sentText, "ok");
      countdown($("#tm"), r.expires_in, () => msg(cdMsg, "시간이 지났어요. [다시 받기]를 눌러 주세요.", "bad"));
      cooldown($("#again"), r.resend_in);
      cooldown($("#send"), r.resend_in);
    }
    $("#send").addEventListener("click", () => send($("#send")));
    $("#again").addEventListener("click", () => send($("#again")));
    const check = async () => {
      const f = fields();
      if (!f) return;
      if (!/^\d{6}$/.test(cd.value.trim())) { mark(cd, true); msg(cdMsg, "인증번호 6자리를 넣어 주세요.", "bad"); return; }
      const r = await api("/api/auth/code/verify", { purpose, ...f, code: cd.value.trim() });
      mark(cd, !r.ok);
      if (!r.ok) { msg(cdMsg, esc(r.error), "bad"); return; }
      clearInterval($("#tm")._t); $("#tm").textContent = "";
      cd.disabled = true; $("#ok").disabled = true;
      // 【판단】 인증을 마치면 [받기] · [다시 받기]는 꺼진 채로 — 1분 막힘이 끝나 다시 켜지지 않게
      [$("#again"), $("#send")].forEach((b) => {
        clearInterval(b._t);
        if (b.dataset.label) b.textContent = b.dataset.label;
        b.disabled = true;
      });
      msg(cdMsg, "✓ 확인됨", "ok");
      onVerified(r, f);
    };
    $("#ok").addEventListener("click", check);
    cd.addEventListener("keydown", (e) => { if (e.key === "Enter") { e.preventDefault(); check(); } });
  }

  // COM-130 본인 확인
  function signup3() {
    const s = S();
    if (!(s.terms && s.terms.use && s.terms.privacy)) return go("signup/1");
    const done = !!s.ticket;
    view.innerHTML = page(steps(2) + `<h2>이메일로 본인 확인</h2>
      <p class="au-lead">이메일로 인증번호를 보냅니다. 아이디 찾기 · 비밀번호 재설정에도 이 이메일을 씁니다.</p>
      <div class="au-field"><label for="nm">이름${req}</label><input class="au-input" id="nm" autocomplete="name" placeholder="홍길동" value="${esc(s.name || "")}" ${done ? "readonly" : ""}></div>
      <div class="au-field"><label for="em">이메일${req}</label><div class="au-row">
        <input class="au-input" id="em" type="email" autocomplete="email" placeholder="hong07@korea.kr" value="${esc(s.email || "")}" ${done ? "readonly" : ""}>
        <button type="button" class="au-btn" id="send" ${done ? "disabled" : ""}>인증번호 받기</button></div><div id="emMsg" aria-live="polite"></div></div>
      ${codeBlock()}
      ${done ? `<p class="au-msg ok">✓ 인증 완료 — 이 이메일은 다음 단계에서 고칠 수 없어요.</p>` : ""}
      <div class="au-acts"><a class="au-btn" href="#/signup/1">이전</a><button class="au-btn primary" id="next" ${done ? "" : "disabled"}>다음</button></div>`, true);
    const nm = $("#nm"), em = $("#em"), emMsg = $("#emMsg");
    const fields = () => {
      const name = nm.value.trim(), email = em.value.trim();
      const nameBad = !/^[가-힣A-Za-z ]{2,20}$/.test(name), emailBad = !/^[^@\s]+@[^@\s]+\.[A-Za-z]{2,}$/.test(email);
      mark(nm, nameBad); mark(em, emailBad);
      if (nameBad) { msg(emMsg, "이름은 2~20자(한글 · 영문)로 적어 주세요.", "bad"); return null; }
      if (emailBad) { msg(emMsg, "이메일 주소 모양이 맞지 않아요.", "bad"); return null; }
      return { name, email };
    };
    if (!done) {
      wireCode({
        purpose: "signup",
        fields,
        onSent: (r) => {
          if (r.ok) { msg(emMsg, ""); return; }
          mark(em, true);
          msg(emMsg, esc(r.error) + (r.taken ? ` <a href="#/find/id">아이디 찾기</a>` : ""), "bad");
        },
        onVerified: (r, f) => {
          saveS({ ticket: r.ticket, name: f.name, email: f.email.toLowerCase() });
          nm.readOnly = true; em.readOnly = true;
          $("#next").disabled = false;
        },
      });
    }
    $("#next").addEventListener("click", () => go("signup/3"));
  }

  // COM-140 정보 입력 · E1 고칠 곳 있음
  let DONGS = null;
  async function signup4() {
    const s = S();
    if (!s.ticket) return go("signup/2");
    DONGS = DONGS || await api("/api/auth/dongs");
    const picked = s.dongs || [];
    const regionOpts = DONGS.regions.map((r) => `<option value="${r.sgg_cd}">${esc(r.name)}</option>`).join("");
    view.innerHTML = page(steps(3) + `<h2>회원 정보를 입력해 주세요</h2><p class="au-lead">${req} 필수</p>
      <div class="au-who">본인 확인 <b>${esc(s.name)}</b> · ${esc(s.email)} <span class="ok">✓ 인증 완료</span></div>
      <div class="au-field"><label for="uid">아이디${req}</label><div class="au-row">
        <input class="au-input" id="uid" autocomplete="username" placeholder="영문 소문자로 시작 4~20자" value="${esc(s.login_id || "")}">
        <button type="button" class="au-btn" id="dup">중복 확인</button></div><div id="uidMsg"></div></div>
      <div class="au-field"><label for="pw">비밀번호${req}</label><div class="au-row">
        <input class="au-input" id="pw" type="password" autocomplete="new-password"><button type="button" class="au-btn" id="peek">보기</button></div>
        <div class="au-checks" id="pwChecks"></div><div id="pwMsg"></div></div>
      <div class="au-field"><label for="pw2">비밀번호 확인${req}</label>
        <input class="au-input" id="pw2" type="password" autocomplete="new-password"><div id="pw2Msg"></div></div>
      <div class="au-field"><span class="au-label">담당 지역${req}</span><div class="au-chips" id="chips"></div>
        <div class="au-row"><select class="au-select" id="rg" aria-label="시군구">${regionOpts}</select>
        <select class="au-select" id="dg" aria-label="읍면동"></select><button type="button" class="au-btn" id="add">+ 추가</button></div>
        <div id="dgMsg"></div></div>
      <div class="au-field"><label for="job">직무</label><select class="au-select" id="job"><option value="">고르지 않음</option>
        ${DONGS.jobs.map((j) => `<option ${s.job === j ? "selected" : ""}>${esc(j)}</option>`).join("")}</select></div>
      <div id="sum" aria-live="polite"></div>
      <div class="au-acts"><a class="au-btn" href="#/signup/2">이전</a><button class="au-btn primary" id="submit" disabled>가입 신청</button></div>`, true);

    const st = { id: null, touched: new Set() };  // id: 확인한 아이디
    const uid = $("#uid"), pw = $("#pw"), pw2 = $("#pw2");
    peek($("#peek"), pw);
    const dongName = (cd) => DONGS.regions.flatMap((r) => r.dongs).find((d) => d.dong_cd === cd)?.name || cd;
    const fillDongs = () => {
      const r = DONGS.regions.find((x) => x.sgg_cd === $("#rg").value);
      // 10-26 점검: 가나다순(22곳에서 찾기 쉽게) · 맨 위는 '동을 고르세요'(고르면 바로 더해짐)
      const ds = [...r.dongs].sort((a, b) => a.name.localeCompare(b.name, "ko"));
      $("#dg").innerHTML = `<option value="">동을 고르세요</option>` +
        ds.map((d) => `<option value="${d.dong_cd}">${esc(d.name)}</option>`).join("");
    };
    const drawChips = () => {
      $("#chips").innerHTML = picked.map((cd) => `<span class="au-chip">${esc(dongName(cd))}
        <button type="button" data-rm="${cd}" aria-label="${esc(dongName(cd))} 빼기">×</button></span>`).join("");
      $$("[data-rm]").forEach((b) => b.addEventListener("click", () => {
        picked.splice(picked.indexOf(b.dataset.rm), 1); saveS({ dongs: picked }); st.touched.add("dongs"); drawChips(); refresh();
      }));
    };
    fillDongs(); drawChips();
    $("#rg").addEventListener("change", fillDongs);
    const addDong = () => {
      const cd = $("#dg").value;
      if (!cd) return;
      if (!picked.includes(cd)) picked.push(cd);
      $("#dg").value = "";
      saveS({ dongs: picked }); st.touched.add("dongs"); drawChips(); refresh();
    };
    // 10-26 점검: 동을 골라도 [+ 추가]를 눌러야 가입 단추가 켜지는데 안내가 없었다 → 고르면 바로 더함
    $("#dg").addEventListener("change", addDong);
    $("#add").addEventListener("click", addDong);

    // 칸마다 지금 맞는지 — 화면이 가입 신청 단추를 켜고 끈다(E1 ⑤)
    const state = () => {
      const id = uid.value.trim();
      const pwOk = pwView($("#pwChecks"), pw.value, id);
      return {
        login_id: st.id === id && !!id,
        password: pwOk,
        password2: pwOk && pw.value === pw2.value && !!pw2.value,
        dongs: picked.length > 0,
      };
    };
    function refresh() {
      const ok = state();
      const bad = Object.entries(ok).filter(([k, v]) => !v && st.touched.has(k)).length;
      $("#submit").disabled = !Object.values(ok).every(Boolean);
      msg($("#dgMsg"), ok.dongs ? "" : "담당 동을 하나 이상 골라 주세요(여러 곳이면 하나씩 고르면 더해져요).",
        st.touched.has("dongs") ? "bad" : "");
      $("#sum").innerHTML = bad ? `<div class="au-alert"><p>고칠 곳이 ${bad}곳 있습니다. 빨간 칸을 확인하세요.</p></div>` : "";
      saveS({ login_id: uid.value.trim(), job: $("#job").value });
    }

    async function checkId() {
      st.touched.add("login_id");
      const id = uid.value.trim();
      if (!/^[a-z][a-z0-9_]{3,19}$/.test(id)) {
        st.id = null; mark(uid, true);
        msg($("#uidMsg"), "아이디는 영문 소문자로 시작하는 4~20자(영문 소문자 · 숫자 · _)로 정해 주세요.", "bad");
        return refresh();
      }
      const r = await api("/api/auth/check-id?login_id=" + encodeURIComponent(id));
      st.id = r.ok ? id : null; mark(uid, !r.ok);
      msg($("#uidMsg"), esc(r.ok ? r.message : r.error), r.ok ? "ok" : "bad");
      refresh();
    }
    $("#dup").addEventListener("click", checkId);
    uid.addEventListener("input", () => { st.id = null; msg($("#uidMsg"), ""); mark(uid, false); refresh(); });
    uid.addEventListener("blur", () => { if (uid.value.trim() && st.id !== uid.value.trim()) checkId(); });

    pw.addEventListener("input", refresh);
    pw.addEventListener("blur", () => {
      st.touched.add("password");
      const ok = pwView($("#pwChecks"), pw.value, uid.value.trim());
      mark(pw, !ok); msg($("#pwMsg"), ok ? "" : "빨간 × 조건을 맞춰 주세요.", "bad"); refresh();
    });
    const pw2Check = () => {
      if (!pw2.value) return;
      st.touched.add("password2");
      const same = pw.value === pw2.value;
      mark(pw2, !same); msg($("#pw2Msg"), same ? "✓ 일치합니다" : "비밀번호가 일치하지 않습니다", same ? "ok" : "bad"); refresh();
    };
    pw2.addEventListener("input", pw2Check);
    pw2.addEventListener("blur", pw2Check);

    $("#job").addEventListener("change", refresh);

    $("#submit").addEventListener("click", async () => {
      $("#submit").disabled = true;
      const r = await api("/api/auth/signup", {
        ticket: S().ticket, login_id: uid.value.trim(), password: pw.value, password2: pw2.value,
        dongs: picked, job: $("#job").value || null, terms: S().terms,
      });
      if (r.ok) {
        store.del("salpim_signup");
        store.set("salpim_signup_done", r);
        go("signup/4");
        return;
      }
      if (r.field === "ticket") { saveS({ ticket: null }); dialog(`<h3>본인 확인 시간이 지났어요</h3><p>${esc(r.error)}</p>
        <div class="au-acts"><button class="au-btn primary" data-close>이메일 인증 다시 하기</button></div>`)
        .addEventListener("close", () => go("signup/2"), { once: true }); return; }
      const where = { login_id: ["#uid", "#uidMsg"], password: ["#pw", "#pwMsg"], password2: ["#pw2", "#pw2Msg"],
        dongs: ["#rg", "#dgMsg"], job: ["#job", "#dgMsg"] };
      Object.entries(r.fields || {}).forEach(([k, m]) => {
        const w = where[k];
        if (w) { mark($(w[0]), true); msg($(w[1]), esc(m), "bad"); }
      });
      $("#sum").innerHTML = `<div class="au-alert"><p>${esc(r.error)}</p>${Object.keys(r.fields || {})
        .filter((k) => !where[k]).map((k) => `<p>${esc(r.fields[k])}</p>`).join("")}</div>`;
    });
    if (uid.value.trim()) checkId();
    refresh();
  }

  // COM-150 가입 완료
  function signup5() {
    const r = store.get("salpim_signup_done");
    if (!r) return go("login");
    view.innerHTML = page(steps(4) + `<div class="au-done"><div class="mark" aria-hidden="true">✓</div>
      <h2>가입이 끝났습니다</h2><p class="au-lead">로그인하면 담당 지역(${esc(r.dongs.join(" · "))}) 기준으로 비서가 시작합니다.</p>
      <table class="au-table"><tr><th>아이디</th><td>${esc(r.login_id)}</td></tr>
      <tr><th>담당 지역</th><td>${esc(r.dongs.join(" · "))}</td></tr>
      <tr><th>가입일</th><td>${esc(r.joined)}</td></tr></table>
      <button class="au-btn primary block" id="toLogin">로그인 하러 가기</button></div>`, true);
    $("#toLogin").addEventListener("click", () => {
      store.del("salpim_signup_done");
      store.set("salpim_saved_id", r.login_id, localStorage);
      go("login");
    });
  }

  // ── COM-161 아이디 찾기 · COM-160 비밀번호 재설정 ──
  const tabs = (on) => `<h2>아이디 · 비밀번호 찾기</h2><nav class="au-tabs">
    <a href="#/find/id" class="${on === "id" ? "on" : ""}">아이디 찾기</a><a href="#/find/pw" class="${on === "pw" ? "on" : ""}">비밀번호 재설정</a></nav>`;

  function findId() {
    view.innerHTML = page(tabs("id") + `
      <div class="au-field"><label for="nm">이름${req}</label><input class="au-input" id="nm" autocomplete="name" placeholder="홍길동"></div>
      <div class="au-field"><label for="em">가입한 이메일${req}</label><div class="au-row">
        <input class="au-input" id="em" type="email" autocomplete="email" placeholder="hong07@korea.kr">
        <button type="button" class="au-btn" id="send">인증번호 받기</button></div><div id="emMsg"></div></div>
      ${codeBlock()}<div id="found"></div>
      <nav class="au-links"><a href="#/login">로그인</a><span>|</span><a href="#/signup/1">회원가입</a></nav>`);
    const nm = $("#nm"), em = $("#em");
    wireCode({
      purpose: "find_id",
      fields: () => {
        const name = nm.value.trim(), email = em.value.trim();
        mark(nm, !name); mark(em, !email);
        if (!name || !email) { msg($("#emMsg"), "이름과 가입한 이메일을 넣어 주세요.", "bad"); return null; }
        return { name, email };
      },
      onSent: (r) => msg($("#emMsg"), r.ok ? "" : esc(r.error), r.ok ? "" : "bad"),
      onVerified: (r) => {
        nm.readOnly = true; em.readOnly = true;
        $("#found").innerHTML = `<div class="au-found"><table class="au-table"><tr><th>가입한 아이디</th><td><b>${esc(r.masked)}</b></td></tr>
          <tr><th>가입일</th><td>${esc(r.joined)}</td></tr></table>
          <p class="au-msg ok">✓ 전체 아이디는 가입한 이메일로 보냈습니다.</p>
          <div class="au-acts"><a class="au-btn primary" href="#/login">로그인 하러 가기</a><a class="au-btn" href="#/find/pw">비밀번호 재설정</a></div></div>`;
      },
    });
    nm.focus();
  }

  function findPw() {
    view.innerHTML = page(tabs("pw") + `
      <div class="au-field"><label for="uid">아이디${req}</label><input class="au-input" id="uid" autocomplete="username" placeholder="hong07"></div>
      <div class="au-field"><label for="em">가입한 이메일${req}</label><div class="au-row">
        <input class="au-input" id="em" type="email" autocomplete="email" placeholder="hong07@korea.kr">
        <button type="button" class="au-btn" id="send">인증번호 받기</button></div><div id="emMsg"></div></div>
      ${codeBlock()}<div id="newPw" hidden>
        <div class="au-field"><label for="pw">새 비밀번호${req}</label><div class="au-row">
          <input class="au-input" id="pw" type="password" autocomplete="new-password"><button type="button" class="au-btn" id="peek">보기</button></div>
          <div class="au-checks" id="pwChecks"></div></div>
        <div class="au-field"><label for="pw2">새 비밀번호 확인${req}</label><input class="au-input" id="pw2" type="password" autocomplete="new-password">
          <div id="pw2Msg"></div></div>
        <div id="pwErr"></div><button class="au-btn primary block" id="change" disabled>비밀번호 바꾸기</button></div>
      <nav class="au-links"><a href="#/login">로그인</a><span>|</span><a href="#/signup/1">회원가입</a></nav>`);
    const uid = $("#uid"), em = $("#em");
    let ticket = null;
    wireCode({
      purpose: "reset_pw",
      fields: () => {
        const login_id = uid.value.trim().toLowerCase(), email = em.value.trim();
        mark(uid, !login_id); mark(em, !email);
        if (!login_id || !email) { msg($("#emMsg"), "아이디와 가입한 이메일을 넣어 주세요.", "bad"); return null; }
        return { login_id, email };
      },
      onSent: (r) => msg($("#emMsg"), r.ok ? "" : esc(r.error), r.ok ? "" : "bad"),
      onVerified: (r) => {
        ticket = r.ticket;
        uid.readOnly = true; em.readOnly = true;
        $("#newPw").hidden = false; $("#pw").focus();
      },
    });
    const pw = $("#pw"), pw2 = $("#pw2");
    peek($("#peek"), pw);
    const refresh = () => {
      const ok = pwView($("#pwChecks"), pw.value, uid.value.trim());
      const same = !!pw2.value && pw.value === pw2.value;
      if (pw2.value) msg($("#pw2Msg"), same ? "✓ 일치합니다" : "비밀번호가 일치하지 않습니다", same ? "ok" : "bad");
      mark(pw2, !!pw2.value && !same);
      $("#change").disabled = !(ok && same && ticket);
    };
    pw.addEventListener("input", refresh); pw2.addEventListener("input", refresh);
    $("#change").addEventListener("click", async () => {
      const r = await api("/api/auth/password/reset", { ticket, password: pw.value, password2: pw2.value });
      if (r.ok) {
        store.set("salpim_flash", "비밀번호를 바꿨어요. 잠김도 풀렸어요. 새 비밀번호로 로그인하세요.");
        store.set("salpim_saved_id", r.login_id, localStorage);
        go("login");
        return;
      }
      $("#pwErr").innerHTML = `<div class="au-alert"><p>${esc(r.error)}</p></div>`;
    });
    uid.focus();
  }

  // ── 로그인해야 쓰는 화면(CHT-AUTH) · 세션 만료(CHT-SESS) ──
  function needLogin(back) {
    store.set("salpim_return", back);
    const d = dialog(`<h3>로그인이 필요합니다</h3><p>로그인한 회원만 쓸 수 있습니다. 회원가입은 이메일 인증만으로 누구나 할 수 있어요.</p>
      <div class="au-acts"><button class="au-btn primary" id="toLogin">로그인</button></div>`);
    d.addEventListener("cancel", (e) => e.preventDefault());   // 뒤 화면은 로그인 전까지 못 쓴다
    $("#toLogin", d).addEventListener("click", () => { d.close(); go("login"); });
  }
  function expired(back, pending) {
    store.set("salpim_return", back);
    if (pending) store.set("salpim_pending", pending);
    // 【판단】 저장하다 끊겼을 때만 '이어서 저장' — 화면에 들어오다 끊긴 것은 시간만 알린다
    const why = pending ? "로그인 시간이 지나 저장하지 못했습니다. 로그인하면 이어서 저장합니다."
      : "로그인 시간이 지났어요(한 달 동안 쓰지 않으면 로그아웃됩니다). 다시 로그인해 주세요.";
    const d = dialog(`<h3>다시 로그인해 주세요</h3><p>${why}</p>
      <div class="au-acts"><button class="au-btn" data-close>나중에</button><button class="au-btn primary" id="toLogin">로그인</button></div>`);
    $("#toLogin", d).addEventListener("click", () => { d.close(); go("login"); });
  }

  // 시험용 첫 화면 — 공용 저장소에서는 대시보드 홈(DSH-100)이 이 자리
  async function home() {
    view.innerHTML = `<div class="au-page"><div class="au-home"><div class="au-bar">
      <a class="au-logo" href="#/home">${LOGO}<span><b>취약 돌보미</b><small>우리 동네 고립 살핌</small></span></a>
      <button class="au-btn" id="out" hidden>로그아웃</button></div><section class="au-paper" id="me"><p class="au-lead">불러오는 중…</p></section></div></div>`;
    const r = await api("/api/auth/me");
    if (!r.ok) {
      $("#me").innerHTML = `<p class="au-lead">로그인한 사람만 볼 수 있는 화면이에요.</p>`;
      return r.code === "session_expired" ? expired("home") : needLogin("home");
    }
    const m = r.member;
    $("#out").hidden = false;
    $("#out").addEventListener("click", async () => { await api("/api/auth/logout", {}); go("login"); });
    $("#me").outerHTML = `<section class="au-paper"><h2>안녕하세요, ${esc(m.name)}님</h2>
      <table class="au-table"><tr><th>아이디</th><td>${esc(m.login_id)}</td></tr>
      <tr><th>직무</th><td>${esc(m.job || "고르지 않음")}</td></tr>
      <tr><th>담당 지역</th><td>${m.regions.map((x) => esc(`${x.sgg} ${x.dong || "전체"}`)).join(" · ")}</td></tr></table></section>
      <section class="au-paper"><h2>로그인 유지 시험</h2><p class="au-lead">로그인은 한 달 동안 유지됩니다. 쓸 때마다 한 달이 다시 늘어납니다.</p>
      <button class="au-btn primary" id="save">했어요(저장 시험)</button><div id="saveMsg" aria-live="polite"></div></section>`;
    const save = async () => {
      const s = await api("/api/demo/save", {});
      if (s.ok) { msg($("#saveMsg"), esc(s.message), "ok"); return; }
      if (s.status === 401) expired("home", "demo_save");
      else msg($("#saveMsg"), esc(s.error || "저장하지 못했어요."), "bad");
    };
    $("#save").addEventListener("click", save);
    if (store.get("salpim_pending") === "demo_save") { store.del("salpim_pending"); save(); }  // CHT-SESS ①
  }

  const ROUTES = {
    login, home, "signup/1": signup2, "signup/2": signup3, "signup/3": signup4, "signup/4": signup5,
    "find/id": findId, "find/pw": findPw,
    // 10-28 사이트 점검: '#/signup' · '#/find'를 바로 열면 로그인 화면이 떴다
    signup: signup2, find: findId,
  };
  function render(name) {
    const d = $("#auDlg");
    if (d && d.open) d.close();
    (ROUTES[name] || login)();
    window.scrollTo(0, 0);
  }
  const route = () => render(location.hash.replace(/^#\//, "") || "login");
  window.SalpimAuth = { api, ROUTES, render, needLogin, expired };
  if (!(window.SALPIM_AUTH && window.SALPIM_AUTH.embed)) {
    window.addEventListener("hashchange", route);
    route();
  }
})();
