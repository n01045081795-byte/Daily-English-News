import os
import json
import re
import urllib.parse
from datetime import datetime, timezone, timedelta
from string import Template

import requests
import feedparser

# ---------------------------
# Time
# ---------------------------
KST = timezone(timedelta(hours=9))
TODAY = datetime.now(KST).strftime("%Y-%m-%d")

# ---------------------------
# Paths
# ---------------------------
DOCS_DIR = "docs"
DAYS_DIR = os.path.join(DOCS_DIR, "days")
ARCHIVE_FILE = os.path.join(DOCS_DIR, "archive.json")
os.makedirs(DAYS_DIR, exist_ok=True)

# ---------------------------
# Site / RSS
# ---------------------------
SITE_TITLE = os.environ.get("SITE_TITLE", "Daily English News (Age 7)")
NEWS_RSS_URL = os.environ.get(
    "NEWS_RSS_URL",
    "https://news.google.com/rss/headlines/section/topic/SCIENCE?hl=en-US&gl=US&ceid=US:en",
)

# ---------------------------
# Gemini
# ---------------------------
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "").strip()
GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")
GEMINI_URL = (
    f"https://generativelanguage.googleapis.com/v1beta/models/"
    f"{GEMINI_MODEL}:generateContent?key={GEMINI_API_KEY}"
)

# ---------------------------
# TTS
# ---------------------------
TTS_RATE = 0.77  # slower

