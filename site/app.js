"use strict";
// Dime front end (NBA props). Reads the JSON the GitHub Action writes to data/. No external libraries.

const FILES = ["run", "standings", "injuries", "props"];
const D = {};               // file name -> parsed JSON (or null if missing)
const S = { conf: "", team: "", status: "", q: "" };
let LIVE = null;            // recent workflow runs from the GitHub API (or null)
const app = document.getElementById("app");

// ---------- formatting ----------
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const NA = (t = "no data") => `<span class="na">${esc(t)}</span>`;
function fmtTime(iso, opts = {}) {
  if (!iso) return "";
  const d = new Date(iso);
  if (isNaN(d)) return esc(iso);
  return d.toLocaleString(undefined, { weekday: "short", month: "numeric", day: "numeric", hour: "numeric", minute: "2-digit", timeZoneName: "short", ...opts });
}
const fmtClock = (iso) => fmtTime(iso, { weekday: undefined, month: undefined, day: undefined });
function fmtDate(isoDate) {
  if (!isoDate) return "";
  const d = new Date(isoDate + "T12:00:00");
  return d.toLocaleDateString(undefined, { weekday: "short", month: "short", day: "numeric" });
}
function ago(iso) {
  const m = (Date.now() - new Date(iso).getTime()) / 60000;
  if (m < 1) return "just now";
  if (m < 60) return `${Math.round(m)} min ago`;
  if (m < 48 * 60) return `${(m / 60).toFixed(m < 600 ? 1 : 0)} h ago`;
  return `${Math.round(m / 1440)} days ago`;
}
const am = (v) => (v == null ? NA("—") : v > 0 ? `+${v}` : String(v));
const pt = (v, signed = true) => (v == null ? "" : signed && v > 0 ? `+${v}` : String(v));
const dec = (o) => (o > 0 ? 1 + o / 100 : 1 + 100 / -o);              // American -> decimal
const impl = (o) => (o == null ? null : o > 0 ? 100 / (o + 100) : -o / (-o + 100));
const median = (a) => { if (!a.length) return null; const s = [...a].sort((x, y) => x - y), m = s.length >> 1; return s.length % 2 ? s[m] : (s[m - 1] + s[m]) / 2; };
const mode = (a) => { const c = new Map(); a.forEach((v) => c.set(v, (c.get(v) || 0) + 1)); let best = null, n = 0; c.forEach((k, v) => { if (k > n || (k === n && Math.abs(v) < Math.abs(best))) { best = v; n = k; } }); return best; };
const rows = (name) => (D[name] && D[name].rows) || [];


// ---------- injuries helpers ----------
function stClass(s) {
  const t = String(s || "").toLowerCase();
  if (t.startsWith("out")) return "out";
  if (t.includes("day") || t.includes("question") || t.includes("doubt") || t.includes("prob")) return "dtd";
  return "other";
}
const injFor = (teamId) => rows("injuries").filter((i) => i.team_id === teamId);

// ---------- Standings ----------
function viewStandings() {
  const all = rows("standings");
  if (!all.length) return `<p class="muted">Standings weren't loaded. Check the <a href="#/log">Log</a> tab.</p>`;
  const confs = [...new Set(all.map((r) => r.conference))];
  const st = (r, k) => r.stats[k + "_display"] ?? r.stats[k];
  let h = `<p class="callout">From ESPN. Lines under seeds 6 and 10 mark the play-in and lottery cutoffs.</p><div class="grid2">`;
  for (const c of confs) {
    const list = all.filter((r) => r.conference === c).sort((a, b) => (a.stats.playoffSeed ?? 99) - (b.stats.playoffSeed ?? 99) || (b.stats.winPercent ?? 0) - (a.stats.winPercent ?? 0));
    h += `<div class="panel"><h3>${esc(c)}</h3><div class="scroll"><table class="stand"><thead><tr>
      <th>#</th><th>Team</th><th class="num">W</th><th class="num">L</th><th class="num">PCT</th><th class="num">GB</th>
      <th class="num wide">Home</th><th class="num wide">Road</th><th class="num wide">L10</th><th>Strk</th>
      <th class="num wide">PPG</th><th class="num wide">OPP</th><th class="num">Diff</th></tr></thead><tbody>`;
    for (const r of list) {
      const seed = r.stats.playoffSeed;
      const strk = String(st(r, "streak") || "");
      const diff = r.stats.differential;
      h += `<tr class="${seed === 6 || seed === 10 ? "cut" : ""}"><td class="muted">${seed ?? ""}</td><td><b>${esc(r.abbr)}</b> <span class="muted small wide">${esc(r.name)}</span>${r.note ? ` <span class="chip" title="${esc(r.note)}">${esc(r.note)}</span>` : ""}</td>
        <td class="num">${esc(st(r, "wins"))}</td><td class="num">${esc(st(r, "losses"))}</td><td class="num">${esc(st(r, "winPercent"))}</td><td class="num">${esc(st(r, "gamesBehind"))}</td>
        <td class="num wide">${esc(r.stats.Home ?? "")}</td><td class="num wide">${esc(r.stats.Road ?? "")}</td><td class="num wide">${esc(r.stats["Last Ten Games"] ?? "")}</td>
        <td class="strk ${strk[0] || ""}">${esc(strk)}</td>
        <td class="num wide">${esc(st(r, "avgPointsFor") ?? "")}</td><td class="num wide">${esc(st(r, "avgPointsAgainst") ?? "")}</td>
        <td class="num ${diff > 0 ? "win" : diff < 0 ? "loss" : ""}">${diff == null ? "" : pt(Number(diff.toFixed(1)))}</td></tr>`;
    }
    h += `</tbody></table></div></div>`;
  }
  return h + `</div>`;
}

