import os
import json
from datetime import datetime, timezone, timedelta
import requests
import feedparser

KST = timezone(timedelta(hours=9))
TODAY = datetime.now(KST).strftime("%Y-%m-%d")

DOCS_DIR = "docs"
DAYS_DIR = os.path.join(DOCS_DIR, "days")
ARCHIVE_FILE = os.path.join(DOCS_DIR, "archive.json")

RSS_URL = "https://news.google.com/rss/headlines/section/topic/SCIENCE?hl=en-US&gl=US&ceid=US:en"

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
GEMINI_URL = (
    "https://generativelanguage.googleapis.com/v1beta/"
    "models/gemini-2.5-flash:generateContent"
)

def ensure_dirs():
    os.makedirs(DAYS_DIR, exist_ok=True)

def fetch_news():
    feed = feedparser.parse(RSS_URL)
    return feed.entries[0]

def generate_kid_news(title, link):
    prompt = f"""
Create an original English worksheet for a 7-year-old child.

Topic hint (do NOT copy):
{title}

Format exactly:
TITLE:
STORY: (4 short sentences)
WORDS: (5 easy words)
QUIZ: (3 very easy questions)
PARENT NOTE (Korean):
"""
    res = requests.post(
        f"{GEMINI_URL}?key={GEMINI_API_KEY}",
        json={"contents":[{"parts":[{"text":prompt}]}]},
        timeout=60
    )
    return res.json()["candidates"][0]["content"]["parts"][0]["text"]

def load_archive():
    if os.path.exists(ARCHIVE_FILE):
        with open(ARCHIVE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return []

def save_archive(data):
    with open(ARCHIVE_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def main():
    ensure_dirs()
    item = fetch_news()
    content = generate_kid_news(item.title, item.link)

    filename = f"days/{TODAY}.html"
    with open(os.path.join(DOCS_DIR, filename), "w", encoding="utf-8") as f:
        f.write(f"<html><body><pre>{content}</pre></body></html>")

    archive = load_archive()
    archive.insert(0, {"date": TODAY, "file": filename, "title": item.title})
    save_archive(archive)

    with open(os.path.join(DOCS_DIR, "index.html"), "w", encoding="utf-8") as f:
        for a in archive:
            f.write(f"<a href='{a['file']}'>{a['date']} - {a['title']}</a><br>")

if __name__ == "__main__":
    main()
