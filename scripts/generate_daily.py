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
        "generationConfig": {"temperature": 0.5, "maxOutputTokens": 2200},
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

def extract_json(text: str) -> dict:
    """
    Gemini sometimes wraps JSON in ```json ... ``` or adds text.
    We'll pull the first {...} block that parses.
    """
    # Try fenced block first
    m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, flags=re.S)
    if m:
        return json.loads(m.group(1))

    # Otherwise, find first { ... } that parses
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        candidate = text[start : end + 1]
        return json.loads(candidate)

    raise RuntimeError("Could not extract JSON from Gemini response.")

# ---------------------------
# Build prompt (JSON output)
# ---------------------------
def build_prompt(headline: str, link: str) -> str:
    return f"""
You create an ORIGINAL daily English worksheet for a 7-year-old beginner.
Use ONLY the headline as inspiration. DO NOT copy any article text.
Headline: "{headline}"
Link: {link}

Safety: avoid violence, war, crime, disasters, scary topics, explicit medical details.
Tone: warm, positive, kid-friendly.

Level: very easy (A1). STORY must be exactly 3~4 short sentences.
Use simple words. No long or difficult words.

Return ONLY valid JSON with this exact schema:

{{
  "kid_title": "short fun title",
  "story_sentences": ["sentence 1", "sentence 2", "sentence 3", "sentence 4 (optional)"],
  "words": [
    {{"en":"word1","ko":"한국어뜻","easy_en":"very easy meaning"}},
    {{"en":"word2","ko":"한국어뜻","easy_en":"very easy meaning"}},
    {{"en":"word3","ko":"한국어뜻","easy_en":"very easy meaning"}},
    {{"en":"word4","ko":"한국어뜻","easy_en":"very easy meaning"}},
    {{"en":"word5","ko":"한국어뜻","easy_en":"very easy meaning"}}
  ],
  "quiz": {{
    "tf": {{
      "q": "True/False question",
      "answer": true
    }},
    "mcq": {{
      "q": "Multiple choice question",
      "choices": ["A ...", "B ...", "C ..."],
      "answer_index": 0
    }},
    "fill": {{
      "q": "Fill in the blank question with ____",
      "answer": "the missing word"
    }}
  }},
  "parent_note_ko": "Korean note 1~2 lines"
}}

Rules:
- story_sentences length 3 or 4.
- words must be 5 items.
- mcq choices must be 3 items.
- answer_index is 0 for A, 1 for B, 2 for C.
- Keep everything very easy.
"""

