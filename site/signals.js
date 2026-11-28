"use strict";
// Dime Signals page (Michael 2026-11-28): the frozen NBA signals, laid out like the Stix NFL Signals page.
// Two groups, clearly split: TEAM signals (game spread / total) and PLAYER signals (props).
// Tiles: title + i, ROI, record, today's count, chart (dot = each week's ROI, line = running ROI). Tap a tile for its
// record, today's plays and week-by-week bets. Data: data/signals.json, written by nba_tracker/signals.py.
// Display only: no rule, list or graded result is changed here.
(function () {
  const S = { sel: null, scope: "season", wopen: false, pick: {} };
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

  // ---------- bet slip (Michael 2026-11-28): checkboxes, Select all / Clear, "Add to FanDuel slip", and a DraftKings
  // popup when DK has a better number, ported from the Stix NFL Signals page. Player plays use data/prop_links.csv (props
  // pull); team plays (spread / total) carry p.links from data/game_links.csv (7 AM game-lines pull). Opening a slip never changes the record.
  const FD_SLIP = /^https:\/\/sportsbook\.fanduel\.com\/addToBetslip\?/;
  const DK_SLIP = /^https:\/\/sportsbook\.draftkings\.com\/\?outcomes=([^&#]+)$/;
  const FD_SLIP_MAX = 25;  // most bets in one FanDuel link (same as Stix)
  const MKID = { pts: "player_points", reb: "player_rebounds", ast: "player_assists", fg3m: "player_threes" };
  const LINKS = () => (typeof D !== "undefined" && D.props && D.props.links) || {};
  const playKey = (p) => p.aid ? `${p.gid}|${p.aid}|${p.mk}` : `${p.gid}|${p.team || "U"}|t`;
  const slipName = (p) => p.player || p.matchup;
  const slipLabel = (p) => p.aid ? `${MKL[p.mk]} Under` : p.pick;
  const pickOf = (id) => S.pick[id] || (S.pick[id] = new Set());
  const openPlay = (p) => p.start && new Date(p.start).getTime() > Date.now() && p.state !== "in";
  const teamLink = (p, book) => { const e = p.links && p.links[book]; return e && e.url && e.point != null && e.price != null ? { point: e.point, cap: e.cap, u: { url: e.url, price: e.price } } : null; };
  const linkOf = (p, book) => { if (!p.aid) return teamLink(p, book); const e = ((LINKS()[p.aid] || {})[MKID[p.mk]] || {})[book]; return e && e.gid === p.gid ? e : null; };
  const fdSlipUrl = (legs) => "https://sportsbook.fanduel.com/addToBetslip?" + legs.map((l, j) => `marketId[${j}]=${l.m}&selectionId[${j}]=${l.sel}`).join("&");
  const dkSlipUrl = (legs) => "https://sportsbook.draftkings.com/?outcomes=" + legs.map((l) => l.dk.oc).join("+");
  function dkOf(p, fd) {
    const dk = linkOf(p, "draftkings"); if (!dk || !dk.u || dk.u.price == null || dk.point == null) return null;
    const m = DK_SLIP.exec(dk.u.url || ""); if (!m) return null;
    const out = { line: dk.point, odds: dk.u.price, cap: dk.cap, oc: m[1], why: null };
    if (fd && fd.u && fd.u.price != null && fd.point != null) {
      if (dk.point > fd.point) out.why = "line"; else if (dk.point === fd.point && dk.u.price > fd.u.price) out.why = "odds";
    }
    return out;
  }
  function slipOf(t) {
    const chosen = pickOf(t.id), legs = [], dkOnly = [], missing = [];
    for (const p of t.plays) {
      if (!chosen.has(playKey(p)) || !openPlay(p)) continue;
      const fd = linkOf(p, "fanduel"), u = fd && fd.u && FD_SLIP.test(fd.u.url || "") ? fd.u : null;
      let m = null, sel = null;
      if (u) { try { const x = new URL(u.url); m = x.searchParams.get("marketId"); sel = x.searchParams.get("selectionId"); } catch { m = sel = null; } }
      const dk = dkOf(p, fd), name = slipName(p), label = slipLabel(p);
      if (m && sel && /^[\d.]+$/.test(m) && /^\d+$/.test(sel)) legs.push({ name, label, m, sel, line: fd.point, odds: u.price, cap: fd.cap, dk: dk && dk.why ? dk : null });
      else if (dk) dkOnly.push({ name, label, dk });
      else missing.push(`${name} (${label})`);
    }
    const chunks = [];
    for (let i = 0; i < legs.length; i += FD_SLIP_MAX) { const part = legs.slice(i, i + FD_SLIP_MAX); chunks.push({ legs: part, from: i + 1, to: i + part.length, url: fdSlipUrl(part) }); }
    return { legs, dkOnly, missing, chunks };
  }
  function slipBox(t) {
    const open = t.plays.filter(openPlay); if (!open.length) return "";
    const f = slipOf(t); S.chunks = f.chunks; S.dkOnly = f.dkOnly;
    const n = [...pickOf(t.id)].filter((k) => open.some((p) => playKey(p) === k)).length;
    const picker = `<span class="small rl-pick"><button type="button" class="linkbtn" data-sgall="1">Select all</button> · <button type="button" class="linkbtn" data-sgall="0">Clear</button> <span class="muted">${n} selected</span></span>`;
    const dkBtn = f.dkOnly.length ? `<a class="betbtn" href="${E(dkSlipUrl(f.dkOnly))}" target="_blank" rel="noopener">Add ${f.dkOnly.length} not on FanDuel to DraftKings slip ↗</a>` : "";
    if (!n) return `<div class="betbox rl-fd sg-slip">${picker}<span class="betbtn rl-off" aria-disabled="true" style="opacity:.5">Check plays to add them to the FanDuel slip</span></div>`;
    if (!f.legs.length) return `<div class="betbox rl-fd sg-slip">${picker}${dkBtn || `<span class="betbtn rl-off" aria-disabled="true" style="opacity:.5">None of the checked plays are on FanDuel</span>`}${f.missing.length ? `<span class="muted small rl-fdnote">No slip link for: ${E(f.missing.join(", "))}</span>` : ""}</div>`;
    const many = f.chunks.length > 1;
    const btns = f.chunks.map((c, k) => `<a class="betbtn${many ? " rl-slip" : ""}" href="${E(c.url)}" target="_blank" rel="noopener" data-sgfd="${k}" title="Opens FanDuel with ${c.legs.length} bets on the slip">${many ? `Slip ${k + 1} · bets ${c.from}–${c.to} ↗` : `Add ${f.legs.length} checked bet${f.legs.length > 1 ? "s" : ""} to FanDuel slip ↗`}</a>`).join("");
    const caps = f.legs.map((l) => l.cap).filter(Boolean).sort();
    return `<div class="betbox rl-fd sg-slip">${picker}${many ? `<span class="muted small rl-fdnote">FanDuel takes up to ${FD_SLIP_MAX} bets per link, so these are split into ${f.chunks.length} slips. Open each one.</span><div class="rl-slips">${btns}</div>` : btns}${dkBtn}
      <span class="muted small rl-fdnote">Lines as of ${E(caps.length ? fmtTime(caps[caps.length - 1]) : "the last pull")}. The slip shows each book's current line. Opening a slip doesn't change the record.</span>
      ${f.missing.length ? `<span class="muted small rl-fdnote">No slip link for: ${E(f.missing.join(", "))}</span>` : ""}</div>`;
  }
  // Popup when a tapped FanDuel slip includes bets with a better DraftKings number (same choices as Stix).
  function dkPopup(chunk) {
    document.querySelector(".rl-dkpop")?.remove();
    const flagged = chunk.legs.filter((l) => l.dk), keep = chunk.legs.filter((l) => !l.dk);
    const caps = flagged.map((l) => l.dk.cap).filter(Boolean).sort(), asOf = caps.length ? fmtTime(caps[0]) : "";
    const rows = flagged.map((l) => `<li><b>${E(l.name)}</b> ${E(l.label)}<br><span class="muted small">FD ${l.line} ${am(l.odds)} · DK ${l.dk.line} ${am(l.dk.odds)} (better ${l.dk.why})</span></li>`).join("");
    const fdUrl = keep.length ? fdSlipUrl(keep) : "", dkUrl = dkSlipUrl(flagged);
    const dkBtn = (label) => `<a class="betbtn" data-dkpick="dk" href="${E(dkUrl)}" target="_blank" rel="noopener">${label} ↗<span class="muted small rl-dkasof">DK lines as of ${E(asOf)}. If DK moved a line since, that bet won't load.</span></a>`;
    const close = `<button type="button" class="betbtn" data-dkpick="cancel">Close</button>`;
    const el = document.createElement("div"); el.className = "rl-dkpop"; el.setAttribute("role", "dialog"); el.setAttribute("aria-modal", "true");
    const step1 = () => {
      const both = keep.length ? `<a class="betbtn rl-both" data-dkpick="both" href="${E(fdUrl)}" target="_blank" rel="noopener">Do both: ${keep.length} to FD, then ${flagged.length} to DK ↗</a>` : "";
      const only = keep.length ? `<a class="betbtn" data-dkpick="best" href="${E(fdUrl)}" target="_blank" rel="noopener">Only take best FD lines to FD (${keep.length}) ↗</a>`
        : `<span class="betbtn rl-off" aria-disabled="true" style="opacity:.5">No bets have the best line on FD</span>`;
      el.innerHTML = `<div class="rl-dkcard"><b>${flagged.length} of ${chunk.legs.length} bets ${flagged.length === 1 ? "has" : "have"} a better line on DraftKings</b><ul>${rows}</ul>
        <div class="rl-dkbtns">${both}${only}${dkBtn(`Take better DK lines to DK (${flagged.length})`)}<a class="betbtn" data-dkpick="all" href="${E(chunk.url)}" target="_blank" rel="noopener">Take all ${chunk.legs.length} to FD ↗</a>${close}</div></div>`;
    };
    const step2 = () => {
      el.innerHTML = `<div class="rl-dkcard"><b>Step 2 of 2</b><p class="small">Sent ${keep.length} bet${keep.length === 1 ? "" : "s"} to FanDuel. Now the ${flagged.length} better on DraftKings:</p>
        <div class="rl-dkbtns">${dkBtn(`Next: open DraftKings (${flagged.length})`)}${close}</div></div>`;
    };
    el.addEventListener("click", (ev) => {
      const b = ev.target.closest && ev.target.closest("[data-dkpick]");
      if (!b) { if (ev.target === el) el.remove(); return; }
      if (b.dataset.dkpick === "cancel") { el.remove(); return; }
      if (b.dataset.dkpick === "both") { setTimeout(step2, 0); return; }
      if (!b.querySelector(".rl-done")) b.insertAdjacentHTML("beforeend", ` <span class="rl-done">✓ opened</span>`);
    });
    step1();
    document.body.appendChild(el);
  }
  function refreshSlip() {
    const box = document.querySelector(".sg-slip"), t = S.sel && sig(S.sel);
    if (box && t) box.outerHTML = slipBox(t);
    const t2 = S.sel && sig(S.sel); if (!t2) return;
    document.querySelectorAll("[data-sgck]").forEach((el) => { el.checked = pickOf(t2.id).has(el.dataset.sgck); });
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
    const ck = openPlay(p) ? `<input type="checkbox" class="rl-ck" data-sgck="${E(playKey(p))}" aria-label="Add ${E(slipName(p))} to the slip" ${pickOf(t.id).has(playKey(p)) ? "checked" : ""}>` : "";
    const who = t.kind === "player"
      ? `${ck}<a class="pname" href="#/player/${E(p.aid)}">${E(p.player)}</a> <span class="muted small">${E(p.team)}</span>`
      : `${ck}<b>${E(p.matchup)}</b>`;
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
      <div class="sg-rec-h"><span class="sg-rec-t">${kindTag(t)}<b>${E(t.title)}</b><span class="rinfo" role="button" tabindex="0" data-dinfo="${t.id}" aria-label="About ${E(t.title)}">i</span></span> <button type="button" class="linkbtn" data-sgclear>Close</button></div>
      <p class="muted small sg-rec-s">${E(t.rule)}</p>
      <div class="la-sum"><div><span class="muted small">${S.scope === "fwd" ? "Since freeze" : S.scope === "last7" ? "Last 7 days" : "Season"}</span><b>${s.n ? recTxt(s) : "—"}</b></div>
        <div><span class="muted small">Hit rate</span><b>${s.hit == null ? "—" : s.hit.toFixed(1) + "%"}</b></div>
        <div><span class="muted small">Units</span><b class="${cls}">${s.n ? unitsTxt(s.U) : "—"}</b></div>
        <div><span class="muted small">ROI</span><b class="${cls}">${roiTxt(s)}</b></div></div>
      ${slipBox(t)}${plays("Today", tp)}${plays("Tomorrow", tm)}${!tp.length && !tm.length ? `<p class="muted small">No plays today or tomorrow yet.${t.kind === "player" ? " Prop lines arrive with the 7 AM pull." : ""}</p>` : ""}
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
  document.addEventListener("click", (e) => {
    if (!document.querySelector(".sg-page")) return;
    const a = e.target.closest && e.target.closest("[data-sgall]");
    if (a && S.sel) {
      const t = sig(S.sel), s = pickOf(t.id); s.clear();
      if (a.dataset.sgall === "1") t.plays.filter(openPlay).forEach((p) => s.add(playKey(p)));
      refreshSlip(); return;
    }
    const b = e.target.closest && e.target.closest("[data-sgfd]");
    if (b) { const chunk = (S.chunks || [])[+b.dataset.sgfd || 0]; if (chunk && chunk.legs.some((l) => l.dk)) { e.preventDefault(); dkPopup(chunk); } }
  });
  document.addEventListener("change", (e) => {
    const k = e.target && e.target.matches && e.target.matches("[data-sgck]") ? e.target : null;
    if (!k || !S.sel) return;
    const s = pickOf(S.sel); if (k.checked) s.add(k.dataset.sgck); else s.delete(k.dataset.sgck);
    refreshSlip();
  });
  document.addEventListener("toggle", (e) => { if (e.target.matches && e.target.matches("[data-wopen]")) S.wopen = e.target.open; }, true);
  document.addEventListener("keydown", (e) => { if ((e.key === "Enter" || e.key === " ") && e.target.closest && e.target.closest("[data-dinfo]")) { e.preventDefault(); openInfo(e.target.closest("[data-dinfo]").dataset.dinfo); } if (e.key === "Escape") closeInfo(); });
  window.DIME_SIGNALS = { view, bind, tally };
})();
