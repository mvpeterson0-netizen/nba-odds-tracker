"use strict";
// Player props: Board, player pages and Results. Loaded before app.js; uses its helpers at render time.
// Data: data/props.json (built by nba_tracker/build.py).

const TREND = { minGames: 3, lastN: 3, pct: 15 };   // trend arrow: last 3 games vs season avg, ±15%
const HIT_N = 10;                                   // hit rate window (games played)
const P = { day: 0, game: "", q: "", pmk: {}, rmk: "core", bset: "core", subFrom: "" };   // day: -1 yesterday, 0 today, 1 tomorrow
let P_TYPING = null;

const PX = () => D.props;
const mkById = (id) => PX().markets.find((m) => m.id === id);
// Short market names for player pages: "Pts", "Reb", "Ast", "3PM", "PRA", "P+R"…
const ABBR = { PTS: "Pts", REB: "Reb", AST: "Ast", STL: "Stl", BLK: "Blk" };
const mkAbbr = (m) => ABBR[m.short] || m.short;
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
function dayET(offset) {   // NBA game date (US Eastern) offset from today
  const d = new Date(todayET() + "T12:00:00Z");
  d.setUTCDate(d.getUTCDate() + offset);
  return d.toISOString().slice(0, 10);
}
const DAYS = [[-1, "Yesterday"], [0, "Today"], [1, "Tomorrow"]];
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
  const date = dayET(P.day);
  const all = propRows(date);
  const gids = [...new Set([...all.map((r) => r.gid), ...gamesOn(date)])].sort((a, b) => String(gameOf(a).start).localeCompare(String(gameOf(b).start)));
  if (P.game && !gids.includes(P.game)) P.game = "";
  const q = P.q.trim().toLowerCase();
  const pl = (aid) => PX().players[aid] || { name: aid };
  let rows = all.filter((r) => (!P.game || r.gid === P.game) && (!q || pl(r.aid).name.toLowerCase().includes(q)));

  let h = `<div class="dayseg">${DAYS.map(([o, l]) => `<button data-pday="${o}" class="${P.day === o ? "on" : ""}">${l}<span>${fmtDate(dayET(o))}</span></button>`).join("")}</div>`;
  // Game chips filter to one game; tap the selected chip again to show every game.
  if (gids.length) h += `<div class="gamebar">` + gids.map((g) => `<button class="gchip ${P.game === g ? "on" : ""}" data-pgid="${esc(g)}"><b>${esc(gLabel(g))}</b><span class="muted small">${gameOf(g).final ? "Final" : esc(fmtClock(gameOf(g).start))}</span></button>`).join("") + `</div>`;
  h += `<div class="filters fsearch"><input type="search" id="p-q" placeholder="Search player" aria-label="Search player" value="${esc(P.q)}"></div>`;
  if (!gids.length) return h + `<p class="muted">No NBA games ${P.day < 0 ? "were played" : "scheduled"} on ${fmtDate(date)}.</p>`;
  const filtered = !!q;
  const waiting = gids.filter((g) => !all.some((r) => r.gid === g) && (!P.game || P.game === g));
  if (!rows.length && (filtered || !waiting.length)) return h + `<p class="muted">${filtered ? "No players match that search." : "No prop lines were captured for this date."}</p>`;

  const phoneView = !!(window.matchMedia && window.matchMedia("(max-width: 760px)").matches);
  if (phoneView) h += `<div class="bgrid-top"><div class="seg">${[["core", "Core"], ["combo", "Combos"]].map(([k, l]) => `<button data-bset="${k}" class="${P.bset === k ? "on" : ""}">${l}</button>`).join("")}</div>
    ${P.day < 0 ? "" : `<span class="muted small"><span class="amdot">•</span> = 8 AM line</span>`}</div>`;
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
      // Team grid: one row per player, one cell per market (line big; season avg, or actual once graded, small).
      const COLS = P.bset === "combo" ? MK_ORDER.slice(4, 8) : MK_ORDER.slice(0, 4);
      const g = gameOf(gid);
      const teams = [g.away, g.home].filter(Boolean);
      const order = [...teams, ...new Set(plist.map(([aid]) => pl(aid).team).filter((t) => !teams.includes(t)))];
      h += `<table class="bgrid"><thead><tr><th>Player</th>${COLS.map((mk) => `<th>${esc(mkById(mk).short)}</th>`).join("")}</tr></thead><tbody>`;
      for (const tm of order) {
        const tp = plist.filter(([aid]) => (pl(aid).team || "") === (tm || ""));
        if (!tp.length) continue;
        h += `<tr class="rteam"><td colspan="${COLS.length + 1}">${esc(tm || "")}</td></tr>`;
        for (const [aid, rs] of tp) {
          const p = pl(aid), by = Object.fromEntries(rs.map((r) => [r.mk, r.l]));
          const pHref = `#/player/${encodeURIComponent(aid)}`;
          h += `<tr><td class="bname"><a href="${pHref}">${face(aid, p.name)}<span class="nm">${esc(p.name)}</span></a></td>` + COLS.map((mk) => {
            const l = by[mk], href = `${pHref}/${mk}`;
            if (!l) return `<td class="bc na"><a href="${href}" aria-label="${esc(p.name)}">—</a></td>`;
            const tip = esc(lineTip(l));
            if (l.res === "void") return `<td class="bc void" title="${tip}"><a href="${href}"><b>${n1(l.line)}</b><small>DNP</small></a></td>`;
            if (l.res && l.res !== "pending") return `<td class="bc ${l.res}" title="${tip}"><a href="${href}"><b>${n1(l.line)}</b><small>act ${n1(l.act)}</small></a></td>`;
            const f = form(aid, mk, date, l.line);
            const cls = f.avg == null ? "" : f.avg > l.line ? "above" : f.avg < l.line ? "below" : "";
            return `<td class="bc ${cls}${l.pt === "morning" ? " am" : ""}" title="${tip}"><a href="${href}"><b>${n1(l.line)}</b><small>${f.avg == null ? "no games" : "avg " + n1(f.avg)}</small></a></td>`;
          }).join("") + `</tr>`;
        }
      }
      h += `</tbody></table>`;
    } else {
      h += `<div class="panel scroll"><table class="ptable"><thead><tr><th>Player</th><th>Mkt</th><th class="num">Line</th><th class="num">Over/Under</th><th>Book</th>
        <th class="num" title="Season average, games played">AVG</th><th class="num" title="Last 5 games played">L5</th><th class="num" title="Over this line, last ${HIT_N} games played">HIT</th><th>Trend</th><th class="num">Actual</th><th>Result</th></tr></thead><tbody>`;
      for (const [aid, rs] of plist) {
        const p = pl(aid);
        rs.sort((a, b) => MK_ORDER.indexOf(a.mk) - MK_ORDER.indexOf(b.mk)).forEach((r, i) => {
          const f = form(aid, r.mk, date, r.l.line);
          h += `<tr class="${i === 0 ? "plr" : ""}">${i === 0 ? `<td rowspan="${rs.length}" class="pcell"><a class="pc-a" href="#/player/${encodeURIComponent(aid)}">${face(aid, p.name)}<b>${esc(p.name)}</b></a><div class="muted small">${esc(p.team || "")}${p.pos ? " · " + esc(p.pos) : ""}${p.nolog ? " · no games yet" : ""}</div></td>` : ""}
            <td>${esc(mkById(r.mk).short)}</td><td class="num" title="${esc(lineTip(r.l))}"><a class="lnk" href="#/player/${encodeURIComponent(aid)}/${r.mk}">${lineCell(r.l)}</a></td><td class="num">${lineOdds(r.l)}</td><td class="muted">${bookShort(r.l.book)}</td>
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
  const W = 640, H = 236, L = 36, R = 16, T = 26, B = 32;
  const vals = [...logs.map((r) => r[st]), ...logs.map((r) => lineFor(r.g)).filter(Boolean).map((l) => l.line)];
  const hi0 = Math.max(...vals), lo0 = Math.min(...vals), pad = Math.max(2, (hi0 - lo0) * 0.18);
  const lo = Math.max(0, Math.floor(lo0 - pad)), hi = Math.ceil(hi0 + pad);
  const x = (i) => L + 10 + i * ((W - L - R - 20) / Math.max(1, logs.length - 1));
  const y = (v) => T + (H - T - B) * (1 - (v - lo) / (hi - lo));
  const tip = (r, l) => `${esc(r.d)} ${r.ha === "home" ? "vs" : "@"} ${esc(r.opp)}: ${n1(r[st])}${l ? ` (line ${n1(l.line)}${l.res ? ", " + l.res : ""})` : ""}`;
  let s = `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="${esc(mkById(mk).label)} by game: actual vs line">`;
  for (const v of [lo, (lo + hi) / 2, hi]) s += `<line x1="${L}" x2="${W - R}" y1="${y(v)}" y2="${y(v)}" stroke="var(--line)"/><text x="${L - 4}" y="${y(v) + 5}" font-size="14" text-anchor="end" fill="var(--muted)">${Math.round(v)}</text>`;
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
    if (l) s += `<text x="${x(i)}" y="${y(l.line) + (r[st] >= l.line ? 22 : -12)}" font-size="13" text-anchor="middle" fill="var(--muted)">${n1(l.line)}</text>`;
    const col = l && l.res === "over" ? "var(--over)" : l && l.res === "under" ? "var(--under)" : "var(--accent)";
    const above = !l || r[st] >= l.line;
    s += `<circle cx="${x(i)}" cy="${y(r[st])}" r="5.5" fill="${col}" stroke="var(--panel)" stroke-width="2"><title>${tip(r, l)}</title></circle>`;
    s += `<text x="${x(i)}" y="${y(r[st]) + (above ? -12 : 22)}" font-size="14" font-weight="600" text-anchor="middle" fill="var(--ink)">${n1(r[st])}</text>`;
    s += `<text x="${x(i)}" y="${H - 9}" font-size="13" text-anchor="middle" fill="var(--muted)">${esc((r.opp || "").slice(0, 3))}</text>`;
  });
  return s + `</svg>`;
}
function viewPlayer(aid, sub) {
  aid = decodeURIComponent(aid || "");
  // #/player/<id>/<market> opens with that market selected (applied once per visit, so tabs still work).
  if (sub && location.hash !== P.subFrom && PX() && mkById(sub)) { P.pmk[aid] = sub; P.subFrom = location.hash; }
  const p = PX() && PX().players[aid];
  if (!p) return `<p>Player not found. <a href="#/board">Back to the board</a></p>`;
  const mk = P.pmk[aid] || "player_points", m = mkById(mk);
  const myLines = PX().lines[aid] || {};
  const upcoming = Object.keys(myLines).filter((g) => !gameOf(g).final).sort((a, b) => String(gameOf(a).start).localeCompare(String(gameOf(b).start)))[0];
  const curG = upcoming || Object.keys(myLines).sort((a, b) => String(gameOf(b).start).localeCompare(String(gameOf(a).start)))[0];
  const cur = curG ? myLines[curG][mk] : null;
  const f = form(aid, mk, curG ? gameOf(curG).date : null, cur ? cur.line : null);
  let h = `<div class="mplayer"><div class="mp-top"><a href="#/board" class="mback" id="m-back">‹ Board</a></div>
    <div class="mp-h">${face(aid, p.name, "lg")}<div><h2>${esc(p.name)}</h2><div class="muted">${esc(p.team || "")}${p.pos ? " · " + esc(p.pos) : ""}</div>${curG ? `<div class="small">${gameHeader(curG)}</div>` : ""}</div></div>
    <div class="mtabs">${PX().markets.map((x) => `<button data-pmk="${x.id}" class="${x.id === mk ? "on" : ""}">${esc(mkAbbr(x))}</button>`).join("")}</div>
    <div class="mtiles">
      <div><span>LINE</span>${cur ? `<b title="${esc(lineTip(cur))}">${n1(cur.line)}</b><small>${lineOdds(cur)} ${bookShort(cur.book)}</small>` : `<span class="na">none</span>`}</div>
      <div><span>AVG</span><b>${n1(f.avg)}</b><small>${f.n} game${f.n === 1 ? "" : "s"}</small></div>
      <div><span>L5</span><b>${n1(f.l5)}</b></div>
      <div><span>HIT</span>${hitHtml(f)}<small>over line</small></div>
      <div><span>TREND</span>${trendHtml(f, true)}</div>
    </div>
    <div class="panel"><h3>${esc(mkAbbr(m))} by game</h3><div class="chart">${chartSVG(aid, mk)}</div>
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
    h += `<p class="callout">${esc(mkAbbr(m))} props this season: <span class="res over">${c("over")} over</span> · <span class="res under">${c("under")} under</span>${c("push") ? ` · ${c("push")} push` : ""}</p>`;
  }
  return h + `</div>`;
}

// ---------- Player photos ----------
// ESPN headshots keyed by ESPN athlete id (the ids Dime already uses). Tries ESPN's resized
// image first, then the full-size file, then falls back to the player's initials.
const HS = (aid) => `https://a.espncdn.com/i/headshots/nba/players/full/${encodeURIComponent(aid)}.png`;
const HS_SM = (aid, w) => `https://a.espncdn.com/combiner/i?img=/i/headshots/nba/players/full/${encodeURIComponent(aid)}.png&w=${w}&h=${Math.round(w * 0.727)}`;
function faceErr(img) {
  if (img.dataset.full) { img.src = img.dataset.full; delete img.dataset.full; }
  else img.remove();
}
function face(aid, name, cls = "") {
  const ini = String(name || "").split(/\s+/).filter(Boolean).map((w) => w[0]).slice(0, 2).join("").toUpperCase();
  const w = cls === "lg" ? 240 : 96;
  return `<span class="face ${cls}" aria-hidden="true"><span class="ini">${esc(ini)}</span><img loading="lazy" alt="" src="${HS_SM(aid, w)}" data-full="${HS(aid)}" onerror="faceErr(this)"></span>`;
}

// ---------- Results ----------
function viewResults() {
  if (!PX()) return `<p class="muted">No prop data yet.</p>`;
  const shown = (r) => r.l.res === "over" || r.l.res === "under"; // Results hides voids and pushes
  const dates = lineDates().filter((d) => propRows(d).some(shown)).reverse();
  if (!dates.length) return `<p class="muted">No graded props yet. Props are graded once each game is final and its box score is in.</p>`;
  let h = `<p class="callout">Green = over, red = under.</p>`;
  const tally = (rs) => { const t = { over: 0, under: 0 }; rs.forEach((r) => { if (t[r.l.res] != null) t[r.l.res]++; }); return t; };
  const COLS = P.rmk === "combo" ? MK_ORDER.slice(4, 8) : MK_ORDER.slice(0, 4);
  h += `<div class="seg rseg">${[["core", "PTS · REB · AST · 3PM"], ["combo", "PRA · P+R · P+A · R+A"]].map(([k, l]) => `<button data-rmk="${k}" class="${P.rmk === k ? "on" : ""}">${l}</button>`).join("")}</div>`;
  dates.forEach((d, di) => {
    const rs = propRows(d).filter(shown);
    const t = tally(rs);
    h += `<details class="panel resday" ${di === 0 ? "open" : ""}><summary><b>${fmtDate(d)}</b> <span class="muted small"><span class="res over">${t.over} over</span> · <span class="res under">${t.under} under</span></span></summary>`;
    const gids = [...new Set(rs.map((r) => r.gid))].sort((a, b) => String(gameOf(a).start).localeCompare(String(gameOf(b).start)));
    for (const gid of gids) {
      const g = gameOf(gid);
      const byP = new Map();
      for (const r of rs.filter((x) => x.gid === gid)) { if (!byP.has(r.aid)) byP.set(r.aid, {}); byP.get(r.aid)[r.mk] = r.l; }
      const team = (aid) => (PX().players[aid] || {}).team || "";
      const ptsLine = (m) => (m.player_points || {}).line || 0;
      h += `<div class="rgame"><div class="rgame-h"><b>${esc(g.away || "")} ${g.as ?? ""}</b> @ <b>${esc(g.home || "")} ${g.hs ?? ""}</b>${g.final ? ` <span class="muted small">Final</span>` : ""}</div>
        <table class="rgrid"><thead><tr><th>Player</th>${COLS.map((mk) => `<th>${esc(mkById(mk).short)}</th>`).join("")}</tr></thead><tbody>`;
      for (const tm of [g.away, g.home]) {
        const plist = [...byP.entries()].filter(([aid]) => team(aid) === tm).sort((a, b) => ptsLine(b[1]) - ptsLine(a[1]));
        if (!plist.length) continue;
        h += `<tr class="rteam"><td colspan="${COLS.length + 1}">${esc(tm)}</td></tr>`;
        for (const [aid, ms] of plist) {
          const nm = (PX().players[aid] || {}).name || aid;
          h += `<tr><td class="rname"><a href="#/player/${encodeURIComponent(aid)}">${face(aid, nm)}<span class="nm">${esc(nm)}</span></a></td>` + COLS.map((mk) => {
            const l = ms[mk];
            if (!l) return `<td class="rc na">—</td>`;
            return `<td class="rc ${l.res}" title="Line ${n1(l.line)}, actual ${n1(l.act)}: ${l.res}"><b>${n1(l.line)}</b><small>act ${n1(l.act)}</small></td>`;
          }).join("") + `</tr>`;
        }
      }
      // Players whose team didn't match either side (rare name/roster mismatches)
      const other = [...byP.keys()].filter((aid) => team(aid) !== g.away && team(aid) !== g.home);
      for (const aid of other) {
        const ms = byP.get(aid), nm = (PX().players[aid] || {}).name || aid;
        h += `<tr><td class="rname"><a href="#/player/${encodeURIComponent(aid)}">${face(aid, nm)}<span class="nm">${esc(nm)}</span></a></td>` + COLS.map((mk) => { const l = ms[mk]; return l ? `<td class="rc ${l.res}"><b>${n1(l.line)}</b><small>act ${n1(l.act)}</small></td>` : `<td class="rc na">—</td>`; }).join("") + `</tr>`;
      }
      h += `</tbody></table></div>`;
    }
    h += `</details>`;
  });
  // season summary by market
  const allRows = dates.flatMap((d) => propRows(d)).filter(shown);
  h += `<div class="panel"><h3>Season so far</h3><div class="scroll"><table><thead><tr><th>Market</th><th class="num">Over</th><th class="num">Under</th><th class="num">Over %</th></tr></thead><tbody>`;
  for (const m of PX().markets) {
    const t = tally(allRows.filter((r) => r.mk === m.id)), dec2 = t.over + t.under;
    h += `<tr><td>${esc(m.label)}</td><td class="num">${t.over}</td><td class="num">${t.under}</td><td class="num">${dec2 ? Math.round((t.over / dec2) * 100) + "%" : "—"}</td></tr>`;
  }
  h += `</tbody></table></div></div>`;
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
  render(tab, arg, sub) {
    if (tab !== "player") P.subFrom = "";
    if (tab === "player") return viewPlayer(arg, sub);
    if (tab === "results") return viewResults();
    if (tab === "guide") return viewGuide();
    if (!tab || tab === "board") return viewBoard();
    return null;
  },
  bind(tab, arg) {
    const on = (id, ev, fn) => { const el = document.getElementById(id); if (el) el.addEventListener(ev, fn); };
    document.querySelectorAll("[data-pgid]").forEach((b) => b.addEventListener("click", () => { P.game = P.game === b.dataset.pgid ? "" : b.dataset.pgid; render(); }));
    document.querySelectorAll("[data-pday]").forEach((b) => b.addEventListener("click", () => { P.day = Number(b.dataset.pday); P.game = ""; render(); }));
    document.querySelectorAll("[data-bset]").forEach((b) => b.addEventListener("click", () => { P.bset = b.dataset.bset; render(); }));
    document.querySelectorAll("[data-rmk]").forEach((b) => b.addEventListener("click", () => { P.rmk = b.dataset.rmk; render(); }));
    on("p-q", "input", (e) => { P.q = e.target.value; clearTimeout(P_TYPING); P_TYPING = setTimeout(() => { render(); const el = document.getElementById("p-q"); el.focus(); el.setSelectionRange(el.value.length, el.value.length); }, 200); });
    document.querySelectorAll("[data-pmk]").forEach((b) => b.addEventListener("click", () => { P.pmk[decodeURIComponent(arg)] = b.dataset.pmk; render(); }));
    const onTab = document.querySelector(".mtabs button.on");
    if (onTab && onTab.scrollIntoView) onTab.scrollIntoView({ block: "nearest", inline: "center" });
    const back = document.getElementById("m-back");
    if (back) back.addEventListener("click", (e) => { if (history.length > 1) { e.preventDefault(); history.back(); } });
  },
};