# ---------------------------
# HTML builders (+TTS)
# ---------------------------
def build_day_html(date_str: str, headline: str, link: str, data: dict) -> str:
    kid_title = str(data.get("kid_title", "Today’s English Fun")).strip()

    sents = data.get("story_sentences", [])
    if not isinstance(sents, list):
        sents = []
    sents = [str(x).strip() for x in sents if str(x).strip()]
    if len(sents) < 3:
        # fallback: make 3 lines from title
        sents = [f"{kid_title}.", "It is a happy story.", "Let’s read together!"]

    # WORDS cards
    words = data.get("words", [])
    if not isinstance(words, list):
        words = []
    words = words[:5]
    word_cards = ""
    for w in words:
        en = esc(str(w.get("en", "")).strip())
        ko = esc(str(w.get("ko", "")).strip())
        easy_en = esc(str(w.get("easy_en", "")).strip())
        if not en:
            continue
        word_cards += f"""
        <div class="word">
          <div class="wrow">
            <div>
              <b>{en}</b>
              <div class="ko">{ko}</div>
              <div class="en">{easy_en}</div>
            </div>
            <button class="btn small speak" data-say="{en}">🔊</button>
          </div>
        </div>
        """

    # Read aloud text with pauses
    read_aloud = " / ".join(sents)

    quiz = data.get("quiz", {}) if isinstance(data.get("quiz", {}), dict) else {}
    tf = quiz.get("tf", {}) if isinstance(quiz.get("tf", {}), dict) else {}
    mcq = quiz.get("mcq", {}) if isinstance(quiz.get("mcq", {}), dict) else {}
    fill = quiz.get("fill", {}) if isinstance(quiz.get("fill", {}), dict) else {}

    tf_q = esc(str(tf.get("q", "True or False: This story is happy.")).strip())
    tf_ans = bool(tf.get("answer", True))

    mcq_q = esc(str(mcq.get("q", "Choose one: What is in the story?")).strip())
    mcq_choices = mcq.get("choices", ["A A space rock", "B A pizza", "C A train"])
    if not isinstance(mcq_choices, list) or len(mcq_choices) != 3:
        mcq_choices = ["A A space rock", "B A pizza", "C A train"]
    mcq_choices = [esc(str(x)) for x in mcq_choices]
    mcq_ans = mcq.get("answer_index", 0)
    try:
        mcq_ans = int(mcq_ans)
    except:
        mcq_ans = 0
    if mcq_ans not in (0, 1, 2):
        mcq_ans = 0

    fill_q = esc(str(fill.get("q", "Fill in the blank: Today is ____.")).strip())
    fill_ans = esc(str(fill.get("answer", "fun")).strip())

    parent_note = esc(str(data.get("parent_note_ko", "오늘은 STORY를 2번 읽고, WORDS 5개만 익히면 충분합니다.")).strip())

    # Story lines with speak buttons
    story_lines_html = ""
    for i, s in enumerate(sents, start=1):
        ss = esc(s)
        story_lines_html += f"""
        <div class="storyline">
          <div class="text"><b>{i}.</b> {ss}</div>
          <button class="btn small speak" data-say="{ss}">🔊</button>
        </div>
        """

    # Full page TTS targets
    full_story_say = esc(" ".join(sents))
    read_aloud_say = esc(read_aloud)

    # Embed answers for JS
    tf_ans_js = "true" if tf_ans else "false"

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
          <div class="sub">Tap 🔊 to listen • Kids can do it alone</div>
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

      <div class="kid-title">{esc(kid_title)}</div>

      <div class="btns" style="margin:10px 0 4px">
        <button class="btn primary speak" data-say="{full_story_say}">🔊 Story (All)</button>
        <button class="btn speak" data-say="{read_aloud_say}">🔊 Read Aloud</button>
        <button class="btn warn" id="stopBtn">⏹ Stop</button>
      </div>

      <div class="story">
        {story_lines_html}
      </div>
    </div>

    <div class="grid">
      <div class="card">
        <div class="h2">WORDS (단어 5개)</div>
        <div class="words">
          {word_cards if word_cards else "<div class='small'>Words are coming soon.</div>"}
        </div>
        <hr/>
        <div class="h2">READ ALOUD (따라 읽기)</div>
        <div class="readaloud">{esc(read_aloud)}</div>
      </div>

      <div class="card">
        <div class="h2">QUIZ (버튼으로 풀기)</div>

        <div class="quiz">

          <!-- TF -->
          <div class="q" id="q_tf">
            <div class="qtitle">1) True / False</div>
            <div class="small">{tf_q}</div>
            <div class="choice" style="margin-top:10px">
              <button class="opt" data-q="tf" data-ans="true">✅ True</button>
              <button class="opt" data-q="tf" data-ans="false">❌ False</button>
            </div>
            <div class="answerline">Answer: <b>{"True" if tf_ans else "False"}</b></div>
          </div>

          <!-- MCQ -->
          <div class="q" id="q_mcq">
            <div class="qtitle">2) Multiple Choice</div>
            <div class="small">{mcq_q}</div>
            <div class="choice" style="margin-top:10px">
              <button class="opt" data-q="mcq" data-idx="0">{mcq_choices[0]}</button>
              <button class="opt" data-q="mcq" data-idx="1">{mcq_choices[1]}</button>
              <button class="opt" data-q="mcq" data-idx="2">{mcq_choices[2]}</button>
            </div>
            <div class="answerline">Answer: <b>{"A" if mcq_ans==0 else "B" if mcq_ans==1 else "C"}</b></div>
          </div>

          <!-- FILL -->
          <div class="q" id="q_fill">
            <div class="qtitle">3) Fill in the Blank</div>
            <div class="small">{fill_q}</div>
            <div class="choice" style="margin-top:10px">
              <input id="fillInput" class="opt" style="text-align:left; font-weight:700; cursor:text; flex:1 1 100%" placeholder="Type one word…" />
              <button class="opt" id="fillCheck">Check</button>
            </div>
            <div class="answerline">Answer: <b>{fill_ans}</b></div>
          </div>

        </div>

        <div style="height:12px"></div>
        <div class="btns">
          <button class="btn ok" id="showAnswers">✅ Show Answers</button>
          <button class="btn" id="resetQuiz">🔄 Reset</button>
        </div>

        <hr/>
        <div class="h2">PARENT NOTE (Korean)</div>
        <div class="small">{parent_note}</div>
      </div>
    </div>

    <script>
      // -------------------------
      // Text-to-Speech (Web Speech API)
      // -------------------------
      const synth = window.speechSynthesis;

      function pickVoice() {{
        const voices = synth.getVoices();
        // Prefer English voices
        const en = voices.find(v => /en/i.test(v.lang));
        return en || voices[0];
      }}

      function speak(text) {{
        if (!text) return;
        try {{
          synth.cancel();
          const u = new SpeechSynthesisUtterance(text);
          const v = pickVoice();
          if (v) u.voice = v;
          u.lang = (v && v.lang) ? v.lang : "en-US";
          u.rate = 0.92;   // slightly slower for kids
          u.pitch = 1.05;
          synth.speak(u);
        }} catch (e) {{
          alert("TTS is not available on this device/browser.");
        }}
      }}

      // Some browsers load voices async
      window.speechSynthesis.onvoiceschanged = () => {{}};

      document.querySelectorAll(".speak").forEach(btn => {{
        btn.addEventListener("click", () => {{
          speak(btn.getAttribute("data-say"));
        }});
      }});

      document.getElementById("stopBtn").addEventListener("click", () => synth.cancel());

      // -------------------------
      // Quiz logic
      // -------------------------
      const TF_ANSWER = {tf_ans_js};
      const MCQ_ANSWER_INDEX = {mcq_ans};
      const FILL_ANSWER = "{fill_ans}".toLowerCase();

      function revealAll() {{
        document.querySelectorAll(".q").forEach(q => q.classList.add("revealed"));
      }}

      function resetAll() {{
        synth.cancel();
        document.querySelectorAll(".opt").forEach(b => b.classList.remove("correct","wrong"));
        document.querySelectorAll(".q").forEach(q => q.classList.remove("revealed"));
        const inp = document.getElementById("fillInput");
        if (inp) inp.value = "";
      }}

      document.getElementById("showAnswers").addEventListener("click", revealAll);
      document.getElementById("resetQuiz").addEventListener("click", resetAll);

      // TF buttons
      document.querySelectorAll("[data-q='tf']").forEach(btn => {{
        btn.addEventListener("click", () => {{
          const chosen = (btn.getAttribute("data-ans") === "true");
          btn.classList.remove("correct","wrong");
          if (chosen === TF_ANSWER) {{
            btn.classList.add("correct");
          }} else {{
            btn.classList.add("wrong");
          }}
        }});
      }});

      // MCQ buttons
      document.querySelectorAll("[data-q='mcq']").forEach(btn => {{
        btn.addEventListener("click", () => {{
          const idx = parseInt(btn.getAttribute("data-idx"), 10);
          if (idx === MCQ_ANSWER_INDEX) {{
            btn.classList.add("correct");
            btn.classList.remove("wrong");
          }} else {{
            btn.classList.add("wrong");
            btn.classList.remove("correct");
          }}
        }});
      }});

      // Fill check
      document.getElementById("fillCheck").addEventListener("click", () => {{
        const inp = document.getElementById("fillInput");
        const val = (inp.value || "").trim().toLowerCase();
        const btn = document.getElementById("fillCheck");
        if (!val) return;
        if (val === FILL_ANSWER) {{
          btn.classList.add("correct");
          btn.classList.remove("wrong");
        }} else {{
          btn.classList.add("wrong");
          btn.classList.remove("correct");
        }}
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

# ---------------------------
# Main
# ---------------------------
def main():
    ensure_dirs()

    headline, link = fetch_headline()
    raw = call_gemini(build_prompt(headline, link))

    data = extract_json(raw)

    # Basic sanity
    kid_title = str(data.get("kid_title", "Today’s English Fun")).strip()
    data["kid_title"] = kid_title or "Today’s English Fun"

    # Write day page
    filename = f"days/{TODAY}.html"
    with open(os.path.join(DOCS_DIR, filename), "w", encoding="utf-8") as f:
        f.write(build_day_html(TODAY, headline, link, data))

    # Update archive (kid title)
    archive = load_archive()
    archive = [a for a in archive if a.get("date") != TODAY]
    archive.insert(0, {"date": TODAY, "file": filename, "title": data["kid_title"]})
    save_archive(archive)

    # Write index + today redirect
    with open(os.path.join(DOCS_DIR, "index.html"), "w", encoding="utf-8") as f:
        f.write(build_index_html(archive))
    write_today_redirect(archive[0]["file"])

if __name__ == "__main__":
    main()
