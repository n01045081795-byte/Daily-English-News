import os
import json
import re
from datetime import datetime, timezone, timedelta

import requests
import feedparser

# ---------------------------
# Config
# ---------------------------
KST = timezone(timedelta(hours=9))
TODAY = datetime.now(KST).strftime("%Y-%m-%d")

DOCS_DIR = "docs"
DAYS_DIR = os.path.join(DOCS_DIR, "days")
ARCHIVE_FILE = os.path.join(DOCS_DIR, "archive.json")

SITE_TITLE = os.environ.get("SITE_TITLE", "Daily English News (Age 7)")

NEWS_RSS_URL = os.environ.get(
    "NEWS_RSS_URL",
    "https://news.google.com/rss/headlines/section/topic/SCIENCE?hl=en-US&gl=US&ceid=US:en",
)

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "").strip()
GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")
GEMINI_URL = (
    f"https://generativelanguage.googleapis.com/v1beta/models/"
    f"{GEMINI_MODEL}:generateContent?key={GEMINI_API_KEY}"
)

# ---------------------------
# Utils
# ---------------------------
def ensure_dirs():
    os.makedirs(DAYS_DIR, exist_ok=True)

def esc(s: str) -> str:
    return (
        s.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )

def fetch_headline():
    feed = feedparser.parse(NEWS_RSS_URL)
    if not getattr(feed, "entries", None):
        raise RuntimeError("RSS has no entries. Change NEWS_RSS_URL.")
    e = feed.entries[0]
    title = getattr(e, "title", "").strip()
    link = getattr(e, "link", "").strip()
    if not title or not link:
        raise RuntimeError("RSS entry missing title or link.")
    return title, link

def call_gemini(prompt: str) -> str:
    if not GEMINI_API_KEY:
        raise RuntimeError("Missing GEMINI_API_KEY. Set GitHub secret GEMINI_API_KEY.")

    payload = {
        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature": 0.6,
            "maxOutputTokens": 1800
        },
    }
    r = requests.post(
        GEMINI_URL,
        headers={"Content-Type": "application/json"},
        json=payload,
        timeout=120,
    )
    r.raise_for_status()
    data = r.json()

    cands = data.get("candidates", [])
    if not cands:
        raise RuntimeError(f"No candidates in Gemini response: {data}")

    parts = cands[0].get("content", {}).get("parts", [])
    text = "".join(p.get("text", "") for p in parts).strip()
    if not text:
        raise RuntimeError(f"Empty Gemini response: {data}")
    return text

