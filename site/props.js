"use strict";
// Player props: Board, player pages and Results. Loaded before app.js; uses its helpers at render time.
// Data: data/props.json (built by nba_tracker/build.py).

const TREND = { minGames: 3, lastN: 3, pct: 15 };   // trend arrow: last 3 games vs season avg, ±15%
const HIT_N = 10;                                   // hit rate window (games played)
const P = { date: "", game: "", mk: "", team: "", q: "", pmk: {} };
let P_TYPING = null;

const PX = () => D.props;
const mkById = (id) => PX().markets.find((m) => m.id === id);
const mean = (a) => (a.length ? a.reduce((x, y) => x + y, 0) / a.length : null);
const n1 = (v) => (v == null ? "—" : Number.isInteger(v) ? String(v) : v.toFixed(1));
const gameOf = (gid) => PX().games[gid] || {};
const gLabel = (gid) => { const g = gameOf(gid); return g.away ? `${g.away} @ ${g.home}` : gid; };

function played(aid, beforeDate) {
  return (PX().logs[aid] || []).filter((r) => r.p && (!beforeDate || r.d < beforeDate));
}
// Season avg, last-5 avg, hit rate vs a line, and trend — all from games before `beforeDate`.
function form(aid, mk, beforeDate, line) {
  const st = mkById(mk).stat;
  const games = played(aid, beforeDate).filter((r) => r[st] != null);
  const vals = games.map((r) => r[st]);
  const out = { n: vals.length, avg: mean(vals), l5: mean(vals.slice(-5)), trend: null };
  if (line != null && vals.length) {
    const last = vals.slice(-HIT_N);
    out.hits = last.filter((v) => v > line).length; out.hitN = last.length;
  }
  if (vals.length >= TREND.minGames && out.avg) {
    const la = mean(vals.slice(-TREND.lastN)), ch = ((la - out.avg) / out.avg) * 100;
    out.lastAvg = la; out.pctCh = ch; out.trend = ch >= TREND.pct ? 1 : ch <= -TREND.pct ? -1 : 0;
  } else if (vals.length >= TREND.minGames) out.trend = 0;
  return out;
}
function trendHtml(f, big) {
  if (f.trend == null) return `<span class="na" title="Fewer than ${TREND.minGames} games">—</span>`;
  const t = f.trend > 0 ? ["↑", "Rising", "up"] : f.trend < 0 ? ["↓", "Falling", "down"] : ["→", "Steady", "flat"];
  const tip = f.lastAvg != null ? `Last ${TREND.lastN} avg ${n1(f.lastAvg)} vs season ${n1(f.avg)} (${f.pctCh > 0 ? "+" : ""}${Math.round(f.pctCh)}%)` : "";
  return `<span class="mtrend ${t[2]}" title="${esc(tip)}">${t[0]}${big ? " " + t[1] : ""}</span>`;
}
function hitHtml(f) {
  if (!f.hitN) return `<span class="na">—</span>`;
  const r = f.hits / f.hitN, cls = r >= 0.7 ? "hot" : r <= 0.3 ? "cold" : "";
  return `<span class="hit ${cls}" title="Over this line in ${f.hits} of the last ${f.hitN} games played">${f.hits}/${f.hitN}</span>`;
}
function resHtml(l) {
  if (!l || !l.res) return "";
  if (l.res === "pending") return `<span class="res pending">pending</span>`;
  return `<span class="res ${l.res}" title="${esc(l.why || (l.act != null ? `Actual ${n1(l.act)} vs line ${n1(l.line)}` : ""))}">${l.res}</span>`;
}
const lineOdds = (l) => `${l.op != null ? am(l.op) : "—"}/${l.up != null ? am(l.up) : "—"}`;
const bookShort = (b) => ({ draftkings: "DK", fanduel: "FD" }[b] || b);
function lineTip(l) {
  if (l.est) {
    const parts = Object.entries(l.from || {}).map(([k, v]) => `${mkById(k).short} ${n1(v)}`).join(" + ");
    return `${l.pt === "morning" ? "8 AM line" : "Pre-game line"}: ${bookShort(l.book)} ${n1(l.line)} -110/-110 (from ${parts})` +
      (l.pt === "morning" ? ". Updates about 1 hour before tip." : "");
  }
  const alt = Object.entries(l.alt || {}).map(([b, x]) => `${bookShort(b)} ${n1(x.line)} (${lineOdds(x)})`).join(", ");
  const kind = l.pt === "morning" ? "8 AM line" : "Pre-game line";
  return `${kind}: ${bookShort(l.book)} ${n1(l.line)} ${lineOdds(l)}, captured ${fmtTime(l.cap)} (${l.mb} min before tip)` +
    (l.am ? `. 8 AM: ${n1(l.am.line)} (${lineOdds(l.am)})` : "") +
    (l.pt === "morning" ? ". Updates about 1 hour before tip." : "") + (alt ? `. Also: ${alt}` : "");
}
// Line with its context: "8 AM" chip until the pre-game pull lands; movement since 8 AM after.
function lineCell(l) {
  let h = `<b>${n1(l.line)}</b>`;
  if (l.pt === "morning") h += ` <span class="chip amchip">8 AM</span>`;
  else if (l.am && l.am.line != null && l.am.line !== l.line) {
    const d = l.line - l.am.line;
    h += ` <span class="mv ${d > 0 ? "up" : "down"}" title="Moved from ${n1(l.am.line)} at 8 AM">${d > 0 ? "▲" : "▼"}${n1(Math.abs(d))}</span>`;
  }
  return h;
}