# ---------------------------
# Helpers
# ---------------------------
def esc(s: str) -> str:
    return (
        str(s)
        .replace("&", "&amp;")
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

def load_archive():
    if os.path.exists(ARCHIVE_FILE):
        with open(ARCHIVE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return []

def save_archive(data):
    with open(ARCHIVE_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def image_sources(date_str: str, topic: str):
    # 1) reliable
    seed = urllib.parse.quote(f"{date_str}-{(topic or 'kids')}".strip()[:60])
    picsum = f"https://picsum.photos/seed/{seed}/1200/750"
    # 2) sometimes blocked
    q = urllib.parse.quote((topic or "kids").strip()[:60])
    unsplash = f"https://source.unsplash.com/featured/1200x750/?{q},kids,illustration,pastel"
    # 3) safe placeholder
    placehold = "https://placehold.co/1200x750/png?text=Daily+English+News"
    return [picsum, unsplash, placehold]

def inline_svg_placeholder(title: str):
    t = esc(title)[:40]
    svg = f"""
<svg viewBox="0 0 800 500" xmlns="http://www.w3.org/2000/svg" role="img" aria-label="kids illustration">
  <defs>
    <linearGradient id="g" x1="0" x2="1" y1="0" y2="1">
      <stop offset="0" stop-color="#dbeafe"/>
      <stop offset="1" stop-color="#fce7f3"/>
    </linearGradient>
  </defs>
  <rect width="800" height="500" fill="url(#g)"/>
  <circle cx="150" cy="120" r="70" fill="#fff" opacity=".7"/>
  <circle cx="690" cy="110" r="55" fill="#fff" opacity=".6"/>
  <circle cx="640" cy="380" r="90" fill="#fff" opacity=".45"/>
  <text x="60" y="280" font-size="52" font-family="system-ui, sans-serif" font-weight="800" fill="#1f2a44">✨</text>
  <text x="120" y="285" font-size="34" font-family="system-ui, sans-serif" font-weight="900" fill="#1f2a44">{t}</text>
  <text x="120" y="330" font-size="22" font-family="system-ui, sans-serif" font-weight="700" fill="#334155">A cute picture will show here.</text>
</svg>
""".strip()
    # Escape backticks for JS template literal
    return svg.replace("`", "\\`")

# ---------------------------
# Gemini robust JSON
# ---------------------------
def call_gemini_text(prompt: str) -> str:
    if not GEMINI_API_KEY:
        raise RuntimeError("Missing GEMINI_API_KEY. Set GitHub secret GEMINI_API_KEY.")

    payload = {
        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": 0.4, "maxOutputTokens": 1800},
    }
    r = requests.post(GEMINI_URL, json=payload, timeout=120)
    r.raise_for_status()
    data = r.json()
    cands = data.get("candidates", [])
    if not cands:
        return ""
    parts = cands[0].get("content", {}).get("parts", [])
    text = "".join(p.get("text", "") for p in parts).strip()
    return text

def extract_json_block(text: str) -> str:
    m = re.search(r"\{.*\}", text, flags=re.S)
    return m.group(0) if m else ""

def repair_json(s: str) -> str:
    if not s:
        return s
    s = s.replace("“", '"').replace("”", '"').replace("’", "'").replace("‘", "'")
    s = re.sub(r",\s*([}\]])", r"\1", s)
    return s

def safe_json_loads(text: str) -> dict:
    # direct
    try:
        return json.loads(text)
    except Exception:
        pass
    block = extract_json_block(text)
    if not block:
        return {}
    try:
        return json.loads(block)
    except Exception:
        pass
    block2 = repair_json(block)
    try:
        return json.loads(block2)
    except Exception:
        return {}

def default_payload(headline: str) -> dict:
    return {
        "title": "Today’s English Fun!",
        "image_topic": "happy kids",
        "story": [
            "Today we read a small news story.",
            "It is simple and fun.",
            "We learn five easy words.",
            "Great job!"
        ],
        "words": [
            {"word": "today", "ko": "오늘", "en": "this day"},
            {"word": "news", "ko": "뉴스", "en": "a new story"},
            {"word": "read", "ko": "읽다", "en": "look at words"},
            {"word": "learn", "ko": "배우다", "en": "get new knowledge"},
            {"word": "happy", "ko": "행복한", "en": "feeling good"},
        ],
        "read_aloud": " / ".join([
            "Today we read a small news story.",
            "It is simple and fun.",
            "We learn five easy words.",
            "Great job!"
        ]),
        "quiz": {
            "tf": {"q": "True or False: This story is happy.", "answer": True},
            "mcq": {"q": "Choose one: What do we do today?", "choices": {"A": "Read", "B": "Sleep", "C": "Swim"}, "answer": "A"},
            "pic": {"q": "Pick the best picture!", "choices": {"A": "📖", "B": "🍕", "C": "🚂"}, "answer": "A"},
        },
        "parent_note_ko": "오늘은 STORY 2번 읽기 + WORDS 5개만 확실히 익히면 충분합니다.",
        "_debug": {"headline": headline}
    }

def normalize_payload(j: dict, headline: str) -> dict:
    if not isinstance(j, dict):
        j = {}
    out = default_payload(headline)

    if isinstance(j.get("title"), str) and j["title"].strip():
        out["title"] = j["title"].strip()
    if isinstance(j.get("image_topic"), str) and j["image_topic"].strip():
        out["image_topic"] = j["image_topic"].strip()
    if isinstance(j.get("parent_note_ko"), str) and j["parent_note_ko"].strip():
        out["parent_note_ko"] = j["parent_note_ko"].strip()

    story = j.get("story")
    if isinstance(story, list):
        clean = [str(x).strip() for x in story if str(x).strip()]
        if clean:
            out["story"] = clean[:4]

    words = j.get("words")
    if isinstance(words, list):
        cleaned = []
        for w in words:
            if isinstance(w, dict):
                ww = str(w.get("word", "")).strip()
                if not ww:
                    continue
                cleaned.append({
                    "word": ww,
                    "ko": str(w.get("ko", "")).strip(),
                    "en": str(w.get("en", "")).strip()
                })
        if cleaned:
            out["words"] = cleaned[:5]

    ra = j.get("read_aloud")
    if isinstance(ra, str) and ra.strip():
        out["read_aloud"] = ra.strip()
    else:
        out["read_aloud"] = " / ".join(out["story"])

    quiz = j.get("quiz")
    if isinstance(quiz, dict):
        tf = quiz.get("tf")
        if isinstance(tf, dict) and isinstance(tf.get("q"), str):
            out["quiz"]["tf"]["q"] = tf["q"].strip() or out["quiz"]["tf"]["q"]
        if isinstance(tf, dict) and isinstance(tf.get("answer"), bool):
            out["quiz"]["tf"]["answer"] = tf["answer"]

        mcq = quiz.get("mcq")
        if isinstance(mcq, dict) and isinstance(mcq.get("q"), str):
            out["quiz"]["mcq"]["q"] = mcq["q"].strip() or out["quiz"]["mcq"]["q"]
        if isinstance(mcq, dict) and isinstance(mcq.get("choices"), dict):
            ch = mcq["choices"]
            out["quiz"]["mcq"]["choices"]["A"] = str(ch.get("A", out["quiz"]["mcq"]["choices"]["A"])).strip()
            out["quiz"]["mcq"]["choices"]["B"] = str(ch.get("B", out["quiz"]["mcq"]["choices"]["B"])).strip()
            out["quiz"]["mcq"]["choices"]["C"] = str(ch.get("C", out["quiz"]["mcq"]["choices"]["C"])).strip()
        if isinstance(mcq, dict) and isinstance(mcq.get("answer"), str):
            ans = mcq["answer"].strip().upper()
            if ans in ("A", "B", "C"):
                out["quiz"]["mcq"]["answer"] = ans

        pic = quiz.get("pic")
        if isinstance(pic, dict) and isinstance(pic.get("q"), str):
            out["quiz"]["pic"]["q"] = pic["q"].strip() or out["quiz"]["pic"]["q"]
        if isinstance(pic, dict) and isinstance(pic.get("choices"), dict):
            ch = pic["choices"]
            out["quiz"]["pic"]["choices"]["A"] = str(ch.get("A", out["quiz"]["pic"]["choices"]["A"])).strip()
            out["quiz"]["pic"]["choices"]["B"] = str(ch.get("B", out["quiz"]["pic"]["choices"]["B"])).strip()
            out["quiz"]["pic"]["choices"]["C"] = str(ch.get("C", out["quiz"]["pic"]["choices"]["C"])).strip()
        if isinstance(pic, dict) and isinstance(pic.get("answer"), str):
            ans = pic["answer"].strip().upper()
            if ans in ("A", "B", "C"):
                out["quiz"]["pic"]["answer"] = ans

    return out

# ---------------------------
# index / today
# ---------------------------
def build_index_html(archive):
    items = ""
    for a in archive[:250]:
        date = a.get("date", "")
        file = a.get("file", "")
        title = a.get("title", "")
        items += f"""
        <div class="card" style="padding:14px" data-date="{esc(date)}">
          <div class="archive-card">
            <div>
              <div class="small">{esc(date)}</div>
              <div class="archive-title"><a href="{esc(file)}"><b>{esc(title)}</b></a></div>
            </div>
            <div class="badge-done" style="display:none">🏁 DONE</div>
          </div>
        </div>
        """

    script = """
    <script>
      function refreshDoneBadges(){
        document.querySelectorAll('[data-date]').forEach(card=>{
          const date = card.getAttribute('data-date');
          const done = localStorage.getItem('den_done_' + date) === '1';
          const badge = card.querySelector('.badge-done');
          if (badge) badge.style.display = done ? 'inline-flex' : 'none';
        });
      }
      refreshDoneBadges();
      window.addEventListener('focus', refreshDoneBadges);
    </script>
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
          <div class="sub">Tap a day • DONE days show a badge</div>
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
      <div style="height:10px"></div>
      <div class="small">완료(달성)는 이 기기(태블릿/폰)에 저장됩니다.</div>
    </div>

    {items if items else "<div class='card'><div class='small'>No items yet.</div></div>"}
    {script}
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
      <a class="btn primary" href="{esc(latest_file)}">Open Today</a>
    </div>
  </main>

  <script>location.href="{latest_file}";</script>
</body>
</html>
"""
    with open(os.path.join(DOCS_DIR, "today.html"), "w", encoding="utf-8") as f:
        f.write(html)

# ---------------------------
# Day HTML (Template to avoid f-string JS issues)
# ---------------------------
DAY_TEMPLATE = Template(r"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover"/>
  <title>${site_title} - ${date}</title>
  <link rel="stylesheet" href="../style.css"/>
</head>
<body>
  <div class="header">
    <div class="wrap">
      <div class="row">
        <div class="brand">
          <h1>${site_title}</h1>
          <div class="sub">Kids mode • Big text • Tap to learn</div>
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
      <span class="pill">📅 ${date}</span>
      <span class="badge-done" id="doneBadge" style="display:none; margin-left:10px">🏁 DONE</span>

      <div style="height:10px"></div>
      <div class="small">Parent source: <a href="${source_link}" target="_blank" rel="noopener">${headline}</a></div>

      <div class="hero" style="margin-top:12px">
        <div>
          <div class="kid-title">${kid_title}</div>
          <div class="story" id="storyText">${story_html}</div>

          <div class="btns" style="margin-top:12px">
            <button class="btn primary" id="btnSpeakStory">🔊 느리게 읽어주기</button>
            <button class="btn" id="btnSpeakRead">🔊 더 천천히</button>
            <button class="btn" id="btnStop">⏹️ 멈춤</button>
            <button class="btn good" id="btnDone">🏁 달성 버튼</button>
          </div>

          <div class="btns" style="margin-top:10px">
            ${sentence_buttons}
          </div>
          <div class="small" style="margin-top:6px">문장 버튼을 누르면 1문장씩 읽어줍니다.</div>
        </div>

        <div class="heroimg" id="heroBox">
          <img id="heroImg" alt="kid illustration" src="" loading="lazy"/>
        </div>
      </div>
    </div>

    <div class="grid">
      <div class="card">
        <div class="h2">WORDS (5)</div>
        <div class="words">${word_cards}</div>
        <hr/>
        <div class="h2">READ ALOUD</div>
        <div class="readaloud" id="readText">${read_aloud}</div>
      </div>

      <div class="card">
        <div class="h2">QUIZ (Tap!)</div>

        <div class="quiz">
          <div class="q">
            <div class="qtitle">1) ${tf_q}</div>
            <div class="choice" id="grp_tf">
              <button data-q="tf" data-a="true">✅ True</button>
              <button data-q="tf" data-a="false">❌ False</button>
            </div>
            <div class="feedback" id="fb_tf"></div>
          </div>

          <div class="q">
            <div class="qtitle">2) ${mcq_q}</div>
            <div class="choice" id="grp_mcq">
              <button data-q="mcq" data-a="A">A) ${mcq_a}</button>
              <button data-q="mcq" data-a="B">B) ${mcq_b}</button>
              <button data-q="mcq" data-a="C">C) ${mcq_c}</button>
            </div>
            <div class="feedback" id="fb_mcq"></div>
          </div>

          <div class="q">
            <div class="qtitle">3) ${pic_q}</div>
            <div class="choice" id="grp_pic">
              <button data-q="pic" data-a="A">${pic_a}</button>
              <button data-q="pic" data-a="B">${pic_b}</button>
              <button data-q="pic" data-a="C">${pic_c}</button>
            </div>
            <div class="feedback" id="fb_pic"></div>
            <div class="small" style="margin-top:8px">Pick the best emoji 👆</div>
          </div>
        </div>

        <hr/>
        <div class="h2">PARENT NOTE (Korean)</div>
        <div class="small">${parent_note}</div>

        <div style="height:12px"></div>
        <a class="btn" href="../index.html">📚 Back to Archive</a>
      </div>
    </div>

