"use strict";
// Player updates (ported from Stix): a notes icon next to a player's name on the Board and player page.
// Tap it for a pop-up of that player's updates: ESPN status note, ESPN headlines, roster moves and big
// role changes (minutes / starting) from his team's latest game. Built in nba_tracker/updates.py ->
// data/updates.json. The icon is red when something was first seen by Dime in the last 24 hours, gray otherwise.
(function () {
  const FRESH_MS = 24 * 3600 * 1000;
  const ICON = '<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><rect x="4" y="3" width="16" height="18" rx="2"/><path d="M8 8h8M8 12h8M8 16h5"/></svg>';
  const items = (aid) => ((D.updates && D.updates.players) || {})[aid] || [];
  const fresh = (it) => it.t && Date.now() - new Date(it.t).getTime() < FRESH_MS;
  function icon(aid) {
    const its = items(aid);
    if (!its.length) return "";
    const hot = its.some(fresh), lab = hot ? "New player updates" : "Player updates";
    return `<span class="newsbtn ${hot ? "hot" : ""}" role="button" tabindex="0" data-upd="${esc(aid)}" title="${lab}" aria-label="${lab}">${ICON}</span>`;
  }
  // "Info as of": the source's own date when it gives one (ESPN items; roster date), else when Dime first saw it.
  function asOf(it) {
    const v = it.at || it.t;
    if (!v) return "";
    return /^\d{4}-\d{2}-\d{2}$/.test(v) ? fmtDate(v) : fmtTime(v);
  }
  function close() { const o = document.getElementById("news-ov"); if (o) o.remove(); }
  function open(aid) {
    close();
    const p = (D.props && D.props.players && D.props.players[aid]) || {};
    const its = items(aid);
    const row = (it) => {
      const a = asOf(it), nw = fresh(it);
      const src = it.url && /^https:\/\//.test(it.url) ? `<a href="${esc(it.url)}" target="_blank" rel="noopener">${esc(it.src)} ›</a>` : esc(it.src);
      return `<div class="nw-item ${nw ? "new" : ""}"><div><span class="chip nw-kind">${esc(it.kind)}</span>${nw ? ' <span class="nw-new">New</span>' : ""}</div>
        <div class="nw-text">${esc(it.text)}</div>
        ${a ? `<div class="small"><b>Info as of ${a}</b></div>` : ""}
        <div class="muted small">${src}</div></div>`;
    };
    const ov = document.createElement("div");
    ov.id = "news-ov"; ov.className = "share-ov";
    ov.innerHTML = `<div class="share-box nw-box" role="dialog" aria-label="Updates for ${esc(p.name || aid)}">
      <div class="nw-h"><b>${esc(p.name || aid)}</b> <span class="muted">${esc(p.team || "")}${p.pos ? " · " + esc(p.pos) : ""}</span><button class="nw-x" aria-label="Close">✕</button></div>
      ${its.length ? its.map(row).join("") : `<p class="muted">No updates right now.</p>`}
      <a class="nw-open" href="#/player/${encodeURIComponent(aid)}">Open player page ›</a></div>`;
    document.body.appendChild(ov);
    ov.addEventListener("click", (e) => { if (e.target === ov || e.target.closest(".nw-x")) close(); });
    const x = ov.querySelector(".nw-x"); if (x) x.focus();
  }
  // Capture phase so a tap on the icon inside a player link doesn't also open the player page.
  const handler = (e) => {
    const b = e.target.closest && e.target.closest("[data-upd]");
    if (!b) return;
    if (e.type === "keydown" && e.key !== "Enter" && e.key !== " ") return;
    e.preventDefault(); e.stopPropagation();
    try { open(b.dataset.upd); } catch (err) { console.error("updates pop-up failed", err); }
  };
  document.addEventListener("click", handler, true);
  document.addEventListener("keydown", (e) => { if (e.key === "Escape") close(); else handler(e); }, true);
  window.addEventListener("hashchange", close);
  window.DIME_NEWS = { icon, open, close };
})();