# ---------------------------
# Parse sections (robust)
# ---------------------------
def parse_sections(raw: str) -> dict:
    # Try to extract labeled blocks. Very tolerant.
    def get_block(label: str):
        m = re.search(rf"^{re.escape(label)}\s*(.*?)(?=^\w|\Z)", raw, flags=re.S | re.M)
        return (m.group(1).strip() if m else "").strip()

    title = get_block("TITLE:")
    story = get_block("STORY:")
    words_raw = get_block("WORDS:")
    read_aloud = get_block("READ ALOUD:")
    quiz = get_block("QUIZ:")
    parent = get_block("PARENT NOTE (Korean):") or get_block("PARENT NOTE:")

    # Clean story if labels leaked inside
    story = re.sub(r"^TITLE:.*\n+", "", story, flags=re.M)
    story = re.sub(r"^STORY:\s*", "", story, flags=re.M).strip()

    # WORDS list
    word_items = []
    for line in words_raw.splitlines():
        ln = line.strip()
        if not ln:
            continue
        ln = re.sub(r"^[•\-\*]\s*", "", ln)
        ln = re.sub(r"^\d+[\.\)]\s*", "", ln)
        if " - " in ln:
            w, m = ln.split(" - ", 1)
        elif "-" in ln:
            w, m = ln.split("-", 1)
        else:
            w, m = ln, ""
        w, m = w.strip(), m.strip()
        if w:
            word_items.append((w, m))
    word_items = word_items[:5]

    # Fallbacks if model output is partial
    if not title:
        m = re.search(r"TITLE:\s*(.*)", raw)
        title = m.group(1).strip() if m else "Today’s English Fun"

    if not story:
        m = re.search(r"STORY:\s*(.*)", raw, flags=re.S)
        story = m.group(1).strip() if m else ""
        story = story.split("\nWORDS:")[0].strip()
        story = re.sub(r"^TITLE:.*\n+", "", story, flags=re.M)

    if not read_aloud and story:
        read_aloud = " / ".join(
            [s.strip() for s in re.split(r"(?<=[.!?])\s+", story) if s.strip()]
        )

    if not word_items and story:
        candidates = re.findall(r"\b[a-zA-Z]{3,8}\b", story.lower())
        stop = set([
            "this","that","with","have","your","from","they","them","very",
            "dont","don't","named","about","like","into","our","sky","its","it's"
        ])
        seen = []
        for w in candidates:
            if w in stop:
                continue
            if w not in seen:
                seen.append(w)
            if len(seen) >= 5:
                break
        word_items = [(w, "easy meaning") for w in seen]

    if not quiz:
        quiz = (
            "1) True/False: This story is happy.\n"
            "2) Multiple choice (A/B/C): What is in the story?\n"
            "A) A space rock\nB) A pizza\nC) A train\n"
            "3) Fill in the blank: Today is ____."
        )

    if not parent:
        parent = "오늘은 STORY 2번 읽기 + WORDS 5개만 확실히 익히면 충분합니다."

    return {
        "title": title,
        "story": story,
        "words": word_items,
        "read_aloud": read_aloud,
        "quiz": quiz,
        "parent": parent,
        "raw": raw,
    }

# ---------------------------
# HTML builders (uses docs/style.css)
# ---------------------------
def build_day_html(date_str: str, headline: str, link: str, s: dict) -> str:
    words_html = "".join(
        f"<div class='word'><b>{esc(w)}</b><span>{esc(m) if m else 'easy meaning'}</span></div>"
        for w, m in s["words"]
    )

    story_html = "<br/>".join(esc(s["story"]).splitlines()).strip()
    read_html = "<br/>".join(esc(s["read_aloud"]).splitlines()).strip()

    # Simple quiz render (readable for kids)
    quiz_lines = [ln.strip() for ln in s["quiz"].splitlines() if ln.strip()]
    quiz_html = "<br/>".join(esc(x) for x in quiz_lines)

    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover"/>
  <title>{esc(SITE_TITLE)} - {esc(date_str)}</title>
  <link rel="stylesheet" href="../style.css"/>
</head>
<body>
  <div class="header">
    <div class="wrap">
      <div class="row">
        <div class="brand">
          <h1>{esc(SITE_TITLE)}</h1>
          <div class="sub">Phone/Tablet friendly • Tap to read</div>
        </div>
        <div class="btns">
          <a class="btn primary" href="../today.html">Today</a>
          <a class="btn" href="../index.html">Archive</a>
        </div>
      </div>
    </div>
  </div>

  <main>
    <div class="card">
      <span class="pill">📅 {esc(date_str)}</span>
      <div style="height:10px"></div>
      <div class="small">Source headline: <a href="{esc(link)}" target="_blank" rel="noopener">{esc(headline)}</a></div>
      <div class="kid-title">{esc(s["title"])}</div>
      <div class="story">{story_html}</div>
    </div>

    <div class="grid">
      <div class="card">
        <div class="h2">WORDS (5)</div>
        <div class="words">{words_html}</div>
        <hr/>
        <div class="h2">READ ALOUD</div>
        <div class="readaloud">{read_html if read_html else "Read slowly and happily."}</div>
      </div>

      <div class="card">
        <div class="h2">QUIZ</div>
        <div class="quiz">
          <div class="q">
            <div class="small">{quiz_html}</div>
          </div>
        </div>
        <div style="height:12px"></div>
        <a class="btn" href="../index.html">📚 Back to Archive</a>
        <hr/>
        <div class="h2">PARENT NOTE (Korean)</div>
        <div class="small">{esc(s["parent"])}</div>
      </div>
    </div>
  </main>
