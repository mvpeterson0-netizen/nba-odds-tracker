"use strict";
// Player props: Board, player pages and Results. Loaded before app.js; uses its helpers at render time.
const updIcon = (aid) => (window.DIME_NEWS && MODE === "nba" ? window.DIME_NEWS.icon(aid) : "");   // notes icon (news.js); NBA only
// Everything below is shared by the NBA and college (cbb.js) sections: MODE ("nba" | "cbb", set by app.js) picks the
// data file and the links. College only ever has the points market, so its views are built in cbb.js.
const R = (path) => `#/${MODE === "cbb" ? "cbb/" : ""}${path}`;       // in-app link for the current section
// Data: data/props.json (built by nba_tracker/build.py).

const TREND = { minGames: 3, lastN: 3, pct: 15 };   // trend arrow: last 3 games vs season avg, ±15%
const HIT_N = 10;                                   // hit rate window (games played)
const P = { day: 0, game: "", q: "", pmk: {}, rf: { mk: "player_points" }, dmk: "player_points", dall: false, bset: "core", subFrom: "" };   // day: -1 yesterday, 0 today, 1 tomorrow
let P_TYPING = null;

const PX = () => (MODE === "cbb" ? D.cbb : D.props);
const mkById = (id) => PX().markets.find((m) => m.id === id);
// Short market names for player pages: "Pts", "Reb", "Ast", "3PM", "PRA", "P+R"…
const ABBR = { PTS: "Pts", REB: "Reb", AST: "Ast", STL: "Stl", BLK: "Blk" };
const mkAbbr = (m) => ABBR[m.short] || m.short;
const mean = (a) => (a.length ? a.reduce((x, y) => x + y, 0) / a.length : null);
const n1 = (v) => (v == null ? "—" : Number.isInteger(v) ? String(v) : v.toFixed(1));
const gameOf = (gid) => PX().games[gid] || {};
const gLabel = (gid) => {
  const g = gameOf(gid);
  if (!g.away) return gid;
  const rk = (r) => (MODE === "cbb" && r ? `#${r} ` : "");   // AP-style rank, college only
  return `${rk(g.ar)}${g.away} @ ${rk(g.hr)}${g.home}`;
};

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
const AM = () => (MODE === "cbb" ? "8 AM" : "7 AM");   // morning-pull label: college 8 AM, NBA 7 AM
const ONE_PULL = () => MODE === "cbb";      // college props are pulled once (8 AM), so there is no "updates before tip" step
const lineKind = (l) => (ONE_PULL() ? "Line (8 AM)" : l.pt === "morning" ? `${AM()} line` : "Pre-game line");
function lineTip(l) {
  if (l.est) {
    const parts = Object.entries(l.from || {}).map(([k, v]) => `${mkById(k).short} ${n1(v)}`).join(" + ");
    return `${lineKind(l)}: ${bookShort(l.book)} ${n1(l.line)} -110/-110 (from ${parts})` +
      (l.pt === "morning" && !ONE_PULL() ? ". Updates about 1 hour before tip." : "");
  }
  const alt = Object.entries(l.alt || {}).map(([b, x]) => `${bookShort(b)} ${n1(x.line)} (${lineOdds(x)})`).join(", ");
  const kind = lineKind(l);
  return `${kind}: ${bookShort(l.book)} ${n1(l.line)} ${lineOdds(l)}, captured ${fmtTime(l.cap)} (${l.mb} min before tip)` +
    (l.am ? `. ${AM()}: ${n1(l.am.line)} (${lineOdds(l.am)})` : "") +
    (l.pt === "morning" && !ONE_PULL() ? ". Updates about 1 hour before tip." : "") + (alt ? `. Also: ${alt}` : "");
}
// Line with its context: "8 AM" chip until the pre-game pull lands; movement since 8 AM after.
function lineCell(l) {
  let h = `<b>${n1(l.line)}</b>`;
  if (l.pt === "morning" && !ONE_PULL()) h += ` <span class="chip amchip">${AM()}</span>`;
  else if (l.am && l.am.line != null && l.am.line !== l.line) {
    const d = l.line - l.am.line;
    h += ` <span class="mv ${d > 0 ? "up" : "down"}" title="Moved from ${n1(l.am.line)} at ${AM()}">${d > 0 ? "▲" : "▼"}${n1(Math.abs(d))}</span>`;
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
  if (ONE_PULL()) return "Player points are pulled once, at 8:00 AM Central on game day (re-checked about hourly until the books post them).";
  return `Lines are pulled at 7:00 AM Central (once the books post them) and again about 1 hour before tip (~${fmtClock(pre.toISOString())}).`;
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
    ${P.day < 0 || ONE_PULL() ? "" : `<span class="muted small"><span class="amdot">•</span> = ${AM()} line</span>`}</div>`;
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
          h += `<tr><td class="bname"><a href="${pHref}">${face(aid, p.name)}<span class="nm">${esc(p.name)}</span>${updIcon(aid)}</a></td>` + COLS.map((mk) => {
            const l = by[mk], href = `${pHref}/${mk}`;
            if (!l) return `<td class="bc na"><a href="${href}" aria-label="${esc(p.name)}">—</a></td>`;
            const tip = esc(lineTip(l));
            if (l.res === "void") return `<td class="bc void" title="${tip}"><a href="${href}"><b>${n1(l.line)}</b><small>DNP</small></a></td>`;
            if (l.res && l.res !== "pending") return `<td class="bc ${l.res}" title="${tip}"><a href="${href}"><b>${n1(l.line)}</b><small>act ${n1(l.act)}</small></a></td>`;
            const f = form(aid, mk, date, l.line);
            const cls = f.avg == null ? "" : f.avg > l.line ? "above" : f.avg < l.line ? "below" : "";
            return `<td class="bc ${cls}${l.pt === "morning" && !ONE_PULL() ? " am" : ""}" title="${tip}"><a href="${href}"><b>${n1(l.line)}</b><small>${f.avg == null ? "no games" : "avg " + n1(f.avg)}</small></a></td>`;
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
          h += `<tr class="${i === 0 ? "plr" : ""}">${i === 0 ? `<td rowspan="${rs.length}" class="pcell"><a class="pc-a" href="#/player/${encodeURIComponent(aid)}">${face(aid, p.name)}<b>${esc(p.name)}</b></a> ${updIcon(aid)}<div class="muted small">${esc(p.team || "")}${p.pos ? " · " + esc(p.pos) : ""}${p.nolog ? " · no games yet" : ""}</div></td>` : ""}
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
// Games with captured lines that haven't been played yet (no box score, not final): today's game,
// shown in the log and chart with lines only until the actual stats arrive.
function pendingGames(aid) {
  const p = PX().players[aid] || {}, seen = new Set((PX().logs[aid] || []).map((r) => r.g));
  return Object.keys(PX().lines[aid] || {}).filter((gid) => !seen.has(gid) && !gameOf(gid).final)
    .sort((a, b) => String(gameOf(a).start).localeCompare(String(gameOf(b).start)))
    .map((gid) => { const g = gameOf(gid), home = p.team ? p.team === g.home : false;
      return { g: gid, d: g.date, pend: true, ha: home ? "home" : "away", opp: home ? g.away : g.home }; });
}
// ---------- Chart labels: sizes and collision-free placement ----------
// Both player charts (line vs defense, and the plain by-game chart) share these. Labels are placed greedily, most
// important first: each tries a few spots around its point and takes the first one that doesn't touch another label or
// any marker; a label with no clear spot is dropped (its value is still in the marker's tooltip).
const chartPhone = () => !!(window.matchMedia && window.matchMedia("(max-width: 760px)").matches);
const chartDims = (rank) => (chartPhone()
  ? { W: 420, H: 380, L: 38, R: rank ? 34 : 14, T: 26, B: 50, fs: 17, games: 7 }
  : { W: 720, H: 380, L: 44, R: rank ? 40 : 18, T: 28, B: 52, fs: 17, games: 7 });
function labelLayer(bounds) {
  const rects = [], pad = 2;
  const hit = (a, b) => a[0] < b[2] + pad && a[2] > b[0] - pad && a[1] < b[3] + pad && a[3] > b[1] - pad;
  const inside = (r) => r[0] >= bounds[0] && r[2] <= bounds[2] && r[1] >= bounds[1] && r[3] <= bounds[3];
  const box = (text, x, y, fs) => { const w = String(text).length * fs * 0.52 + 4; return [x - w / 2, y - fs * 0.92, x + w / 2, y + fs * 0.28]; };   // a little wider than real glyphs
  return {
    marker(x, y, r = 7) { rects.push([x - r, y - r, x + r, y + r]); },
    // pref "up" / "down": which side of the point to try first. Returns {x, y} of the text baseline, or null.
    place(text, x, y, fs, pref, bold) {
      const w = String(text).length * fs * 0.52 + 4, step = fs * 1.15;
      const up = (k) => y - 16 - k * step, dn = (k) => y + fs + 9 + k * step;
      const order = pref === "down" ? [dn, up] : [up, dn];
      const spots = [];
      for (const k of [0, 1, 2, 3]) for (const f of order) spots.push([x, f(k)]);                 // straight above / below, nearer first
      for (const k of [0, 1]) for (const f of order) for (const sx of [-1, 1]) spots.push([x + sx * (w / 2 + 9), f(k)]);   // diagonals
      for (const sx of [-1, 1]) spots.push([x + sx * (w / 2 + 12), y + fs * 0.36]);            // beside the point
      for (const [sx, sy] of spots) {
        const b = box(text, sx, sy, fs);
        if (inside(b) && !rects.some((o) => hit(b, o))) { rects.push(b); return { x: sx, y: sy }; }
      }
      return null;
    },
  };
}
// Axis scale for a set of stat values: padded range with whole-number ticks.
function statScale(vals, T, H, B) {
  const hi0 = Math.max(...vals), lo0 = Math.min(...vals), pad = Math.max(hi0 - lo0 <= 6 ? 1 : 2, (hi0 - lo0) * 0.18);
  const lo = Math.max(0, Math.floor(lo0 - pad)); let hi = Math.ceil(hi0 + pad); if ((hi - lo) % 2) hi++;     // even span: the middle tick is a whole number
  return { lo, hi, y: (v) => T + (H - T - B) * (1 - (v - lo) / (hi - lo)) };
}
const oppLabel = (r) => esc((r.opp || "").slice(0, MODE === "cbb" ? 4 : 3));

function chartSVG(aid, mk) {
  const st = mkById(mk).stat, D0 = chartDims(false), { W, H, L, R, T, B, fs } = D0;
  const lineFor = (gid) => ((PX().lines[aid] || {})[gid] || {})[mk];
  const pend = pendingGames(aid).filter((r) => lineFor(r.g)).slice(0, 2);
  const logs = [...played(aid).filter((r) => r[st] != null).slice(-(D0.games - pend.length)), ...pend];
  if (logs.length < 2) return `<p class="muted small pad">Not enough games for a chart yet.</p>`;
  const x = (i) => L + 28 + i * ((W - L - R - 56) / Math.max(1, logs.length - 1));
  const vals = [...logs.filter((r) => !r.pend).map((r) => r[st]), ...logs.map((r) => lineFor(r.g)).filter(Boolean).map((l) => l.line)];
  const { lo, hi, y } = statScale(vals, T, H, B);
  const tip = (r, l) => `${esc(r.d)} ${r.ha === "home" ? "vs" : "@"} ${esc(r.opp)}: ${n1(r[st])}${l ? ` (line ${n1(l.line)}${l.res ? ", " + l.res : ""})` : ""}`;
  const lay = labelLayer([L, 4, W - R, H - B - 1]);
  logs.forEach((r, i) => { const l = lineFor(r.g); if (l) lay.marker(x(i), y(l.line)); if (!r.pend) lay.marker(x(i), y(r[st])); });
  let s = `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="${esc(mkById(mk).label)} by game: actual vs line">`;
  for (const v of [lo, (lo + hi) / 2, hi]) s += `<line x1="${L}" x2="${W - R}" y1="${y(v)}" y2="${y(v)}" stroke="var(--line)"/><text x="${L - 6}" y="${y(v) + fs * 0.35}" font-size="${fs}" text-anchor="end" fill="var(--muted)">${Math.round(v)}</text>`;
  let seg = [];
  const flush = () => { if (seg.length > 1) s += `<polyline points="${seg.join(" ")}" fill="none" stroke="var(--muted)" stroke-width="1.5" stroke-dasharray="4 4"/>`; seg = []; };
  logs.forEach((r, i) => { const l = lineFor(r.g); if (l) seg.push(`${x(i)},${y(l.line)}`); else flush(); });
  flush();
  s += `<polyline points="${logs.map((r, i) => (r.pend ? "" : `${x(i)},${y(r[st])}`)).filter(Boolean).join(" ")}" fill="none" stroke="var(--accent)" stroke-width="2.5" stroke-linejoin="round"/>`;
  let marks = "", text = "";
  logs.forEach((r, i) => {
    const l = lineFor(r.g);
    if (l) marks += `<rect x="${x(i) - 4.5}" y="${y(l.line) - 4.5}" width="9" height="9" transform="rotate(45 ${x(i)} ${y(l.line)})" fill="var(--panel)" stroke="var(--ink)" stroke-width="2"><title>${r.pend ? `${esc(r.d)} ${r.ha === "home" ? "vs" : "@"} ${esc(r.opp || "")}: line ${n1(l.line)} (not played yet)` : `Line ${n1(l.line)}`}</title></rect>`;
    if (!r.pend) {
      const col = l && l.res === "over" ? "var(--over)" : l && l.res === "under" ? "var(--under)" : "var(--accent)";
      marks += `<circle cx="${x(i)}" cy="${y(r[st])}" r="5.5" fill="${col}" stroke="var(--panel)" stroke-width="2"><title>${tip(r, l)}</title></circle>`;
    }
    text += `<text x="${x(i)}" y="${H - B + fs + 8}" font-size="${fs}" text-anchor="middle" fill="var(--muted)">${oppLabel(r)}</text>` + (r.pend ? `<text x="${x(i)}" y="${H - 6}" font-size="${fs - 3}" text-anchor="middle" fill="var(--muted)">next</text>` : "");
  });
  // value labels, most important first: actuals, then lines
  logs.forEach((r, i) => { if (r.pend) return; const l = lineFor(r.g), p = lay.place(n1(r[st]), x(i), y(r[st]), fs, !l || r[st] >= l.line ? "up" : "down", true);
    if (p) text += `<text x="${p.x}" y="${p.y}" stroke="var(--panel)" stroke-width="4" paint-order="stroke" stroke-linejoin="round" font-size="${fs}" font-weight="700" text-anchor="middle" fill="var(--ink)">${n1(r[st])}</text>`; });
  logs.forEach((r, i) => { const l = lineFor(r.g); if (!l) return; const p = lay.place(n1(l.line), x(i), y(l.line), fs, "up", false);
    if (p) text += `<text x="${p.x}" y="${p.y}" stroke="var(--panel)" stroke-width="4" paint-order="stroke" stroke-linejoin="round" font-size="${fs}" text-anchor="middle" fill="var(--muted)"${r.pend ? ' font-style="italic"' : ""}>${n1(l.line)}</text>`; });
  return s + marks + text + `</svg>`;
}
// "Bet on FanDuel": Over / Under buttons that open FanDuel with that bet on the slip (addToBetslip?marketId=…&selectionId=…,
// from the latest FanDuel pull; built in nba_tracker/build.py from data/prop_links.csv). Ported from the NFL tracker (Stix).
// Shown before tip when FanDuel had the player's line in that pull (core markets only: pts, reb, ast, 3PM; combos are
// estimated here, so they have no link). FanDuel's link names the market and side, not a number, so the buttons show the
// line and odds FanDuel had at the last pull; FanDuel's slip shows whatever it is posting now.
const FD_SLIP = /^https:\/\/sportsbook\.fanduel\.com\/addToBetslip\?/;
function betBox(aid, mk) {
  if (MODE !== "nba") return "";
  const e = ((((PX().links || {})[aid] || {})[mk]) || {}).fanduel;
  if (!e) return "";
  const o = e.o && FD_SLIP.test(e.o.url || "") ? e.o : null, u = e.u && FD_SLIP.test(e.u.url || "") ? e.u : null;
  if (!o && !u) return "";
  const g = gameOf(e.gid);
  if (!g.start || new Date(g.start) <= new Date() || g.final) return "";
  const a = (side, x) => x ? `<a class="betbtn" href="${esc(x.url)}" target="_blank" rel="noopener" title="Opens FanDuel with this bet on the slip">${side} ${n1(e.point)} <span class="muted">${x.price == null ? "" : am(x.price)}</span> ↗</a>` : "";
  return `<div class="betbox"><span class="betlbl">Bet on FanDuel</span>${a("Over", o)}${a("Under", u)}
    <span class="betnote muted small">As of ${esc(fmtTime(e.cap))}. FanDuel's slip shows its current line.</span></div>`;
}

function viewPlayer(aid, sub) {
  aid = decodeURIComponent(aid || "");
  // #/player/<id>/<market> opens with that market selected (applied once per visit, so tabs still work).
  if (sub && location.hash !== P.subFrom && PX() && mkById(sub)) { P.pmk[aid] = sub; P.subFrom = location.hash; }
  const p = PX() && PX().players[aid];
  if (!p) return `<p>Player not found. <a href="${R("board")}">Back to the board</a></p>`;
  const mk = P.pmk[aid] || "player_points", m = mkById(mk);
  const myLines = PX().lines[aid] || {};
  const upcoming = Object.keys(myLines).filter((g) => !gameOf(g).final).sort((a, b) => String(gameOf(a).start).localeCompare(String(gameOf(b).start)))[0];
  const curG = upcoming || Object.keys(myLines).sort((a, b) => String(gameOf(b).start).localeCompare(String(gameOf(a).start)))[0];
  const cur = curG ? myLines[curG][mk] : null;
  const f = form(aid, mk, curG ? gameOf(curG).date : null, cur ? cur.line : null);
  let h = `<div class="mplayer"><div class="mp-top"><a href="${R("board")}" class="mback" id="m-back">‹ Board</a></div>
    <div class="mp-h">${face(aid, p.name, "lg")}<div><h2>${esc(p.name)} ${updIcon(aid)}</h2><div class="muted">${esc(p.team || "")}${p.pos ? " · " + esc(p.pos) : ""}</div>${curG ? `<div class="small">${gameHeader(curG)}</div>` : ""}</div></div>
    ${PX().markets.length > 1 ? `<div class="mtabs">${PX().markets.map((x) => `<button data-pmk="${x.id}" class="${x.id === mk ? "on" : ""}">${esc(mkAbbr(x))}</button>`).join("")}</div>` : ""}
    <div class="mtiles">
      <div><span>LINE</span>${cur ? `<b title="${esc(lineTip(cur))}">${n1(cur.line)}</b><small>${lineOdds(cur)} ${bookShort(cur.book)}</small>` : `<span class="na">none</span>`}</div>
      <div><span>AVG</span><b>${n1(f.avg)}</b><small>${f.n} game${f.n === 1 ? "" : "s"}</small></div>
      <div><span>L5</span><b>${n1(f.l5)}</b></div>
      <div><span>HIT</span>${hitHtml(f)}<small>over line</small></div>
      <div><span>TREND</span>${trendHtml(f, true)}</div>
    </div>
    ${betBox(aid, mk)}
  `;
  // NBA: the line-vs-opponent-defense chart replaces the plain "by game" chart; fall back to the plain one when it can't be drawn
  const defPanel = MODE === "nba" ? defTrendPanel(aid, mk) : "";
  h += defPanel || `<div class="panel"><h3>${esc(mkAbbr(m))} by game</h3><div class="chart">${chartSVG(aid, mk)}</div>
      <div class="legend"><span><i class="lg-act"></i>Actual</span>${Object.values(myLines).some((ms) => ms[mk]) ? `<span><i class="lg-line"></i>Line</span>` : ""}</div></div>`;
  // game log
  const logs = [...(PX().logs[aid] || [])].reverse();
  // Base box-score columns, plus the selected market's column when it's a combo (PRA, P+R, ...).
  // Phones hide STL/BLK (no longer pulled) unless that market is the one selected.
  const isPhone = !!(window.matchMedia && window.matchMedia("(max-width: 760px)").matches);
  const allCols = MODE === "cbb" ? [["pts", "PTS"]] : BASE_COLS;    // college box scores are kept for points only
  const base = isPhone ? allCols.filter(([k]) => !["stl", "blk"].includes(k) || k === m.stat) : allCols;
  const cols = base.some(([k]) => k === m.stat) ? base : [...base, [m.stat, m.short]];
  const oppTxt = (r) => `${r.ha === "home" ? "" : "@"}${esc(r.opp || "")}`;   // "IND" = home, "@CLE" = away
  h += `<div class="panel"><h3>Game log</h3><div class="scroll"><table class="ltable"><thead><tr><th>Date</th><th>Opp</th><th class="num">MIN</th>
    ${cols.map(([k, lab]) => `<th class="num ${k === m.stat ? "sel" : ""}">${esc(lab)}</th>`).join("")}<th class="num">Line</th><th>Result</th></tr></thead><tbody>`;
  // Today's (unplayed) game on top: each stat column shows that market's line in italics until the box score is in.
  const pendRows = pendingGames(aid).reverse();
  for (const r of pendRows) {
    const ms = myLines[r.g] || {}, l = ms[mk];
    const lineOf = (k) => { const x = PX().markets.find((mm) => mm.stat === k && ms[mm.id]); return x ? ms[x.id] : null; };
    h += `<tr class="pendrow"><td>${fmtDate(r.d)}</td><td>${oppTxt(r)}</td><td class="num na">—</td>
      ${cols.map(([k]) => { const lx = lineOf(k); return `<td class="num ${k === m.stat ? "sel" : ""}">${lx ? `<i title="${esc(lineTip(lx))}">${n1(lx.line)}</i>` : `<span class="na">—</span>`}</td>`; }).join("")}
      <td class="num">${l ? `<span title="${esc(lineTip(l))}">${n1(l.line)}</span>` : ""}</td><td>${l ? resHtml(l) : ""}</td></tr>`;
  }
  if (!logs.length && !pendRows.length) h += `<tr><td colspan="${cols.length + 5}" class="muted">No games played yet this season.</td></tr>`;
  for (const r of logs) {
    const l = (myLines[r.g] || {})[mk];
    h += `<tr><td>${fmtDate(r.d)}</td><td>${oppTxt(r)}${r.st ? "" : ` <span class="muted small">bench</span>`}</td>
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
const HS_LG = () => (MODE === "cbb" ? "mens-college-basketball" : "nba");     // ESPN's headshot folder per league
const HS = (aid) => `https://a.espncdn.com/i/headshots/${HS_LG()}/players/full/${encodeURIComponent(aid)}.png`;
const HS_SM = (aid, w) => `https://a.espncdn.com/combiner/i?img=/i/headshots/${HS_LG()}/players/full/${encodeURIComponent(aid)}.png&w=${w}&h=${Math.round(w * 0.727)}`;
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
// Filters (top of page): market, position, and the team the player was up against (the opponent).
const POS_LIST = ["G", "F", "C"];
// The only markets offered in the Market filters (Results and Defense).
const FILTER_MKS = ["player_points", "player_rebounds", "player_assists", "player_threes", "player_steals", "player_blocks"];
const FILTER_LABEL = { player_points: "Points", player_rebounds: "Rebounds", player_assists: "Assists", player_threes: "Threes made", player_steals: "Steals", player_blocks: "Blocks" };
const posOf = (aid) => (PX().players[aid] || {}).pos || "";
const oppOf = (r) => {     // opponent of the player's team in that game ("" if the player's team doesn't match either side)
  const g = gameOf(r.gid), t = (PX().players[r.aid] || {}).team;
  return t && t === g.home ? g.away || "" : t && t === g.away ? g.home || "" : "";
};
const rfCols = (mk) => [mk];
const gradedRow = (r) => r.l && (r.l.res === "over" || r.l.res === "under");   // Results hides voids and pushes

function viewResults() {
  if (!PX()) return `<p class="muted">No prop data yet.</p>`;
  const allGraded = lineDates().flatMap((d) => propRows(d)).filter(gradedRow);
  if (!allGraded.length) return `<p class="muted">No graded props yet. Props are graded once each game is final and its box score is in.</p>`;
  const tally = (rs) => {
    const t = { over: 0, under: 0, diff: 0 };
    rs.forEach((r) => { if (t[r.l.res] != null) t[r.l.res]++; t.diff += r.l.act - r.l.line; });
    return t;
  };
  const pct = (t) => (t.over + t.under ? Math.round((t.over / (t.over + t.under)) * 100) + "%" : "—");
  let h = `<p class="callout">Season to date. Over–under counts and the average of (actual − line) for graded props. Pushes and voids are excluded.</p>`;
  h += `<div class="panel"><h3>Season by market</h3><div class="scroll"><table><thead><tr><th>Market</th><th class="num">Over</th><th class="num">Under</th><th class="num">Over %</th><th class="num">Avg vs line</th></tr></thead><tbody>`;
  for (const m of PX().markets) {
    const t = tally(allGraded.filter((r) => r.mk === m.id)), n = t.over + t.under;
    if (!n && !["player_points", "player_rebounds", "player_assists", "player_threes"].includes(m.id)) continue;
    h += `<tr><td>${esc(m.label)}</td><td class="num">${t.over}</td><td class="num">${t.under}</td><td class="num">${pct(t)}</td><td class="num">${n ? sgn(t.diff / n) : "—"}</td></tr>`;
  }
  return h + `</tbody></table></div></div>`;
}

// ---------- Defense ----------
// Which defenses give up the most to each position, by market. Every graded player-game (a line plus the actual stat;
// pushes count, voids don't) credits the opponent's defense with (actual − line): using the line as the baseline keeps a
// team from looking bad just because it faced stars. All 30 teams are always ranked: a team's average is shrunk toward 0
// (the line) as if it had DEF_K extra games at exactly the line, so a defense with few games can't jump to the extremes,
// and one with none sits in the middle. Rank 30 = worst defense (gives up the most over the line), 1 = toughest.
const DEF_MIN_N = 5;       // fewer graded player-games than this and the row is greyed ("thin sample")
const DEF_K = 5;           // shrinkage strength (extra games at exactly the line)
const DEF_TOP = 10;
// Steals and blocks have no book lines any more, so for those the baseline is the player's own average over his earlier
// games (at least AVG_MIN played games before the one being judged); the opponent is credited with (actual − that average).
const DEF_AVG = ["player_steals", "player_blocks"];
const AVG_MIN = 3;
function avgGames(aid, mk) {
  const st = mkById(mk).stat, p = PX().players[aid] || {};
  const rs = (PX().logs[aid] || []).filter((r) => r.p && r[st] != null && r.opp).sort((a, b) => a.d.localeCompare(b.d) || String(a.g).localeCompare(String(b.g)));
  const out = []; let sum = 0;
  rs.forEach((r, i) => {
    if (i >= AVG_MIN) out.push({ gid: r.g, d: r.d, opp: r.opp, home: r.ha === "home", line: sum / i, act: r[st], res: r[st] > sum / i ? "over" : r[st] < sum / i ? "under" : "push", avg: true, team: p.team });
    sum += r[st];
  });
  return out;
}
let DEF_CACHE = { key: null, map: null };
function defEntries() {
  const key = PX().generated_utc;
  if (DEF_CACHE.key === key && DEF_CACHE.map) return DEF_CACHE.map;
  const map = {};
  for (const mk of DEF_AVG) for (const aid of Object.keys(PX().logs || {})) {
    const pos = posOf(aid); if (!POS_LIST.includes(pos)) continue;
    for (const g of avgGames(aid, mk)) (map[`${mk}|${pos}`] = map[`${mk}|${pos}`] || []).push({ d: g.d, opp: g.opp, diff: g.act - g.line, act: g.act, res: g.res });
  }
  for (const d of lineDates()) for (const r of propRows(d)) {
    const l = r.l, pos = posOf(r.aid), opp = oppOf(r);
    if (DEF_AVG.includes(r.mk)) continue;
    if (!l || l.act == null || !["over", "under", "push"].includes(l.res) || !POS_LIST.includes(pos) || !opp) continue;
    (map[`${r.mk}|${pos}`] = map[`${r.mk}|${pos}`] || []).push({ d, opp, diff: l.act - l.line, act: l.act, res: l.res });
  }
  DEF_CACHE = { key, map };
  return map;
}
const allTeams = () => [...new Set(Object.values(PX().games).flatMap((g) => [g.home, g.away]).filter(Boolean))].sort();
// Every team, worst first, with rank (30 = worst). `date` (optional): only games before that date count.
function defTable(mk, pos, date) {
  const agg = {};
  for (const e of defEntries()[`${mk}|${pos}`] || []) {
    if (date && e.d >= date) continue;
    const t = agg[e.opp] = agg[e.opp] || { n: 0, s: 0, a: 0, o: 0, dec: 0 };
    t.n++; t.s += e.diff; t.a += e.act;
    if (e.res !== "push") { t.dec++; if (e.res === "over") t.o++; }
  }
  const rows = allTeams().map((team) => {
    const t = agg[team] || { n: 0, s: 0, a: 0, o: 0, dec: 0 };
    return { team, n: t.n, diff: t.n ? t.s / t.n : null, act: t.n ? t.a / t.n : null, over: t.dec ? t.o / t.dec : null, score: Math.round((t.s / (t.n + DEF_K)) * 1e9) / 1e9 };
  }).sort((a, b) => b.score - a.score || b.n - a.n || a.team.localeCompare(b.team));
  const of = rows.length;
  for (let i = 0; i < of;) {      // tied scores (e.g. teams with no games yet) share the middle rank of their group
    let j = i; while (j + 1 < of && rows[j + 1].score === rows[i].score) j++;
    for (let k = i; k <= j; k++) rows[k].rank = Math.round(of - (i + j) / 2);
    i = j + 1;
  }
  return rows;
}
const sgn = (v) => (v > 0 ? "+" : "") + v.toFixed(1);

// A team's next game that hasn't started (not final, not live), today or later; earliest tip first.
function nextGameFor(team) {
  const t = todayET();
  return Object.entries(PX().games)
    .filter(([, g]) => (g.home === team || g.away === team) && !g.final && g.state !== "in" && g.date >= t)
    .sort((a, b) => String(a[1].start).localeCompare(String(b[1].start)))[0] || null;
}
// Expanded detail under a Defense row: the opposing players at this position in the defense's next game, with their line.
// Markets with no book line (steals / blocks) show the player's season average instead.
function defPlayersHtml(team, mk, pos) {
  const ng = nextGameFor(team);
  if (!ng) return `<p class="muted small">${esc(team)} has no upcoming game on the schedule.</p>`;
  const [gid, g] = ng, oppTeam = g.home === team ? g.away : g.home, avgMode = DEF_AVG.includes(mk);
  const head = `<div class="defx-h"><b>${esc(gLabel(gid))}</b> <span class="muted">${esc(g.date)} · ${fmtTime(g.start)}</span></div>`;
  const rows = Object.entries(PX().players)
    .filter(([aid, p]) => p.team === oppTeam && p.pos === pos)
    .map(([aid, p]) => {
      const l = ((PX().lines[aid] || {})[gid] || {})[mk];
      return { aid, p, l, avg: avgMode ? form(aid, mk).avg : null };
    })
    .filter((r) => (avgMode ? r.avg != null : r.l))
    .sort((a, b) => (avgMode ? b.avg - a.avg : b.l.line - a.l.line));
  if (!rows.length) return head + `<p class="muted small">No ${esc(oppTeam)} ${pos} ${avgMode ? "averages" : "lines"} for ${esc(mkById(mk).short)} yet. ${avgMode ? "" : esc(linesDueText(gid))}</p>`;
  let h = head + `<table class="defx-t"><thead><tr><th>Player</th><th class="num">${avgMode ? "Avg" : "Line"}</th>${avgMode ? "" : `<th class="num">O/U</th>`}</tr></thead><tbody>`;
  for (const r of rows) {
    h += `<tr><td class="bname"><a href="#/player/${encodeURIComponent(r.aid)}/${mk}">${face(r.aid, r.p.name)}<span class="nm">${esc(r.p.name)}</span></a> <span class="muted small">${esc(oppTeam)}</span></td>` +
      (avgMode ? `<td class="num"><b>${n1(Number(r.avg.toFixed(1)))}</b></td>` : `<td class="num" title="${esc(lineTip(r.l))}">${lineCell(r.l)}</td><td class="num muted small">${lineOdds(r.l)}</td>`) + `</tr>`;
  }
  return h + `</tbody></table>`;
}

function viewDefense() {
  if (!PX()) return `<p class="muted">No prop data yet.</p>`;
  const ent = defEntries();
  const mks = FILTER_MKS.filter((id) => PX().markets.some((m) => m.id === id) && POS_LIST.some((p) => ent[`${id}|${p}`]));
  if (!mks.length) return `<p class="muted">No graded props yet, so there's nothing to rank. Props are graded once each game is final and its box score is in.</p>`;
  if (!mks.includes(P.dmk)) P.dmk = mks[0];
  let h = `<p class="callout">Worst defenses first, by position and market (30 = worst defense, 1 = toughest). “vs line” is the average of (actual − line) for every graded player the team faced at that position. The rank pulls each team's average toward zero, as if it had ${DEF_K} extra games at exactly the line, so a team with few games can't jump to the top or bottom; all 30 teams are always ranked. Greyed rows have fewer than ${DEF_MIN_N} graded player-games. Position is ESPN's G / F / C. These are today's live standings; the ranks on player pages are frozen on each game's date.</p>`;
  // overview: the single worst defense for every position × market
  h += `<div class="panel"><h3>Worst defense by position &amp; market</h3><div class="scroll"><table class="defgrid"><thead><tr><th>Market</th>${POS_LIST.map((p) => `<th>${p}</th>`).join("")}</tr></thead><tbody>`;
  for (const mk of mks) {
    h += `<tr class="${P.dmk === mk ? "sel" : ""}"><td><button type="button" class="linkbtn" data-dmk="${esc(mk)}">${esc(mkById(mk).short)}</button></td>` + POS_LIST.map((p) => {
      const w = defTable(mk, p)[0];
      return w && w.n ? `<td><b>${esc(w.team)}</b> <span class="muted small">${sgn(w.diff)}</span></td>` : `<td class="na">—</td>`;
    }).join("") + `</tr>`;
  }
  h += `</tbody></table></div></div>`;
  // detail for one market: one ranked table per position
  h += `<div class="filters"><label>Market <select id="d-mk">${mks.map((id) => `<option value="${esc(id)}" ${P.dmk === id ? "selected" : ""}>${FILTER_LABEL[id]}</option>`).join("")}</select></label></div>`;
  h += `<div class="grid3">`;
  for (const pos of POS_LIST) {
    const rows = defTable(P.dmk, pos), list = rows.slice(0, DEF_TOP);
    h += `<div class="panel"><h3>${esc(mkById(P.dmk).short)} vs ${pos}</h3><div class="scroll"><table class="deftbl"><thead><tr><th>#</th><th>Defense</th><th class="num">Avg</th><th class="num">${DEF_AVG.includes(P.dmk) ? "vs avg" : "vs line"}</th><th class="num">${DEF_AVG.includes(P.dmk) ? "Above" : "Over"}</th><th class="num">N</th></tr></thead><tbody>`;
    list.forEach((r) => {
      h += `<tr class="deft ${r.n < DEF_MIN_N ? "lowN" : ""}"><td class="muted">${r.rank}</td><td><button type="button" class="linkbtn deftm" aria-expanded="false" data-dteam="${esc(r.team)}">${esc(r.team)}</button></td><td class="num">${r.n ? n1(Number(r.act.toFixed(1))) : "—"}</td>
        <td class="num ${r.diff > 0 ? "win" : r.diff < 0 ? "loss" : ""}">${r.n ? sgn(r.diff) : "—"}</td><td class="num">${r.over == null ? "—" : Math.round(r.over * 100) + "%"}</td><td class="num">${r.n}</td></tr>
        <tr class="defx" hidden><td colspan="6">${defPlayersHtml(r.team, P.dmk, pos)}</td></tr>`;
    });
    h += `</tbody></table></div></div>`;
  }
  return h + `</div>`;
}


// ---------- Line trend vs opponent defense (player page) ----------
// For each game, the opponent's rank (same table as the Defense tab; 30 = worst defense) against the player's position
// for the selected stat, using only games played BEFORE that game's date (what you could have known then). The rank is
// frozen: it comes from the snapshot taken for that game date (data/defense/), so later games never change it.
const DEF_THIN_N = 3;      // fewer prior games than this: the marker is hollow (a rough lean, shrunk toward the middle)
function defAsOf(mk, pos, opp, date) {
  // Frozen snapshot for that game date (data/defense/<date>.json, written once by the collector) when it exists.
  const snap = (PX().defense || {})[date], frozen = snap && snap.r[`${mk}|${pos}`];
  if (frozen) { const r = frozen.find((x) => x[0] === opp); return r ? { rank: r[1], of: frozen.length, diff: r[3], n: r[2], frozen: true, backfilled: snap.b } : null; }
  // No snapshot yet (a game on a future date): preview from today's data; it freezes on game day.
  const rows = defTable(mk, pos, date), r = rows.find((x) => x.team === opp);
  return r ? { rank: r.rank, of: rows.length, diff: r.diff, n: r.n, frozen: false } : null;
}
function defTrendRows(aid, mk) {
  const p = PX().players[aid] || {}, lines = PX().lines[aid] || {}, st = mkById(mk).stat;
  if (DEF_AVG.includes(mk)) return avgGames(aid, mk).map((r) => ({ ...r, start: gameOf(r.gid).start || r.d, def: POS_LIST.includes(p.pos) ? defAsOf(mk, p.pos, r.opp, r.d) : null }))
    .sort((a, b) => String(a.start).localeCompare(String(b.start))).slice(-chartDims(true).games);
  const logByG = Object.fromEntries((PX().logs[aid] || []).map((r) => [r.g, r]));
  return Object.entries(lines).filter(([, ms]) => ms[mk]).map(([gid, ms]) => {
    const g = gameOf(gid), home = p.team === g.home, opp = home ? g.away : g.home, l = ms[mk], lg = logByG[gid];
    return { gid, d: g.date, start: g.start, opp, home, line: l.line, res: l.res, act: l.act != null ? l.act : lg && lg.p && lg[st] != null ? lg[st] : null,
      def: POS_LIST.includes(p.pos) ? defAsOf(mk, p.pos, opp, g.date) : null };
  }).sort((a, b) => String(a.start).localeCompare(String(b.start))).slice(-chartDims(true).games);
}
function defTrendSVG(rows) {
  const D0 = chartDims(true), { W, H, L, R, T, B, fs } = D0;
  const x = (i) => L + 28 + i * ((W - L - R - 56) / Math.max(1, rows.length - 1));
  const { lo, hi, y } = statScale(rows.flatMap((r) => [r.line, r.act].filter((v) => v != null)), T, H, B);
  const yr = (rk, of) => T + (H - T - B) * ((of - rk) / Math.max(1, of - 1));      // worst defense (highest rank) at the top
  const lay = labelLayer([L, 4, W - R, H - B - 1]);
  rows.forEach((r, i) => { lay.marker(x(i), y(r.line)); if (r.act != null) lay.marker(x(i), y(r.act)); if (r.def) lay.marker(x(i), yr(r.def.rank, r.def.of)); });
  let s = `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="Line vs opponent defensive rank by game">`;
  for (const v of [lo, (lo + hi) / 2, hi]) s += `<line x1="${L}" x2="${W - R}" y1="${y(v)}" y2="${y(v)}" stroke="var(--line)"/><text x="${L - 6}" y="${y(v) + fs * 0.35}" font-size="${fs}" text-anchor="end" fill="var(--muted)">${Number.isInteger(v) ? v : v.toFixed(1)}</text>`;
  // right axis: defense rank, 30 (worst) at the top to 1 (toughest) at the bottom
  const of = (rows.find((r) => r.def) || { def: { of: 30 } }).def.of;
  for (const [v, yy] of [[of, T], [Math.round((of + 1) / 2), (T + H - B) / 2], [1, H - B]]) s += `<text x="${W - R + 6}" y="${yy + fs * 0.35}" font-size="${fs}" font-weight="700" fill="var(--def)">${v}</text>`;
  const seg = (pts, attrs) => { if (pts.length > 1) s += `<polyline points="${pts.join(" ")}" fill="none" ${attrs}/>`; };
  seg(rows.map((r, i) => `${x(i)},${y(r.line)}`), `stroke="var(--muted)" stroke-width="1.5" stroke-dasharray="4 4"`);
  seg(rows.map((r, i) => (r.def ? `${x(i)},${yr(r.def.rank, r.def.of)}` : "")).filter(Boolean), `stroke="var(--def)" stroke-width="2"`);
  seg(rows.map((r, i) => (r.act != null ? `${x(i)},${y(r.act)}` : "")).filter(Boolean), `stroke="var(--accent)" stroke-width="2.5" stroke-linejoin="round"`);
  let marks = "", text = "";
  rows.forEach((r, i) => {
    marks += `<rect x="${x(i) - 4.5}" y="${y(r.line) - 4.5}" width="9" height="9" transform="rotate(45 ${x(i)} ${y(r.line)})" fill="var(--panel)" stroke="var(--ink)" stroke-width="2"><title>${r.avg ? "Average before this game" : "Line"} ${n1(r.line)}</title></rect>`;
    if (r.def) {
      const cy = yr(r.def.rank, r.def.of), thin = r.def.n < DEF_THIN_N, none = r.def.n === 0;
      const tip = none ? `${esc(r.opp)}: no earlier games against this position, so it sits in the middle (n/a)`
        : `${esc(r.opp)} defense: #${r.def.rank} of ${r.def.of} (${sgn(r.def.diff)} vs ${r.avg ? "average" : "line"}, ${r.def.n} earlier game${r.def.n === 1 ? "" : "s"})${thin ? ". Small sample: a rough lean" : ""}. ${r.def.frozen ? (r.def.backfilled ? "Frozen as of that date (rebuilt from the data after the fact)" : "Frozen on game day") : "Preview: freezes on game day"}.`;
      marks += `<circle cx="${x(i)}" cy="${cy}" r="5.5" fill="${thin ? "var(--panel)" : "var(--def)"}" stroke="var(--def)" stroke-width="2"><title>${tip}</title></circle>`;
    }
    if (r.act != null) {
      const col = r.res === "over" ? "var(--over)" : r.res === "under" ? "var(--under)" : "var(--accent)";
      marks += `<circle cx="${x(i)}" cy="${y(r.act)}" r="5.5" fill="${col}" stroke="var(--panel)" stroke-width="2"><title>${esc(r.d)} ${r.home ? "vs" : "@"} ${esc(r.opp)}: ${n1(r.act)}</title></circle>`;
    }
    text += `<text x="${x(i)}" y="${H - B + fs + 8}" font-size="${fs}" text-anchor="middle" fill="var(--muted)">${oppLabel(r)}</text>` + (r.act == null ? `<text x="${x(i)}" y="${H - 6}" font-size="${fs - 3}" text-anchor="middle" fill="var(--muted)">next</text>` : "");
  });
  // value labels, most important first: actuals, defense ranks, then lines
  rows.forEach((r, i) => { if (r.act == null) return; const p = lay.place(n1(r.act), x(i), y(r.act), fs, r.act >= r.line ? "up" : "down", true);
    if (p) text += `<text x="${p.x}" y="${p.y}" stroke="var(--panel)" stroke-width="4" paint-order="stroke" stroke-linejoin="round" font-size="${fs}" font-weight="700" text-anchor="middle" fill="var(--ink)">${n1(r.act)}</text>`; });
  rows.forEach((r, i) => { if (!r.def) return; const lab = r.def.n === 0 ? "n/a" : "#" + r.def.rank + (r.def.n < DEF_THIN_N ? "*" : "");
    const yy = yr(r.def.rank, r.def.of), p = lay.place(lab, x(i), yy, fs, yy < (T + H - B) / 2 ? "down" : "up", true);
    if (p) text += `<text x="${p.x}" y="${p.y}" stroke="var(--panel)" stroke-width="4" paint-order="stroke" stroke-linejoin="round" font-size="${fs}" font-weight="700" text-anchor="middle" fill="var(--def)">${lab}</text>`; });
  rows.forEach((r, i) => { const p = lay.place(n1(r.line), x(i), y(r.line), fs, "up", false);
    if (p) text += `<text x="${p.x}" y="${p.y}" stroke="var(--panel)" stroke-width="4" paint-order="stroke" stroke-linejoin="round" font-size="${fs}" text-anchor="middle" fill="var(--muted)">${n1(r.line)}</text>`; });
  return s + marks + text + `</svg>`;
}
function defTrendPanel(aid, mk) {
  const p = PX().players[aid] || {};
  if (!POS_LIST.includes(p.pos)) return "";
  const rows = defTrendRows(aid, mk);
  if (rows.length < 2) return "";
  return `<div class="panel"><h3>${esc(mkAbbr(mkById(mk)))} ${DEF_AVG.includes(mk) ? "average" : "line"} vs opponent defense</h3><div class="chart">${defTrendSVG(rows)}</div>
    <div class="legend"><span><i class="lg-line"></i>${DEF_AVG.includes(mk) ? "Avg" : "Line"}</span><span><i class="lg-act"></i>Actual</span><span><b class="dot" style="background:var(--def)"></b>Opp. defense rank (30 = worst)</span></div></div>`;
}

// ---------- Guide ----------
function viewGuide() {
  return `<div class="panel"><h3>How the player board works</h3><div class="body guide">
    <p><b>Lines.</b> DraftKings and FanDuel player props are pulled from The Odds API twice per game: at <b>7:00 AM Central</b> on game day (retried until the books post them) and again about <b>1 hour before tip</b>. Until the 1-hour pull lands, the board shows the 7 AM line with an <span class="chip amchip">7 AM</span> chip; after it, ▲/▼ shows how far the line moved since 7 AM. The 1-hour line is the one graded. Only the core markets (points, rebounds, assists, threes) are pulled. PRA and the two-stat combos are built from those lines (two-stat combos: sum + 0.5; PRA: the sum, matching how DraftKings and FanDuel have most often set them in this season's captures), priced at -110/-110 and graded like any other line. Steals and blocks are no longer pulled; earlier captures still show. Their opponent-defense chart uses the player's own average over his earlier games (at least ${AVG_MIN}) in place of a line, and the defense is credited with actual minus that average. Nothing is pulled after tip. DraftKings is the line shown and graded; FanDuel is used when DraftKings has no line for that player and stat. Hover or tap a line to see both books.</p>
    <p><b>Grading.</b> Once the game is final, the actual stat from ESPN's box score is compared with the line: over, under or push. A player who had a line but didn't play is <i>void</i>, with ESPN's reason when it gives one.</p>
    <p><b>Results filters.</b> The Results tab has one filter, Market (points, rebounds, assists, threes made, steals, blocks). The page is season to date: one row per player with an over–under record for that market (and the average of actual − line). The market summary above it always shows every market.</p>
    <p><b>Defense.</b> For every graded player-game, the opponent's defense is credited with actual minus line. Each team's average of that, by position and market, ranks all 30 defenses: 30 = worst (gives up the most over the books' lines), 1 = toughest. A team's average is pulled toward zero as if it had ${DEF_K} extra games at exactly the line, so a defense with few games can't jump to the extremes and one with none sits in the middle. That is why every game on a player's chart gets a rank, even early on or for centers (few graded games per team). On player pages the rank is frozen: a snapshot is saved for each game date (using only earlier games) and never rewritten, so a game keeps the rank it had on the day it was played even as defenses change; snapshots for dates before this feature existed were rebuilt from the data afterward, and a game on a future date shows a preview until its date arrives. Hollow markers (*) on the player chart mean fewer than ${DEF_THIN_N} earlier games at that position, so treat them as a rough lean. Greyed rows on the Defense tab have fewer than ${DEF_MIN_N} graded player-games. Early in the season these samples are small.</p>
    <p><b>AVG / L5.</b> Season average and last-5 average over games the player actually played, counting only games before the date being viewed.</p>
    <p><b>HIT.</b> How many of his last ${HIT_N} games played went over <i>this</i> line (not the lines he had in those games).</p>
    <p><b>Trend.</b> Average of the last ${TREND.lastN} games vs. the season average: ↑ at least ${TREND.pct}% higher, ↓ at least ${TREND.pct}% lower, → otherwise. Needs ${TREND.minGames} games.</p>
    <p><b>Player updates.</b> A notes icon next to a name means Dime has updates for that player; tap it for the list. It's red when something was first seen by Dime in the last 24 hours (Dime's own detection time, not the source's date), gray otherwise. Items: <b>ESPN</b> — ESPN's status note (status, injury, one-line note); <b>ESPN news</b> — ESPN headlines tagged with the player, last 7 days, newest 3; <b>Roster</b> — he's on a different team's ESPN roster than in his last box score; <b>Role</b> — from his team's most recent game, once he has 4+ games played: minutes at least 10 away from his prior average, or he started after coming off the bench in every prior game (or the reverse). "Info as of" is the source's own date for ESPN and roster items, and when Dime first saw the item otherwise. ESPN's feeds are unofficial and can change or stop at any time.</p>
    <p><b>Players with "no games yet"</b> have a line but no box score this season (first game, new team, or returning from injury). They're matched to ESPN's roster; stats appear after their first game.</p>
    <p class="muted">Data quality: ESPN's feeds are unofficial and can change. Player names are matched between the sportsbooks and ESPN by name; unmatched names are listed in the Log tab. Research tool only — not betting advice.</p>
  </div></div>`;
}

window.STIX_PROPS = {
  render(tab, arg, sub) {
    if (tab !== "player") P.subFrom = "";
    if (tab === "player") return viewPlayer(arg, sub);
    if (tab === "results") return viewResults();
    if (tab === "defense" && MODE === "nba") return viewDefense();
    if (tab === "guide") return viewGuide();
    if (!tab || tab === "board") return viewBoard();
    return null;
  },
  bind(tab, arg) {
    const on = (id, ev, fn) => { const el = document.getElementById(id); if (el) el.addEventListener(ev, fn); };
    document.querySelectorAll("[data-pgid]").forEach((b) => b.addEventListener("click", () => { P.game = P.game === b.dataset.pgid ? "" : b.dataset.pgid; render(); }));
    document.querySelectorAll("[data-pday]").forEach((b) => b.addEventListener("click", () => { P.day = Number(b.dataset.pday); P.game = ""; render(); }));
    document.querySelectorAll("[data-bset]").forEach((b) => b.addEventListener("click", () => { P.bset = b.dataset.bset; render(); }));
    on("r-mk", "change", (e) => { P.rf.mk = e.target.value; render(); });
    on("d-mk", "change", (e) => { P.dmk = e.target.value; render(); });
    document.querySelectorAll("[data-dmk]").forEach((b) => b.addEventListener("click", () => { P.dmk = b.dataset.dmk; render(); }));
    // Defense tab: tap a team to show / hide the opposing players at that position in its next game (no re-render)
    document.querySelectorAll("[data-dteam]").forEach((b) => b.addEventListener("click", () => {
      const x = b.closest("tr").nextElementSibling, open = x.hidden;
      x.hidden = !open; b.setAttribute("aria-expanded", String(open)); b.closest("tr").classList.toggle("open", open);
    }));
    on("p-q", "input", (e) => { P.q = e.target.value; clearTimeout(P_TYPING); P_TYPING = setTimeout(() => { render(); const el = document.getElementById("p-q"); el.focus(); el.setSelectionRange(el.value.length, el.value.length); }, 200); });
    document.querySelectorAll("[data-pmk]").forEach((b) => b.addEventListener("click", () => { P.pmk[decodeURIComponent(arg)] = b.dataset.pmk; render(); }));
    const onTab = document.querySelector(".mtabs button.on");
    if (onTab && onTab.scrollIntoView) onTab.scrollIntoView({ block: "nearest", inline: "center" });
    const back = document.getElementById("m-back");
    if (back) back.addEventListener("click", (e) => { if (history.length > 1) { e.preventDefault(); history.back(); } });
  },
};
