/* ANITorr docs — theme toggle, particles, scroll-triggered terminals, TOC. */
(() => {
  const $  = (s, p = document) => p.querySelector(s);
  const $$ = (s, p = document) => Array.from(p.querySelectorAll(s));

  /* ============================================================
   * Theme
   * ============================================================ */
  const root = document.documentElement;
  const saved = localStorage.getItem("anitorr-theme");
  if (saved) root.dataset.theme = saved;
  else if (window.matchMedia("(prefers-color-scheme: dark)").matches) root.dataset.theme = "dark";
  $("#themeBtn")?.addEventListener("click", () => {
    root.dataset.theme = root.dataset.theme === "dark" ? "light" : "dark";
    localStorage.setItem("anitorr-theme", root.dataset.theme);
  });

  /* ============================================================
   * Copy-on-click
   * ============================================================ */
  $$(".copy").forEach(el => {
    el.addEventListener("click", () => {
      navigator.clipboard?.writeText(el.dataset.copy || el.textContent.trim());
      el.classList.add("copied");
      setTimeout(() => el.classList.remove("copied"), 1500);
    });
  });

  /* ============================================================
   * Particles background (square pastel dots drifting)
   * ============================================================ */
  const cvs = $("#particles");
  if (cvs) {
    const ctx = cvs.getContext("2d");
    let W, H, parts = [];
    const palette = ["#ec2a6a","#ffb3c8","#d6eaff","#d6f5d6","#fff1c2","#e8d6ff"];
    const resize = () => {
      W = cvs.width = innerWidth * devicePixelRatio;
      H = cvs.height = innerHeight * devicePixelRatio;
      cvs.style.width = innerWidth + "px"; cvs.style.height = innerHeight + "px";
      parts = Array.from({ length: 60 }, () => ({
        x: Math.random() * W, y: Math.random() * H,
        vx: (Math.random() - .5) * 0.15, vy: (Math.random() - .5) * 0.15,
        s: (2 + Math.random() * 4) * devicePixelRatio,
        c: palette[Math.floor(Math.random() * palette.length)],
        a: 0.15 + Math.random() * 0.35,
      }));
    };
    const draw = () => {
      ctx.clearRect(0, 0, W, H);
      parts.forEach(p => {
        p.x += p.vx; p.y += p.vy;
        if (p.x < 0) p.x = W; if (p.x > W) p.x = 0;
        if (p.y < 0) p.y = H; if (p.y > H) p.y = 0;
        ctx.globalAlpha = p.a; ctx.fillStyle = p.c;
        ctx.fillRect(p.x, p.y, p.s, p.s);
      });
      requestAnimationFrame(draw);
    };
    resize(); draw();
    addEventListener("resize", resize);
  }

  /* ============================================================
   * Reveal on scroll
   * ============================================================ */
  const revealIO = new IntersectionObserver(es => {
    es.forEach(e => { if (e.isIntersecting) e.target.classList.add("on"); });
  }, { threshold: 0.08 });
  $$(".reveal").forEach(el => revealIO.observe(el));

  /* ============================================================
   * TERMINAL animations — typewriter, scroll-triggered, replayable.
   *
   * Each script is a list of step objects:
   *   { c: 'class', t: 'text', d: typingDelay(ms) }  → typed line
   *   { c: 'class', t: '...',  i: true }             → instant (paste) line
   *   { sleep: ms }                                  → pause
   *   { clear: true }                                → wipe screen
   * ============================================================ */
  const TERMINALS = {};

  // ---- INSTALL terminal ----
  TERMINALS["t-install"] = [
    { c: "t-prompt", t: "$ ", i: true }, { c: "t-cmd", t: "git clone https://github.com/you/anitorr" },
    { sleep: 250 },
    { c: "t-muted", t: "Cloning into 'anitorr'...", i: true },
    { c: "t-muted", t: "remote: Enumerating objects: 412, done.", i: true },
    { c: "t-muted", t: "Receiving objects: 100% (412/412), 1.34 MiB", i: true },
    { sleep: 200 },
    { c: "t-prompt", t: "$ ", i: true }, { c: "t-cmd", t: "cd anitorr && pip install -r requirements.txt" },
    { sleep: 300 },
    { c: "t-muted", t: "Installing flask, beautifulsoup4, rich, pyfiglet, textual, qbittorrent-api…", i: true },
    { c: "t-ok",    t: "Successfully installed 14 packages", i: true },
    { sleep: 200 },
    { c: "t-prompt", t: "$ ", i: true }, { c: "t-cmd", t: "python backend/app.py" },
    { sleep: 250 },
    { c: "t-muted", t: " * Serving Flask app 'app'", i: true },
    { c: "t-muted", t: " * Running on http://0.0.0.0:5000", i: true },
    { c: "t-ok",    t: " * Debugger is active!", i: true },
    { sleep: 400 },
    { c: "t-accent", t: "→ open http://localhost:5000", i: true },
  ];

  // ---- CLI mode picker ----
  TERMINALS["t-cli-modepick"] = [
    { c: "t-prompt", t: "$ ", i: true }, { c: "t-cmd", t: "python cli/anitorr_cli.py" },
    { sleep: 300 },
    { c: "t-pink",  t: "    ___    _   _ ____________               ", i: true },
    { c: "t-pink",  t: "   /   |  / | / //  _/_  __/___  __________ ", i: true },
    { c: "t-pink",  t: "  / /| | /  |/ / / /  / / / __ \\/ ___/ ___/ ", i: true },
    { c: "t-pink",  t: " / ___ |/ /|  /_/ /  / / / /_/ / /  / /     ", i: true },
    { c: "t-pink",  t: "/_/  |_/_/ |_/___/ /_/  \\____/_/  /_/      ", i: true },
    { c: "t-muted", t: "       plugin-driven anime + manga + torrents", i: true },
    { c: "",        t: "" },
    { c: "box",     t: "╭─────────╮  ╭─────────╮  ╭───────────╮", i: true },
    { c: "box",     t: "│ [1] ANIME│  │ [2] MANGA│  │ [3] SETTINGS│", i: true },
    { c: "box",     t: "│ torrent  │  │ 13 srcs  │  │ edit config │", i: true },
    { c: "box",     t: "│ NN rank  │  │ EPUB/CBZ │  │ live save   │", i: true },
    { c: "box",     t: "╰─────────╯  ╰─────────╯  ╰───────────╯", i: true },
    { c: "",        t: "" },
    { c: "t-accent", t: "What do you want? (anime/manga/settings) [anime]: ", i: true },
    { sleep: 600, },
    { c: "t-cmd",   t: "anime", d: 80 },
  ];

  // ---- ANIME search flow ----
  TERMINALS["t-cli-anime"] = [
    { c: "t-accent", t: "Anime title: ", i: true }, { c: "t-cmd", t: "Frieren", d: 70 },
    { c: "t-accent", t: "Quality [480p/720p/1080p/2160p/any] (1080p): ", i: true }, { c: "t-cmd", t: "1080p", d: 60 },
    { c: "t-accent", t: "Language [en/jp/es/fr/multi/any] (en): ", i: true }, { c: "t-cmd", t: "en", d: 70 },
    { c: "t-accent", t: "Use AI title normalization? [Y/n]: ", i: true }, { c: "t-cmd", t: "y", d: 80 },
    { sleep: 300 },
    { c: "t-muted", t: "⠋ metadata… variants: ['Frieren', 'Sousou no Frieren', '葬送のフリーレン']", i: true },
    { c: "t-muted", t: "⠙ querying 8 sources… ████████████████ 4/4", i: true },
    { c: "t-muted", t: "relevance filter: 142 → 89 results", i: true },
    { sleep: 250 },
    { c: "box", t: "╭─ AniList ───────────────────────────────────╮", i: true },
    { c: "box", t: "│       Title : Sousou no Frieren             │", i: true },
    { c: "box", t: "│       Score : 91                            │", i: true },
    { c: "box", t: "│    Episodes : 28                            │", i: true },
    { c: "box", t: "│      Status : FINISHED                       │", i: true },
    { c: "box", t: "│      Genres : Adventure, Drama, Fantasy     │", i: true },
    { c: "box", t: "╰─────────────────────────────────────────────╯", i: true },
    { c: "",    t: "" },
    { c: "box", t: "╭─# ─ Title ──────────────────────────── Src ── Group ─── Res ── Size ── S ── L ── NN ─╮", i: true },
    { c: "box", t: "│ 1  [SubsPlease] Sousou no Frieren 12      nyaa  SubsPlease 1080p 1.3G  312 12  2.41 │", i: true },
    { c: "box", t: "│ 2  [ASW] Sousou no Frieren - 12 1080p     nyaa  ASW        1080p 1.1G  188  7  2.10 │", i: true },
    { c: "box", t: "│ 3  [Erai-raws] Sousou no Frieren 12       erai  Erai-raws  1080p 1.2G  144  4  1.88 │", i: true },
    { c: "box", t: "│ 4  [Judas] Sousou no Frieren S1 [Batch]   tosho Judas      1080p 18G    92  3  1.71 │", i: true },
    { c: "box", t: "╰────────────────────────────────────────────────────────────────────────────────────╯", i: true },
    { c: "",    t: "" },
    { c: "t-accent", t: "Pick # (n=new search, q=quit) [1]: ", i: true }, { c: "t-cmd", t: "1", d: 200 },
    { sleep: 250 },
    { c: "t-muted", t: "⠴ asking qBittorrent for metadata… (~10s)", i: true },
    { sleep: 250 },
    { c: "box", t: "╭─#  File ─────────────────────────────────────── Size ─╮", i: true },
    { c: "box", t: "│  1  [SubsPlease] Frieren - 12 (1080p) [F00D].mkv 1.3G │", i: true },
    { c: "box", t: "│  2  [SubsPlease] Frieren - 12 (1080p) [F00D].srt 28K  │", i: true },
    { c: "box", t: "╰───────────────────────────────────────────────────────╯", i: true },
    { c: "t-accent", t: "Files to download (e.g. '1,3,5' or 'all') [all]: ", i: true }, { c: "t-cmd", t: "1", d: 200 },
    { c: "t-accent", t: "Action [qbit/file/magnet/copy/skip] (qbit): ", i: true }, { c: "t-cmd", t: "qbit", d: 80 },
    { sleep: 250 },
    { c: "t-ok", t: "✓ Sent to qBittorrent.", i: true },
    { c: "t-ok", t: "✓ Set 1 files to download, 1 skipped.", i: true },
    { c: "t-ok", t: "✓ Ranker learned (new weight: trust=1.62, prompt=2.08)", i: true },
  ];

  // ---- MANGA flow ----
  TERMINALS["t-cli-manga"] = [
    { c: "t-prompt", t: "$ ", i: true }, { c: "t-cmd", t: "python cli/anitorr_cli.py --manga" },
    { sleep: 200 },
    { c: "t-accent", t: "Manga / manhua / webtoon title: ", i: true }, { c: "t-cmd", t: "Chainsaw Man", d: 70 },
    { c: "t-muted", t: "⠹ searching 13 sources…", i: true },
    { sleep: 300 },
    { c: "box", t: "╭─# ─ Title ──────────────────── Source ──── Status ──── Lang ╮", i: true },
    { c: "box", t: "│ 1  Chainsaw Man                mangadex    ongoing       ja  │", i: true },
    { c: "box", t: "│ 2  Chainsaw Man                manganato   ongoing       en  │", i: true },
    { c: "box", t: "│ 3  Chainsaw Man (Webtoon)      webtoons    ongoing       en  │", i: true },
    { c: "box", t: "│ 4  Chainsaw Man (Color)        mangadex    completed     ja  │", i: true },
    { c: "box", t: "╰──────────────────────────────────────────────────────────────╯", i: true },
    { c: "t-accent", t: "Pick series # [1]: ", i: true }, { c: "t-cmd", t: "1", d: 150 },
    { sleep: 250 },
    { c: "t-muted", t: "⠼ loading chapters…", i: true },
    { sleep: 250 },
    { c: "box", t: "╭─#  Chapter title ─────── Num ── Pages ╮", i: true },
    { c: "box", t: "│  1  Dog & Chainsaw         1     53    │", i: true },
    { c: "box", t: "│  2  The Place Chainsaw     2     42    │", i: true },
    { c: "box", t: "│  3  Arrival in Tokyo       3     38    │", i: true },
    { c: "box", t: "│ …   165 more chapters available        │", i: true },
    { c: "box", t: "╰────────────────────────────────────────╯", i: true },
    { c: "t-accent", t: "Chapters (e.g. 1,2,3 / 1-10 / all) [1]: ", i: true }, { c: "t-cmd", t: "1-3", d: 200 },
    { c: "t-accent", t: "Format [cbz/zip/epub/pdf] (cbz): ", i: true }, { c: "t-cmd", t: "epub", d: 120 },
    { c: "t-accent", t: "Auto-crop margins? [y/N]: ", i: true }, { c: "t-cmd", t: "y", d: 200 },
    { sleep: 300 },
    { c: "t-pink", t: "⠹ chapters  ████████████ 1/3", i: true },
    { c: "t-ok",   t: "✓ Chainsaw Man - Dog & Chainsaw.epub", i: true },
    { c: "t-pink", t: "⠼ chapters  ████████████████ 2/3", i: true },
    { c: "t-ok",   t: "✓ Chainsaw Man - The Place Chainsaw.epub", i: true },
    { c: "t-pink", t: "⠿ chapters  ████████████████████ 3/3", i: true },
    { c: "t-ok",   t: "✓ Chainsaw Man - Arrival in Tokyo.epub", i: true },
    { c: "",       t: "" },
    { c: "t-accent", t: "Saved to /home/user/anitorr/manga", i: true },
  ];

  // ---- SETTINGS flow ----
  TERMINALS["t-cli-settings"] = [
    { c: "t-prompt", t: "$ ", i: true }, { c: "t-cmd", t: "python cli/anitorr_cli.py --settings" },
    { sleep: 250 },
    { c: "box", t: "╭─#  Section ──────── Key ───────────────── Value ───╮", i: true },
    { c: "box", t: "│ 1  Theme & lang    theme                  cream    │", i: true },
    { c: "box", t: "│ 2                  language               en       │", i: true },
    { c: "box", t: "│ 3                  default_resolution     1080p    │", i: true },
    { c: "box", t: "│ 4                  default_lang           en       │", i: true },
    { c: "box", t: "│ 5  Behaviour       min_seeders            1        │", i: true },
    { c: "box", t: "│ 6                  aggregator_threshold   5        │", i: true },
    { c: "box", t: "│ 7  qBittorrent     qbittorrent.enabled    True     │", i: true },
    { c: "box", t: "│ 8                  qbittorrent.host       http://… │", i: true },
    { c: "box", t: "│ 9  Manga           manga.default_format   cbz      │", i: true },
    { c: "box", t: "│10                  manga.autocrop         False    │", i: true },
    { c: "box", t: "│11                  manga.page_progression rtl      │", i: true },
    { c: "box", t: "╰────────────────────────────────────────────────────╯", i: true },
    { c: "t-accent", t: "Pick # to edit (s=save, q=quit) [q]: ", i: true }, { c: "t-cmd", t: "9", d: 250 },
    { sleep: 200 },
    { c: "t-accent", t: "new value for manga.default_format [cbz/zip/epub/pdf] (cbz): ", i: true },
    { c: "t-cmd", t: "epub", d: 120 },
    { c: "t-ok", t: "saved → config.json", i: true },
  ];

  // ---- TUI screenshot animation ----
  TERMINALS["t-tui"] = [
    { c: "t-prompt", t: "$ ", i: true }, { c: "t-cmd", t: "python cli/anitorr_cli.py --tui" },
    { sleep: 250 },
    { c: "t-pink",   t: "┌─ ANITorr ──────────────────────────────────────────────────────────────┐", i: true },
    { c: "box", t: "│ ★ Anime    Manga    Settings                                          │", i: true },
    { c: "box", t: "├────────────────────────────────────────────────────────────────────────┤", i: true },
    { c: "box", t: "│ ┌─────────────────────────────────┐ ┌──────────┐                       │", i: true },
    { c: "box", t: "│ │ Anime title… (Enter)            │ │ Quality  │                       │", i: true },
    { c: "box", t: "│ └─────────────────────────────────┘ │ 1080p ▾  │                       │", i: true },
    { c: "box", t: "│                                     └──────────┘                       │", i: true },
    { c: "box", t: "│ ┌────────────────────────────────────────────────────────────────────┐ │", i: true },
    { c: "box", t: "│ │ #  Title                            Src     Group   Res   Size  S/L│ │", i: true },
    { c: "t-accent",t: "│ │ 1  [SubsPlease] Frieren 12 [1080] nyaa  SubsPl. 1080p 1.3G 312/12│ │", i: true },
    { c: "box", t: "│ │ 2  [ASW] Frieren - 12 1080p HEVC    nyaa  ASW    1080p 1.1G 188/7 │ │", i: true },
    { c: "box", t: "│ │ 3  [Erai-raws] Frieren - 12         erai  Erai…  1080p 1.2G 144/4 │ │", i: true },
    { c: "box", t: "│ └────────────────────────────────────────────────────────────────────┘ │", i: true },
    { c: "t-muted",t: "│ 89 results · NN quality 87%                                            │", i: true },
    { c: "t-pink", t: "└────────────────────────────────────────────────────────────────────────┘", i: true },
    { c: "t-muted",t: "  q quit  / search  d download  c copy  r re-search  Ctrl+L theme", i: true },
  ];

  // ---- API curl ----
  TERMINALS["t-api"] = [
    { c: "t-prompt", t: "$ ", i: true },
    { c: "t-cmd", t: 'curl -s "http://localhost:5000/api/search?q=Frieren&res=1080p" | jq .', d: 12 },
    { sleep: 300 },
    { c: "box", t: "{", i: true },
    { c: "box", t: '  "meta": {', i: true },
    { c: "box", t: '    "id": 154587,', i: true },
    { c: "t-str",t: '    "title": { "english": "Frieren: Beyond Journey\'s End",', i: true },
    { c: "t-str",t: '              "romaji":  "Sousou no Frieren" },', i: true },
    { c: "box", t: '    "averageScore": 91,', i: true },
    { c: "box", t: '    "episodes": 28', i: true },
    { c: "box", t: '  },', i: true },
    { c: "box", t: '  "variants": ["Frieren", "Sousou no Frieren", "葬送のフリーレン"],', i: true },
    { c: "box", t: '  "nn_quality": 0.87,', i: true },
    { c: "box", t: '  "fallback": false,', i: true },
    { c: "box", t: '  "results": [', i: true },
    { c: "box", t: '    {', i: true },
    { c: "t-str",t: '      "title": "[SubsPlease] Sousou no Frieren - 12 (1080p) [F00D].mkv",', i: true },
    { c: "box", t: '      "source": "nyaa", "group": "SubsPlease",', i: true },
    { c: "box", t: '      "seeders": 312, "leechers": 12, "size_bytes": 1395864371,', i: true },
    { c: "t-accent", t: '      "nn_score": 2.41, "nn_rank": 1,', i: true },
    { c: "box", t: '      "magnet": "magnet:?xt=urn:btih:…",', i: true },
    { c: "box", t: '      "torrent_url": "https://nyaa.si/download/1234567.torrent"', i: true },
    { c: "box", t: '    },', i: true },
    { c: "t-muted", t: '    /* … 199 more rows … */', i: true },
    { c: "box", t: '  ]', i: true },
    { c: "box", t: "}", i: true },
  ];

  // ---- One-liner ----
  TERMINALS["t-oneliner"] = [
    { c: "t-prompt", t: "$ ", i: true },
    { c: "t-cmd", t: 'anitorr ', i: true },
    { c: "t-flag",t: '-q ', i: true }, { c: "t-str", t: '"Frieren" ', d: 40 },
    { c: "t-flag",t: '-r ', i: true }, { c: "t-str", t: '1080 ', d: 40 },
    { c: "t-flag",t: '--auto', d: 40 },
    { sleep: 300 },
    { c: "t-muted", t: "→ NN-ranked top pick auto-selected", i: true },
    { c: "t-ok",    t: "→ Sent to qBittorrent", i: true },
    { c: "t-ok",    t: "→ Ranker learned", i: true },
    { sleep: 400 },
    { c: "t-prompt", t: "$ ", i: true },
    { c: "t-cmd", t: 'anitorr ', i: true },
    { c: "t-flag", t: '--module ', i: true }, { c: "t-str", t: 'season_pack ', d: 30 },
    { c: "t-flag", t: '--param ', i: true }, { c: "t-str", t: 'title="Vinland Saga" ', d: 25 },
    { c: "t-flag", t: '--param ', i: true }, { c: "t-str", t: 'season=2', d: 30 },
    { sleep: 250 },
    { c: "t-muted", t: "→ found 7 batches, smallest 8.4 GiB (Judas, 1080p, x265)", i: true },
  ];

  // ---- Module sample ----
  TERMINALS["t-module"] = [
    { c: "t-purple", t: "# modules/hello.module", i: true },
    { c: "t-cmd",    t: "name: hello", i: true },
    { c: "t-cmd",    t: "description: Say hi from a custom block", i: true },
    { c: "t-cmd",    t: "category: utility", i: true },
    { c: "t-cmd",    t: "params:", i: true },
    { c: "t-cmd",    t: "  - {name: who, type: string, default: world}", i: true },
    { c: "t-cmd",    t: "entry: hello.py", i: true },
    { c: "t-cmd",    t: "function: run", i: true },
    { c: "",         t: "" },
    { c: "t-purple", t: "# modules/hello.py", i: true },
    { c: "t-blue",   t: "def ", i: true }, { c: "t-cmd", t: "run(who=", i: true },
    { c: "t-str",    t: '"world"', i: true }, { c: "t-cmd", t: "):", i: true },
    { c: "t-cmd",    t: '    return f"Hello, {who}! — ANITorr module."', i: true },
    { c: "",         t: "" },
    { c: "t-prompt", t: "$ ", i: true },
    { c: "t-cmd", t: "anitorr --module hello --param who=Mikasa", d: 25 },
    { sleep: 200 },
    { c: "t-ok", t: "Hello, Mikasa! — ANITorr module.", i: true },
  ];

  // ---- Neural-network learning ----
  TERMINALS["t-nn"] = [
    { c: "t-muted", t: "─── ranker weights before training ───", i: true },
    { c: "box", t: "  seeders         1.000", i: true },
    { c: "box", t: "  resolution      1.200", i: true },
    { c: "box", t: "  group_trust     1.500", i: true },
    { c: "box", t: "  prompt_match    2.000", i: true },
    { c: "box", t: "  bias           -0.500", i: true },
    { c: "",    t: "" },
    { c: "t-accent", t: "User picks SubsPlease 1080p HEVC for 'Frieren' (positive sample)", i: true },
    { sleep: 250 },
    { c: "t-muted", t: "→ SGD step on 25 negative + 1 positive examples", i: true },
    { c: "",    t: "" },
    { c: "t-muted", t: "─── ranker weights after training ───", i: true },
    { c: "t-ok", t: "  seeders         1.024  ▲ 0.024", i: true },
    { c: "t-ok", t: "  resolution      1.246  ▲ 0.046", i: true },
    { c: "t-ok", t: "  group_trust     1.587  ▲ 0.087", i: true },
    { c: "t-ok", t: "  prompt_match    2.081  ▲ 0.081", i: true },
    { c: "t-ok", t: "  bias           -0.482  ▲ 0.018", i: true },
    { c: "",    t: "" },
    { c: "t-pink", t: "→ next search ranks SubsPlease 1080p HEVC higher automatically", i: true },
  ];

  // ---- Plugin ----
  TERMINALS["t-plugin"] = [
    { c: "t-purple", t: "# plugins/manga/mycustom.py — drop in to add a new source", i: true },
    { c: "t-blue", t: "from ", i: true }, { c: "t-cmd", t: "bs4 ", i: true },
    { c: "t-blue", t: "import ", i: true }, { c: "t-cmd", t: "BeautifulSoup", i: true },
    { c: "t-blue", t: "import ", i: true }, { c: "t-cmd", t: "requests", i: true },
    { c: "",       t: "" },
    { c: "t-blue", t: "def ", i: true }, { c: "t-cmd", t: "search(query):", i: true },
    { c: "t-cmd", t: "    r = requests.get(f\"https://my-source.example/?q={query}\")", i: true },
    { c: "t-cmd", t: "    s = BeautifulSoup(r.text, \"lxml\")", i: true },
    { c: "t-cmd", t: "    return [{...}]   # uniform shape", i: true },
    { c: "",       t: "" },
    { c: "t-blue", t: "def ", i: true }, { c: "t-cmd", t: "chapters(url): ...", i: true },
    { c: "t-blue", t: "def ", i: true }, { c: "t-cmd", t: "pages(chapter_url): ...", i: true },
    { c: "",       t: "" },
    { c: "t-prompt", t: "$ ", i: true }, { c: "t-cmd", t: "ls plugins/manga/", d: 30 },
    { c: "t-ok", t: "mycustom.py    # ← auto-loaded on next request, shows up in /manga", i: true },
  ];

  /* ----- Engine ----- */
  function runTerminal(id, script) {
    const term = document.getElementById(id);
    if (!term) return;
    const body = term.querySelector(".term-body");
    if (term.dataset.running === "1") return;
    term.dataset.running = "1";
    body.innerHTML = "";

    // current line accumulator
    let line = document.createElement("div");
    line.appendChild(document.createElement("span"));
    body.appendChild(line);

    let stepIdx = 0;
    const next = () => {
      if (stepIdx >= script.length) {
        term.dataset.running = "0";
        // blinking final cursor
        const cur = document.createElement("span"); cur.className = "cursor";
        body.lastChild.appendChild(cur);
        return;
      }
      const step = script[stepIdx++];

      if (step.clear) {
        body.innerHTML = "";
        line = document.createElement("div");
        line.appendChild(document.createElement("span"));
        body.appendChild(line);
        return next();
      }
      if (step.sleep != null) {
        setTimeout(next, step.sleep);
        return;
      }

      const span = document.createElement("span");
      if (step.c) span.className = step.c;
      line.appendChild(span);

      // newline rule:
      // - lines that start a new "line" simply create a new div if the previous
      //   line was already populated. We keep adding spans to the same line until
      //   we encounter the "i: true" closer or a typed text — actually simplest:
      //   each script step is its own logical line UNLESS it has no trailing newline.
      // We'll treat every step as: append text to current line, then if step.t
      // ends with "\n" don't newline, else newline after step.

      const text = step.t || "";
      if (step.i) {
        span.textContent += text;
        // If this step has explicit "\n" within text it stays; otherwise close line
        if (!shouldStayInline(step, script[stepIdx])) closeLine();
        setTimeout(next, 6);
      } else {
        // typed
        const delay = step.d || 32;
        let ci = 0;
        const tick = () => {
          if (ci < text.length) {
            span.textContent += text[ci++];
            // auto-scroll
            body.scrollTop = body.scrollHeight;
            setTimeout(tick, delay + Math.random() * 24);
          } else {
            if (!shouldStayInline(step, script[stepIdx])) closeLine();
            setTimeout(next, 80);
          }
        };
        tick();
      }
      body.scrollTop = body.scrollHeight;
    };

    function closeLine() {
      line = document.createElement("div");
      body.appendChild(line);
    }
    // Stay inline if next step is the continuation of the same line:
    //   prompt followed by command, etc. We detect by: a step with i:true AND
    //   the very next step exists AND we're inside a "prompt + cmd" pair.
    // Simpler heuristic: if the current step ends with text that doesn't naturally
    // close a line (e.g. ends with ": " or "$ "), AND the next exists, keep inline.
    function shouldStayInline(cur, nxt) {
      if (!nxt) return false;
      if (nxt.sleep != null || nxt.clear) return false;
      const t = cur.t || "";
      if (/[: ]$/.test(t)) return true;
      return false;
    }

    next();
  }

  // Build a stub <pre class="term-body"> for every .terminal[data-script]
  $$(".terminal[data-script]").forEach(t => {
    if (!t.querySelector(".term-body")) {
      const body = document.createElement("div");
      body.className = "term-body";
      t.appendChild(body);
    }
  });

  // Replay buttons
  $$(".terminal .replay").forEach(btn => {
    btn.addEventListener("click", () => {
      const t = btn.closest(".terminal");
      const id = t.id;
      t.dataset.running = "0";
      runTerminal(id, TERMINALS[id]);
    });
  });

  // Trigger when scrolled into view (once)
  const termIO = new IntersectionObserver(es => {
    es.forEach(e => {
      if (e.isIntersecting) {
        const id = e.target.id;
        if (TERMINALS[id] && e.target.dataset.played !== "1") {
          e.target.dataset.played = "1";
          runTerminal(id, TERMINALS[id]);
          termIO.unobserve(e.target);
        }
      }
    });
  }, { threshold: 0.25 });
  $$(".terminal[data-script]").forEach(t => termIO.observe(t));

  /* ============================================================
   * TOC active state
   * ============================================================ */
  const sections = $$("section[id]");
  const tocLinks = $$(".toc a");
  if (sections.length && tocLinks.length) {
    addEventListener("scroll", () => {
      let cur = null;
      for (const s of sections) {
        if (s.getBoundingClientRect().top < 140) cur = s.id;
      }
      tocLinks.forEach(a => a.classList.toggle("active", a.getAttribute("href") === "#" + cur));
    });
  }
})();