// Rows for a date: [{aid, gid, mk, l}]
function propRows(date) {
  const out = [];
  for (const [aid, gs] of Object.entries(PX().lines)) {
    for (const [gid, ms] of Object.entries(gs)) {
      if (gameOf(gid).date !== date) continue;
      for (const [mk, l] of Object.entries(ms)) out.push({ aid, gid, mk, l });
    }
  }
  return out;
}
function lineDates() {
  const s = new Set();
  for (const gs of Object.values(PX().lines)) for (const gid of Object.keys(gs)) if (gameOf(gid).date) s.add(gameOf(gid).date);
  // Today's slate shows up even before any lines are captured.
  const t = todayET();
  if (Object.values(PX().games).some((g) => g.date === t)) s.add(t);
  return [...s].sort();
}
const gamesOn = (date) => Object.entries(PX().games).filter(([, g]) => g.date === date).map(([gid]) => gid);
function linesDueText(gid) {
  const g = gameOf(gid);
  if (g.final || g.state === "in") return "No lines were captured for this game.";
  const pre = new Date(new Date(g.start).getTime() - 3600000);
  return `Lines are pulled at 8:00 AM Central (once the books post them) and again about 1 hour before tip (~${fmtClock(pre.toISOString())}).`;
}
function todayET() { return new Date().toLocaleDateString("en-CA", { timeZone: "America/New_York" }); }
function defaultDate() {
  const ds = lineDates(), t = todayET();
  return ds.includes(t) ? t : ds.filter((d) => d <= t).pop() || ds[ds.length - 1] || t;
}
const MK_ORDER = ["player_points", "player_rebounds", "player_assists", "player_threes", "player_points_rebounds_assists",
  "player_points_rebounds", "player_points_assists", "player_rebounds_assists", "player_steals", "player_blocks"];
const BASE_COLS = [["pts", "PTS"], ["reb", "REB"], ["ast", "AST"], ["fg3m", "3PM"], ["stl", "STL"], ["blk", "BLK"]];

function gameHeader(gid) {
  const g = gameOf(gid);
  let st = "";
  if (g.final) st = `<span class="res">Final</span> ${g.as ?? ""}–${g.hs ?? ""}`;
  else if (g.state === "in") st = `<span class="live">● ${esc(g.status || "Live")}</span> ${g.as ?? ""}–${g.hs ?? ""}`;
  else st = `<span class="muted">${fmtTime(g.start)}</span>`;
  return `<b>${esc(gLabel(gid))}</b> ${st}`;
}

