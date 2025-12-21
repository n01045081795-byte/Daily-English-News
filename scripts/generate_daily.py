# scripts/generate_daily.py
import os
import json
import hashlib
from datetime import datetime, timezone, timedelta

import requests
import feedparser

KST = timezone(timedelta(hours=9))
TODAY = datetime.now(KST).strftime("%Y-%m-%d")

REPO_ROOT = os.path.dirname(os.path.dirname(__file__))
DOCS_DIR = os.path.join(REPO_ROOT, "docs")
DAYS_DIR = os.path.join(DOCS_DIR, "days")
ARCHIVE_JSON = os.path.join(DOCS_DIR, "archive.json")

SITE_TITLE = os.environ.get("SITE_TITLE", "Daily English News (Age 7)")
MAX_DAYS_SHOW = int(os.environ.get("MAX_DAYS_SHOW", "200"))

# Default: science topic (safe-ish). You can change later via Actions env.
NEWS_RSS_URL = os.environ.get(
    "NEWS_RSS_URL",
    "https://news.google.com/rss/headlines/section/topic/SCIENCE?hl=en-US&gl=US&ceid=US:en",
)

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "").strip()
GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")
GEMINI_ENDPOINT = (
    f"https://generativelanguage.googleapis.com/v1beta/models/"
    f"{GEMINI_MODEL}:generateContent?key={GEMINI_API_KEY}"
)


def ensure_dirs():
    os.makedirs(DOCS_DIR, exist_ok=True)
    os.makedirs(DAYS_DIR, exist_ok=True)


def fetch_rss_items(url: str, limit: int = 1):
    feed = feedparser.parse(url)
    items = []
    for e in feed.entries[:limit]:
        title = getattr(e, "title", "").strip()
        link = getattr(e, "link", "").strip()
        published = getattr(e, "published", "") or getattr(e, "updated", "")
        if title and link:
            items.append({"title": title, "link": link, "published": published})
    return items