<script>
  const RATE = ${tts_rate};
  const DATE = "${date}";
  const DONE_KEY = "den_done_" + DATE;

  // --- Image loader ---
  const IMG_SRCS = ${img_srcs};
  const imgEl = document.getElementById('heroImg');
  let imgIdx = 0;

  function tryNextImg() {
    if (!imgEl) return;
    if (imgIdx >= IMG_SRCS.length) {
      const box = document.getElementById('heroBox');
      if (box) {
        box.innerHTML = `${svg_placeholder}`;
      }
      return;
    }
    imgEl.src = IMG_SRCS[imgIdx++];
  }

  if (imgEl) {
    imgEl.addEventListener('error', () => tryNextImg());
    tryNextImg();
  }

  // --- TTS ---
  function speakText(text) {
    if (!('speechSynthesis' in window)) {
      alert('This device does not support text-to-speech.');
      return;
    }
    window.speechSynthesis.cancel();
    const u = new SpeechSynthesisUtterance(text);
    u.rate = RATE;
    u.pitch = 1.0;
    u.lang = 'en-US';
    window.speechSynthesis.speak(u);
  }

  function getPlainText(id) {
    const el = document.getElementById(id);
    return el ? el.innerText.replace(/\s+/g,' ').trim() : '';
  }

  document.getElementById('btnSpeakStory')?.addEventListener('click', () => {
    speakText(getPlainText('storyText'));
  });

  document.getElementById('btnSpeakRead')?.addEventListener('click', () => {
    speakText(getPlainText('readText').replace(/\s*\/\s*/g, '. '));
  });

  document.getElementById('btnStop')?.addEventListener('click', () => {
    window.speechSynthesis.cancel();
  });

  document.querySelectorAll('[data-say]').forEach(btn => {
    btn.addEventListener('click', () => {
      const t = btn.getAttribute('data-say') || '';
      speakText(t);
    });
  });

  // --- DONE toggle ---
  function updateDoneUI() {
    const done = localStorage.getItem(DONE_KEY) === '1';
    const badge = document.getElementById('doneBadge');
    const btn = document.getElementById('btnDone');
    if (badge) badge.style.display = done ? 'inline-flex' : 'none';
    if (btn) btn.textContent = done ? '✅ 달성 완료!' : '🏁 달성 버튼';
    if (btn) btn.classList.toggle('good', done);
  }

  document.getElementById('btnDone')?.addEventListener('click', () => {
    const done = localStorage.getItem(DONE_KEY) === '1';
    if (done) {
      localStorage.removeItem(DONE_KEY);
      alert('달성 해제 ✅');
    } else {
      localStorage.setItem(DONE_KEY, '1');
      alert('달성! 🎉');
    }
    updateDoneUI();
  });

  updateDoneUI();

  // --- Quiz: wrong -> try again (no reveal, no lock) ---
  function setFeedback(id, ok, msg) {
    const el = document.getElementById(id);
    if (!el) return;
    el.classList.add('show');
    el.classList.toggle('ok', ok);
    el.classList.toggle('no', !ok);
    el.textContent = msg;
  }

  function lockButtons(groupEl) {
    groupEl.querySelectorAll('button').forEach(b => b.disabled = true);
  }

  function clearMarks(groupEl) {
    groupEl.querySelectorAll('button').forEach(b => {
      b.classList.remove('correct');
      b.classList.remove('wrong');
    });
  }

  const TF_ANS = ${tf_ans};
  const MCQ_ANS = "${mcq_ans}";
  const PIC_ANS = "${pic_ans}";

  document.querySelectorAll('[data-q="tf"]').forEach(btn => {
    btn.addEventListener('click', () => {
      const group = document.getElementById('grp_tf');
      clearMarks(group);
      const pick = btn.getAttribute('data-a') === 'true';
      const correct = (pick === TF_ANS);
      if (correct) {
        btn.classList.add('correct');
        lockButtons(group);
        setFeedback('fb_tf', true, '✅ Great!');
      } else {
        btn.classList.add('wrong');
        setFeedback('fb_tf', false, '❌ Try again!');
      }
    });
  });

  document.querySelectorAll('[data-q="mcq"]').forEach(btn => {
    btn.addEventListener('click', () => {
      const group = document.getElementById('grp_mcq');
      clearMarks(group);
      const pick = btn.getAttribute('data-a');
      const correct = (pick === MCQ_ANS);
      if (correct) {
        btn.classList.add('correct');
        lockButtons(group);
        setFeedback('fb_mcq', true, '✅ Nice!');
      } else {
        btn.classList.add('wrong');
        setFeedback('fb_mcq', false, '❌ Try again!');
      }
    });
  });

  document.querySelectorAll('[data-q="pic"]').forEach(btn => {
    btn.addEventListener('click', () => {
      const group = document.getElementById('grp_pic');
      clearMarks(group);
      const pick = btn.getAttribute('data-a');
      const correct = (pick === PIC_ANS);
      if (correct) {
        btn.classList.add('correct');
        lockButtons(group);
        setFeedback('fb_pic', true, '✅ Yay!');
      } else {
        btn.classList.add('wrong');
        setFeedback('fb_pic', false, '❌ Try again!');
      }
    });
  });