// ---------- Board ----------
function viewBoard() {
  if (!PX()) return `<p class="muted">Player prop data isn't available yet. It's built on each scheduled run — check the <a href="#/log">Log</a>.</p>`;
  const dates = lineDates();
  if (!P.date || !dates.includes(P.date)) P.date = defaultDate();
  const all = propRows(P.date);
  const gids = [...new Set([...all.map((r) => r.gid), ...gamesOn(P.date)])].sort((a, b) => String(gameOf(a).start).localeCompare(String(gameOf(b).start)));
  if (P.game && !gids.includes(P.game)) P.game = "";
  const q = P.q.trim().toLowerCase();
  const pl = (aid) => PX().players[aid] || { name: aid };
  const GROUPS = { core: MK_ORDER.slice(0, 4), combo: MK_ORDER.slice(4, 8), def: MK_ORDER.slice(8) };
  const mkOk = (mk) => !P.mk || (GROUPS[P.mk] ? GROUPS[P.mk].includes(mk) : mk === P.mk);
  let rows = all.filter((r) => (!P.game || r.gid === P.game) && mkOk(r.mk) &&
    (!P.team || pl(r.aid).team === P.team) && (!q || pl(r.aid).name.toLowerCase().includes(q)));
  const teams = [...new Set(all.map((r) => pl(r.aid).team).filter(Boolean))].sort();

  const chip = (gid, label, sub) => `<button class="gchip ${P.game === gid ? "on" : ""}" data-pgid="${esc(gid)}">${label}<span class="muted small">${sub}</span></button>`;
  let h = `<div class="gamebar">${chip("", "<b>All games</b>", `${gids.length} game${gids.length === 1 ? "" : "s"}`)}` +
    gids.map((g) => chip(g, `<b>${esc(gLabel(g))}</b>`, gameOf(g).final ? "Final" : esc(fmtClock(gameOf(g).start)))).join("") + `</div>`;
  h += `<div class="filters">
    <label>Date <select id="p-date">${dates.slice().reverse().map((d) => `<option value="${d}" ${d === P.date ? "selected" : ""}>${fmtDate(d)}</option>`).join("")}</select></label>
    <label>Market <select id="p-mk">${[["", "All markets"], ["core", "Core (PTS/REB/AST/3PM)"], ["combo", "Combos (PRA, P+R, P+A, R+A)"], ["def", "Steals & blocks"]].map(([v, t]) => `<option value="${v}" ${v === P.mk ? "selected" : ""}>${t}</option>`).join("")}
      <optgroup label="Single market">${PX().markets.map((m) => `<option value="${m.id}" ${m.id === P.mk ? "selected" : ""}>${esc(m.label)}</option>`).join("")}</optgroup></select></label>
    <label>Team <select id="p-team"><option value="">All</option>${teams.map((t) => `<option ${t === P.team ? "selected" : ""}>${esc(t)}</option>`).join("")}</select></label>
    <label>Player <input type="search" id="p-q" placeholder="Search name" value="${esc(P.q)}"></label>
    <button type="button" id="p-clear" class="fclear" ${P.game || P.mk || P.team || P.q || P.date !== defaultDate() ? "" : "disabled"}>Clear filters</button></div>`;
  const nPl = new Set(rows.map((r) => r.aid)).size;
  h += `<p class="callout">${nPl} players · lines pulled at 8 AM CT and ~1 h before tip; the 1-hour line is graded (DraftKings; FanDuel if DK has none) · AVG/L5/HIT use games before this date · HIT = games over this line, last ${HIT_N} played · <a href="#/guide">how it works</a></p>`;
  const filtered = P.mk || P.team || q;
  const waiting = gids.filter((g) => !all.some((r) => r.gid === g) && (!P.game || P.game === g));
  if (!rows.length && (filtered || !waiting.length)) return h + `<p class="muted">${dates.length ? "No lines match these filters." : "No prop lines captured yet. Lines are pulled about 3 hours before each tip-off."}</p>`;

  // group: game -> player -> markets
  const byGame = new Map();
  for (const r of rows) {
    if (!byGame.has(r.gid)) byGame.set(r.gid, new Map());
    const m = byGame.get(r.gid);
    if (!m.has(r.aid)) m.set(r.aid, []);
    m.get(r.aid).push(r);
  }
  const phone = !!(window.matchMedia && window.matchMedia("(max-width: 760px)").matches);
  for (const gid of gids.filter((g) => byGame.has(g) || (!filtered && waiting.includes(g)))) {
    if (!byGame.has(gid)) {
      h += `<section class="mgame"><div class="mgame-h">${gameHeader(gid)}</div><p class="muted small">${linesDueText(gid)}</p></section>`;
      continue;
    }
    const plist = [...byGame.get(gid).entries()].sort((a, b) => {
      const pa = a[1].find((x) => x.mk === "player_points"), pb = b[1].find((x) => x.mk === "player_points");
      return (pb ? pb.l.line : 0) - (pa ? pa.l.line : 0);
    });
    h += `<section class="mgame"><div class="mgame-h">${gameHeader(gid)}</div>`;
    if (phone) {
      for (const [aid, rs] of plist) {
        const p = pl(aid);
        h += `<a class="mcard" href="#/player/${encodeURIComponent(aid)}"><div class="mcard-h"><div><div class="mname">${esc(p.name)}</div>
          <div class="muted small">${esc(p.team || "")}${p.pos ? " · " + esc(p.pos) : ""}${p.nolog ? " · no games yet" : ""}</div></div><span class="mchev">›</span></div>
          <div class="mrow mhead"><span></span><span>LINE</span><span>AVG</span><span>L5</span><span>HIT</span><span>TREND</span></div>`;
        for (const r of rs.sort((a, b) => MK_ORDER.indexOf(a.mk) - MK_ORDER.indexOf(b.mk))) {
          const f = form(aid, r.mk, P.date, r.l.line);
          h += `<div class="mrow"><span class="mlab">${esc(mkById(r.mk).short)}</span><span>${lineCell(r.l)} ${resHtml(r.l)}</span><span>${n1(f.avg)}</span><span>${n1(f.l5)}</span><span>${hitHtml(f)}</span><span>${trendHtml(f)}</span></div>`;
        }
        h += `</a>`;
      }
    } else {
      h += `<div class="panel scroll"><table class="ptable"><thead><tr><th>Player</th><th>Mkt</th><th class="num">Line</th><th class="num">Over/Under</th><th>Book</th>
        <th class="num" title="Season average, games played">AVG</th><th class="num" title="Last 5 games played">L5</th><th class="num" title="Over this line, last ${HIT_N} games played">HIT</th><th>Trend</th><th class="num">Actual</th><th>Result</th></tr></thead><tbody>`;
      for (const [aid, rs] of plist) {
        const p = pl(aid);
        rs.sort((a, b) => MK_ORDER.indexOf(a.mk) - MK_ORDER.indexOf(b.mk)).forEach((r, i) => {
          const f = form(aid, r.mk, P.date, r.l.line);
          h += `<tr class="${i === 0 ? "plr" : ""}">${i === 0 ? `<td rowspan="${rs.length}" class="pcell"><a href="#/player/${encodeURIComponent(aid)}"><b>${esc(p.name)}</b></a><div class="muted small">${esc(p.team || "")}${p.pos ? " · " + esc(p.pos) : ""}${p.nolog ? " · no games yet" : ""}</div></td>` : ""}
            <td>${esc(mkById(r.mk).short)}</td><td class="num" title="${esc(lineTip(r.l))}">${lineCell(r.l)}</td><td class="num">${lineOdds(r.l)}</td><td class="muted">${bookShort(r.l.book)}</td>
            <td class="num">${n1(f.avg)}</td><td class="num">${n1(f.l5)}</td><td class="num">${hitHtml(f)}</td><td>${trendHtml(f)}</td>
            <td class="num">${r.l.act != null ? `<b>${n1(r.l.act)}</b>` : ""}</td><td>${resHtml(r.l)}</td></tr>`;
        });
      }
      h += `</tbody></table></div>`;
    }
    h += `</section>`;
  }
  return h;
}