// ---------- Injuries ----------
function viewInjuries() {
  const all = rows("injuries");
  if (!D.injuries) return `<p class="muted">Injuries weren't loaded. Check the <a href="#/log">Log</a> tab.</p>`;
  const teams = [...new Map(all.map((i) => [i.team_abbr, i.team])).entries()].sort((a, b) => String(a[1]).localeCompare(String(b[1])));
  const statuses = [...new Set(all.map((i) => i.status).filter(Boolean))].sort();
  const q = S.q.trim().toLowerCase();
  const list = all.filter((i) => (!S.team || i.team_abbr === S.team) && (!S.status || i.status === S.status) &&
    (!q || String(i.player).toLowerCase().includes(q) || String(i.injury).toLowerCase().includes(q)));
  let h = `<div class="filters">
    <label>Team <select id="i-team"><option value="">All teams</option>${teams.map(([a, n]) => `<option value="${esc(a)}" ${a === S.team ? "selected" : ""}>${esc(n)}</option>`).join("")}</select></label>
    <label>Status <select id="i-status"><option value="">All</option>${statuses.map((s) => `<option ${s === S.status ? "selected" : ""}>${esc(s)}</option>`).join("")}</select></label>
    <label>Player / injury <input type="search" id="i-q" placeholder="Search" value="${esc(S.q)}"></label></div>
    <p class="callout">${list.length} of ${all.length} players · from ESPN, pulled ${ago(D.injuries.fetched_at)}. Return dates are ESPN's estimates.</p>`;
  if (!list.length) return h + `<p class="muted">No injuries match these filters.</p>`;
  h += `<div class="panel stablep"><div class="scroll"><table class="stable"><thead><tr><th>Team</th><th>Player</th><th>Status</th><th>Injury</th><th>Est. return</th><th>Updated</th><th>Note</th></tr></thead><tbody>`;
  for (const i of list) {
    h += `<tr><td data-label="Team">${esc(i.team_abbr)}</td><td><b>${esc(i.player)}</b> <span class="muted small">${esc(i.position || "")}</span></td>
      <td data-label="Status"><span class="st ${stClass(i.status)}">${esc(i.status || "—")}</span></td><td data-label="Injury">${esc(i.injury || "—")}</td>
      <td data-label="Est. return">${i.return_date ? fmtDate(i.return_date) : NA("—")}</td><td data-label="Updated">${i.updated ? fmtDate(i.updated.slice(0, 10)) : ""}</td>
      <td class="note">${esc(i.comment || "")}</td></tr>`;
  }
  return h + `</tbody></table></div></div>`;
}