</script>

  </main>
</body>
</html>
""")

def build_day_html(date_str: str, headline: str, link: str, j: dict) -> str:
    title = j["title"]
    story_lines = j["story"][:4]
    words = j["words"][:5]

    # story html + sentence buttons
    story_html = "<br/>".join(esc(x) for x in story_lines)
    sentence_buttons = ""
    for i, s in enumerate(story_lines, start=1):
        sentence_buttons += f"""<button class="btn small" data-say="{esc(s)}">🔊 {i}문장</button>"""

    # words cards
    word_cards = ""
    for w in words:
        ww = w.get("word", "")
        ko = w.get("ko", "")
        en = w.get("en", "")
        meaning = " · ".join([x for x in [ko, en] if x]) or "easy meaning"
        word_cards += f"""<div class="word"><b>{esc(ww)}</b><span>{esc(meaning)}</span></div>"""

    img_srcs = json.dumps(image_sources(date_str, j.get("image_topic", title)))
    svg_ph = inline_svg_placeholder(title)

    # quiz
    tf_q = esc(j["quiz"]["tf"]["q"])
    tf_ans = "true" if bool(j["quiz"]["tf"]["answer"]) else "false"

    mcq_q = esc(j["quiz"]["mcq"]["q"])
    mcq_choices = j["quiz"]["mcq"]["choices"]
    mcq_a = esc(mcq_choices.get("A", "A"))
    mcq_b = esc(mcq_choices.get("B", "B"))
    mcq_c = esc(mcq_choices.get("C", "C"))
    mcq_ans = esc(j["quiz"]["mcq"]["answer"])

    pic_q = esc(j["quiz"]["pic"]["q"])
    pic_choices = j["quiz"]["pic"]["choices"]
    pic_a = esc(pic_choices.get("A", "⭐"))
    pic_b = esc(pic_choices.get("B", "🍕"))
    pic_c = esc(pic_choices.get("C", "🚂"))
    pic_ans = esc(j["quiz"]["pic"]["answer"])

    html = DAY_TEMPLATE.safe_substitute(
        site_title=esc(SITE_TITLE),
        date=esc(date_str),
        source_link=esc(link),
        headline=esc(headline),
        kid_title=esc(title),
        story_html=story_html,
        sentence_buttons=sentence_buttons,
        word_cards=word_cards,
        read_aloud=esc(j["read_aloud"]),
        parent_note=esc(j["parent_note_ko"]),
        tts_rate=str(TTS_RATE),
        img_srcs=img_srcs,
        svg_placeholder=svg_ph,
        tf_q=tf_q,
        tf_ans=tf_ans,
        mcq_q=mcq_q,
        mcq_a=mcq_a,
        mcq_b=mcq_b,
        mcq_c=mcq_c,
        mcq_ans=mcq_ans,
        pic_q=pic_q,
        pic_a=pic_a,
        pic_b=pic_b,
        pic_c=pic_c,
        pic_ans=pic_ans,
    )
    return html

# ---------------------------
# Main
# ---------------------------
def main():
    headline, link = fetch_headline()

    prompt = f"""
