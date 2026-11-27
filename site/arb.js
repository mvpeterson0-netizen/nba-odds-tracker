"use strict";
// Arbitrage tab (#/arb), ported from the NFL tracker's books.js. Reads D.props.books (built by nba_tracker/build.py from
// each upcoming game's latest multi-book pull: one line per player / stat / book). Display only: grading, Results and the
// Defense ranks still use DraftKings/FanDuel. Two lists: guaranteed-profit arbitrages and middles.
(function () {
  const BOOKS = { draftkings: "DraftKings", fanduel: "FanDuel", betmgm: "BetMGM", fanatics: "Fanatics", betrivers: "BetRivers",
    espnbet: "theScore Bet", hardrockbet: "Hard Rock", ballybet: "Bally Bet", novig: "Novig" };
  const bname = (b) => BOOKS[b] || b;
  const LS_OFF = "dime_arb_off";    // books the viewer switched off (this browser only)
  const LS_MID = "dime_arb_mid";    // minimum middle size, % of the line (this browser only)
  const LS_EDGE = "dime_arb_edge";  // "only middles whose estimated hit chance beats break-even" (default on)
  // NBA differences from the NFL page, chosen from this season's data (2026-11-27, DraftKings vs FanDuel):
  //  - 99.8% of cross-book line gaps are exactly one whole number (24.5 vs 25.5), so a middle needs only 1 result inside the gap
  //    (the NFL page requires 2, which would leave this page empty);
  //  - a one-point gap is 4% of a 25-point line, so the gap filter starts lower (3%) and has a 2% step.
  const MID_OPTS = [2, 3, 5, 8, 10, 15], MID_DEFAULT = 3, MID_MIN_RESULTS = 1;
  const MID_WORST_PRICE = -120;   // both middle legs must be priced -120 or better: a wider gap bought with a heavy-juice alt line is not a real middle
  const STALE_MIN = 180;          // lines older than this get a "may be stale" colour (the 7 AM pull is hours old by tip)
  const MIN_SIG_N = 200;          // graded lines needed in a stat before its hit-chance estimate is shown
  const A = {
    mk: "",
    edge: (() => { try { return localStorage.getItem(LS_EDGE) !== "0"; } catch (e) { return true; } })(),
    mid: (() => { try { const v = Number(localStorage.getItem(LS_MID)); return MID_OPTS.includes(v) ? v : MID_DEFAULT; } catch (e) { return MID_DEFAULT; } })(),
    off: (() => { try { const v = JSON.parse(localStorage.getItem(LS_OFF) || "[]"); return Array.isArray(v) ? v : []; } catch (e) { return []; } })(),
  };
  const PX = () => D.props || {};
  const books = () => PX().books || {};
  const decOdds = (o) => (o == null ? null : o > 0 ? 1 + o / 100 : 1 + 100 / Math.abs(o));
  const sg = (v) => (v > 0 ? `+${v}` : String(v));
  const num = (v) => (Number.isInteger(v) ? String(v) : v.toFixed(1));
  // Novig is an exchange: its American price first, with the contract price in cents in parentheses, e.g. "-113 (53¢)".
  const px = (book, v) => (book === "novig" ? `${sg(v)} (${Math.round(100 * (v > 0 ? 100 / (v + 100) : -v / (-v + 100)))}¢)` : sg(v));
  const med = (xs) => { const s = [...xs].sort((a, b) => a - b), n = s.length; return n ? (n % 2 ? s[(n - 1) / 2] : (s[n / 2 - 1] + s[n / 2]) / 2) : null; };
  const started = (gid) => { const g = (PX().games || {})[gid]; return !g || new Date(g.start) <= new Date(); };
  const ageMin = (iso) => (Date.now() - new Date(iso).getTime()) / 60000;
  const ageTxt = (iso) => { const m = Math.max(0, Math.round(ageMin(iso))); return m < 60 ? `${m} min ago` : m < 1440 ? `${Math.round(m / 60)} h ago` : `${Math.round(m / 1440)} d ago`; };
  const aid2 = (aid) => PX().players && PX().players[aid];
  const mkLabel = (id) => ((PX().markets || []).find((m) => m.id === id) || {}).label || id;

  // ---------- arbitrage ----------
  // Per player/stat: the best pair of Over at one book and Under at another (Over line <= Under line, same pull).
  // Stakes split so both sides pay the same: return = 1 / (1/dOver + 1/dUnder) - 1 of the total stake, whichever side wins.
  // If the Over line is lower than the Under line, both can win (a "middle"); the return is then at least that.
  function compute() {
    const out = [];
    for (const [gid, g] of Object.entries(books())) {
      if (started(gid)) continue;
      for (const [aid, ms] of Object.entries(g.p || {})) {
        for (const [mk, rows] of Object.entries(ms)) {
          if (A.mk && mk !== A.mk) continue;
          const rs = rows.filter((r) => !A.off.includes(r[0]));
          let best = null;
          for (const o of rs) for (const u of rs) {
            if (o[0] === u[0] || o[2] == null || u[3] == null || o[1] > u[1]) continue;
            const S = 1 / decOdds(o[2]) + 1 / decOdds(u[3]), ret = 1 / S - 1, both = u[1] > o[1] ? 2 / S - 1 : null;
            const c = { gid, aid, mk, cap: g.cap, pt: g.pt, o, u, S, ret, both };
            if (!best || ret > best.ret + 1e-9 || (Math.abs(ret - best.ret) < 1e-9 && u[1] - o[1] > best.u[1] - best.o[1])) best = c;
          }
          if (best) out.push(best);
        }
      }
    }
    return out.sort((a, b) => b.ret - a.ret || (b.u[1] - b.o[1]) - (a.u[1] - a.o[1]));
  }

  // ---------- middles ----------
  // Over at one book and Under at a higher line at another, so both bets win if the stat lands between the two lines.
  // Size = Under line - Over line as a % of the midpoint of the two lines. Per player/stat the pair with the widest gap is kept
  // (ties: better return). "Needs" = how often the middle must hit just to break even, from the stake split (miss = one side
  // wins, one loses; hit = both win). Stats are whole numbers, so the results inside the gap are ceil(Under) - floor(Over) - 1
  // (Over 24.5 / Under 25.5 -> just 25).
  // Estimated hit chance: spread of each stat sd = a * sqrt(line), with a fitted per stat from every graded real line of the season
  // so far (actual - pre-game line; a^2 = sum of squared misses / sum of lines). Centre = median of the shown books' lines for that
  // player/stat. Chance = P(Over line < result < Under line) under a normal curve, with half-point boundaries for whole-number
  // results. Checked 2026-11-27 on 1,587 DraftKings/FanDuel line pairs from this season: predicted 12.4% vs actual 12.5% overall,
  // but threes were overstated (26.7% vs 21.3%, n=169) and assists 4-8 understated (15.8% vs 21.5%, n=135). It is an estimate.
  let SIG = null, SIGKEY = null;
  function sigmas() {
    const key = PX().generated_utc;
    if (SIG && SIGKEY === key) return SIG;
    const se = {}, sl = {}, n = {};
    for (const byGame of Object.values(PX().lines || {})) for (const ms of Object.values(byGame)) for (const [mk, l] of Object.entries(ms)) {
      if (l.est || l.act == null || !l.line || !["over", "under", "push"].includes(l.res)) continue;
      const e = l.act - l.line; se[mk] = (se[mk] || 0) + e * e; sl[mk] = (sl[mk] || 0) + l.line; n[mk] = (n[mk] || 0) + 1;
    }
    SIG = {}; SIGKEY = key;
    for (const mk of Object.keys(se)) if (n[mk] >= MIN_SIG_N) SIG[mk] = Math.sqrt(se[mk] / sl[mk]);
    return SIG;
  }
  const Phi = (z) => { const t = 1 / (1 + 0.2316419 * Math.abs(z)), d = 0.3989423 * Math.exp(-z * z / 2),
    p = d * t * (0.3193815 + t * (-0.3565638 + t * (1.781478 + t * (-1.821256 + t * 1.330274)))); return z > 0 ? 1 - p : p; };
  function middles() {
    const out = [];
    for (const [gid, g] of Object.entries(books())) {
      if (started(gid)) continue;
      for (const [aid, ms] of Object.entries(g.p || {})) {
        for (const [mk, rows] of Object.entries(ms)) {
          if (A.mk && mk !== A.mk) continue;
          const rs = rows.filter((r) => !A.off.includes(r[0]));
          let best = null;
          for (const o of rs) for (const u of rs) {
            if (o[0] === u[0] || o[2] == null || u[3] == null || !(u[1] > o[1])) continue;
            if (o[2] < MID_WORST_PRICE || u[3] < MID_WORST_PRICE) continue;   // both legs must be priced -120 or better
            const gp = (u[1] - o[1]) / ((o[1] + u[1]) / 2) * 100, n = Math.ceil(u[1]) - Math.floor(o[1]) - 1;
            if (gp < A.mid || n < MID_MIN_RESULTS) continue;
            const S = 1 / decOdds(o[2]) + 1 / decOdds(u[3]), ret = 1 / S - 1, both = 2 / S - 1;
            const a = sigmas()[mk], ctr = med(rs.map((r) => r[1]));
            const sd = a ? a * Math.sqrt(ctr) : null;
            const pHit = sd ? Phi((Math.ceil(u[1]) - 0.5 - ctr) / sd) - Phi((Math.floor(o[1]) + 0.5 - ctr) / sd) : null;
            const need = (-ret) / (both - ret);
            if (A.edge && !(pHit != null && pHit >= need)) continue;          // estimated hit chance must beat break-even
            const c = { pHit, gid, aid, mk, cap: g.cap, pt: g.pt, o, u, S, ret, both, gp, n, need };
            if (!best || gp > best.gp + 1e-9 || (Math.abs(gp - best.gp) < 1e-9 && ret > best.ret)) best = c;
          }
          if (best) out.push(best);
        }
      }
    }
    return out.sort((a, b) => (A.edge ? (b.pHit / b.need) - (a.pHit / a.need) : b.gp - a.gp) || b.gp - a.gp);
  }

  // ---------- rows ----------
  // Profit on $100 total, rounded to cents (so 0.00% from rounding never counts as a guaranteed profit).
  const cents = (v) => Math.round(v * 10000) / 100;
  const pct = (v) => { const c = cents(v); return `${c > 0 ? "+" : c < 0 ? "−" : ""}${Math.abs(c).toFixed(2)}%`; };
  const usd = (v) => { const c = cents(v); return `${c > 0 ? "+" : c < 0 ? "−" : ""}$${Math.abs(c).toFixed(2)}`; };
  function head(x, badge) {
    const p = aid2(x.aid), g = (PX().games || {})[x.gid] || {};
    const stale = ageMin(x.cap) > STALE_MIN;
    return `<div class="rlhead"><a class="pname" href="#/player/${encodeURIComponent(x.aid)}/${esc(x.mk)}">${esc(p ? p.name : x.aid)}</a> <span class="rlstat">${esc(mkLabel(x.mk))}</span>${badge}</div>
      <div class="muted small">${esc(p ? p.team : "")} · ${esc(gLabel(x.gid))} · ${fmtTime(g.start)} · <span class="${stale ? "arb-stale" : ""}">lines ${ageTxt(x.cap)}${x.pt === "morning" ? " (7 AM pull)" : ""}</span></div>`;
  }
  function legs(x) {
    const so = 100 / decOdds(x.o[2]) / x.S, su = 100 / decOdds(x.u[3]) / x.S;
    return `<div class="arb-legs small"><span><b class="legtag over">OVER</b> <b>${num(x.o[1])}</b> ${esc(bname(x.o[0]))} ${px(x.o[0], x.o[2])} · bet <b>$${so.toFixed(2)}</b></span>
        <span><b class="legtag under">UNDER</b> <b>${num(x.u[1])}</b> ${esc(bname(x.u[0]))} ${px(x.u[0], x.u[3])} · bet <b>$${su.toFixed(2)}</b></span></div>`;
  }
  function row(x) {
    const ev = x.both != null ? `≥ ${pct(x.ret)}` : pct(x.ret);
    return `<div class="rlrow arbrow">${head(x, `<span class="arb-ev ${cents(x.ret) > 0 ? "pos" : "neg"}">${ev}</span>`)}${legs(x)}
      <div class="small">If both bet ($100 total): <b>${usd(x.ret)}</b> whichever side wins${x.both != null ? ` · both win (<b>${usd(x.both)}</b>) if he lands between ${num(x.o[1])} and ${num(x.u[1])}` : ""}</div></div>`;
  }
  function midRow(x) {
    const lo = Math.floor(x.o[1]) + 1, hi = Math.ceil(x.u[1]) - 1, span = lo === hi ? `${lo}` : `${lo} to ${hi}`;
    return `<div class="rlrow arbrow">${head(x, `<span class="arb-ev pos">${x.gp.toFixed(1)}% gap</span>`)}${legs(x)}
      <div class="small">Both win (<b>${usd(x.both)}</b> on $100) if he lands on ${span} (${x.n} result${x.n === 1 ? "" : "s"}). Otherwise one side wins: <b>${usd(x.ret)}</b>. ${x.need <= 0 ? "Already profitable either way (see Guaranteed profit); estimated middle chance" : `Needs the middle to hit about <b>${(x.need * 100).toFixed(1)}%</b> of the time to break even; estimated chance`} <b>${x.pHit == null ? "n/a" : (x.pHit * 100).toFixed(1) + "%"}</b>.</div></div>`;
  }

  function view() {
    const bks = books(), any = Object.keys(bks).some((gid) => !started(gid));
    let h = `<section class="pad arb"><h2 class="gsec">Arbitrage</h2>
      <p class="muted small">Best Over at one book and Under at another, from the same pull. "If both bet" splits $100 so either side pays the same. Dime pulls lines at 7 AM and about 1 hour before tip, so a line can be hours old (the age is on every row). Lines move: check both books before betting.</p>`;
    if (!any) return h + `<p class="muted">No multi-book lines for upcoming games yet. They arrive with each game's next line pull (7 AM Central and about 1 hour before tip).</p></section>`;
    const seen = new Set(), marks = new Set();
    for (const g of Object.values(bks)) for (const ms of Object.values(g.p || {})) for (const [mk, rows] of Object.entries(ms)) { marks.add(mk); for (const r of rows) seen.add(r[0]); }
    h += `<div class="arb-books">${[...seen].sort((a, b) => bname(a).localeCompare(bname(b))).map((b) => `<button type="button" class="gchip ${A.off.includes(b) ? "" : "on"}" data-arbbook="${esc(b)}">${esc(bname(b))}</button>`).join("")}</div>
      <div class="filters"><label>Stat <select id="arb-mk"><option value="">All stats</option>${(PX().markets || []).filter((m) => marks.has(m.id)).map((m) => `<option value="${m.id}" ${m.id === A.mk ? "selected" : ""}>${esc(m.label)}</option>`).join("")}</select></label></div>`;
    const arbs = compute().filter((x) => cents(x.ret) > 0);   // arbs at 0% or lower are hidden
    h += `<h3 class="small">Guaranteed profit (${arbs.length})</h3>`;
    h += arbs.length ? `<div class="panel rlist">${arbs.slice(0, 40).map(row).join("")}</div>` : `<p class="muted small">None right now with these books.</p>`;
    const mids = middles();
    h += `<h3 class="small">Middles (${mids.length})</h3>
      <div class="filters"><label class="chk"><input type="checkbox" id="arb-edge" ${A.edge ? "checked" : ""}> Only if estimated hit chance beats break-even</label></div>
      <div class="filters"><label>Minimum gap <select id="arb-mid">${MID_OPTS.map((v) => `<option value="${v}" ${v === A.mid ? "selected" : ""}>${v}% of the line</option>`).join("")}</select></label></div>
      <p class="muted small">Over at one book and Under at a higher line at another: if the stat lands between the two lines, both bets win. Gap = Under line minus Over line, as a % of the two lines' midpoint. Both bets must be priced -120 or better (no heavy-juice alt lines). The estimated hit chance comes from how far each stat usually lands from its line; it is a model, not a promise. Not guaranteed: you give up a little when it misses.</p>`;
    h += mids.length ? `<div class="panel rlist">${mids.slice(0, 40).map(midRow).join("")}</div>` : `<p class="muted small">None right now${A.edge ? " whose estimated hit chance beats break-even" : ` at ${A.mid}% or wider`} with these books.</p>`;
    return h + `</section>`;
  }
  function bind() {
    document.querySelectorAll("[data-arbbook]").forEach((b) => b.addEventListener("click", () => {
      const k = b.dataset.arbbook;
      A.off = A.off.includes(k) ? A.off.filter((x) => x !== k) : A.off.concat(k);
      try { localStorage.setItem(LS_OFF, JSON.stringify(A.off)); } catch (e) { /* this browser only */ }
      render();
    }));
    const ed = document.getElementById("arb-edge");
    if (ed) ed.addEventListener("change", (e) => { A.edge = e.target.checked; try { localStorage.setItem(LS_EDGE, A.edge ? "1" : "0"); } catch (er) { /* this browser only */ } render(); });
    const m = document.getElementById("arb-mid");
    if (m) m.addEventListener("change", (e) => { A.mid = Number(e.target.value); try { localStorage.setItem(LS_MID, String(A.mid)); } catch (er) { /* this browser only */ } render(); });
    const s = document.getElementById("arb-mk"); if (s) s.addEventListener("change", (e) => { A.mk = e.target.value; render(); });
  }
  window.DIME_ARB = { view, bind, compute, middles };
})();