// ---------- Player page ----------
function chartSVG(aid, mk) {
  const st = mkById(mk).stat;
  const logs = played(aid).filter((r) => r[st] != null).slice(-15);
  if (logs.length < 2) return `<p class="muted small pad">Not enough games for a chart yet.</p>`;
  const lineFor = (gid) => ((PX().lines[aid] || {})[gid] || {})[mk];
  const W = 640, H = 230, L = 30, R = 16, T = 22, B = 26;
  const vals = [...logs.map((r) => r[st]), ...logs.map((r) => lineFor(r.g)).filter(Boolean).map((l) => l.line)];
  const hi0 = Math.max(...vals), lo0 = Math.min(...vals), pad = Math.max(2, (hi0 - lo0) * 0.18);
  const lo = Math.max(0, Math.floor(lo0 - pad)), hi = Math.ceil(hi0 + pad);
  const x = (i) => L + 10 + i * ((W - L - R - 20) / Math.max(1, logs.length - 1));
  const y = (v) => T + (H - T - B) * (1 - (v - lo) / (hi - lo));
  const tip = (r, l) => `${esc(r.d)} ${r.ha === "home" ? "vs" : "@"} ${esc(r.opp)}: ${n1(r[st])}${l ? ` (line ${n1(l.line)}${l.res ? ", " + l.res : ""})` : ""}`;
  let s = `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="${esc(mkById(mk).label)} by game: actual vs line">`;
  for (const v of [lo, (lo + hi) / 2, hi]) s += `<line x1="${L}" x2="${W - R}" y1="${y(v)}" y2="${y(v)}" stroke="var(--line)"/><text x="${L - 4}" y="${y(v) + 4}" font-size="11" text-anchor="end" fill="var(--muted)">${Math.round(v)}</text>`;
  // Line series: dashed segments between consecutive games that both had a line; gaps stay open.
  let seg = [];
  const flush = () => { if (seg.length > 1) s += `<polyline points="${seg.join(" ")}" fill="none" stroke="var(--muted)" stroke-width="1.5" stroke-dasharray="4 4"/>`; seg = []; };
  logs.forEach((r, i) => { const l = lineFor(r.g); if (l) seg.push(`${x(i)},${y(l.line)}`); else flush(); });
  flush();
  // Actual series: solid line through every game.
  s += `<polyline points="${logs.map((r, i) => `${x(i)},${y(r[st])}`).join(" ")}" fill="none" stroke="var(--accent)" stroke-width="2.5" stroke-linejoin="round"/>`;
  logs.forEach((r, i) => {
    const l = lineFor(r.g);
    if (l) s += `<rect x="${x(i) - 4.5}" y="${y(l.line) - 4.5}" width="9" height="9" transform="rotate(45 ${x(i)} ${y(l.line)})" fill="var(--panel)" stroke="var(--ink)" stroke-width="2"><title>Line ${n1(l.line)}</title></rect>`;
    if (l) s += `<text x="${x(i)}" y="${y(l.line) + (r[st] >= l.line ? 18 : -10)}" font-size="10" text-anchor="middle" fill="var(--muted)">${n1(l.line)}</text>`;
    const col = l && l.res === "over" ? "var(--over)" : l && l.res === "under" ? "var(--under)" : "var(--accent)";
    const above = !l || r[st] >= l.line;
    s += `<circle cx="${x(i)}" cy="${y(r[st])}" r="5.5" fill="${col}" stroke="var(--panel)" stroke-width="2"><title>${tip(r, l)}</title></circle>`;
    s += `<text x="${x(i)}" y="${y(r[st]) + (above ? -10 : 18)}" font-size="11" font-weight="600" text-anchor="middle" fill="var(--ink)">${n1(r[st])}</text>`;
    s += `<text x="${x(i)}" y="${H - 8}" font-size="10" text-anchor="middle" fill="var(--muted)">${esc((r.opp || "").slice(0, 3))}</text>`;
  });
  return s + `</svg>`;
}
function viewPlayer(aid) {
  aid = decodeURIComponent(aid || "");
  const p = PX() && PX().players[aid];
  if (!p) return `<p>Player not found. <a href="#/board">Back to the board</a></p>`;
  const mk = P.pmk[aid] || "player_points", m = mkById(mk);
  const myLines = PX().lines[aid] || {};
  const upcoming = Object.keys(myLines).filter((g) => !gameOf(g).final).sort((a, b) => String(gameOf(a).start).localeCompare(String(gameOf(b).start)))[0];
  const curG = upcoming || Object.keys(myLines).sort((a, b) => String(gameOf(b).start).localeCompare(String(gameOf(a).start)))[0];
  const cur = curG ? myLines[curG][mk] : null;
  const f = form(aid, mk, curG ? gameOf(curG).date : null, cur ? cur.line : null);
  let h = `<div class="mplayer"><div class="mp-top"><a href="#/board" class="mback" id="m-back">‹ Board</a></div>
    <div class="mp-h"><div><h2>${esc(p.name)}</h2><div class="muted">${esc(p.team || "")}${p.pos ? " · " + esc(p.pos) : ""}</div>${curG ? `<div class="small">${gameHeader(curG)}</div>` : ""}</div></div>
    <div class="mtabs">${PX().markets.map((x) => `<button data-pmk="${x.id}" class="${x.id === mk ? "on" : ""}">${esc(x.label)}</button>`).join("")}</div>
    <div class="mtiles">
      <div><span>LINE</span>${cur ? `<b title="${esc(lineTip(cur))}">${n1(cur.line)}</b><small>${lineOdds(cur)} ${bookShort(cur.book)}</small>` : `<span class="na">none</span>`}</div>
      <div><span>AVG</span><b>${n1(f.avg)}</b><small>${f.n} game${f.n === 1 ? "" : "s"}</small></div>
      <div><span>L5</span><b>${n1(f.l5)}</b></div>
      <div><span>HIT</span>${hitHtml(f)}<small>over line</small></div>
      <div><span>TREND</span>${trendHtml(f, true)}</div>
    </div>
    <div class="panel"><h3>${esc(m.label)} by game</h3><div class="chart">${chartSVG(aid, mk)}</div>
      <div class="legend"><span><i class="lg-act"></i>Actual</span><span><i class="lg-line"></i>Pre-game line</span><span><b class="dot" style="background:var(--over)"></b>Over</span><span><b class="dot" style="background:var(--under)"></b>Under</span><span><b class="dot" style="background:var(--accent)"></b>No line</span></div></div>`;
  // game log
  const logs = [...(PX().logs[aid] || [])].reverse();
  // Base box-score columns, plus the selected market's column when it's a combo (PRA, P+R, ...).
  const cols = BASE_COLS.some(([k]) => k === m.stat) ? BASE_COLS : [...BASE_COLS, [m.stat, m.short]];
  h += `<div class="panel"><h3>Game log</h3><div class="scroll"><table class="ltable"><thead><tr><th>Date</th><th>Opp</th><th class="num">MIN</th>
    ${cols.map(([k, lab]) => `<th class="num ${k === m.stat ? "sel" : ""}">${esc(lab)}</th>`).join("")}<th class="num">Line</th><th>Result</th></tr></thead><tbody>`;
  if (!logs.length) h += `<tr><td colspan="${cols.length + 5}" class="muted">No games played yet this season.</td></tr>`;
  for (const r of logs) {
    const l = (myLines[r.g] || {})[mk];
    h += `<tr><td>${fmtDate(r.d)}</td><td>${r.ha === "home" ? "vs" : "@"} ${esc(r.opp || "")}${r.st ? "" : ` <span class="muted small">bench</span>`}</td>
      ${r.p ? `<td class="num">${n1(r.min)}</td>${cols.map(([k]) => `<td class="num ${k === m.stat ? "sel" : ""}">${n1(r[k])}</td>`).join("")}` : `<td colspan="${cols.length + 1}" class="na">DNP${r.why ? " — " + esc(r.why) : ""}</td>`}
      <td class="num">${l ? `<span title="${esc(lineTip(l))}">${n1(l.line)}</span>` : ""}</td><td>${l ? resHtml(l) : ""}</td></tr>`;
  }
  h += `</tbody></table></div></div>`;
  // line record
  const graded = Object.values(myLines).map((ms) => ms[mk]).filter((l) => l && ["over", "under", "push"].includes(l.res));
  if (graded.length) {
    const c = (k) => graded.filter((l) => l.res === k).length;
    h += `<p class="callout">${esc(m.label)} props this season: <span class="res over">${c("over")} over</span> · <span class="res under">${c("under")} under</span>${c("push") ? ` · ${c("push")} push` : ""}</p>`;
  }
  return h + `</div>`;
}