</body>
</html>
"""

def load_archive():
    if os.path.exists(ARCHIVE_FILE):
        with open(ARCHIVE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return []

def save_archive(data):
    with open(ARCHIVE_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def build_index_html(archive):
    items = ""
    for a in archive[:200]:
        items += f"""
        <div class="card" style="padding:12px">
          <div class="small">{esc(a["date"])}</div>
          <div style="margin-top:6px;font-size:16px">
            <a href="{esc(a["file"])}"><b>{esc(a["title"])}</b></a>
          </div>
        </div>
        """

    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover"/>
  <title>{esc(SITE_TITLE)} - Archive</title>
  <link rel="stylesheet" href="style.css"/>
</head>
<body>
  <div class="header">
    <div class="wrap">
      <div class="row">
        <div class="brand">
          <h1>{esc(SITE_TITLE)}</h1>
          <div class="sub">Archive • Missed days are saved here</div>
        </div>
        <div class="btns">
          <a class="btn primary" href="today.html">Today</a>
        </div>
      </div>
    </div>
  </div>

  <main>
    <div class="card">
      <span class="pill">📚 Archive</span>
      <div style="height:8px"></div>
      <div class="small">A new worksheet is added every morning automatically.</div>
    </div>
    {items if items else "<div class='card'><div class='small'>No items yet.</div></div>"}
  </main>
</body>
</html>
"""

def write_today_redirect(latest_file: str):
    html = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover"/>
  <title>{esc(SITE_TITLE)} - Today</title>
  <link rel="stylesheet" href="style.css"/>
</head>
<body>
  <div class="header">
    <div class="wrap">
      <div class="row">
        <div class="brand">
          <h1>{esc(SITE_TITLE)}</h1>
          <div class="sub">Opening today’s page…</div>
        </div>
        <div class="btns">
          <a class="btn" href="index.html">Archive</a>
        </div>
      </div>
    </div>
  </div>
  <main>
    <div class="card">
      <div class="kid-title">Today</div>
      <div class="small">If it doesn’t open, tap the button.</div>
      <div style="height:12px"></div>
      <a class="btn primary" href="{esc(latest_file)}">Open Today’s Page</a>
    </div>
  </main>
  <script>location.href="{latest_file}";</script>
</body>
</html>
"""
    with open(os.path.join(DOCS_DIR, "today.html"), "w", encoding="utf-8") as f:
        f.write(html)

# ---------------------------
# Main
# ---------------------------
def main():
    ensure_dirs()

    headline, link = fetch_headline()
    raw = call_gemini(
        f"""Create an ORIGINAL daily English mini-news worksheet for a 7-year-old beginner.

Use ONLY this headline as inspiration (DO NOT copy article text):
- {headline} ({link})

Safety: avoid violence, war, crime, disasters, explicit medical details. Keep it warm and positive.
Language: A1. Short sentences. Kid-friendly.

Output EXACTLY in this order with these headings:
TITLE:
STORY: (4~6 short sentences)
WORDS: (5 items, format "word - very easy meaning")
READ ALOUD: (repeat STORY but add " / " for natural pauses)
QUIZ:
1) True/False:
2) Multiple choice (A/B/C):
3) Fill in the blank:
PARENT NOTE (Korean): (1~2 lines)
"""
    )

    s = parse_sections(raw)

    # Write day page
    filename = f"days/{TODAY}.html"
    with open(os.path.join(DOCS_DIR, filename), "w", encoding="utf-8") as f:
        f.write(build_day_html(TODAY, headline, link, s))

    # Update archive (store kid title, not raw headline)
    archive = load_archive()
    archive = [a for a in archive if a.get("date") != TODAY]
    archive.insert(0, {"date": TODAY, "file": filename, "title": s["title"]})
    save_archive(archive)

    # Write index + today redirect
    with open(os.path.join(DOCS_DIR, "index.html"), "w", encoding="utf-8") as f:
        f.write(build_index_html(archive))
    write_today_redirect(archive[0]["file"])

if __name__ == "__main__":
    main()