Return ONLY valid JSON. No markdown. No extra text.

Make a DAILY English worksheet for a 7-year-old beginner.
Use ONLY this headline as inspiration (do NOT copy article text):
- {headline} ({link})

Rules:
- VERY EASY English (A1).
- STORY: 3 to 4 short sentences.
- WORDS: exactly 5 items with Korean meaning.
- QUIZ: only BUTTON quizzes. NO typing.
- quizzes:
  1) True/False
  2) Multiple choice (A/B/C)
  3) Emoji picture choice (A/B/C)

JSON schema:
{{
  "title": "Kid-friendly title",
  "image_topic": "one or two simple keywords",
  "story": ["S1","S2","S3","S4"],
  "words": [{{"word":"","ko":"","en":""}},{{"word":"","ko":"","en":""}},{{"word":"","ko":"","en":""}},{{"word":"","ko":"","en":""}},{{"word":"","ko":"","en":""}}],
  "read_aloud": "Story with / pauses",
  "quiz": {{
    "tf": {{"q":"...", "answer": true}},
    "mcq": {{"q":"...", "choices": {{"A":"", "B":"", "C":""}}, "answer": "A"}},
    "pic": {{"q":"...", "choices": {{"A":"😀", "B":"🐶", "C":"🚀"}}, "answer": "B"}}
  }},
  "parent_note_ko": "..."
}}
"""

    text = call_gemini_text(prompt)
    j_raw = safe_json_loads(text)
    j = normalize_payload(j_raw, headline)

    filename = f"days/{TODAY}.html"
    with open(os.path.join(DOCS_DIR, filename), "w", encoding="utf-8") as f:
        f.write(build_day_html(TODAY, headline, link, j))

    archive = load_archive()
    archive = [a for a in archive if a.get("date") != TODAY]
    archive.insert(0, {"date": TODAY, "file": filename, "title": j["title"]})
    save_archive(archive)

    with open(os.path.join(DOCS_DIR, "index.html"), "w", encoding="utf-8") as f:
        f.write(build_index_html(archive))

    write_today_redirect(archive[0]["file"])

if __name__ == "__main__":
    main()
