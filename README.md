# ANITorr

> Cool, fast, plugin-driven anime torrent finder & downloader.
> Flask web dashboard + colored CLI + Node CORS proxy + neural-network ranking + qBittorrent integration.

```
   _   _   _ ___ _____             
  /_\ | \ | |_ _|_   _|___ _ _ _ _ 
 / _ \|  \| || |  | |/ _ \ '_| '_|
/_/ \_\_|\_|___| |_|\___/_| |_|  
```

---

## Features (all 30+ implemented as toggleable plugins)

### High Priority
- Watch history & favorites
- Auto-download new episodes via RSS
- qBittorrent / Deluge / Transmission client integration
- AniList + MAL metadata fetcher
- Smart title autocomplete

### Search Intelligence
- AI title normalization (synonyms, romaji, English, native JP)
- Fansub group trust / ranking database
- Duplicate detection for consistent group selection across episodes
- 10+ torrent sources aggregated (Nyaa, AniDex, TokyoTosho, Anirena, Subsplease, Erai-raws, AnimeTosho, RuTracker, BakaBT, ShanaProject)
- 10+ DDL fallback APIs (Animepahe, Gogoanime, 9anime, Zoro, Animixplay, Animekisa, Kissanime, Twist, MarinMoe, AllAnime)
- Streaming availability fallback notices

### CLI
- One-liner flag mode (`anitorr -q "Frieren" --res 1080 --lang en`)
- Full TUI mode (Textual)
- Multiple color themes (`--theme dracula|nord|pastel|mono`)
- Pyfiglet banners + Rich progress bars + colored tables

### Web UI
- Live SSE streaming search results
- PWA / installable
- Client-side filter, sort, side-by-side compare
- Anime info sidebar with cover art, score, episode count
- Theme switcher in settings

### Backend
- Flask + Beautiful Soup
- Search result caching (TTL)
- Rate limiting w/ proxy rotation
- Node.js CORS proxy → real nyaa.si links
- Docker support
- Test suite (pytest)
- Multi-threaded source fan-out

### Media & Playback
- Direct stream via mpv/webtorrent
- Codec/audio/source tag parser (x265/x264/AV1, FLAC/AAC, BD/WEB/TV)
- Batch episode downloading
- File-level selection inside a torrent

### i18n
- Native JP title search
- Multi-language UI (EN / JP / ES / FR / DE)

### Stats & Health
- Personal stats dashboard
- Color-coded seeder health + ETA

### Integrations
- Discord Rich Presence
- Discord webhook notifications
- Browser extension (right-click search)
- Push via ntfy.sh / Telegram / email

### Privacy & Safety
- Cross-source torrent verification
- VPN disconnect detection

### Quick Wins
- One-click magnet copy
- Shareable URLs
- Bulk selection
- "Did you mean?" suggestions
- Star torrents
- Re-search
- Size filter slider
- "Seen before" indicators
- Auto dark mode
- Vim keybindings
- JSON / CSV export

### Plugin / Module System
- `.module` files describe custom CLI blocks (Scratch-style metadata)
- `interpreter.py` parses them and dispatches to paired Python files
- Drop a `.module` + `module.py` in `/modules/` — instant new command

### Neural Network Ranking
- Trains continuously on every user selection
- Caches training data to `data/nn_cache.json`
- Re-ranks future results by similarity to past picks
- Parameters: size/resolution ratio, fansub group trust, prompt fit, seeders, codec, audio, batch vs episode

---

## Quick start

```bash
git clone https://github.com/you/anitorr
cd anitorr
pip install -r requirements.txt
cd cors_proxy && npm i && cd ..
python backend/app.py                 # web dashboard → http://localhost:5000
python cli/anitorr_cli.py             # interactive CLI
python cli/anitorr_cli.py -q "Spy x Family" --res 1080 --lang en --auto
```

## CLI syntax

```
anitorr [QUERY] [options]

  -q, --query TEXT          Anime title
  -r, --res {480,720,1080,2160}
  -l, --lang {en,jp,es,fr,multi}
  -s, --source nyaa|anidex|tosho|all
  -g, --group TEXT          Preferred fansub group
  -b, --batch               Prefer batch releases
  -a, --auto                Auto-pick top NN-ranked result
  -t, --theme dracula|nord|pastel|mono
      --tui                 Launch Textual TUI
      --export json|csv
      --client qbit|deluge|transmission|file|magnet
      --module NAME [args]  Run a .module command
```

## .module file syntax

A `.module` file is a YAML-style block. Each one is paired with a `*.py` file.

```yaml
# modules/hello.module
name: hello
description: Say hi from a custom block
category: utility
params:
  - name: who
    type: string
    default: world
entry: hello.py
function: run
```

```python
# modules/hello.py
def run(who="world"):
    return f"Hello, {who}!"
```

Run with `anitorr --module hello --who Frieren`.

See `docs/` for the full feature & syntax reference (GitHub Pages site).