// ---------- Results ----------
function viewResults() {
  if (!PX()) return `<p class="muted">No prop data yet.</p>`;
  const dates = lineDates().filter((d) => propRows(d).some((r) => r.l.res && r.l.res !== "pending")).reverse();
  if (!dates.length) return `<p class="muted">No graded props yet. Props are graded once each game is final and its box score is in.</p>`;
  let h = `<p class="callout">Every captured line, graded against the box score. Void = had a line but didn't play.</p>`;
  const tally = (rs) => { const t = { over: 0, under: 0, push: 0, void: 0 }; rs.forEach((r) => { if (t[r.l.res] != null) t[r.l.res]++; }); return t; };
  // season summary by market
  const allRows = dates.flatMap((d) => propRows(d)).filter((r) => r.l.res && r.l.res !== "pending");
  h += `<div class="panel"><h3>Season so far</h3><div class="scroll"><table><thead><tr><th>Market</th><th class="num">Over</th><th class="num">Under</th><th class="num">Push</th><th class="num">Void</th><th class="num">Over %</th></tr></thead><tbody>`;
  for (const m of PX().markets) {
    const t = tally(allRows.filter((r) => r.mk === m.id)), dec2 = t.over + t.under;
    h += `<tr><td>${esc(m.label)}</td><td class="num">${t.over}</td><td class="num">${t.under}</td><td class="num">${t.push}</td><td class="num">${t.void}</td><td class="num">${dec2 ? Math.round((t.over / dec2) * 100) + "%" : "—"}</td></tr>`;
  }
  h += `</tbody></table></div></div>`;
  for (const d of dates) {
    const rs = propRows(d).filter((r) => r.l.res && r.l.res !== "pending");
    const t = tally(rs);
    h += `<details class="panel resday"><summary><b>${fmtDate(d)}</b> <span class="muted small">${rs.length} props · <span class="res over">${t.over} over</span> · <span class="res under">${t.under} under</span>${t.push ? ` · ${t.push} push` : ""}${t.void ? ` · ${t.void} void` : ""}</span></summary>
      <div class="scroll"><table class="stable"><thead><tr><th>Player</th><th>Game</th><th>Mkt</th><th class="num">Line</th><th class="num">Actual</th><th>Result</th></tr></thead><tbody>`;
    rs.sort((a, b) => (PX().players[a.aid] || {}).name?.localeCompare((PX().players[b.aid] || {}).name) || MK_ORDER.indexOf(a.mk) - MK_ORDER.indexOf(b.mk));
    for (const r of rs) {
      h += `<tr><td data-label="Player"><a href="#/player/${encodeURIComponent(r.aid)}">${esc((PX().players[r.aid] || {}).name || r.aid)}</a></td><td data-label="Game">${esc(gLabel(r.gid))}</td>
        <td data-label="Market">${esc(mkById(r.mk).short)}</td><td class="num" data-label="Line">${n1(r.l.line)}</td><td class="num" data-label="Actual">${r.l.act != null ? n1(r.l.act) : "—"}</td><td data-label="Result">${resHtml(r.l)}</td></tr>`;
    }
    h += `</tbody></table></div></details>`;
  }
  return h;
}

