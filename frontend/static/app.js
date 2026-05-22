/* ANITorr web client.
 *
 * This file is structured as small per-page init() functions that run only
 * when their page is detected. Every clickable element has a real handler
 * (no placeholders). Themes apply instantly on change.
 */
(() => {
  "use strict";

  // ---------- micro-DOM ----------
  const $  = (s, p = document) => p.querySelector(s);
  const $$ = (s, p = document) => Array.from(p.querySelectorAll(s));
  const api = (path, opts = {}) =>
    fetch(path, { headers: { "Content-Type": "application/json" }, ...opts })
      .then(r => r.json().catch(() => ({})));

  const escapeHtml = s => String(s ?? "").replace(/[&<>"']/g, c =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

  const fmtBytes = b => {
    if (!b) return "—";
    const u = ["B", "KiB", "MiB", "GiB", "TiB"]; let i = 0, n = b;
    while (n >= 1024 && i < u.length - 1) { n /= 1024; i++; }
    return `${n.toFixed(1)} ${u[i]}`;
  };

  // ---------- toast ----------
  const toast = (msg, kind = "") => {
    let wrap = $("#toasts");
    if (!wrap) {
      wrap = document.createElement("div");
      wrap.id = "toasts"; wrap.className = "toasts";
      document.body.appendChild(wrap);
    }
    const t = document.createElement("div");
    t.className = "toast " + kind; t.textContent = msg;
    wrap.appendChild(t);
    setTimeout(() => t.remove(), 3200);
  };

  // ---------- theme (global, applies on every page) ----------
  const setTheme = name => {
    document.documentElement.dataset.theme = name || "cream";
    try { localStorage.setItem("anitorr.theme", name || "cream"); } catch (e) {}
  };
  const persistedTheme = (() => { try { return localStorage.getItem("anitorr.theme"); } catch (e) { return null; } })();
  if (persistedTheme) setTheme(persistedTheme);

  /* ============================================================
   * GLOBAL: nav (runs on every page)
   * ============================================================ */
  initNav();

  function initNav() {
    // Collapsibles
    $$(".collapsible").forEach(el => {
      const key = el.dataset.collapsible;
      el.addEventListener("click", () => {
        const target = document.querySelector(`[data-children="${key}"]`);
        if (!target) return;
        const open = !target.hasAttribute("hidden");
        if (open) { target.setAttribute("hidden", ""); el.classList.remove("expanded"); }
        else      { target.removeAttribute("hidden");  el.classList.add("expanded"); }
      });
    });

    // Cache clear
    $$('[data-action="cache-clear"]').forEach(el =>
      el.addEventListener("click", async () => {
        await api("/api/cache/clear", { method: "POST" });
        toast("Cache cleared", "ok");
      }));

    // Sidebar quick search
    const navSearch = $("#navSearch");
    if (navSearch) {
      navSearch.addEventListener("keydown", e => {
        if (e.key === "Enter" && e.target.value.trim()) {
          location.href = "/?q=" + encodeURIComponent(e.target.value.trim());
        }
      });
    }

    // Badge counts (favorites, history, notifications)
    (async () => {
      try {
        const favs = await api("/api/favorites");
        const hist = await api("/api/history");
        const unread = await api("/api/notifications/unread");

        setBadge("navFavCount", (favs || []).length);
        setBadge("navHistCount", (hist || []).length);
        setBadge("navNotifCount", unread?.count || 0);
        setBadge("navAnalyticsCount", (hist || []).length);

        const dot = $("#bellDot");
        if (dot) {
          if (unread?.count > 0) {
            dot.removeAttribute("hidden");
            dot.textContent = unread.count > 99 ? "99+" : String(unread.count);
          } else dot.setAttribute("hidden", "");
        }
      } catch (e) {}
    })();
  }
  function setBadge(id, n) {
    const el = document.getElementById(id); if (!el) return;
    el.textContent = String(n);
    if (n > 0) el.removeAttribute("hidden"); else el.setAttribute("hidden", "");
  }

  /* ============================================================
   * Global keyboard
   * ============================================================ */
  document.addEventListener("keydown", e => {
    if (e.key === "Escape") {
      $$(".modal-bg.open").forEach(m => m.classList.remove("open"));
      $$(".dropdown-menu.open").forEach(m => m.classList.remove("open"));
    }
    if (e.key === "/" && document.activeElement.tagName !== "INPUT"
        && document.activeElement.tagName !== "TEXTAREA") {
      const input = $("#globalQ") || $("#mangaQ") || $("#browseQ") || $("#navSearch");
      if (input) { e.preventDefault(); input.focus(); }
    }
  });

  /* ============================================================
   * Generic dropdown wiring
   * ============================================================ */
  function wireDropdown(btnSel, menuSel, onSelect) {
    const btn = $(btnSel), menu = $(menuSel);
    if (!btn || !menu) return;
    btn.addEventListener("click", e => {
      e.stopPropagation();
      $$(".dropdown-menu.open").forEach(m => { if (m !== menu) m.classList.remove("open"); });
      menu.classList.toggle("open");
    });
    document.addEventListener("click", e => {
      if (!menu.contains(e.target) && e.target !== btn) menu.classList.remove("open");
    });
    $$(".opt", menu).forEach(o =>
      o.addEventListener("click", e => {
        e.stopPropagation();
        menu.classList.remove("open");
        onSelect?.(o.dataset);
      }));
  }

  /* ============================================================
   * PAGE: DASHBOARD
   * ============================================================ */
  if (document.getElementById("rows") && !window.__BROWSE_PAGE) initDashboard();

  function initDashboard() {
    const state = {
      query: "", results: [], shown: [],
      filters: { res: "", source: "" },
      sort: "nn_score",
      nn: true,
      compare: [],
      meta: null,
      editing: false,
    };

    // ---- Recent chips ----
    const RKEY = "anitorr.recents";
    const getRecents = () => { try { return JSON.parse(localStorage.getItem(RKEY) || "[]"); } catch { return []; } };
    const setRecents = arr => { try { localStorage.setItem(RKEY, JSON.stringify(arr.slice(0, 8))); } catch (e) {} };
    const renderChips = () => {
      const wrap = $("#chipRow");
      if (!wrap) return;
      $$(".chip", wrap).forEach(c => c.remove());
      getRecents().forEach(q => {
        const c = document.createElement("div");
        c.className = "chip";
        c.innerHTML = `<div class="av"></div><b></b><span class="x" title="Remove">×</span>`;
        $("b", c).textContent = q;
        c.addEventListener("click", e => {
          if (e.target.classList.contains("x")) {
            setRecents(getRecents().filter(x => x !== q));
            renderChips();
            return;
          }
          $("#globalQ").value = q; state.query = q; runSearch();
        });
        wrap.appendChild(c);
      });
    };
    const pushRecent = q => { setRecents([q, ...getRecents().filter(x => x !== q)]); renderChips(); };
    renderChips();

    // ---- Autocomplete ----
    let acTimer = 0, acBox = null;
    const inputEl = $("#globalQ");
    inputEl.addEventListener("input", e => {
      clearTimeout(acTimer);
      const v = e.target.value.trim();
      if (!v) { hideAC(); return; }
      acTimer = setTimeout(async () => {
        const s = await api("/api/autocomplete?q=" + encodeURIComponent(v));
        showAC(Array.isArray(s) ? s : []);
      }, 250);
    });
    function showAC(items) {
      hideAC(); if (!items.length) return;
      acBox = document.createElement("div");
      acBox.className = "dropdown-menu open";
      acBox.style.cssText = "position:absolute;z-index:50;min-width:320px";
      items.forEach(t => {
        const o = document.createElement("div");
        o.className = "opt"; o.textContent = t;
        o.addEventListener("click", () => {
          inputEl.value = t; state.query = t; hideAC(); runSearch();
        });
        acBox.appendChild(o);
      });
      const r = inputEl.getBoundingClientRect();
      acBox.style.left = r.left + "px";
      acBox.style.top  = (r.bottom + window.scrollY + 4) + "px";
      document.body.appendChild(acBox);
    }
    function hideAC() { if (acBox) { acBox.remove(); acBox = null; } }
    document.addEventListener("click", e => {
      if (acBox && !acBox.contains(e.target) && e.target !== inputEl) hideAC();
    });

    // ---- Search trigger ----
    inputEl.addEventListener("keydown", e => {
      if (e.key === "Enter") { state.query = e.target.value.trim(); hideAC(); runSearch(); }
      if (e.key === "Escape") hideAC();
    });
    document.addEventListener("keydown", e => {
      if (e.altKey && e.key.toLowerCase() === "r") { e.preventDefault(); runSearch(); }
    });
    $("#researchBtn")?.addEventListener("click", runSearch);
    $("#reSearchBtn")?.addEventListener("click", runSearch);
    $("#newSearchBtn")?.addEventListener("click", () => inputEl.focus());

    // ---- NN toggle ----
    const nnSwitch = $("#nnToggle");
    if (nnSwitch) {
      nnSwitch.classList.toggle("off", !state.nn);
      nnSwitch.addEventListener("click", () => {
        state.nn = !state.nn;
        nnSwitch.classList.toggle("off", !state.nn);
        renderResults();
      });
    }

    // ---- Dropdowns ----
    wireDropdown("#sortBtn", "#sortMenu", d => {
      if (!d.sort) return;
      state.sort = d.sort;
      $("#sortLabel").textContent = "Sort: " + ({
        nn_score: "NN", seeders: "Seeders", size_asc: "Size ↑",
        size_desc: "Size ↓", title: "Title"
      })[d.sort];
      $$("#sortMenu .opt").forEach(o => o.classList.toggle("active", o.dataset.sort === d.sort));
      renderResults();
    });
    wireDropdown("#resFilterBtn", "#resFilterMenu", d => {
      state.filters.res = d.res || "";
      $("#resFilterLabel").textContent = "Resolution: " + (d.res || "any");
      $$("#resFilterMenu .opt").forEach(o => o.classList.toggle("active", o.dataset.res === (d.res || "")));
      renderResults(); renderResBars();
    });

    $("#clearSourceFilter")?.addEventListener("click", () => {
      state.filters.source = "";
      $$("#sourceList .platform-row").forEach(el => el.classList.remove("active"));
      renderResults();
    });
    $("#clearResFilter")?.addEventListener("click", () => {
      state.filters.res = "";
      $("#resFilterLabel").textContent = "Resolution: any";
      renderResults(); renderResBars();
    });

    // ---- Bulk, CSV, share, export ----
    $("#bulkAll")?.addEventListener("change", e => $$("#rows .bulk").forEach(c => { c.checked = e.target.checked; }));
    $("#bulkBtn")?.addEventListener("click", async () => {
      const picked = $$("#rows .bulk:checked").map(c => state.shown[+c.dataset.i]);
      if (!picked.length) return toast("Select some rows first", "err");
      for (const r of picked) await sendToQbit(r, false);
      toast(`Sent ${picked.length} to qBittorrent`, "ok");
    });
    $("#csvBtn")?.addEventListener("click", () => {
      if (!state.results.length) return toast("Nothing to export", "err");
      const cols = ["title","source","group","resolution","size_bytes","seeders","leechers","nn_score","magnet","torrent_url"];
      const csv = [cols.join(",")].concat(state.results.map(r =>
        cols.map(c => `"${String(r[c] ?? "").replace(/"/g,'""')}"`).join(","))).join("\n");
      downloadBlob(csv, (state.query || "anitorr") + ".csv", "text/csv");
    });
    $("#exportBtn")?.addEventListener("click", () => {
      if (!state.results.length) return toast("Nothing to export", "err");
      downloadBlob(JSON.stringify(state.results, null, 2),
                   (state.query || "anitorr") + ".json", "application/json");
    });
    $("#shareBtn")?.addEventListener("click", () => {
      const u = new URL(location.href);
      if (state.query) u.searchParams.set("q", state.query); else u.searchParams.delete("q");
      navigator.clipboard?.writeText(u.toString()); toast("URL copied", "ok");
    });
    $("#clearCompare")?.addEventListener("click", () => { state.compare = []; renderCompare(); });

    // ---- Quick actions ----
    $("#qaCopy")?.addEventListener("click", () => state.shown[0] && copyMagnet(state.shown[0]));
    $("#qaSend")?.addEventListener("click", () => state.shown[0] && sendToQbit(state.shown[0]));
    $("#qaSaveTorrent")?.addEventListener("click", async () => {
      const r = state.shown[0]; if (!r) return toast("No results", "err");
      const res = await api("/api/download", { method: "POST", body: JSON.stringify({
        mode: "file", torrent_url: r.torrent_url, title: r.title })});
      toast(res.ok ? `Saved → ${res.path}` : "Failed (no torrent URL?)", res.ok ? "ok" : "err");
    });
    $("#qaSaveMagnet")?.addEventListener("click", async () => {
      const r = state.shown[0]; if (!r) return toast("No results", "err");
      const res = await api("/api/download", { method: "POST", body: JSON.stringify({
        mode: "magnet", magnet: r.magnet, title: r.title })});
      toast(res.ok ? `Saved → ${res.path}` : "Failed (no magnet?)", res.ok ? "ok" : "err");
    });

    // ---- Favorite / AniList ----
    $("#favBtn")?.addEventListener("click", async () => {
      if (!state.query) return toast("Search something first", "err");
      await api("/api/favorites", { method: "POST", body: JSON.stringify({
        title: state.query, ts: Date.now(), anilist_id: state.meta?.id || null })});
      toast(`Favorited "${state.query}"`, "ok");
    });
    $("#aniLink")?.addEventListener("click", () => {
      if (state.meta?.id) window.open(`https://anilist.co/anime/${state.meta.id}`, "_blank");
      else toast("No AniList match", "err");
    });

    // ---- File modal ----
    $$("#filesModal [data-close]").forEach(b =>
      b.addEventListener("click", () => $("#filesModal").classList.remove("open")));
    $("#filesModal")?.addEventListener("click", e => {
      if (e.target.id === "filesModal") $("#filesModal").classList.remove("open");
    });

    // ---- Dashboard customize ----
    $("#customizeBtn")?.addEventListener("click", () => {
      state.editing = !state.editing;
      $("#app")?.classList.toggle("editing-dashboard", state.editing);
      $$(".widget").forEach(w => w.classList.toggle("editing", state.editing));
      $("#widgetPanel")?.classList.toggle("open", state.editing);
      $("#customizeBtn").textContent = state.editing ? "Done" : "Customize";
    });
    initWidgetCustomizer();

    // ---- URL params ----
    const urlParams = new URL(location.href).searchParams;
    const initialQ = urlParams.get("q");
    const initialRes = urlParams.get("res");
    if (initialRes) {
      state.filters.res = initialRes;
      $("#resFilterLabel") && ($("#resFilterLabel").textContent = "Resolution: " + initialRes);
      $$("#resFilterMenu .opt").forEach(o => o.classList.toggle("active", o.dataset.res === initialRes));
    }
    if (urlParams.get("focus")) inputEl.focus();
    if (initialQ) { inputEl.value = initialQ; state.query = initialQ; runSearch(); }

    refreshRanker();

    // ====== core search ======
    async function runSearch() {
      if (!state.query) { toast("Enter a query first", "err"); return; }
      pushRecent(state.query);
      $("#searchTitle").textContent = state.query;
      $("#searchSubtitle").innerHTML = `<span class="spinner"></span> querying sources…`;
      $("#rows").innerHTML = `<tr><td colspan="9" style="text-align:center;padding:30px"><span class="spinner"></span> searching…</td></tr>`;
      const params = new URLSearchParams({ q: state.query });
      if (state.filters.res) params.set("res", state.filters.res);
      let data;
      try { data = await api("/api/search?" + params.toString()); }
      catch (e) { toast("Search failed", "err"); return; }
      if (data.error) { toast(data.error, "err"); return; }
      state.results = data.results || [];
      state.meta = data.meta;
      $("#searchSubtitle").textContent =
        `${state.results.length} results — tried: ${(data.variants || []).slice(0, 4).join(", ")}`;
      renderResults(); renderKPIs(); renderTopThree();
      renderSourceList(); renderResBars(); renderMeta();
      refreshRanker();
    }

    function getFilteredSorted() {
      let rows = state.results.slice();
      if (state.filters.res)    rows = rows.filter(r => r.resolution === state.filters.res);
      if (state.filters.source) rows = rows.filter(r => r.source === state.filters.source);
      if (state.sort === "seeders")    rows.sort((a, b) => (b.seeders || 0) - (a.seeders || 0));
      else if (state.sort === "size_asc")  rows.sort((a, b) => (a.size_bytes || 0) - (b.size_bytes || 0));
      else if (state.sort === "size_desc") rows.sort((a, b) => (b.size_bytes || 0) - (a.size_bytes || 0));
      else if (state.sort === "title") rows.sort((a, b) => a.title.localeCompare(b.title));
      else {
        rows.sort((a, b) => (b.nn_score || 0) - (a.nn_score || 0));
        if (!state.nn) rows.sort((a, b) => (b.seeders || 0) - (a.seeders || 0));
      }
      return rows;
    }
    const healthClass = s => s >= 50 ? "ok" : (s >= 5 ? "warn" : "err");

    function renderResults() {
      const rows = getFilteredSorted();
      state.shown = rows.slice(0, 100);
      $("#resCount").textContent = `${rows.length} result${rows.length === 1 ? "" : "s"}`;
      const isSelected = r => state.compare.find(c => c.title === r.title && c.source === r.source);
      $("#rows").innerHTML = state.shown.length ? state.shown.map((r, i) => `
        <tr class="row ${isSelected(r) ? "selected" : ""}" data-i="${i}">
          <td><input type="checkbox" class="bulk" data-i="${i}"></td>
          <td class="title-cell" title="${escapeHtml(r.title)}">${escapeHtml(r.title || "")}</td>
          <td><span class="src">${escapeHtml(r.source || "")}</span></td>
          <td>${escapeHtml(r.group || "—")}</td>
          <td>${escapeHtml(r.resolution || "—")}</td>
          <td>${fmtBytes(r.size_bytes)}</td>
          <td><span class="health-dot ${healthClass(r.seeders || 0)}"></span>${r.seeders || 0} / ${r.leechers || 0}</td>
          <td><b>${(r.nn_score || 0).toFixed(2)}</b></td>
          <td class="actions-cell">
            <button class="icon-btn" data-act="files" data-i="${i}" title="List files">${SVG.files}</button>
            <button class="icon-btn" data-act="copy"  data-i="${i}" title="Copy magnet">${SVG.copy}</button>
            <button class="icon-btn" data-act="qbit"  data-i="${i}" title="Send to qBittorrent">${SVG.dl}</button>
            <button class="icon-btn" data-act="link"  data-i="${i}" title="Open page">${SVG.link}</button>
          </td>
        </tr>`).join("") : `<tr><td colspan="9" style="text-align:center;color:var(--muted);padding:24px">No matches.</td></tr>`;

      $$("#rows .icon-btn").forEach(b => b.addEventListener("click", e => {
        e.stopPropagation();
        const r = state.shown[+b.dataset.i]; if (!r) return;
        if (b.dataset.act === "copy") copyMagnet(r);
        else if (b.dataset.act === "link") window.open(r.page_url || r.torrent_url || "#", "_blank");
        else if (b.dataset.act === "qbit") sendToQbit(r);
        else if (b.dataset.act === "files") openFiles(r);
      }));
      $$("#rows .row").forEach(tr => tr.addEventListener("click", e => {
        if (e.target.closest(".icon-btn") || e.target.closest("input")) return;
        const r = state.shown[+tr.dataset.i];
        const idx = state.compare.findIndex(c => c.title === r.title && c.source === r.source);
        if (idx >= 0) state.compare.splice(idx, 1); else state.compare.push(r);
        tr.classList.toggle("selected");
        renderCompare();
      }));
    }

    function renderKPIs() {
      const r = state.results;
      const totalSeed = r.reduce((s, x) => s + (x.seeders || 0), 0);
      const seedersEl = $("#kpiSeeders"); if (seedersEl) seedersEl.textContent = totalSeed.toLocaleString();
      const badge = $("#kpiSeedersBadge"); if (badge) badge.textContent = `${r.length} torrents`;
      const avg = r.length ? Math.round(totalSeed / r.length) : 0;
      const delta = $("#kpiSeedersDelta");
      if (delta) { delta.textContent = `avg ${avg}/torrent`;
        delta.className = "pill " + (avg >= 30 ? "ok" : avg >= 5 ? "warn" : "err"); }

      const top = r[0];
      $("#kpiTopRes") && ($("#kpiTopRes").textContent = top ? (top.resolution || "—") : "—");
      $("#kpiTopGroup") && ($("#kpiTopGroup").textContent = top ? (top.group || top.source || "—") : "—");

      const best = r.slice().filter(x => x.resolution === "1080p" && x.size_bytes)
                    .sort((a, b) => a.size_bytes - b.size_bytes)[0];
      $("#kpiBestSize") && ($("#kpiBestSize").textContent  = best ? fmtBytes(best.size_bytes) : "—");
      $("#kpiBestGroup") && ($("#kpiBestGroup").textContent = best ? (best.group || best.source || "—") : "—");

      const srcs = new Set(r.map(x => x.source));
      $("#kpiSources") && ($("#kpiSources").textContent = srcs.size);
      const det = $("#kpiSourcesDetail");
      if (det) { det.textContent = `${srcs.size} source${srcs.size === 1 ? "" : "s"}`;
        det.className = "pill " + (srcs.size >= 4 ? "ok" : srcs.size >= 2 ? "warn" : "err"); }
    }

    function renderTopThree() {
      const el = $("#topThree"); if (!el) return;
      const top = getFilteredSorted().slice(0, 4);
      if (!top.length) {
        el.innerHTML = `<div class="card empty" style="grid-column: 1 / -1; padding: 16px;">No top picks yet.</div>`;
        return;
      }
      el.innerHTML = top.map((r, i) => `
        <div class="card" data-i="${i}">
          <div class="av"></div>
          <div style="min-width:0">
            <b style="display:block;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;max-width:180px">${escapeHtml(r.group || r.source || "—")}</b>
            <span style="color:var(--muted);font-size:11.5px">${r.resolution || "?"} · ${fmtBytes(r.size_bytes)}</span>
          </div>
          <span class="pct">${r.seeders || 0}S</span>
        </div>`).join("");
      $$("#topThree .card[data-i]").forEach(c =>
        c.addEventListener("click", () => sendToQbit(top[+c.dataset.i])));
    }

    function renderSourceList() {
      const el = $("#sourceList"); if (!el) return;
      const buckets = {};
      state.results.forEach(r => { buckets[r.source] = (buckets[r.source] || 0) + 1; });
      const total = state.results.length || 1;
      const entries = Object.entries(buckets).sort((a, b) => b[1] - a[1]);
      if (!entries.length) {
        el.innerHTML = `<div class="empty" style="border-radius:12px;padding:18px">No sources yet.</div>`;
        return;
      }
      el.innerHTML = entries.map(([k, v]) => {
        const pct = Math.round(100 * v / total);
        const active = state.filters.source === k ? " active" : "";
        return `<div class="platform-row${active}" data-src="${k}" style="position:relative">
          <span class="ic">${SVG.source}</span>
          <span class="nm">${escapeHtml(k)}</span>
          <span class="vl">${v}</span>
          <span class="pc">${pct}%</span>
          <span class="bar" style="width: ${pct}%"></span>
        </div>`;
      }).join("");
      $$("#sourceList .platform-row").forEach(rowEl =>
        rowEl.addEventListener("click", () => {
          state.filters.source = state.filters.source === rowEl.dataset.src ? "" : rowEl.dataset.src;
          $$("#sourceList .platform-row").forEach(e => e.classList.toggle("active", e.dataset.src === state.filters.source));
          renderResults();
        }));
    }

    function renderResBars() {
      const el = $("#resBars"); if (!el) return;
      const buckets = { "2160p": 0, "1080p": 0, "720p": 0, "480p": 0, "other": 0 };
      state.results.forEach(r => {
        const k = ["2160p","1080p","720p","480p"].includes(r.resolution) ? r.resolution : "other";
        buckets[k]++;
      });
      const max = Math.max(...Object.values(buckets), 1);
      el.innerHTML = "";
      Object.entries(buckets).forEach(([k, v]) => {
        const h = 30 + (v / max) * 150;
        const isActive = state.filters.res === k;
        const div = document.createElement("div");
        div.className = "bar-col" + (isActive ? " acc" : "");
        div.style.height = `${h}px`;
        div.innerHTML = `<span class="count">${v}</span><span class="label">${k}</span>`;
        div.addEventListener("click", () => {
          state.filters.res = (state.filters.res === k || k === "other") ? "" : k;
          $("#resFilterLabel") && ($("#resFilterLabel").textContent = "Resolution: " + (state.filters.res || "any"));
          renderResults(); renderResBars();
        });
        el.appendChild(div);
      });
    }

    function renderMeta() {
      const m = state.meta;
      const titleEl = $("#animeTitle"), subEl = $("#animeSub"),
            tagsEl = $("#animeTags"), coverEl = $("#animeCover");
      if (!titleEl) return;
      if (!m) {
        titleEl.textContent = state.query || "—";
        subEl.textContent = "No AniList match.";
        tagsEl.innerHTML = "";
        if (coverEl) coverEl.innerHTML = "no cover";
        return;
      }
      titleEl.textContent = m.title?.english || m.title?.romaji || m.title?.native || state.query;
      subEl.textContent = `Score ${m.averageScore ?? "—"} · ${m.episodes ?? "?"} eps · ${m.format ?? ""} ${m.season ?? ""} ${m.seasonYear ?? ""}`.trim();
      tagsEl.innerHTML = (m.genres || []).map(g => `<span class="tag">${escapeHtml(g)}</span>`).join("");
      if (coverEl) {
        if (m.coverImage?.large) coverEl.innerHTML = `<img alt="" src="${m.coverImage.large}">`;
        else coverEl.innerHTML = "no cover";
      }
    }

    function renderCompare() {
      const body = $("#compareTable tbody"); if (!body) return;
      if (!state.compare.length) {
        body.innerHTML = `<tr><td colspan="4" style="color:var(--muted);font-size:12px">Click rows to compare.</td></tr>`;
        return;
      }
      body.innerHTML = state.compare.map(r => `
        <tr>
          <td title="${escapeHtml(r.title)}">${escapeHtml((r.title || "").slice(0, 40))}…</td>
          <td>${r.resolution || "—"}</td>
          <td>${fmtBytes(r.size_bytes)}</td>
          <td><span class="num">${r.seeders || 0}</span></td>
        </tr>`).join("");
    }

    async function copyMagnet(r) {
      const t = r.magnet || r.torrent_url || r.page_url || "";
      if (!t) return toast("No magnet or URL", "err");
      try { await navigator.clipboard.writeText(t); toast(r.magnet ? "Magnet copied" : "Link copied", "ok"); }
      catch { toast(t.slice(0, 80) + "…"); }
    }
    async function sendToQbit(r, withToast = true) {
      const res = await api("/api/download", { method: "POST", body: JSON.stringify({
        mode: "qbit", magnet: r.magnet, torrent_url: r.torrent_url, title: r.title })});
      if (withToast) toast(res.ok ? "Sent to qBittorrent" : "qBit add failed: " + (res.error || ""), res.ok ? "ok" : "err");
      if (res.ok) {
        await api("/api/pick", { method: "POST", body: JSON.stringify({
          picked: r, shown: state.shown, query: state.query })});
        refreshRanker();
      }
      return res;
    }
    async function openFiles(r) {
      $("#filesTitle").textContent = r.title;
      $("#filesBody").innerHTML = '<span class="spinner"></span> fetching file list…';
      $("#filesModal").classList.add("open");
      const files = await api("/api/torrent_files?url=" + encodeURIComponent(r.page_url || ""));
      $("#filesBody").innerHTML = (Array.isArray(files) && files.length)
        ? files.map((f, i) => `<label class="file-row"><input type="checkbox" checked data-fi="${i}"> <span>${escapeHtml(f)}</span></label>`).join("")
        : `<div style="color:var(--muted)">Cannot enumerate files — whole-torrent download only.</div>`;
      $("#dlQbit").onclick = () => { sendToQbit(r); $("#filesModal").classList.remove("open"); };
      $("#dlMagnet").onclick = async () => {
        const res = await api("/api/download", { method: "POST", body: JSON.stringify({
          mode: "magnet", magnet: r.magnet, title: r.title })});
        toast(res.ok ? `Saved → ${res.path}` : "Failed", res.ok ? "ok" : "err");
      };
      $("#dlFile").onclick = async () => {
        const res = await api("/api/download", { method: "POST", body: JSON.stringify({
          mode: "file", torrent_url: r.torrent_url, title: r.title })});
        toast(res.ok ? `Saved → ${res.path}` : "Failed", res.ok ? "ok" : "err");
      };
    }

    async function refreshRanker() {
      const s = await api("/api/stats");
      const box = $("#rankerStats"); if (!box || !s?.weights) return;
      const top = Object.entries(s.weights).filter(([k]) => k !== "bias")
        .sort((a, b) => b[1] - a[1]).slice(0, 4);
      box.innerHTML =
        `<div>${s.samples || 0} samples learned</div>` +
        `<div>bias: ${(s.weights.bias || 0).toFixed(2)}</div>` +
        top.map(([k, v]) => `<div>${k}: <b>${v.toFixed(2)}</b></div>`).join("");
    }

    async function initWidgetCustomizer() {
      const panel = $("#widgetPanel"); if (!panel) return;
      const cfg = await api("/api/dashboard/widgets");
      const widgets = cfg.widgets || [];
      panel.querySelector(".widget-toggle-list").innerHTML = widgets.map(w =>
        `<label><input type="checkbox" data-wid="${w.id}" ${w.enabled ? "checked" : ""}>${w.id}</label>`).join("");
      applyWidgetVisibility(widgets);
      $$('[data-wid]', panel).forEach(c => c.addEventListener("change", async () => {
        const updated = widgets.map(w => ({ ...w, enabled: panel.querySelector(`[data-wid="${w.id}"]`).checked }));
        await api("/api/dashboard/widgets", { method: "POST", body: JSON.stringify({ widgets: updated })});
        applyWidgetVisibility(updated);
      }));
    }
    function applyWidgetVisibility(widgets) {
      widgets.forEach(w => {
        const el = document.querySelector(`[data-widget="${w.id}"]`);
        if (el) el.style.display = w.enabled ? "" : "none";
      });
    }
  }

  /* ============================================================
   * PAGE: SETTINGS (auto-save)
   * ============================================================ */
  if (window.__SETTINGS_PAGE) initSettings();

  async function initSettings() {
    let cfg;
    try { cfg = await api("/api/config"); }
    catch (e) { toast("Cannot reach API", "err"); return; }
    if (!cfg || !cfg.theme) { toast("Failed to load config", "err"); return; }

    const setStatus = (txt, saving = false) => {
      const el = $("#saveStatus"); if (!el) return;
      el.classList.toggle("saving", saving);
      const lbl = el.querySelector(".lbl"); if (lbl) lbl.textContent = txt;
    };
    setStatus("loaded");

    const getByPath = (o, p) => p.split(".").reduce((a, k) => a && a[k], o);
    const setByPath = (o, p, v) => {
      const ks = p.split("."); let cur = o;
      for (let i = 0; i < ks.length - 1; i++) cur = cur[ks[i]] = cur[ks[i]] || {};
      cur[ks[ks.length - 1]] = v;
    };

    // Populate path-based fields
    $$("[data-path]").forEach(el => {
      const v = getByPath(cfg, el.dataset.path);
      if (el.dataset.list) el.value = (v || []).join(", ");
      else if (el.dataset.type === "bool") el.value = String(!!v);
      else if (v !== undefined && v !== null) el.value = v;
    });

    // NN weights — defensive (cfg might not have all fields)
    const nnW = $("#nnWeights");
    if (nnW && cfg.neural_network?.feature_weights) {
      nnW.innerHTML = Object.entries(cfg.neural_network.feature_weights).map(([k, v]) =>
        `<div class="field"><label>${k}</label><input type="number" step="0.05" data-nnw="${k}" value="${v}"></div>`).join("");
    }

    // Source / DDL / Plugin / Manga-source toggles (DEFENSIVE)
    const renderToggles = (containerSel, obj, attr) => {
      const el = $(containerSel);
      if (!el) { console.warn("missing", containerSel); return; }
      if (!obj || typeof obj !== "object") {
        el.innerHTML = `<div class="empty" style="border-radius:10px">No entries.</div>`;
        return;
      }
      const html = Object.entries(obj).map(([k, v]) =>
        `<div class="toggle-row"><span class="name">${escapeHtml(k)}</span>
          <input type="checkbox" ${attr}="${escapeHtml(k)}" ${v ? "checked" : ""}></div>`).join("");
      el.innerHTML = html || `<div class="empty" style="border-radius:10px">No entries.</div>`;
    };
    renderToggles("#sourcesToggle", cfg.sources, "data-src");
    renderToggles("#ddlToggle", cfg.ddl_sources, "data-ddl");
    renderToggles("#pluginsToggle", cfg.plugins, "data-plug");
    renderToggles("#mangaSourcesToggle", cfg.manga_sources, "data-mangasrc");

    // ===== Save (auto + force) =====
    const AUTOSAVE_KEY = "anitorr.autosave";
    let autoSave = (() => { try { return localStorage.getItem(AUTOSAVE_KEY) !== "false"; } catch { return true; }})();
    const autoSel = $("#autoSaveToggle");
    if (autoSel) {
      autoSel.value = String(autoSave);
      autoSel.addEventListener("change", () => {
        autoSave = autoSel.value === "true";
        try { localStorage.setItem(AUTOSAVE_KEY, String(autoSave)); } catch {}
        setStatus(autoSave ? "auto-save on" : "auto-save off · use Force save");
      });
    }

    let saveTimer = 0;
    const doSave = async () => {
      setStatus("saving…", true);
      const next = JSON.parse(JSON.stringify(cfg));
      $$("[data-path]").forEach(el => {
        let v = el.value;
        if (el.dataset.list) v = v.split(",").map(s => s.trim()).filter(Boolean);
        else if (el.dataset.type === "bool") v = v === "true";
        else if (el.type === "number") v = v === "" ? 0 : parseFloat(v);
        setByPath(next, el.dataset.path, v);
      });
      $$("[data-nnw]").forEach(el => {
        if (!next.neural_network) next.neural_network = { feature_weights: {} };
        if (!next.neural_network.feature_weights) next.neural_network.feature_weights = {};
        next.neural_network.feature_weights[el.dataset.nnw] = parseFloat(el.value) || 0;
      });
      $$("[data-src]").forEach(el => { next.sources = next.sources || {}; next.sources[el.dataset.src] = el.checked; });
      $$("[data-ddl]").forEach(el => { next.ddl_sources = next.ddl_sources || {}; next.ddl_sources[el.dataset.ddl] = el.checked; });
      $$("[data-plug]").forEach(el => { next.plugins = next.plugins || {}; next.plugins[el.dataset.plug] = el.checked; });
      $$("[data-mangasrc]").forEach(el => { next.manga_sources = next.manga_sources || {}; next.manga_sources[el.dataset.mangasrc] = el.checked; });

      try {
        const res = await api("/api/config", { method: "POST", body: JSON.stringify(next) });
        if (res.ok) { cfg = next; setStatus("saved · " + new Date().toLocaleTimeString()); setTheme(next.theme); }
        else { setStatus("save failed"); toast("Save failed", "err"); }
      } catch (e) { setStatus("offline"); toast("Network error", "err"); }
    };

    const queueSave = (immediate = false) => {
      if (!autoSave && !immediate) { setStatus("unsaved · click Force save"); return; }
      clearTimeout(saveTimer);
      saveTimer = setTimeout(doSave, immediate ? 0 : 400);
    };

    // Wire change/input handlers
    const wireAutoSave = () => {
      $$("[data-path], [data-nnw], [data-src], [data-ddl], [data-plug], [data-mangasrc]").forEach(el => {
        if (el._wired) return; el._wired = true;
        const ev = el.type === "checkbox" || el.tagName === "SELECT" ? "change" : "input";
        el.addEventListener(ev, queueSave);
        if (el.dataset.path === "theme") {
          el.addEventListener("change", () => setTheme(el.value));
        }
      });
    };
    wireAutoSave();

    $("#forceSaveBtn")?.addEventListener("click", async () => { await doSave(); toast("Settings saved", "ok"); });
    document.addEventListener("keydown", e => {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "s" && window.__SETTINGS_PAGE) {
        e.preventDefault(); doSave().then(() => toast("Saved", "ok"));
      }
    });

    // Bulk toggles
    $("#srcAll")?.addEventListener("click", () => { $$("[data-src]").forEach(el => el.checked = true); queueSave(true); toast("All torrent sources enabled", "ok"); });
    $("#srcNone")?.addEventListener("click", () => { $$("[data-src]").forEach(el => el.checked = false); queueSave(true); toast("All torrent sources disabled"); });
    $("#ddlAll")?.addEventListener("click", () => { $$("[data-ddl]").forEach(el => el.checked = true); queueSave(true); toast("All DDL sources enabled", "ok"); });
    $("#ddlNone")?.addEventListener("click", () => { $$("[data-ddl]").forEach(el => el.checked = false); queueSave(true); toast("All DDL sources disabled"); });
    $("#plugAll")?.addEventListener("click", () => { $$("[data-plug]").forEach(el => el.checked = true); queueSave(true); toast("All plugins enabled", "ok"); });
    $("#plugNone")?.addEventListener("click", () => { $$("[data-plug]").forEach(el => el.checked = false); queueSave(true); toast("All plugins disabled"); });
    $("#mangaAll")?.addEventListener("click", () => { $$("[data-mangasrc]").forEach(el => el.checked = true); queueSave(true); toast("All manga sources enabled", "ok"); });
    $("#mangaNone")?.addEventListener("click", () => { $$("[data-mangasrc]").forEach(el => el.checked = false); queueSave(true); toast("All manga sources disabled"); });

    // Tests
    $("#testNotify")?.addEventListener("click", async () => {
      const r = await api("/api/notify/test", { method: "POST" });
      toast(r.ok ? "Test notification sent" : "Test failed", r.ok ? "ok" : "err");
    });
    $("#testQbit")?.addEventListener("click", async () => {
      const r = await api("/api/qbit/test", { method: "POST" });
      toast(r.ok ? "qBit reachable" : "qBit unreachable: " + (r.error || ""), r.ok ? "ok" : "err");
    });

    // Export / reload
    $("#exportCfg")?.addEventListener("click", () =>
      downloadBlob(JSON.stringify(cfg, null, 2), "anitorr-config.json", "application/json"));
    $("#reloadCfg")?.addEventListener("click", () => location.reload());

    // Search-within-settings
    $("#settingsSearch")?.addEventListener("input", e => {
      const q = e.target.value.toLowerCase();
      $$(".section-card").forEach(card => {
        card.style.display = q && !card.textContent.toLowerCase().includes(q) ? "none" : "";
      });
    });
  }

  /* ============================================================
   * PAGE: STATS
   * ============================================================ */
  if (window.__STATS_PAGE) initStats();

  async function initStats() {
    const load = async () => {
      const s = await api("/api/stats");
      if (!s?.weights) { $("#statsSubtitle").textContent = "no stats yet"; return; }
      $("#statsSubtitle").textContent = `Updated ${new Date().toLocaleTimeString()}`;
      $("#kSamples").textContent = s.samples;
      $("#kBias").textContent = (s.weights.bias || 0).toFixed(2);
      $("#kRecent").textContent = (s.recent || []).length;
      const feats = Object.entries(s.weights).filter(([k]) => k !== "bias").sort((a, b) => b[1] - a[1]);
      if (feats.length) {
        $("#kTopFeat").textContent = feats[0][0];
        $("#kTopFeatVal").textContent = feats[0][1].toFixed(2);
      }
      const max = Math.max(...feats.map(f => Math.abs(f[1])), 0.01);
      $("#featWeights").innerHTML = feats.map(([k, v]) => {
        const pct = Math.min(100, Math.abs(v) / max * 100);
        return `<div style="margin:6px 0">
          <div style="display:flex;justify-content:space-between;font-size:12.5px"><span>${escapeHtml(k)}</span><b>${v.toFixed(3)}</b></div>
          <div style="height:6px;background:var(--panel-2);border:1px solid var(--line);border-radius:999px;overflow:hidden;margin-top:4px">
            <div style="width:${pct}%;height:100%;background:${v >= 0 ? "var(--accent)" : "var(--err)"}"></div>
          </div></div>`;
      }).join("");
      const tbody = $("#recentTable tbody");
      const rec = (s.recent || []).slice().reverse();
      tbody.innerHTML = rec.length ? rec.map(r => `
        <tr><td title="${escapeHtml(r.title || "")}">${escapeHtml(r.query || "")}</td>
        <td>${escapeHtml(r.group || "—")}</td>
        <td>${escapeHtml(r.resolution || "—")}</td>
        <td>${r.ts ? new Date(r.ts * 1000).toLocaleString() : "—"}</td></tr>`).join("")
        : `<tr><td colspan="4" style="color:var(--muted)">No picks yet.</td></tr>`;
    };
    await load();
    $("#refreshStats")?.addEventListener("click", load);
    $("#resetRanker")?.addEventListener("click", async () => {
      if (!confirm("Wipe all learned weights and history?")) return;
      await api("/api/stats/reset", { method: "POST" });
      toast("Ranker reset", "ok"); load();
    });
  }

  /* ============================================================
   * PAGE: MODULES
   * ============================================================ */
  if (window.__MODULES_PAGE) initModules();

  function initModules() {
    $$(".run").forEach(btn => btn.addEventListener("click", async () => {
      const name = btn.dataset.name;
      const wrap = document.querySelector(`.params[data-for="${name}"]`);
      const params = {};
      $$('input[data-pname]', wrap).forEach(i => { if (i.value !== "") params[i.dataset.pname] = i.value; });
      btn.disabled = true; btn.textContent = "Running…";
      const res = await api("/api/modules/run", { method: "POST", body: JSON.stringify({ name, params })});
      btn.disabled = false; btn.textContent = "Run";
      $("#out-" + name).textContent = JSON.stringify(res.result ?? res.error, null, 2);
      toast(res.ok ? `${name}: ok` : `${name}: error`, res.ok ? "ok" : "err");
    }));
    $("#modSearch")?.addEventListener("input", e => {
      const q = e.target.value.toLowerCase();
      $$(".module-card").forEach(c => { c.style.display = q && !c.textContent.toLowerCase().includes(q) ? "none" : ""; });
    });
    $("#reloadMods")?.addEventListener("click", () => location.reload());
  }

  /* ============================================================
   * PAGE: BROWSE / FAVORITES / RECENT / DOWNLOADS
   * ============================================================ */
  if (window.__BROWSE_PAGE)    initBrowse();
  if (window.__FAVORITES_PAGE) initFavoritesPage();
  if (window.__RECENT_PAGE)    initRecentPage();
  if (window.__DOWNLOADS_PAGE) initDownloadsPage();

  async function initBrowse() {
    const filters = window.__BROWSE_FILTERS || {};
    const kind    = filters._kind || "";
    const defaultQ = window.__BROWSE_QUERY || "";

    if (kind === "favorites") {
      const items = await api("/api/favorites");
      renderListCards(items || [], "favorites"); return;
    }
    if (kind === "history" || kind === "searches" || kind === "picks") {
      const items = await api("/api/history");
      renderListCards((items || []).reverse(), "history"); return;
    }
    if (kind === "downloads" || kind === "download_duration") {
      const items = await api("/api/analytics/downloads");
      renderListCards(items || [], "downloads"); return;
    }

    const $rows = $("#rows");
    const runQuery = async () => {
      const q = $("#browseQ").value.trim() || defaultQ;
      if (!q) return toast("Type a query first", "err");
      $("#curQ").textContent = q;
      $rows.innerHTML = `<tr><td colspan="8" style="text-align:center;padding:30px"><span class="spinner"></span> searching…</td></tr>`;
      const params = new URLSearchParams({ q });
      if (filters.res) params.set("res", filters.res);
      const data = await api("/api/search?" + params.toString());
      let rows = data.results || [];
      if (filters.batch) rows = rows.filter(r => r.batch);
      $("#resCount").textContent = `${rows.length} result${rows.length === 1 ? "" : "s"}`;
      $rows.innerHTML = rows.length ? rows.slice(0, 100).map(r => `
        <tr class="row">
          <td class="title-cell" title="${escapeHtml(r.title)}">${escapeHtml(r.title || "")}</td>
          <td><span class="src">${escapeHtml(r.source || "")}</span></td>
          <td>${escapeHtml(r.group || "—")}</td>
          <td>${escapeHtml(r.resolution || "—")}</td>
          <td>${fmtBytes(r.size_bytes)}</td>
          <td>${r.seeders || 0}/${r.leechers || 0}</td>
          <td><b>${(r.nn_score || 0).toFixed(2)}</b></td>
          <td class="actions-cell">
            <button class="icon-btn br-copy" data-m="${(r.magnet||'').replace(/"/g,'&quot;')}">${SVG.copy}</button>
            <button class="icon-btn br-qbit" data-m="${(r.magnet||'').replace(/"/g,'&quot;')}" data-u="${(r.torrent_url||'').replace(/"/g,'&quot;')}" data-t="${(r.title||'').replace(/"/g,'&quot;')}">${SVG.dl}</button>
            <button class="icon-btn br-open" data-u="${(r.page_url||'').replace(/"/g,'&quot;')}">${SVG.link}</button>
          </td>
        </tr>`).join("") : `<tr><td colspan="8" class="empty">No results.</td></tr>`;
      $$(".br-copy").forEach(b => b.addEventListener("click", () => { navigator.clipboard?.writeText(b.dataset.m); toast("copied", "ok"); }));
      $$(".br-open").forEach(b => b.addEventListener("click", () => window.open(b.dataset.u, "_blank")));
      $$(".br-qbit").forEach(b => b.addEventListener("click", async () => {
        const r = await api("/api/download", { method: "POST", body: JSON.stringify({
          mode: "qbit", magnet: b.dataset.m, torrent_url: b.dataset.u, title: b.dataset.t })});
        toast(r.ok ? "Sent" : "Failed", r.ok ? "ok" : "err");
      }));
    };
    $("#runBtn")?.addEventListener("click", runQuery);
    $("#browseQ")?.addEventListener("keydown", e => { if (e.key === "Enter") runQuery(); });
    const auto = $("#autoRun");
    if (auto) {
      const saved = localStorage.getItem("anitorr.browse.auto") === "1";
      auto.classList.toggle("off", !saved);
      auto.addEventListener("click", () => {
        const on = auto.classList.contains("off");
        auto.classList.toggle("off", !on);
        localStorage.setItem("anitorr.browse.auto", on ? "1" : "0");
      });
      if (saved && defaultQ) runQuery();
    }

    function renderListCards(items, k) {
      const body = $("#browseBody");
      if (!items.length) { body.innerHTML = `<div class="card empty">No data.</div>`; return; }
      if (k === "favorites") {
        body.innerHTML = `<div class="grid-2" style="grid-template-columns: repeat(auto-fill, minmax(260px,1fr))">` +
          items.map(f => `<div class="card"><div style="font-weight:700">${escapeHtml(f.title || "—")}</div>
            <div style="color:var(--muted);font-size:12px;margin-top:4px">added ${f.ts ? new Date(f.ts).toLocaleString() : "—"}</div>
            <div style="display:flex;gap:6px;margin-top:10px">
              <a class="filter-btn" href="/?q=${encodeURIComponent(f.title || "")}">Search</a>
              ${f.anilist_id ? `<a class="filter-btn" target="_blank" href="https://anilist.co/anime/${f.anilist_id}">AniList</a>` : ""}
            </div></div>`).join("") + `</div>`;
      } else if (k === "history") {
        body.innerHTML = `<div class="card" style="padding:0;overflow:hidden">
          <table class="results-table" style="margin:0"><thead><tr><th style="padding-left:16px">When</th><th>Query</th><th>Title</th><th>Group</th><th>Res</th></tr></thead>
          <tbody>${items.map(h => `<tr class="row">
            <td style="padding-left:16px;color:var(--muted);font-size:12px">${h.ts ? new Date(h.ts * 1000).toLocaleString() : "—"}</td>
            <td>${escapeHtml(h.query || "—")}</td><td>${escapeHtml(h.title || "—")}</td>
            <td>${escapeHtml(h.group || "—")}</td><td>${escapeHtml(h.resolution || "—")}</td></tr>`).join("")}</tbody></table></div>`;
      } else if (k === "downloads") {
        body.innerHTML = `<div class="card" style="padding:0;overflow:hidden">
          <table class="results-table" style="margin:0"><thead><tr><th style="padding-left:16px">Name</th><th>Type</th><th>Size</th><th>Saved</th></tr></thead>
          <tbody>${items.map(it => `<tr class="row"><td style="padding-left:16px">${escapeHtml(it.name)}</td>
            <td><span class="src">${it.type}</span></td><td>${fmtBytes(it.size)}</td>
            <td style="color:var(--muted);font-size:12px">${it.mtime ? new Date(it.mtime * 1000).toLocaleString() : "—"}</td></tr>`).join("")}</tbody></table></div>`;
      }
    }
  }

  function initFavoritesPage() {
    $$(".search-btn").forEach(b => b.addEventListener("click", () => location.href = "/?q=" + encodeURIComponent(b.dataset.q)));
    $$(".rm-btn").forEach(b => b.addEventListener("click", async () => {
      await api("/api/favorites", { method: "DELETE", body: JSON.stringify({ title: b.dataset.title })});
      b.closest(".fav-card").remove(); toast(`Removed`, "ok");
    }));
    $("#favFilter")?.addEventListener("input", e => {
      const q = e.target.value.toLowerCase();
      $$(".fav-card").forEach(c => { c.style.display = q && !c.dataset.title.toLowerCase().includes(q) ? "none" : ""; });
    });
    $("#favExport")?.addEventListener("click", async () => {
      const items = await api("/api/favorites");
      downloadBlob(JSON.stringify(items, null, 2), "anitorr-favorites.json", "application/json");
    });
    $("#favClear")?.addEventListener("click", async () => {
      if (!confirm("Remove ALL favorites?")) return;
      const items = await api("/api/favorites") || [];
      for (const it of items) await api("/api/favorites", { method: "DELETE", body: JSON.stringify({ title: it.title })});
      toast("All cleared", "ok"); setTimeout(() => location.reload(), 600);
    });
    $$(".fav-card").forEach(c => {
      const sub = c.querySelector("div:nth-child(2)");
      if (sub && /added \d+/.test(sub.textContent)) {
        const ts = parseInt(sub.textContent.match(/added (\d+)/)[1], 10);
        sub.textContent = sub.textContent.replace(/added \d+/, "added " + new Date(ts).toLocaleString());
      }
    });
  }

  function initRecentPage() {
    $$("#recentRows tr.row").forEach(tr => {
      const td = tr.querySelector("td");
      const ts = parseInt(td.textContent.trim(), 10);
      if (ts) td.textContent = new Date(ts * 1000).toLocaleString();
    });
    $$(".redo").forEach(b => b.addEventListener("click", e => { e.stopPropagation(); location.href = "/?q=" + encodeURIComponent(b.dataset.q); }));
    $$("#recentRows tr.row").forEach(tr => tr.addEventListener("click", e => {
      if (e.target.closest(".icon-btn")) return;
      location.href = "/?q=" + encodeURIComponent(tr.dataset.q);
    }));
    $("#recentFilter")?.addEventListener("input", e => {
      const q = e.target.value.toLowerCase();
      $$("#recentRows tr.row").forEach(tr => { tr.style.display = q && !tr.textContent.toLowerCase().includes(q) ? "none" : ""; });
    });
    $("#recExport")?.addEventListener("click", async () => {
      const items = await api("/api/history");
      downloadBlob(JSON.stringify(items, null, 2), "anitorr-history.json", "application/json");
    });
    $("#recClear")?.addEventListener("click", async () => {
      if (!confirm("Clear all history?")) return;
      await api("/api/history", { method: "DELETE" });
      toast("History cleared", "ok"); setTimeout(() => location.reload(), 600);
    });
  }

  function initDownloadsPage() {
    let total = 0;
    $$("#dlRows tr.row").forEach(tr => {
      const tds = tr.querySelectorAll("td");
      const size = parseInt(tds[2].dataset.size, 10) || 0; total += size;
      tds[2].textContent = fmtBytes(size);
      const ts = parseInt(tds[3].textContent.trim(), 10);
      if (ts) tds[3].textContent = new Date(ts * 1000).toLocaleString();
    });
    const sz = $("#dlSize"); if (sz) sz.textContent = fmtBytes(total);
    $$(".dl-rm").forEach(b => b.addEventListener("click", async () => {
      if (!confirm(`Delete ${b.dataset.name}?`)) return;
      const r = await api("/api/downloads/delete", { method: "POST", body: JSON.stringify({ name: b.dataset.name })});
      if (r.ok) { b.closest("tr").remove(); toast("Deleted", "ok"); } else toast("Delete failed", "err");
    }));
    $("#dlFilter")?.addEventListener("input", e => {
      const q = e.target.value.toLowerCase();
      $$("#dlRows tr.row").forEach(tr => { tr.style.display = q && !tr.dataset.name.toLowerCase().includes(q) ? "none" : ""; });
    });
    $("#dlRefresh")?.addEventListener("click", () => location.reload());
  }

  /* ============================================================
   * PAGE: MANGA
   * ============================================================ */
  if (window.__MANGA_PAGE) initMangaPage();

  function initMangaPage() {
    const cfg = window.__MANGA_CFG || {};
    const cropToggle = $("#cropToggle");
    let autocrop = !!cfg.autocrop;
    if (cropToggle) cropToggle.addEventListener("click", () => {
      autocrop = !autocrop; cropToggle.classList.toggle("off", !autocrop);
    });

    const search = async () => {
      const q = $("#mangaQ").value.trim();
      if (!q) return toast("Type a search", "err");
      const out = $("#mangaResults");
      out.innerHTML = `<div class="card"><span class="spinner"></span> searching ${(window.__MANGA_SOURCES || []).length} sources…</div>`;
      const rows = await api("/api/manga/search?q=" + encodeURIComponent(q));
      if (!Array.isArray(rows) || !rows.length) {
        out.innerHTML = `<div class="card empty">No matches.</div>`; return;
      }
      out.innerHTML = `<div class="manga-grid">${rows.map(r => `
        <a class="manga-card" href="/manga/${encodeURIComponent(r.source)}/${encodeURIComponent(r.slug || r.url)}" title="${escapeHtml(r.title)}">
          <div class="mc-cover">${r.cover ? `<img loading="lazy" src="${r.cover}" alt="">` : "no cover"}</div>
          <div class="mc-body">
            <div class="mc-title">${escapeHtml(r.title)}</div>
            <span class="mc-source">${escapeHtml(r.source)}</span>
          </div>
        </a>`).join("")}</div>`;
    };
    $("#mangaQ")?.addEventListener("keydown", e => { if (e.key === "Enter") search(); });
    $("#mangaRefresh")?.addEventListener("click", search);

    // URL downloader
    $("#urlGo")?.addEventListener("click", async () => {
      const url = $("#urlInput").value.trim();
      const fmt = $("#urlFmt").value;
      const title = $("#urlTitle").value.trim();
      if (!url) return toast("Enter a URL", "err");
      const r = await api("/api/manga/download/by-url", { method: "POST",
        body: JSON.stringify({ url, fmt, title, autocrop })});
      if (r.ok) { toast("Download started: " + r.job_id, "ok"); refreshJobs(); }
      else toast("Failed: " + (r.error || ""), "err");
    });

    // Jobs
    async function refreshJobs() {
      const jobs = await api("/api/manga/jobs");
      const el = $("#jobList");
      if (!jobs.length) { el.innerHTML = "No jobs yet."; el.className = "empty"; return; }
      el.className = "";
      el.innerHTML = jobs.map(j => {
        const pct = j.total ? Math.round((j.done / j.total) * 100) : 0;
        return `<div class="job-row" id="job-${j.id}">
          <div>
            <b>${escapeHtml(j.title)}</b>
            <div style="color:var(--muted);font-size:11px">${j.source} · ${j.fmt.toUpperCase()} · ${j.done}/${j.total} pages</div>
          </div>
          <div class="job-bar"><span style="width:${pct}%"></span></div>
          <span class="job-status s-${j.status}">${j.status}</span>
          ${j.path ? `<span class="kbd" title="${j.path}">${j.path.split('/').pop()}</span>` : '<span></span>'}
        </div>`;
      }).join("");
    }
    $("#refreshJobs")?.addEventListener("click", refreshJobs);
    refreshJobs();
    setInterval(refreshJobs, 3000);

    // Pre-search if URL has ?q=
    const initQ = new URL(location.href).searchParams.get("q");
    if (initQ) { $("#mangaQ").value = initQ; search(); }
  }

  /* ============================================================
   * PAGE: MANGA DETAIL
   * ============================================================ */
  if (window.__MANGA_DETAIL) initMangaDetail();

  async function initMangaDetail() {
    const source = window.__MD_SOURCE, slug = window.__MD_SLUG;
    // Try to reconstruct URL from slug
    let url = slug;
    if (!/^https?:\/\//.test(url)) {
      const guesses = {
        mangadex: `https://mangadex.org/title/${slug}`,
        webtoons: `https://www.webtoons.com/${slug}`,
      };
      url = guesses[source] || slug;
    }
    const chapters = await api(`/api/manga/chapters?source=${encodeURIComponent(source)}&url=${encodeURIComponent(url)}`);
    const tbody = $("#chRows");
    if (!Array.isArray(chapters) || !chapters.length) {
      tbody.innerHTML = `<tr><td colspan="5" class="empty">No chapters found.</td></tr>`;
      return;
    }
    tbody.innerHTML = chapters.map((c, i) => `
      <tr class="row" data-i="${i}">
        <td style="padding-left:16px"><input type="checkbox" class="ch-chk" data-i="${i}"></td>
        <td class="title-cell">${escapeHtml(c.title)}</td>
        <td>${escapeHtml(c.number || "—")}</td>
        <td>${c.pages || "?"}</td>
        <td class="actions-cell" style="padding-right:16px">
          <button class="icon-btn ch-dl" data-i="${i}" title="Download this chapter">${SVG.dl}</button>
        </td>
      </tr>`).join("");
    $("#chkAll")?.addEventListener("change", e => $$(".ch-chk").forEach(c => c.checked = e.target.checked));
    $$(".ch-dl").forEach(b => b.addEventListener("click", async () => {
      const c = chapters[+b.dataset.i];
      await downloadChapters([c], "cbz", false);
    }));
    $("#bulkDl")?.addEventListener("click", () => {
      const sel = $$(".ch-chk:checked").map(c => chapters[+c.dataset.i]);
      if (!sel.length) return toast("Select chapters first", "err");
      $("#fmtModal").classList.add("open");
      $("#bulkGo").onclick = async () => {
        $("#fmtModal").classList.remove("open");
        await downloadChapters(sel, $("#bulkFmt").value, $("#bulkCrop").value === "1");
      };
    });
    $$('#fmtModal [data-close]').forEach(b => b.addEventListener("click", () => $("#fmtModal").classList.remove("open")));

    async function downloadChapters(items, fmt, autocrop) {
      for (const ch of items) {
        const pages = await api(`/api/manga/pages?source=${encodeURIComponent(source)}&url=${encodeURIComponent(ch.url)}`);
        if (!pages.length) { toast(`No pages for ${ch.title}`, "err"); continue; }
        await api("/api/manga/download", { method: "POST", body: JSON.stringify({
          title: `${slug} - ${ch.title}`, source, pages, fmt, autocrop, series: slug })});
        toast(`Queued ${ch.title}`, "ok");
      }
    }
    $("#searchInPage")?.addEventListener("input", e => {
      const q = e.target.value.toLowerCase();
      $$("#chRows tr.row").forEach(tr => { tr.style.display = q && !tr.textContent.toLowerCase().includes(q) ? "none" : ""; });
    });
  }

  /* ============================================================
   * PAGE: NOTIFICATIONS
   * ============================================================ */
  if (window.__NOTIF_PAGE) initNotifPage();

  function initNotifPage() {
    // Humanize timestamps
    $$(".notif-ts").forEach(el => {
      const ts = parseInt(el.textContent.trim(), 10);
      if (ts) el.textContent = new Date(ts * 1000).toLocaleString();
    });
    // Mark each row read on click
    $$(".notif-row").forEach(row => row.addEventListener("click", async () => {
      const id = parseInt(row.dataset.id, 10);
      await api("/api/notifications/read", { method: "POST", body: JSON.stringify({ id })});
      row.classList.remove("unread");
    }));
    $("#markAllRead")?.addEventListener("click", async () => {
      await api("/api/notifications/read", { method: "POST", body: JSON.stringify({ all: true })});
      $$(".notif-row").forEach(r => r.classList.remove("unread"));
      toast("All marked read", "ok");
    });
    $("#clearAllNotif")?.addEventListener("click", async () => {
      if (!confirm("Clear all notifications?")) return;
      await api("/api/notifications", { method: "DELETE" });
      toast("Cleared", "ok"); setTimeout(() => location.reload(), 600);
    });
    $("#notifFilter")?.addEventListener("input", e => {
      const q = e.target.value.toLowerCase();
      $$(".notif-row").forEach(r => { r.style.display = q && !r.dataset.text.toLowerCase().includes(q) ? "none" : ""; });
    });
  }


  /* ============================================================
   * PAGE: LIBRARY
   * ============================================================ */
  if (window.__LIBRARY_PAGE) initLibraryPage();

  async function initLibraryPage() {
    const d = await api("/api/library/summary");
    if (!d) return;
    $("#libTorrents").textContent = d.torrents_count;
    $("#libManga").textContent    = d.manga_count;
    $("#libFavs").textContent     = d.favorites_count;
    $("#libSize").textContent     = fmtBytes((d.torrents_size||0) + (d.manga_size||0));

    const renderList = (sel, items, type) => {
      const el = $(sel);
      if (!items.length) { el.className = "empty"; el.innerHTML = "Nothing here yet."; return; }
      el.className = "";
      el.innerHTML = items.slice(0, 8).map(it => {
        if (type === "torrent" || type === "manga") {
          return `<div class="job-row">
            <div><b>${escapeHtml(it.name)}</b>
              <div style="color:var(--muted);font-size:11px">${type} · ${fmtBytes(it.size)} · ${new Date(it.mtime*1000).toLocaleString()}</div>
            </div>
            <span class="job-status">${it.type||"file"}</span>
          </div>`;
        }
        if (type === "fav") {
          return `<div class="job-row"><div><b>${escapeHtml(it.title)}</b>
            <div style="color:var(--muted);font-size:11px">added ${it.ts ? new Date(it.ts).toLocaleString() : "—"}</div></div>
            <a class="filter-btn" href="/?q=${encodeURIComponent(it.title)}">Search</a></div>`;
        }
        return `<div class="job-row"><div><b>${escapeHtml(it.title || it.query || "—")}</b>
          <div style="color:var(--muted);font-size:11px">${it.group||""} ${it.resolution||""} ${it.ts ? new Date(it.ts*1000).toLocaleString() : ""}</div></div></div>`;
      }).join("");
    };
    renderList("#libTorrentList", d.torrents, "torrent");
    renderList("#libMangaList",   d.manga,    "manga");
    renderList("#libFavList",     d.favorites,"fav");
    renderList("#libRecentList",  d.recent,   "recent");

    $("#libFilter")?.addEventListener("input", e => {
      const q = e.target.value.toLowerCase();
      $$(".job-row").forEach(r => { r.style.display = q && !r.textContent.toLowerCase().includes(q) ? "none" : ""; });
    });
    $("#libRefresh")?.addEventListener("click", () => location.reload());
  }

  /* ============================================================
   * PAGE: REPORTS (live log viewer)
   * ============================================================ */
  if (window.__REPORTS_PAGE) initReportsPage();

  function initReportsPage() {
    let timer = 0, autoOn = false;
    const $body = $("#logBody");

    const render = async () => {
      const d = await api("/api/logs?n=500");
      if (!d) return;
      const lines = (d.lines || []).map(l => {
        const cls = /\[ERROR\]|\[CRITICAL\]/.test(l) ? "err"
                 : /\[WARNING\]/.test(l) ? "warn"
                 : /\[INFO\]/.test(l) ? "ok" : "";
        return `<span style="display:block;color:var(--${cls === "err" ? "err" : cls === "warn" ? "warn" : "ink-soft"})">${escapeHtml(l)}</span>`;
      });
      $body.innerHTML = lines.join("") || `<span style="color:var(--muted)">empty.</span>`;
      $body.scrollTop = $body.scrollHeight;
      $("#rTotal").textContent  = d.totals.total;
      $("#rErrors").textContent = d.totals.errors;
      $("#rWarns").textContent  = d.totals.warns;
      $("#rLast").textContent   = (d.totals.last || "—").slice(0, 40);
      $("#logSubtitle").textContent = `${d.totals.total} lines · updated ${new Date().toLocaleTimeString()}`;
    };
    render();

    $("#logRefresh")?.addEventListener("click", render);
    $("#logDownload")?.addEventListener("click", async () => {
      const d = await api("/api/logs?n=100000");
      downloadBlob((d.lines || []).join("\n"), "anitorr.log", "text/plain");
    });
    $("#logClear")?.addEventListener("click", async () => {
      if (!confirm("Clear log file?")) return;
      await api("/api/logs", { method: "DELETE" });
      render();
    });
    $("#logFilter")?.addEventListener("input", e => {
      const q = e.target.value.toLowerCase();
      $$("#logBody > span").forEach(sp => { sp.style.display = q && !sp.textContent.toLowerCase().includes(q) ? "none" : ""; });
    });

    const auto = $("#logAuto");
    auto?.addEventListener("click", () => {
      autoOn = auto.classList.contains("off");
      auto.classList.toggle("off", !autoOn);
      clearInterval(timer);
      if (autoOn) timer = setInterval(render, 2000);
    });
  }

  /* ============================================================
   * Generic helpers
   * ============================================================ */
  function downloadBlob(content, name, type) {
    const blob = new Blob([content], { type });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob); a.download = name; a.click();
    setTimeout(() => URL.revokeObjectURL(a.href), 2000);
  }
})();
