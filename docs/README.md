# ANITorr — docs site

This directory is the GitHub Pages source. Enable Pages with `/docs` as the source
(or push the contents of this folder to a `gh-pages` branch) and the site is live.

```
docs/
├── index.html         # full landing page with 14 sections
├── assets/
│   ├── docs.css       # dark + light themes, pastel accents, square corners
│   └── docs.js        # theme toggle, particles, scroll-triggered terminals
```

## What's animated

The docs include **11 live terminal previews** that animate when scrolled into view:

| Terminal id        | What it shows |
|--------------------|---------------|
| `t-install`        | git clone → pip install → flask run |
| `t-cli-modepick`   | Pastel ANIME / MANGA / SETTINGS panel picker |
| `t-cli-anime`      | Full anime search → results table → file picker → qBit send |
| `t-cli-manga`      | Manga search → series → chapters → EPUB export with progress bar |
| `t-cli-settings`   | Interactive settings table editor |
| `t-tui`            | Mock TUI screenshot with cursor + tabs |
| `t-oneliner`       | `anitorr -q … --auto` non-interactive mode |
| `t-api`            | `curl /api/search` with full JSON response |
| `t-nn`             | Ranker weights before/after a training step |
| `t-module`         | `.module` YAML + paired `.py` |
| `t-plugin`         | `plugins/manga/<name>.py` template |

Each terminal has:
- A real macOS-style header with replay button
- Scrolling text output, color-coded by Rich-equivalent themes
- IntersectionObserver triggers playback only once you scroll to it
- Click "replay" to re-run any animation

## Themes

- `[data-theme="light"]` — pastel cream/pink, square corners, dot-matrix bg
- `[data-theme="dark"]` (default) — same shapes, dark palette, pink accents
- Persisted in `localStorage` as `anitorr-theme`
- Respects `prefers-color-scheme` on first visit

## What's documented

14 numbered sections, in order:

1. Intro hero with copy-to-clipboard install command
2. **All 60+ features** grouped by colored pastel badges
3. Install (3 cards + Docker alt)
4. CLI overview with mode picker animation
5. Anime flow with relevance gate + NN fallback explainers
6. Manga flow with EPUB metadata details + 13-source table
7. Settings flow
8. TUI with key bindings table
9. One-liner mode with full flag reference (15 flags)
10. HTTP API — **49 endpoints documented**
11. Neural net — model + training loop + live animation
12. `.module` field reference
13. `plugins/manga` shape
14. Function reference — every public Python function from backend.sources,
    backend.neural, backend.metadata, backend.clients, backend.manga_sources,
    backend.manga_dl, backend.interpreter, backend.notify
15. `config.json` reference — every key with default + description

A floating TOC sidebar appears on screens ≥ 1500 px wide with auto-active links.

## No external resources

No web fonts, no CDN, no Google icons. Everything inline:
- SVG icons hand-written in HTML
- Pink square favicon as inline `currentColor`
- Pastel colors as CSS custom properties
- Particles drawn to a `<canvas>` from a fixed palette