// ---------- Guide ----------
function viewGuide() {
  return `<div class="panel"><h3>How the player board works</h3><div class="body guide">
    <p><b>Lines.</b> DraftKings and FanDuel player props are pulled from The Odds API twice per game: at <b>8:00 AM Central</b> on game day (retried until the books post them) and again about <b>1 hour before tip</b>. Until the 1-hour pull lands, the board shows the 8 AM line with an <span class="chip amchip">8 AM</span> chip; after it, ▲/▼ shows how far the line moved since 8 AM. The 1-hour line is the one graded. Only the core markets (points, rebounds, assists, threes) are pulled. PRA and the two-stat combos are built from those lines (two-stat combos: sum + 0.5; PRA: the sum, matching how DraftKings and FanDuel have most often set them in this season's captures), priced at -110/-110 and graded like any other line. Steals and blocks are no longer pulled; earlier captures still show. Nothing is pulled after tip. DraftKings is the line shown and graded; FanDuel is used when DraftKings has no line for that player and stat. Hover or tap a line to see both books.</p>
    <p><b>Grading.</b> Once the game is final, the actual stat from ESPN's box score is compared with the line: over, under or push. A player who had a line but didn't play is <i>void</i>, with ESPN's reason when it gives one.</p>
    <p><b>AVG / L5.</b> Season average and last-5 average over games the player actually played, counting only games before the date being viewed.</p>
    <p><b>HIT.</b> How many of his last ${HIT_N} games played went over <i>this</i> line (not the lines he had in those games).</p>
    <p><b>Trend.</b> Average of the last ${TREND.lastN} games vs. the season average: ↑ at least ${TREND.pct}% higher, ↓ at least ${TREND.pct}% lower, → otherwise. Needs ${TREND.minGames} games.</p>
    <p><b>Players with "no games yet"</b> have a line but no box score this season (first game, new team, or returning from injury). They're matched to ESPN's roster; stats appear after their first game.</p>
    <p class="muted">Data quality: ESPN's feeds are unofficial and can change. Player names are matched between the sportsbooks and ESPN by name; unmatched names are listed in the Log tab. Research tool only — not betting advice.</p>
  </div></div>`;
}

