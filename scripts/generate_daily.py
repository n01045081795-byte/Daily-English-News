import os
import json
import re
from datetime import datetime, timezone, timedelta

import requests
import feedparser

KST = timezone(timedelta(hours=9))
TODAY = datetime.now(KST).strftime("%Y-%m-%d")

DOCS_DIR = "docs"
DAYS_DIR = os.path.join(DOCS_DIR, "days")
ARCHIVE_FILE = os.path.join(DOCS_DIR, "archive.json")

RSS_URL = os.environ.get(
    "NEWS_RSS_URL",
    "https://news.google.com/rss/headlines/section/topic/SCIENCE?hl=en-US&gl=US&ceid=US:en",
)

SITE_TITLE = os.environ.get("SITE_TITLE", "Daily English News (Age 7)")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "").strip()
GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")
GEMINI_URL = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent?key={GEMINI_API_KEY}"


def ensure_dirs():
    os.makedirs(DAYS_DIR, exist_ok=True)


def esc(s: str) -> str:
    return (
        s.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def fetch_news():
    feed = feedparser.parse(RSS_URL)
    if not feed.entries:
        raise RuntimeError("RSS has no entries. Try different NEWS_RSS_URL.")
    return feed.entries[0]


def gemini_generate(headline: str, link: str) -> str:
    if not GEMINI_API_KEY:
        raise RuntimeError("Missing GEMINI_API_KEY in Actions Secrets.")

    prompt = f"""You create an ORIGINAL daily English mini-news worksheet for a 7-year-old beginner.

Use ONLY this headline as inspiration (DO NOT copy article text; do not quote; do not paste paragraphs):
- {headline} ({link})

Safety: avoid violence, war, crime, disasters, explicit medical details. Keep it warm and positive.
Language: A1 level. Short sentences. Kid-friendly.

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

    payload = {
        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": 0.7, "maxOutputTokens": 900},
    }

    r = requests.post(GEMINI_URL, json=payload, timeout=60)
    r.raise_for_status()
    data = r.json()
    cands = data.get("candidates", [])
    parts = cands[0].get("content", {}).get("parts", []) if cands else []
    text = "".join(p.get("text", "") for p in parts).strip()
    if not text:
        raise RuntimeError(f"Empty Gemini response: {data}")
    return text


def parse_sections(text: str):
    # Very forgiving parsing
    def grab(label, default=""):
        m = re.search(rf"^{label}\s*(.*?)(?=^\w|\Z)", text, flags=re.S | re.M)
        return (m.group(1).strip() if m else default).strip()

    title = grab("TITLE:")
    story = grab("STORY:")
    words = grab("WORDS:")
    read_aloud = grab("READ ALOUD:")
    quiz = grab("QUIZ:")
    parent = grab("PARENT NOTE \\(Korean\\):") or grab("PARENT NOTE:")

    word_items = []
    for line in words.splitlines():
        line = line.strip(" -•\t")
        if not line:
            continue
        # accept "1. word - meaning" etc
        line = re.sub(r"^\d+\.\s*", "", line)
        if " - " in line:
            w, m = line.split(" - ", 1)
        elif "-" in line:
            w, m = line.split("-", 1)
        else:
            w, m = line, ""
        word_items.append((w.strip(), m.strip()))
    word_items = word_items[:5]

    return {
        "title": title,
        "story": story,
        "words": word_items,
        "read_aloud": read_aloud,
        "quiz": quiz,
        "parent": parent,
        "raw": text,
    }


def build_daily_html(date_str: str, headline: str, link: str, s):
    # Create simple interactive quiz (show answers button)
    # We'll keep quiz text, but render choices nicely if possible for MCQ.
    raw_quiz = s["quiz"].strip()
    parent = s["parent"].strip()

    story_html = "<br/>".join(esc(s["story"]).splitlines()).strip() or esc(s["raw"])
    read_html = "<br/>".join(esc(s["read_aloud"]).splitlines()).strip()

    words_html = ""
    for w, m in s["words"]:
        words_html += f"""
        <div class="word">
          <b>{esc(w)}</b>
          <span>{esc(m) if m else "easy meaning"}</span>
        </div>
        """

    quiz_html = ""
    if raw_quiz:
        # Split by lines and create blocks.
        lines = [ln.strip() for ln in raw_quiz.splitlines() if ln.strip()]
        blocks = []
        cur = []
        for ln in lines:
            if re.match(r"^\d+\)", ln) or re.match(r"^\d+\.", ln):
                if cur:
                    blocks.append(cur)
                cur = [ln]
            else:
                cur.append(ln)
        if cur:
            blocks.append(cur)

        if not blocks:
            blocks = [lines]

        for i, b in enumerate(blocks[:3], start=1):
            qtext = b[0]
            rest = b[1:]
            # Try to detect A/B/C lines
            choices = []
            for ln in rest:
                m = re.match(r"^[A-Ca-c][\)\.\:]\s*(.*)$", ln)
                if m:
                    choices.append(m.group(1).strip())
            if choices:
                choice_html = ""
                for ci, c in enumerate(choices, start=1):
                    letter = ["A", "B", "C"][ci - 1]
                    choice_html += f"""
                    <label>
                      <input type="radio" name="q{i}" />
                      <span>{letter}. {esc(c)}</span>
                    </label>
                    """
                quiz_html += f"""
                <div class="q" id="q{i}">
                  <div class="qtitle">{esc(qtext)}</div>
                  <div class="choice">{choice_html}</div>
                  <div class="answer">Answer is in the text above 👆</div>
                </div>
                """
            else:
                quiz_html += f"""
                <div class="q" id="q{i}">
                  <div class="qtitle">{esc(qtext)}</div>
                  <div class="small">{esc(" ".join(rest))}</div>
                  <div class="answer">Answer is in the story 👆</div>
                </div>
                """
    else:
        quiz_html = f"<div class='muted'>{esc(s['raw'])}</div>"

    base = ""  # relative links work best in GitHub Pages
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover"/>
  <title>{esc(SITE_TITLE)} - {esc(date_str)}</title>
  <link rel="stylesheet" href="{base}../style.css"/>
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
          <a class="btn primary" href="{base}../today.html">Today</a>
          <a class="btn" href="{base}../index.html">Archive</a>
        </div>
      </div>
    </div>
  </div>

  <main>
    <div class="card">
      <span class="pill">📅 {esc(date_str)}</span>
      <div style="height:10px"></div>
      <div class="small">Source headline: <a href="{esc(link)}" target="_blank" rel="noopener">{esc(headline)}</a></div>
      <div class="kid-title">{esc(s["title"]) if s["title"] else "Today’s Kid News"}</div>
      <div class="story">{story_html}</div>
    </div>

    <div class="grid">
      <div class="card">
        <div class="h2">WORDS (5)</div>
        <div class="words">{words_html}</div>
        <hr/>
        <div class="h2">READ ALOUD</div>
        <div class="readaloud">{read_html if read_html else "Read the story slowly and happily."}</div>
      </div>

      <div class="card">
        <div class="h2">QUIZ</div>
        <div class="quiz">{quiz_html}</div>
        <div style="height:12px"></div>
        <a class="btn" href="{base}../index.html">📚 Back to Archive</a>
        <hr/>
        <div class="h2">PARENT NOTE (Korean)</div>
        <div class="small">{esc(parent) if parent else "오늘은 STORY를 2번 읽고, WORDS 5개만 확실히 익히면 충분합니다."}</div>
      </div>
    </div>

    <script>
      // Optional: tap a quiz block to show answer hint
      document.querySelectorAll('.q').forEach(q => {{
        q.addEventListener('click', () => q.classList.toggle('show-answer'));
      }});
    </script>
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


def main():
    ensure_dirs()

    item = fetch_news()
    generated = gemini_generate(item.title, item.link)
    sections = parse_sections(generated)

    filename = f"days/{TODAY}.html"
    html = build_daily_html(TODAY, item.title, item.link, sections)

    with open(os.path.join(DOCS_DIR, filename), "w", encoding="utf-8") as f:
        f.write(html)

    archive = load_archive()
    archive = [a for a in archive if a.get("date") != TODAY]
    archive.insert(0, {"date": TODAY, "file": filename, "title": item.title})
    save_archive(archive)

    with open(os.path.join(DOCS_DIR, "index.html"), "w", encoding="utf-8") as f:
        f.write(build_index_html(archive))

    write_today_redirect(archive[0]["file"])


if __name__ == "__main__":
    main()