def sha12(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()[:12]


def gemini_generate(prompt: str) -> str:
    if not GEMINI_API_KEY:
        raise RuntimeError("GEMINI_API_KEY is missing (GitHub Secrets).")

    payload = {
        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": 0.7, "maxOutputTokens": 1000},
    }
    r = requests.post(
        GEMINI_ENDPOINT,
        headers={"Content-Type": "application/json"},
        json=payload,
        timeout=60,
    )
    r.raise_for_status()
    data = r.json()
    cands = data.get("candidates", [])
    if not cands:
        raise RuntimeError(f"No candidates: {data}")
    parts = cands[0].get("content", {}).get("parts", [])
    text = "".join(p.get("text", "") for p in parts).strip()
    if not text:
        raise RuntimeError(f"Empty text: {data}")
    return text


def esc(s: str) -> str:
    return (
        s.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


CSS = """
:root{
  --bg:#0b0c10;
  --card:#11131a;
  --text:#f5f7ff;
  --muted:#b7c0ff;
  --soft:#202336;
  --accent:#7aa2ff;
  --accent2:#89f7fe;
}
*{box-sizing:border-box}
body{
  margin:0; font-family: system-ui, -apple-system, Segoe UI, Roboto, Arial, "Apple SD Gothic Neo", "Noto Sans KR", sans-serif;
  background: linear-gradient(180deg, #070812, #0b0c10 40%, #0b0c10);
  color:var(--text);
}
header{
  position:sticky; top:0; z-index:10;
  background: rgba(11,12,16,.78);
  backdrop-filter: blur(10px);
  border-bottom: 1px solid rgba(255,255,255,.06);
}
.wrap{max-width:980px; margin:0 auto; padding:16px}
.hrow{display:flex; gap:10px; align-items:center; justify-content:space-between; flex-wrap:wrap}
h1{margin:0; font-size:18px; letter-spacing:.2px}
.small{font-size:12px; color:rgba(245,247,255,.75)}
main{max-width:980px; margin:0 auto; padding:16px 16px 70px}
.card{
  background: linear-gradient(180deg, rgba(255,255,255,.06), rgba(255,255,255,.03));
  border:1px solid rgba(255,255,255,.08);
  border-radius:16px;
  padding:16px;
  box-shadow: 0 10px 30px rgba(0,0,0,.35);
  margin:14px 0;
}
.grid{
  display:grid;
  grid-template-columns: 1fr;
  gap:12px;
}
@media (min-width: 820px){
  .grid{grid-template-columns: 1.2fr .8fr}
}
.badge{
  display:inline-flex; align-items:center; gap:6px;
  padding:6px 10px;
  border-radius:999px;
  background: rgba(122,162,255,.14);
  border: 1px solid rgba(122,162,255,.28);
  color: var(--text);
  font-size: 12px;
}
.btnrow{display:flex; gap:10px; flex-wrap:wrap}
a.btn{
  display:inline-flex; align-items:center; justify-content:center;
  padding:12px 14px; border-radius:14px;
  background: rgba(255,255,255,.06);
  border: 1px solid rgba(255,255,255,.10);
  color: var(--text);
  text-decoration:none;
  min-height:44px;
}
a.btn:active{transform: translateY(1px)}
a{color: #b9d0ff}
a:hover{text-decoration:underline}
.kid{
  font-size: clamp(18px, 2.2vw, 22px);
  line-height: 1.55;
}
.section-title{
  margin: 0 0 10px;
  font-size: 14px;
  color: rgba(245,247,255,.85);
  letter-spacing: .3px;
}
.muted{color: rgba(245,247,255,.72); font-size: 13px}
hr{border:0; height:1px; background: rgba(255,255,255,.08); margin: 14px 0}
.list{display:flex; flex-direction:column; gap:10px}
.item{
  display:flex; gap:10px; align-items:flex-start; justify-content:space-between;
  background: rgba(255,255,255,.04);
  border:1px solid rgba(255,255,255,.07);
  border-radius:14px;
  padding:12px;
}
.item .left{min-width:0}
.item .date{font-size:12px; color: rgba(245,247,255,.70)}
.item .head{font-size:14px; margin-top:2px; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; max-width: 70vw}
@media (min-width: 820px){ .item .head{max-width: 520px} }
.pill{
  display:inline-block; padding:4px 10px; border-radius:999px;
  background: rgba(137,247,254,.10);
  border: 1px solid rgba(137,247,254,.22);
  font-size:12px;
}
pre{
  margin:0;
  white-space:pre-wrap;
  word-break:break-word;
  font-family: inherit;
}
"""

def page_html(title: str, body: str) -> str:
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover"/>
<title>{esc(title)}</title>
<style>{CSS}</style>
</head>
<body>
<header>
  <div class="wrap">
    <div class="hrow">
      <div>
        <h1>{esc(SITE_TITLE)}</h1>
        <div class="small">Age 7 • Daily • Phone/Tablet friendly</div>
      </div>
      <div class="btnrow">
        <a class="btn" href="/Daily-English-News/today.html">Today</a>
        <a class="btn" href="/Daily-English-News/index.html">Archive</a>
      </div>
    </div>
  </div>
</header>
<main>
{body}
</main>
</body>
</html>"""


def build_prompt(items):
    lines = "\n".join([f"- {it['title']} ({it['link']})" for it in items])
    return f"""You create an ORIGINAL daily English mini-news worksheet for a 7-year-old beginner.

Use ONLY these headlines as inspiration (DO NOT copy any article text; do not quote; do not reproduce copyrighted paragraphs):
{lines}

Safety: avoid violence, disasters, crime, war, explicit medical details. Keep it warm and positive.

Write in very easy English (A1). Short sentences. Kid-friendly.

Output EXACTLY in this order with these headings:
TITLE:
STORY: (4~6 sentences)
WORDS: (5 items, format "word - very easy meaning")
READ ALOUD: (repeat STORY but add " / " for natural pauses)
QUIZ:
1) True/False:
2) Multiple choice (A/B/C):
3) Fill in the blank:
PARENT NOTE (Korean): (1~2 lines)
"""


def daily_body(date_str: str, items, text: str) -> str:
    source_html = "".join(
        f'<div class="muted">Source headline: <a href="{esc(it["link"])}" target="_blank" rel="noopener">{esc(it["title"])}</a></div>'
        for it in items
    )
    safe_text = esc(text)
    return f"""
<div class="card">
  <div class="badge">📅 {esc(date_str)}</div>
  <div style="height:10px"></div>
  {source_html}
</div>

<div class="grid">
  <div class="card">
    <div class="section-title">Today’s Worksheet</div>
    <div class="kid"><pre>{safe_text}</pre></div>
  </div>

  <div class="card">
    <div class="section-title">How to use (Parent)</div>
    <div class="muted">
      1) Read STORY aloud once.<br/>
      2) Read again with READ ALOUD (slashes).<br/>
      3) Do QUIZ (3 questions).<br/>
      4) Review WORDS (5 words).
    </div>
    <hr/>
    <a class="btn" href="/Daily-English-News/index.html">📚 Open Archive</a>
  </div>
</div>
"""


def load_archive():
    if os.path.exists(ARCHIVE_JSON):
        with open(ARCHIVE_JSON, "r", encoding="utf-8") as f:
            return json.load(f)
    return []


def save_archive(archive):
    with open(ARCHIVE_JSON, "w", encoding="utf-8") as f:
        json.dump(archive, f, ensure_ascii=False, indent=2)


def upsert_archive(date_str: str, file_path: str, headline: str, source_link: str):
    archive = load_archive_