window.STIX_PROPS = {
  render(tab, arg) {
    if (tab === "player") return viewPlayer(arg);
    if (tab === "results") return viewResults();
    if (tab === "guide") return viewGuide();
    if (!tab || tab === "board") return viewBoard();
    return null;
  },
  bind(tab, arg) {
    const on = (id, ev, fn) => { const el = document.getElementById(id); if (el) el.addEventListener(ev, fn); };
    document.querySelectorAll("[data-pgid]").forEach((b) => b.addEventListener("click", () => { P.game = b.dataset.pgid; render(); }));
    on("p-date", "change", (e) => { P.date = e.target.value; P.game = ""; render(); });
    on("p-clear", "click", () => { Object.assign(P, { date: defaultDate(), game: "", mk: "", team: "", q: "" }); render(); });
    on("p-mk", "change", (e) => { P.mk = e.target.value; render(); });
    on("p-team", "change", (e) => { P.team = e.target.value; render(); });
    on("p-q", "input", (e) => { P.q = e.target.value; clearTimeout(P_TYPING); P_TYPING = setTimeout(() => { render(); const el = document.getElementById("p-q"); el.focus(); el.setSelectionRange(el.value.length, el.value.length); }, 200); });
    document.querySelectorAll("[data-pmk]").forEach((b) => b.addEventListener("click", () => { P.pmk[decodeURIComponent(arg)] = b.dataset.pmk; render(); }));
    const back = document.getElementById("m-back");
    if (back) back.addEventListener("click", (e) => { if (history.length > 1) { e.preventDefault(); history.back(); } });
  },
};
