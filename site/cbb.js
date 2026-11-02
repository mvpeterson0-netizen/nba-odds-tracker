"use strict";
// Dime college basketball: Power 4 games, player points only. Loaded after props.js (which it borrows from: the player
// page, chart, form/hit helpers, date tabs, headshots) and before app.js. Data: data/cbb.json (cbb_tracker/build.py),
// same shape as props.json but with a single market, so props.js works on it unchanged once MODE is "cbb".
(function () {
  const MK = "player_points";
  const confChips = (gid) => {
    const g = gameOf(gid);
    return [...new Set([g.ac, g.hc].filter(Boolean))].map((c) => `<span class="chip">${esc(c)}</span>`).join(" ");
  };
  const gameStatus = (gid) => {
    const g = gameOf(gid);
    if (g.final) return `Final ${g.as ?? ""}–${g.hs ?? ""}`;
    if (g.state === "in") return `<span class="live">● ${esc(g.status || "Live")}</span> ${g.as ?? ""}–${g.hs ?? ""}`;
    return esc(fmtClock(g.start));
  };
  // Game spread and total (bulk pull at 8 AM and about 1 hour before tip): "DUKE -7.5 · O/U 151.5 ▼1.5".
  const sgn = (x) => (x > 0 ? "+" : "") + n1(x);
  function glineHtml(gid) {
    const gl = (PX().game_lines || {})[gid], g = gameOf(gid);
    if (!gl || (gl.sp == null && gl.tot == null)) return "";
    const mv = (cur, old) => (cur != null && old != null && cur !== old ? ` <span class="mv ${cur > old ? "up" : "down"}">${cur > old ? "▲" : "▼"}${n1(Math.abs(cur - old))}</span>` : "");
    const am = gl.am || {};
    const parts = [];
    if (gl.sp != null) parts.push(`<b>${esc(g.home || "")} ${sgn(gl.sp)}</b>${mv(gl.sp, am.sp)}`);
    if (gl.tot != null) parts.push(`O/U <b>${n1(gl.tot)}</b>${mv(gl.tot, am.tot)}`);
    const tip = `${bookShort(gl.book)}, captured ${fmtTime(gl.cap)} (${gl.mb} min before tip)` +
      (gl.am ? `. 8 AM: ${gl.am.sp != null ? esc(g.home || "") + " " + sgn(gl.am.sp) : ""}${gl.am.tot != null ? " / O/U " + n1(gl.am.tot) : ""}` : "");
    return `<span class="gline" title="${esc(tip)}">${parts.join(" · ")}</span>`;
  }
  const byStart = (a, b) => String(gameOf(a).start).localeCompare(String(gameOf(b).start));
  const phone = () => !!(window.matchMedia && window.matchMedia("(max-width: 760px)").matches);
  const plink = (aid) => R(`player/${encodeURIComponent(aid)}`);

  // ---------- Board ----------
  function viewBoard() {
    if (!PX()) return `<p class="muted pad">College basketball data isn't available yet. It's built on each scheduled run — check the <a href="#/cbb/log">Log</a>.</p>`;
    const date = dayET(P.day);
    const all = propRows(date);
    const withLines = new Set(all.map((r) => r.gid));
    const gids = [...new Set([...withLines, ...gamesOn(date)])].sort(byStart);
    const lined = gids.filter((g) => withLines.has(g)), bare = gids.filter((g) => !withLines.has(g));
    if (P.game && !lined.includes(P.game)) P.game = "";
    const q = P.q.trim().toLowerCase();
    const pl = (aid) => PX().players[aid] || { name: aid };
    const rows = all.filter((r) => (!P.game || r.gid === P.game) && (!q || pl(r.aid).name.toLowerCase().includes(q)));

    let h = `<div class="dayseg">${DAYS.map(([o, l]) => `<button data-pday="${o}" class="${P.day === o ? "on" : ""}">${l}<span>${fmtDate(dayET(o))}</span></button>`).join("")}</div>`;
    if (lined.length) h += `<div class="gamebar">` + lined.map((g) => `<button class="gchip ${P.game === g ? "on" : ""}" data-pgid="${esc(g)}"><b>${esc(gLabel(g))}</b><span class="muted small">${gameOf(g).final ? "Final" : esc(fmtClock(gameOf(g).start))}</span></button>`).join("") + `</div>`;
    h += `<div class="filters fsearch"><input type="search" id="p-q" placeholder="Search player" aria-label="Search player" value="${esc(P.q)}"></div>`;
    if (!gids.length) return h + `<p class="muted">No Power 4 games ${P.day < 0 ? "were played" : "scheduled"} on ${fmtDate(date)}.</p>`;
    if (lined.length && !rows.length) h += `<p class="muted">No players match that search.</p>`;

    const byGame = new Map();
    for (const r of rows) {
      if (!byGame.has(r.gid)) byGame.set(r.gid, []);
      byGame.get(r.gid).push(r);
    }
    const isPhone = phone();
    for (const gid of lined.filter((g) => byGame.has(g))) {
      const plist = byGame.get(gid).sort((a, b) => b.l.line - a.l.line);
      const g = gameOf(gid);
      h += `<section class="mgame"><div class="mgame-h">${gameHeader(gid)} ${confChips(gid)} ${glineHtml(gid)}</div>`;
      if (isPhone) {
        // One row per player: line (big) with season avg, or the actual once graded; last-5 average; hit rate.
        const teams = [g.away, g.home].filter(Boolean);
        const order = [...teams, ...new Set(plist.map((r) => pl(r.aid).team || "").filter((t) => !teams.includes(t)))];
        h += `<table class="bgrid cbbgrid"><thead><tr><th>Player</th><th>PTS</th><th>L5</th><th>HIT</th></tr></thead><tbody>`;
        for (const tm of order) {
          const tp = plist.filter((r) => (pl(r.aid).team || "") === tm);
          if (!tp.length) continue;
          const conf = tm === g.away ? g.ac : tm === g.home ? g.hc : null;
          h += `<tr class="rteam"><td colspan="4">${esc(tm)}${conf ? ` · ${esc(conf)}` : ""}</td></tr>`;
          for (const { aid, l } of tp) {
            const p = pl(aid), href = `${plink(aid)}/${MK}`, tip = esc(lineTip(l));
            const f = form(aid, MK, date, l.line);
            let cell;
            if (l.res === "void") cell = `<td class="bc void" title="${tip}"><a href="${href}"><b>${n1(l.line)}</b><small>DNP</small></a></td>`;
            else if (l.res && l.res !== "pending") cell = `<td class="bc ${l.res}" title="${tip}"><a href="${href}"><b>${n1(l.line)}</b><small>act ${n1(l.act)}</small></a></td>`;
            else {
              const cls = f.avg == null ? "" : f.avg > l.line ? "above" : f.avg < l.line ? "below" : "";
              cell = `<td class="bc ${cls}${l.pt === "morning" ? " am" : ""}" title="${tip}"><a href="${href}"><b>${n1(l.line)}</b><small>${f.avg == null ? "no games" : "avg " + n1(f.avg)}</small></a></td>`;
            }
            h += `<tr><td class="bname"><a href="${plink(aid)}">${face(aid, p.name)}<span class="nm">${esc(p.name)}</span></a></td>${cell}
              <td class="bc plain"><b>${n1(f.l5)}</b></td><td class="bc plain">${hitHtml(f)}</td></tr>`;
          }
        }
        h += `</tbody></table>`;
      } else {
        h += `<div class="panel scroll"><table class="ptable"><thead><tr><th>Player</th><th class="num">Line</th><th class="num">Over/Under</th><th>Book</th>
          <th class="num" title="Average over tracked games played">AVG</th><th class="num" title="Last 5 games played">L5</th><th class="num" title="Over this line, last ${HIT_N} games played">HIT</th><th>Trend</th><th class="num">Actual</th><th>Result</th></tr></thead><tbody>`;
        for (const { aid, l } of plist) {
          const p = pl(aid), f = form(aid, MK, date, l.line);
          h += `<tr class="plr"><td class="pcell"><a class="pc-a" href="${plink(aid)}">${face(aid, p.name)}<b>${esc(p.name)}</b></a><div class="muted small">${esc(p.team || "")}${p.pos ? " · " + esc(p.pos) : ""}${p.nolog ? " · no games yet" : ""}</div></td>
            <td class="num" title="${esc(lineTip(l))}"><a class="lnk" href="${plink(aid)}/${MK}">${lineCell(l)}</a></td><td class="num">${lineOdds(l)}</td><td class="muted">${bookShort(l.book)}</td>
            <td class="num">${n1(f.avg)}</td><td class="num">${n1(f.l5)}</td><td class="num">${hitHtml(f)}</td><td>${trendHtml(f)}</td>
            <td class="num">${l.act != null ? `<b>${n1(l.act)}</b>` : ""}</td><td>${resHtml(l)}</td></tr>`;
        }
        h += `</tbody></table></div>`;
      }
      h += `</section>`;
    }
    // Power 4 games with no points line: most of a day's games, since books only post props for some.
    if (bare.length && !P.game && !q) {
      const why = P.day < 0 ? "No player-points lines were captured for these games."
        : "Books post props for only some games. Dime checks at 8:00 AM Central on game day (and about hourly until props post); a game moves up to the board once a points line posts. Spread and total, when posted, show beside each game.";
      h += `<section class="mgame"><div class="mgame-h"><b>No points lines</b> <span class="muted small">${bare.length} game${bare.length === 1 ? "" : "s"}</span></div>
        <p class="muted small">${why}</p><ul class="nolines">${bare.map((g) => `<li><b>${esc(gLabel(g))}</b> ${confChips(g)} <span class="muted small">${gameStatus(g)}</span> ${glineHtml(g)}</li>`).join("")}</ul></section>`;
    }
    return h;
  }

  // ---------- Results ----------
  function viewResults() {
    if (!PX()) return `<p class="muted pad">No college data yet.</p>`;
    const shown = (r) => r.l.res === "over" || r.l.res === "under";   // like the NBA Results: voids and pushes hidden
    const dates = lineDates().filter((d) => propRows(d).some(shown)).reverse();
    if (!dates.length) return `<p class="muted">No graded props yet. Props are graded once each game is final and its box score is in.</p>`;
    const tally = (rs) => { const t = { over: 0, under: 0 }; rs.forEach((r) => { if (t[r.l.res] != null) t[r.l.res]++; }); return t; };
    let h = `<p class="callout">Green = over, red = under. Power 4 player points.</p>`;
    dates.forEach((d, di) => {
      const rs = propRows(d).filter(shown), t = tally(rs);
      h += `<details class="panel resday" ${di === 0 ? "open" : ""}><summary><b>${fmtDate(d)}</b> <span class="muted small"><span class="res over">${t.over} over</span> · <span class="res under">${t.under} under</span></span></summary>`;
      const gids = [...new Set(rs.map((r) => r.gid))].sort(byStart);
      for (const gid of gids) {
        const g = gameOf(gid), grs = rs.filter((x) => x.gid === gid);
        const team = (aid) => (PX().players[aid] || {}).team || "";
        h += `<div class="rgame"><div class="rgame-h"><b>${esc(g.away || "")} ${g.as ?? ""}</b> @ <b>${esc(g.home || "")} ${g.hs ?? ""}</b>${g.final ? ` <span class="muted small">Final</span>` : ""} ${confChips(gid)}</div>
          <table class="rgrid"><thead><tr><th>Player</th><th>Line</th><th>Act</th><th>Diff</th></tr></thead><tbody>`;
        const teams = [g.away, g.home];
        const groups = [...teams.map((tm) => [tm, grs.filter((r) => team(r.aid) === tm)]), ["", grs.filter((r) => !teams.includes(team(r.aid)))]];
        for (const [tm, list] of groups) {
          if (!list.length) continue;
          if (tm) h += `<tr class="rteam"><td colspan="4">${esc(tm)}</td></tr>`;
          for (const { aid, l } of list.sort((a, b) => b.l.line - a.l.line)) {
            const nm = (PX().players[aid] || {}).name || aid, diff = l.act - l.line;
            const tip = `Line ${n1(l.line)}, actual ${n1(l.act)}: ${l.res}`;
            h += `<tr><td class="rname"><a href="${plink(aid)}">${face(aid, nm)}<span class="nm">${esc(nm)}</span></a></td>
              <td class="rc ${l.res}" title="${tip}"><b>${n1(l.line)}</b></td><td class="rc ${l.res}" title="${tip}"><b>${n1(l.act)}</b></td>
              <td class="rc ${l.res}" title="${tip}"><b>${diff > 0 ? "+" : ""}${n1(diff)}</b></td></tr>`;
          }
        }
        h += `</tbody></table></div>`;
      }
      h += `</details>`;
    });
    const t = tally(dates.flatMap((d) => propRows(d)).filter(shown)), n = t.over + t.under;
    h += `<div class="panel"><h3>Season so far</h3><div class="scroll"><table><thead><tr><th>Market</th><th class="num">Over</th><th class="num">Under</th><th class="num">Over %</th></tr></thead><tbody>
      <tr><td>Points</td><td class="num">${t.over}</td><td class="num">${t.under}</td><td class="num">${n ? Math.round((t.over / n) * 100) + "%" : "—"}</td></tr></tbody></table></div></div>`;
    return h;
  }

  // ---------- Log & sources ----------
  function viewLog() {
    const run = D.cbb_run;
    const label = { ok: ["ok", "OK"], failed: ["out", "Failed"], no_key: ["dtd", "Waiting for API key"], skipped: ["other", "Skipped"] };
    const names = { results_yesterday: "yesterday's games", games_today: "today's games", games_tomorrow: "tomorrow's games", boxscores: "box scores", props: "points props" };
    let h = `<div class="grid2"><div class="panel"><h3>Last college data pull</h3><div class="body">`;
    if (run) {
      h += `<div class="kv"><div>Finished</div><div>${fmtTime(run.finished_at)} (${ago(run.finished_at)})</div><div>Game date</div><div>${fmtDate(run.game_date)}</div>
        <div>Power 4</div><div>${esc((run.power4 || []).join(", "))}${run.p4_mode === "both" ? " (both teams)" : " (either team)"}</div>`;
      for (const [k, v] of Object.entries(run.sources || {})) {
        const [cls, txt] = label[v] || ["other", v];
        const f = D.cbb_run && D.cbb_run[k];
        h += `<div>${esc(names[k] || k)}</div><div><span class="st ${cls}">${esc(txt)}</span>${k === "boxscores" && f && f.new_games != null ? ` <span class="muted small">${f.new_games} new games${f.queued > f.new_games ? `, ${f.queued - f.new_games} queued` : ""}</span>` : ""}</div>`;
      }
      h += `</div>`;
      const pr = run.props;
      if (pr) {
        h += `<div class="kv" style="margin-top:8px">` + Object.entries(pr.credits || {}).map(([k, v]) => `<div>Credits left (${esc(k)})</div><div>${v ?? "?"}</div>`).join("") +
          (pr.events != null ? `<div>Odds events seen</div><div>${pr.events} <span class="muted small">(${pr.p4_events} matched to Power 4 games)</span></div>` : "") + `</div>`;
      }
    } else h += NA("Run summary not found. The first college run may still be in progress.");
    h += `</div></div><div class="panel"><h3>Odds events with no ESPN match</h3><div class="body small">`;
    const um = (run && run.props && run.props.unmatched) || [];
    h += um.length ? `<p class="muted">The books list these, but none matched a game on ESPN's scoreboard (yesterday–tomorrow). Usually they are Division II/III or far-off games. If a Power 4 game shows up here, its team name needs an alias in <code>cbb_tracker/teams.py</code>.</p><ul class="nolines">${um.map((u) => `<li>${esc(u)}</li>`).join("")}</ul>`
      : `<p class="muted">None this run.</p>`;
    h += `</div></div></div>${propsLog(D.cbb)}
      <div class="panel"><h3>Sources</h3><div class="body"><table class="stable"><thead><tr><th>Data</th><th>Source</th><th>Notes</th></tr></thead><tbody>
        <tr><td data-label="Data">Schedule, scores, rankings, conferences</td><td data-label="Source">ESPN men's college basketball scoreboard feed</td><td class="note">Unofficial, undocumented endpoint; may change without notice. Power 4 = the conference ESPN lists for each team.</td></tr>
        <tr><td data-label="Data">Box scores, rosters</td><td data-label="Source">ESPN game summary and roster feeds</td><td class="note">Same caveat. Disney's Terms of Use limit use to personal, noncommercial use and bar automated access.</td></tr>
        <tr><td data-label="Data">Player points lines</td><td data-label="Source"><a href="https://the-odds-api.com/liveapi/guides/v4/">The Odds API v4</a></td><td class="note">DraftKings and FanDuel, points only (1 credit per game pulled; an empty answer is free). Shares the NBA's credits; the NBA pre-game pulls are never starved.</td></tr>
      </tbody></table></div></div>`;
    return h;
  }

  // ---------- Guide ----------
  function viewGuide() {
    return `<div class="panel"><h3>How the college board works</h3><div class="body guide">
      <p><b>What's tracked.</b> Power 4 games (ACC, Big Ten, Big 12, SEC), and only <b>player points</b>. By default a game counts when at least one team is Power 4, so a Power 4 team against a mid-major is included; the Log tab shows which setting is live. Conferences come from ESPN's current membership. Ranks (#) are ESPN's AP-style ranks for the top 25.</p>
      <p><b>Player lines.</b> DraftKings and FanDuel points props from The Odds API, pulled <b>once per game, at 8:00 AM Central</b> on game day (re-checked about hourly until the books post them, up to tip). Books post college props for only some games, so many games show under "No points lines". That morning line is the one graded; it is not updated later, so it can differ from the closing line. DraftKings is shown and graded; FanDuel is used when DraftKings has no line for that player.</p>
      <p><b>Game lines.</b> Each game's spread (shown for the home team) and total come from the same books, captured at <b>8:00 AM Central</b> and again about <b>1 hour before tip</b>. The header shows the latest capture, with ▲/▼ for the move since 8 AM. They are for context only and are not graded.</p>
      <p><b>Grading.</b> Once the game is final, the player's actual points from ESPN's box score are compared with the line: over, under or push. A player with a line who didn't play is <i>void</i>. Results hides voids and pushes, like the NBA.</p>
      <p><b>AVG / L5 / HIT / Trend.</b> Same as the NBA tab (season average, last-5 average, how many of the last ${HIT_N} games went over this line, last ${TREND.lastN} vs season ±${TREND.pct}%), but computed over the games Dime tracks: Power 4 games since opening night (Nov 2). A mid-major player's numbers only include his games against Power 4 teams, and a Power 4 player's games against other opponents (such as Division II exhibitions) aren't counted.</p>
      <p><b>Players with "no games yet"</b> have a line but no tracked box score (first game, a transfer or a freshman). They're matched to ESPN's roster; stats appear after their first game.</p>
      <p class="muted">Data quality: ESPN's feeds are unofficial and can change. Team and player names are matched between ESPN and the sportsbooks by name; anything unmatched is listed in the Log tab. Research tool only — not betting advice.</p>
    </div></div>`;
  }

  window.DIME_CBB = {
    render(tab, arg, sub) {
      if (tab !== "player") P.subFrom = "";
      if (tab === "player") return window.STIX_PROPS.render("player", arg, sub);
      if (!tab || tab === "board") return viewBoard();
      if (tab === "results") return viewResults();
      if (tab === "log") return viewLog();
      if (tab === "guide") return viewGuide();
      return null;
    },
    bind(tab, arg) { window.STIX_PROPS.bind(tab, arg); },
  };
})();