// ---------- Log & sources ----------
function viewLog() {
  const run = D.run;
  const label = { ok: ["ok", "OK"], failed: ["out", "Failed"], no_key: ["dtd", "Waiting for API key"], skipped: ["other", "Skipped"], not_due: ["other", "Not due this run"] };
  let h = `<div class="grid2"><div class="panel"><h3>Last data pull</h3><div class="body">`;
  if (run) {
    h += `<div class="kv"><div>Finished</div><div>${fmtTime(run.finished_at)} (${ago(run.finished_at)})</div><div>Game date</div><div>${fmtDate(run.game_date)}</div>`;
    for (const [k, v] of Object.entries(run.sources || {})) {
      const [cls, txt] = label[v] || ["other", v];
      const f = D[k];
      h += `<div>${esc(k.replace(/_/g, " "))}</div><div><span class="st ${cls}">${esc(txt)}</span>${f && f.count != null ? ` <span class="muted small">${f.count} rows</span>` : ""}</div>`;
    }
    h += `</div>`;
  } else h += NA("Run summary not found.");
  if (run && run.props && run.props.credits) {
    h += `<div class="kv" style="margin-top:8px">` + Object.entries(run.props.credits).map(([k, v]) => `<div>Credits left (${esc(k)})</div><div>${v ?? "?"}</div>`).join("") + `</div>`;
  }
  h += `</div></div><div class="panel"><h3>Recent workflow runs</h3><div class="body">`;
  if (LIVE && LIVE.length) {
    h += `<table><thead><tr><th>Started</th><th>Trigger</th><th>Result</th></tr></thead><tbody>` +
      LIVE.slice(0, 10).map((r) => `<tr><td><a href="${esc(r.html_url)}">${fmtTime(r.run_started_at || r.created_at)}</a></td><td>${esc(r.event)}</td>
        <td><span class="st ${r.conclusion === "success" ? "ok" : r.conclusion ? "out" : "other"}">${esc(r.conclusion || r.status)}</span></td></tr>`).join("") + `</tbody></table>`;
  } else h += `<p class="muted">Couldn't reach the GitHub API (it limits anonymous requests). <a href="https://github.com/${esc(repo())}/actions">Open the runs on GitHub</a>.</p>`;
  h += `</div></div></div>
  ${propsLog()}
  <div class="panel"><h3>Sources</h3><div class="body">
    <table class="stable"><thead><tr><th>Data</th><th>Source</th><th>Notes</th></tr></thead><tbody>
      <tr><td data-label="Data">Schedule, scores, leaders</td><td data-label="Source">ESPN scoreboard feed</td><td class="note">Unofficial, undocumented endpoint; may change without notice.</td></tr>
      <tr><td data-label="Data">Standings</td><td data-label="Source">ESPN standings feed</td><td class="note">Same caveat.</td></tr>
      <tr><td data-label="Data">Injuries</td><td data-label="Source">ESPN league injury feed</td><td class="note">Return dates are ESPN estimates, not official.</td></tr>
      <tr><td data-label="Data">Sportsbook odds</td><td data-label="Source"><a href="https://the-odds-api.com/liveapi/guides/v4/">The Odds API v4</a></td><td class="note">US books; moneyline, spread, total in American odds. Each pull costs API credits. No-vig % = each book's two moneyline prices normalized to 100%, averaged across books.</td></tr>
    </tbody></table>
    <p class="muted small">Lines are pulled at 8:00 AM Central and about 1 hour before each tip; ESPN data refreshes on every run. Code and raw data: <a href="https://github.com/${esc(repo())}">github.com/${esc(repo())}</a></p>
  </div></div>`;
  return h;
}

function propsLog() {
  const px = D.props;
  if (!px) return "";
  let h = `<div class="panel"><h3>Recent prop pulls</h3><div class="scroll"><table class="stable"><thead><tr><th>When</th><th>Game</th><th>Pull</th><th class="num">Min before tip</th><th>Status</th><th class="num">Prices</th><th class="num">Credits used / left</th></tr></thead><tbody>`;
  const pulls = [...(px.pulls || [])].reverse().slice(0, 25);
  if (!pulls.length) h += `<tr><td colspan="7" class="muted">No prop pulls yet.</td></tr>`;
  for (const p of pulls) {
    const cls = p.status === "ok" ? "ok" : p.status === "empty" ? "other" : "out";
    h += `<tr><td data-label="When">${fmtTime(p.at)}</td><td data-label="Game">${esc(p.matchup)}</td><td data-label="Pull">${p.pull_type === "morning" ? "8 AM" : "1 h pre-game"}</td><td class="num" data-label="Min before tip">${esc(p.minutes_before)}</td>
      <td data-label="Status"><span class="st ${cls}" title="${esc(p.note || "")}">${esc(p.status)}</span></td><td class="num" data-label="Prices">${esc(p.rows)}</td><td class="num" data-label="Credits">${esc(p.credits_last || "—")} / ${esc(p.credits_remaining || "—")}</td></tr>`;
  }
  h += `</tbody></table></div>`;
  const um = px.unmatched || {};
  if ((um.players || []).length || (um.games || []).length) {
    h += `<div class="body small muted">Names from the sportsbooks with no ESPN box score yet: ${esc((um.players || []).join(", ")) || "none"}.${(um.games || []).length ? ` Games not matched to ESPN: ${esc(um.games.join(", "))}.` : ""}</div>`;
  }
  return h + `</div>`;
}

