"use strict";
// Dime Signals page (Michael 2026-11-28): the frozen NBA signals, laid out like the Stix NFL Signals page.
// Two groups, clearly split: TEAM signals (game spread / total) and PLAYER signals (props).
// Tiles: title + i, ROI, record, today's count, chart (dot = each week's ROI, line = running ROI). Tap a tile for its
// record, today's plays and week-by-week bets. Data: data/signals.json, written by nba_tracker/signals.py.
// Display only: no rule, list or graded result is changed here.
(function () {
  const S = { sel: null, scope: "season", wopen: false };
  const SCOPES = [["season", "This season"], ["fwd", "Since freeze"], ["last7", "Last 7 days"]];
  const KIND = { team: ["TEAM", "Team signals · game lines", "Whole-game bets: the spread or the game total. DraftKings line and price from the 7 AM CT pull."],
                 player: ["PLAYER", "Player signals · props", "Player prop bets: points, rebounds, assists, threes. DraftKings line and price from the ~1 h pre-game pull."] };
  const SD = () => (typeof D !== "undefined" ? D.signals : null);
  const E = (s) => (typeof esc === "function" ? esc(s) : String(s ?? ""));
  const sig = (id) => (SD() && SD().signals.find((s) => s.id === id)) || null;
  const daysAgo = (n) => { const d = new Date(SD().today + "T12:00:00"); d.setDate(d.getDate() - n); return d.toISOString().slice(0, 10); };
  function inScope(b) {
    if (S.scope === "fwd") return b.date >= SD().freeze_date;
    if (S.scope === "last7") return b.date > daysAgo(7);
    return true;
  }
  function tally(bets) {
    let W = 0, L = 0, P = 0, U = 0;
    for (const b of bets) { if (b.res === "W") W++; else if (b.res === "L") L++; else P++; U += b.u; }
    const n = W + L + P;
    return { W, L, P, U, n, roi: n ? (100 * U) / n : null, hit: W + L ? (100 * W) / (W + L) : null };
  }
  const sgn = (v, d = 1) => `${v > 0 ? "+" : v < 0 ? "−" : ""}${Math.abs(v).toFixed(d)}`;
  const recTxt = (s) => `${s.W}-${s.L}${s.P ? `-${s.P}` : ""}`;
  const unitsTxt = (u) => `${sgn(u, 2)}u`;
  const roiTxt = (s) => (s.roi == null ? "—" : `${sgn(s.roi, Math.abs(s.roi) >= 100 ? 0 : 1)}%`);
  const am = (v) => (v == null ? "" : v > 0 ? `+${v}` : String(v));
  const md = (d) => { const x = new Date(d + "T12:00:00"); return `${x.getMonth() + 1}/${x.getDate()}`; };
  const tipTime = (iso) => { try { return new Date(iso).toLocaleTimeString([], { hour: "numeric", minute: "2-digit" }); } catch { return ""; } };
  const MKL = { pts: "Pts", reb: "Reb", ast: "Ast", fg3m: "3PM" };

  // chart: a dot for each week's ROI plus a line for the running ROI, weeks along the bottom (same as Stix)
  function spark(bets) {
    const weeks = [...new Set(bets.map((b) => b.wk))].sort((a, b) => a - b);
    if (!weeks.length) return `<div class="sg-nospark muted small">no graded bets</div>`;
    const all = []; for (let w = weeks[0]; w <= weeks[weeks.length - 1]; w++) all.push(w);
    let U = 0, N = 0;
    const pts = all.map((w) => { const s = tally(bets.filter((b) => b.wk === w)); U += s.U; N += s.n; return { w, n: s.n, roi: s.n ? s.roi : null, cum: N ? (100 * U) / N : null }; });
    const w = 170, h = 70, l = 30, r = 11, tp = 6, bt = 13, n = pts.length, base = h - bt;
    const vals = pts.flatMap((q) => [q.roi, q.cum]).filter((v) => v != null).concat(0);
    let mn = Math.min(...vals), mx = Math.max(...vals); if (mx - mn < 20) { mx += 10; mn -= 10; }
    const rg = mx - mn, X = (i) => (n < 2 ? (l + w - r) / 2 : l + (i * (w - l - r)) / (n - 1)), Y = (v) => tp + ((mx - v) / rg) * (base - tp);
    const fmt = (v) => `${v > 0 ? "+" : v < 0 ? "−" : ""}${Math.abs(Math.round(v))}%`;
    const ticks = []; let prevY = -99;
    for (const v of [...new Set([mx, 0, mn])].sort((a, b) => b - a)) { if (Y(v) - prevY >= 11) { ticks.push(v); prevY = Y(v); } }
    const every = n > 9 ? 2 : 1, cp = pts.map((q, i) => [i, q]).filter(([, q]) => q.cum != null);
    const last = cp.length ? cp[cp.length - 1][1].cum : 0, col = last >= 0 ? "--over" : "--under";
    return `<svg class="sg-spark" viewBox="0 0 ${w} ${h}" role="img" aria-label="Weekly ROI and running ROI by week, now ${fmt(last)}">
      <g class="sg-ax"><line x1="${l}" x2="${l}" y1="${tp}" y2="${base}"/><line x1="${l}" x2="${w - r}" y1="${base}" y2="${base}"/>
      ${ticks.map((v) => `<line class="sg-gl" x1="${l}" x2="${w - r}" y1="${Y(v).toFixed(1)}" y2="${Y(v).toFixed(1)}"/><text x="${l - 3}" y="${(Y(v) + 2.8).toFixed(1)}" text-anchor="end">${fmt(v)}</text>`).join("")}
      ${pts.map((q, i) => ((n - 1 - i) % every ? "" : `<text x="${X(i).toFixed(1)}" y="${h - 3}" text-anchor="middle">W${q.w}</text>`)).join("")}</g>
      <line x1="${l}" x2="${w - r}" y1="${Y(0).toFixed(1)}" y2="${Y(0).toFixed(1)}" style="stroke:var(--line)" stroke-dasharray="3 3"/>
      <path d="${cp.map(([i, q], k) => `${k ? "L" : "M"}${X(i).toFixed(1)},${Y(q.cum).toFixed(1)}`).join(" ")}" fill="none" style="stroke:var(${col})" stroke-width="1.6" stroke-linejoin="round"/>
      ${pts.filter((q) => q.n).map((q) => `<circle cx="${X(pts.indexOf(q)).toFixed(1)}" cy="${Y(q.roi).toFixed(1)}" r="2.3" style="fill:var(${q.roi >= 0 ? "--over" : "--under"})"><title>Week ${q.w}: ${fmt(q.roi)} ROI (${q.n} bets) · running ${fmt(q.cum)}</title></circle>`).join("")}</svg>`;
  }
  const kindTag = (t) => `<span class="sg-kind ${t.kind}">${KIND[t.kind][0]}</span><span class="sg-mkt">${E(t.market)}</span>`;
  const todayPlays = (t) => t.plays.filter((p) => p.date === SD().today);
  function tileHtml(t) {
    const bets = t.bets.filter(inScope), s = tally(bets), on = S.sel === t.id;
    const cls = s.n ? (s.U > 0 ? "la-pos" : s.U < 0 ? "la-neg" : "") : "";
    const cnt = todayPlays(t).length;
    return `<div class="sg-cell"><button type="button" class="sg-tile ${t.kind} ${on ? "on" : ""}" data-sig="${t.id}" aria-pressed="${on}">
      <div class="sg-kindrow">${kindTag(t)}</div>
      <div class="sg-hd"><b class="sg-ttl2">${E(t.title)}</b><span class="rinfo" role="button" tabindex="0" data-dinfo="${t.id}" aria-label="About ${E(t.title)}">i</span></div>
      <div class="sg-r2"><span class="sg-roi ${cls}">${s.n ? roiTxt(s) : "—"}</span><span class="small sg-st">${s.n ? recTxt(s) : `<span class="muted">no bets</span>`}<br><span class="sg-wk"><b>${cnt}</b> today</span></span></div>
      ${spark(bets)}</button></div>`;
  }
  function playRow(p, t) {
    const who = t.kind === "player"
      ? `<a class="pname" href="#/player/${E(p.aid)}">${E(p.player)}</a> <span class="muted small">${E(p.team)}</span>`
      : `<b>${E(p.matchup)}</b>`;
    const live = p.state === "in" ? `<span class="chip live">Live</span>` : `<span class="muted small">${tipTime(p.start)}</span>`;
    const price = p.line != null ? ` <span class="muted small">${am(p.price)} ${p.book === "fanduel" ? "FD" : "DK"}${p.pull ? ` · ${E(p.pull)} line` : ""}</span>` : ` <span class="muted small">line after the 7 AM pull</span>`;
    return `<div class="rlrow sg-play"><div class="rlhead">${who}<span class="rlsize">${live}</span></div>
      <div class="sg-m"><span><b class="sg-pick ${t.bet === "Under" ? "under" : ""}">${E(p.pick)}</b>${price}</span>${t.kind === "player" ? `<span class="muted small">${E(p.matchup)}</span>` : ""}</div>
      <div class="muted small">${E(p.why)}</div></div>`;
  }
  function betRow(b, t) {
    const mark = b.res === "W" ? "✓" : b.res === "L" ? "✗" : "–";
    const cls = b.res === "W" ? "la-hit" : b.res === "L" ? "la-miss" : "la-push";
    const who = t.kind === "player" ? `<a class="pname" href="#/player/${E(b.aid)}">${E(b.player)}</a> <span class="muted small">${E(b.team)} · ${E(b.matchup)}</span>` : `<b>${E(b.matchup)}</b>`;
    const out = t.kind === "player" ? `actual ${b.actual}` : b.actual != null ? `total ${b.actual}` : E(b.score || "");
    return `<div class="rlrow ${cls}"><div class="rlhead"><span class="la-mark">${mark}</span>${who}<span class="rlsize">${md(b.date)}</span></div>
      <div class="muted small">${E(b.pick)} (${am(b.price)}) · ${out} · ${b.u >= 0 ? "+" : ""}${b.u.toFixed(2)}u</div>
      <div class="muted small">${E(b.why)}</div></div>`;
  }
  function detailHtml(t) {
    const bets = t.bets.filter(inScope), s = tally(bets), cls = s.U > 0 ? "la-pos" : s.U < 0 ? "la-neg" : "";
    const today = SD().today, tp = t.plays.filter((p) => p.date === today), tm = t.plays.filter((p) => p.date > today);
    const weeks = [...new Set(bets.map((b) => b.wk))].sort((a, b) => b - a).map((w) => {
      const list = bets.filter((b) => b.wk === w).slice().reverse(), st = tally(list);
      const sec = (k, ttl, g) => (g.length ? `<h3 class="la-h ${k}">${ttl} (${g.length})</h3><div class="panel rlist">${g.map((b) => betRow(b, t)).join("")}</div>` : "");
      return `<details class="la-wk"><summary><span class="la-wk-t">Week ${w}</span><span class="muted small">${recTxt(st)} · ${unitsTxt(st.U)} · ${roiTxt(st)} ROI</span></summary>
        ${sec("hit", "Hits", list.filter((b) => b.res === "W"))}${sec("miss", "Misses", list.filter((b) => b.res === "L"))}${sec("push", "Pushes", list.filter((b) => b.res === "P"))}</details>`;
    }).join("");
    const plays = (lbl, ps) => (ps.length ? `<h3 class="sg-sec">${lbl} (${ps.length})</h3><div class="panel rlist">${ps.map((p) => playRow(p, t)).join("")}</div>` : "");
    return `<div class="sg-detail"><div class="panel sg-rec"><div class="body">
      <div class="sg-rec-h"><span class="sg-rec-t">${kindTag(t)}<b>${E(t.title)}</b><span class="rinfo" role="button" tabindex="0" data-dinfo="${t.id}" aria-label="About ${E(t.title)}">i</span></span> <button type="button" class="linkbtn" data-sgclear>Clear</button></div>
      <p class="muted small sg-rec-s">${E(t.rule)}</p>
      <div class="la-sum"><div><span class="muted small">${S.scope === "fwd" ? "Since freeze" : S.scope === "last7" ? "Last 7 days" : "Season"}</span><b>${s.n ? recTxt(s) : "—"}</b></div>
        <div><span class="muted small">Hit rate</span><b>${s.hit == null ? "—" : s.hit.toFixed(1) + "%"}</b></div>
        <div><span class="muted small">Units</span><b class="${cls}">${s.n ? unitsTxt(s.U) : "—"}</b></div>
        <div><span class="muted small">ROI</span><b class="${cls}">${roiTxt(s)}</b></div></div>
      ${plays("Today", tp)}${plays("Tomorrow", tm)}${!tp.length && !tm.length ? `<p class="muted small">No plays today or tomorrow yet.${t.kind === "player" ? " Prop lines arrive with the 7 AM pull." : ""}</p>` : ""}
      ${bets.length ? `<details class="sg-weeks" data-wopen ${S.wopen ? "open" : ""}><summary>Week by week (${new Set(bets.map((b) => b.wk)).size} weeks, ${bets.length} bets)</summary>${weeks}</details>` : `<p class="muted small">No graded bets in this window.</p>`}
    </div></div></div>`;
  }
  function gridHtml(kind) {
    const ts = SD().signals.filter((t) => t.kind === kind);
    const rk = (t) => tally(t.bets).roi ?? -1e9;
    ts.sort((a, b) => rk(b) - rk(a));
    // the picked tile's detail goes right after the row it sits in (2 tiles per row), spanning the grid
    const cols = window.matchMedia && window.matchMedia("(min-width: 900px)").matches ? 3 : 2;
    let h = "";
    ts.forEach((t, i) => {
      h += tileHtml(t);
      const rowEnd = (i + 1) % cols === 0 || i === ts.length - 1;
      if (rowEnd) { const row = ts.slice(i - (i % cols), i + 1); const pick = row.find((x) => x.id === S.sel); if (pick) h += detailHtml(pick); }
    });
    return `<div class="sg-grid">${h}</div>`;
  }
  function view() {
    const d = SD();
    if (!d) return `<p class="pad">Signals data didn't load yet. It's written by the next data run.</p>`;
    const fz = md(d.freeze_date);
    let h = `<div class="sg-page"><div class="sg-title"><h2>Signals</h2><span class="muted small">Frozen ${fz} · 1 unit flat · W = week of the season</span></div>
      <div class="sg-scope" role="tablist" aria-label="Time">${SCOPES.map(([k, l]) => `<button class="gchip ${S.scope === k ? "on" : ""}" data-sgscope="${k}">${l}</button>`).join("")}</div>`;
    for (const kind of ["team", "player"]) {
      const [tag, ttl, note] = KIND[kind];
      h += `<div class="sg-grp"><b><span class="sg-kind ${kind}">${tag}</span> ${ttl}</b><span class="muted small">${note}</span></div>${gridHtml(kind)}`;
    }
    h += `<p class="muted small sg-foot">Records before ${fz} are the in-season sweep the signals were chosen from, so they flatter the signals. "Since freeze" counts only bets made after the rules were locked. Research tool, not betting advice.</p></div>`;
    return h;
  }
  function closeInfo() { const o = document.getElementById("sgi-ov"); if (o) o.remove(); }
  function openInfo(id) {
    closeInfo();
    const t = sig(id); if (!t) return;
    const lead = t.gates.length === 1 ? "Must pass 1 gate" : t.gates.length === 2 ? "Must pass both gates" : `Must pass all ${t.gates.length} gates`;
    const ov = document.createElement("div");
    ov.id = "sgi-ov"; ov.className = "share-ov";
    ov.innerHTML = `<div class="share-box sgp" role="dialog" aria-label="${E(t.title)}">
      <div class="sgp-h"><div><div class="sg-kindrow">${kindTag(t)}</div><div class="sgp-code">${E(t.title)}</div><div class="small muted">${E(t.id)} · ${E(t.short)}</div></div><button class="nw-x" aria-label="Close">✕</button></div>
      <div class="small muted sgp-lead">${lead}</div>
      <ol class="sgp-gl">${t.gates.map((g) => `<li>${E(g)}</li>`).join("")}</ol>
      <p class="small"><b>Bet:</b> ${t.kind === "team" ? (t.bet === "Under" ? "the game Under" : "the other team on the spread") : "the Under"} · ${E(t.rule)}</p>
      <p class="small muted sgp-why">💡 ${E(t.why)}</p>
      <div class="sgp-res small">${(() => { const pre = tally(t.bets.filter((b) => b.date < SD().freeze_date)), fw = tally(t.bets.filter((b) => b.date >= SD().freeze_date)); return `<b>This season before the freeze:</b> ${pre.n ? `${recTxt(pre)}, ${roiTxt(pre)} ROI` : "no bets"}<br><b>Since the freeze:</b> ${fw.n ? `${recTxt(fw)}, ${roiTxt(fw)} ROI` : "no bets yet"}<br><b>History:</b> ${E(t.found)}`; })()}</div>
      <p class="small muted">Frozen ${md(SD().freeze_date)}. The rule won't change; a new version would be a new signal.</p></div>`;
    document.body.appendChild(ov);
    ov.addEventListener("click", (e) => { if (e.target === ov || e.target.closest(".nw-x")) closeInfo(); });
  }
  function redraw() { const app = document.getElementById("app"); app.innerHTML = view(); }
  function bind() { /* events are delegated on document (below); nothing to attach per render */ }
  // one delegated listener for the page (tiles, scope chips, info, clear)
  document.addEventListener("click", (e) => {
    if (!document.querySelector(".sg-page")) return;
    const info = e.target.closest("[data-dinfo]");
    if (info) { e.preventDefault(); e.stopPropagation(); openInfo(info.dataset.dinfo); return; }
    const sc = e.target.closest("[data-sgscope]");
    if (sc) { S.scope = sc.dataset.sgscope; redraw(); return; }
    if (e.target.closest("[data-sgclear]")) { S.sel = null; redraw(); return; }
    const tile = e.target.closest("[data-sig]");
    if (tile) { S.sel = S.sel === tile.dataset.sig ? null : tile.dataset.sig; redraw(); const el = document.querySelector(".sg-detail"); if (el && S.sel) el.scrollIntoView({ behavior: "smooth", block: "nearest" }); }
  }, true);
  document.addEventListener("toggle", (e) => { if (e.target.matches && e.target.matches("[data-wopen]")) S.wopen = e.target.open; }, true);
  document.addEventListener("keydown", (e) => { if ((e.key === "Enter" || e.key === " ") && e.target.closest && e.target.closest("[data-dinfo]")) { e.preventDefault(); openInfo(e.target.closest("[data-dinfo]").dataset.dinfo); } if (e.key === "Escape") closeInfo(); });
  window.DIME_SIGNALS = { view, bind, tally };
})();
