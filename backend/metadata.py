"""AniList + MAL metadata + title normalization."""
import requests, re, json
from typing import Dict, List

ANILIST = "https://graphql.anilist.co"
JIKAN = "https://api.jikan.moe/v4"

ANILIST_Q = """
query ($search: String) {
  Media(search: $search, type: ANIME) {
    id idMal
    title { romaji english native }
    synonyms episodes status format season seasonYear
    averageScore popularity
    coverImage { large color }
    bannerImage
    description(asHtml:false)
    genres
    studios(isMain:true){ nodes { name } }
  }
}
"""

def anilist_lookup(query: str) -> Dict | None:
    try:
        r = requests.post(ANILIST, json={"query": ANILIST_Q, "variables": {"search": query}}, timeout=12)
        d = r.json().get("data", {}).get("Media")
        return d
    except Exception:
        return None

def mal_lookup(query: str) -> Dict | None:
    try:
        r = requests.get(f"{JIKAN}/anime", params={"q": query, "limit": 1}, timeout=12)
        arr = r.json().get("data") or []
        return arr[0] if arr else None
    except Exception:
        return None

def autocomplete(query: str) -> List[str]:
    try:
        r = requests.get(f"{JIKAN}/anime", params={"q": query, "limit": 8}, timeout=10)
        return [a["title"] for a in r.json().get("data", [])]
    except Exception:
        return []

def title_variants(query: str, meta: Dict | None = None) -> List[str]:
    out = {query}
    if meta:
        t = meta.get("title") or {}
        for k in ("romaji", "english", "native"):
            v = t.get(k)
            if v: out.add(v)
        for s in meta.get("synonyms", []) or []:
            out.add(s)
    # normalize punctuation
    norm = []
    for v in out:
        norm.append(v)
        norm.append(re.sub(r"[^\w\s]", " ", v))
        norm.append(re.sub(r"\s+", " ", v).strip())
    return [x for x in dict.fromkeys(norm) if x]

def ai_normalize(query: str, ai_cfg: Dict) -> List[str]:
    """Optional Ollama / OpenAI-compatible normalization. Best-effort, never raises."""
    if not ai_cfg.get("use_for_title_normalization"): return []
    prompt = (f"List up to 6 alternative search strings for the anime '{query}'. "
              "Include romaji, english, native JP, common abbreviations. "
              "Return one per line, no numbering, no commentary.")
    try:
        if ai_cfg.get("openai_api_key") and ai_cfg.get("openai_compatible_url"):
            r = requests.post(
                ai_cfg["openai_compatible_url"].rstrip("/") + "/chat/completions",
                headers={"Authorization": f"Bearer {ai_cfg['openai_api_key']}"},
                json={"model": ai_cfg.get("openai_model","gpt-4o-mini"),
                      "messages":[{"role":"user","content":prompt}], "temperature":0.2},
                timeout=20)
            txt = r.json()["choices"][0]["message"]["content"]
        elif ai_cfg.get("ollama_url"):
            r = requests.post(ai_cfg["ollama_url"].rstrip("/") + "/api/generate",
                json={"model": ai_cfg.get("ollama_model","llama3"),
                      "prompt": prompt, "stream": False}, timeout=30)
            txt = r.json().get("response","")
        else:
            return []
        return [l.strip("-• ").strip() for l in txt.splitlines() if l.strip()][:6]
    except Exception:
        return []