// ---------- router ----------
function render() {
  const hash = location.hash || "#/board";
  let [, tab, arg, sub] = hash.split("/");
  if (tab === "games" || tab === "odds") { location.replace("#/board"); return; }   // removed pages
  const active = tab === "player" ? "board" : tab || "board";
  document.querySelectorAll("#tabs a").forEach((a) => a.classList.toggle("on", a.dataset.tab === active));
  const views = { standings: viewStandings, injuries: viewInjuries, log: viewLog };
  let propsView = false;
  try {
    let html = views[tab] ? views[tab]() : null;
    if (html == null && window.STIX_PROPS) { html = window.STIX_PROPS.render(tab, arg, sub); propsView = html != null; }
    app.innerHTML = html ?? `<p class="pad">Page not found. <a href="#/board">Back to the board</a>.</p>`;
  } catch (e) { console.error(e); app.innerHTML = `<p class="pad">This view hit an error: ${esc(e.message)}. The data may have changed shape — check the <a href="#/log">Log</a>.</p>`; }
  bind();
  if (propsView) { try { window.STIX_PROPS.bind(tab, arg); } catch (e) { console.error(e); } }
}
function bind() {
  const on = (id, ev, fn) => { const el = document.getElementById(id); if (el) el.addEventListener(ev, fn); };
  on("i-team", "change", (e) => { S.team = e.target.value; render(); });
  on("i-status", "change", (e) => { S.status = e.target.value; render(); });
  on("i-q", "input", (e) => { S.q = e.target.value; clearTimeout(bind.t); bind.t = setTimeout(() => { render(); const el = document.getElementById("i-q"); el.focus(); el.setSelectionRange(el.value.length, el.value.length); }, 200); });
}

// ---------- loading + status ----------
const repo = () => (D.run && D.run.repo) || "mvpeterson0-netizen/nba-odds-tracker";
async function loadAll() {
  await Promise.all(FILES.map(async (f) => {
    try {
      const r = await fetch(`data/${f}.json?t=${Date.now()}`, { cache: "no-store" });
      D[f] = r.ok ? await r.json() : null;
    } catch { D[f] = null; }
  }));
}
async function liveRuns() {
  try {
    const r = await fetch(`https://api.github.com/repos/${repo()}/actions/workflows/update-data.yml/runs?per_page=20`);
    if (!r.ok) return null;
    return (await r.json()).workflow_runs || null;
  } catch { return null; }
}
async function status() {
  const st = document.getElementById("status"), stale = document.getElementById("stale");
  const warn = [];
  const t = D.run && D.run.finished_at;
  if (t) {
    st.textContent = `Updated ${ago(t)} (${fmtTime(t)})`;
    if (Date.now() - new Date(t).getTime() > 75 * 60000) warn.push(`Data may be stale: the last pull was ${ago(t)}.`);
    const failed = Object.entries(D.run.sources || {}).filter(([, v]) => v === "failed").map(([k]) => k.replace(/_/g, " "));
    if (failed.length) warn.push(`Last pull failed for: ${failed.join(", ")}. Showing the previous data for those.`);
  } else st.textContent = "No run summary";
  LIVE = await liveRuns();
  const latest = LIVE && LIVE.find((r) => r.status === "completed");
  if (latest && latest.conclusion !== "success") warn.push(`The most recent workflow run (${fmtTime(latest.updated_at)}) ended with "${latest.conclusion}".`);
  stale.hidden = !warn.length; stale.textContent = warn.length ? "⚠ " + warn.join(" ") : "";
  st.classList.toggle("bad", warn.length > 0);
  if ((location.hash || "").startsWith("#/log")) render();
}

(async function init() {
  await loadAll();
  if (!D.run && !D.props) {
    app.innerHTML = `<p class="pad">Could not load data yet. The first scheduled run may still be in progress.</p>`;
    document.getElementById("status").textContent = "No data";
    return;
  }
  window.addEventListener("hashchange", () => { render(); window.scrollTo(0, 0); });
  render();
  status();
  // Pick up new data without a manual reload: check every 5 minutes and when the tab comes back into view.
  const refresh = async () => {
    const before = D.run && D.run.finished_at;
    await loadAll();
    if ((D.run && D.run.finished_at) !== before) {
      const typing = document.activeElement && document.activeElement.tagName === "INPUT";
      if (!typing) render();
      status();
    }
  };
  setInterval(refresh, 5 * 60 * 1000);
  document.addEventListener("visibilitychange", () => { if (document.visibilityState === "visible") refresh(); });
})();

// Installable app: register the service worker (network-first; offline fallback only).
if ("serviceWorker" in navigator) {
  window.addEventListener("load", () => { navigator.serviceWorker.register("sw.js").catch(() => {}); });
}
