import os, json, re, urllib.parse
from datetime import datetime, timezone, timedelta
import requests, feedparser

# ================== TIME ==================
KST = timezone(timedelta(hours=9))
TODAY = datetime.now(KST).strftime("%Y-%m-%d")

# ================== PATH ==================
DOCS = "docs"
DAYS = os.path.join(DOCS, "days")
ARCHIVE = os.path.join(DOCS, "archive.json")
os.makedirs(DAYS, exist_ok=True)

# ================== SITE ==================
SITE_TITLE = "Daily English News (Age 7)"
RSS = "https://news.google.com/rss/headlines/section/topic/SCIENCE?hl=en-US&gl=US&ceid=US:en"

# ================== GEMINI ==================
API_KEY = os.environ.get("GEMINI_API_KEY", "")
MODEL = "gemini-2.5-flash"
URL = f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL}:generateContent?key={API_KEY}"

TTS_RATE = 0.77

# ================== UTILS ==================
def esc(s):
    return str(s).replace("&","&amp;").replace("<","&lt;").replace(">","&gt;")

# ================== RSS ==================
def get_headline():
    feed = feedparser.parse(RSS)
    e = feed.entries[0]
    return e.title, e.link

# ================== GEMINI ==================
def call_gemini(prompt):
    r = requests.post(URL, json={
        "contents":[{"role":"user","parts":[{"text":prompt}]}],
        "generationConfig":{"temperature":0.4,"maxOutputTokens":1500}
    }, timeout=120)
    r.raise_for_status()
    return r.json()["candidates"][0]["content"]["parts"][0]["text"]

def safe_json(txt):
    m = re.search(r"\{.*\}", txt, re.S)
    if not m:
        return {}
    try:
        return json.loads(m.group(0))
    except:
        return {}

# ================== FALLBACK ==================
def fallback():
    return {
        "title":"A Happy Star",
        "story":[
            "Look! A little star lives in space.",
            "It likes to fly far away.",
            "The star looks at other stars.",
            "Earth is safe and happy!"
        ],
        "words":[
            {"word":"star","ko":"별"},
            {"word":"space","ko":"우주"},
            {"word":"fly","ko":"날다"},
            {"word":"look","ko":"보다"},
            {"word":"Earth","ko":"지구"}
        ],
        "quiz":{
            "tf":{"q":"The star lives on Earth.","answer":False},
            "mcq":{"q":"What does the star like to do?","answer":"B"},
            "pic":{"q":"Where does the star live?","answer":"C"}
        },
        "parent":"천천히 읽고 단어 5개만 익혀도 충분합니다."
    }

# ================== HTML ==================
def day_html(data, date):
    return """<!doctype html>
<html>
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Daily English News</title>
<link rel="stylesheet" href="../style.css">
</head>
<body>

<h1>{title}</h1>
<p>{date}</p>

<div id="story">{story}</div>

<div>
<button onclick="readAll()">🔊 전체 읽기</button>
<button onclick="toggleDone()">🏁 달성</button>
</div>

<h2>QUIZ</h2>
<p>{q1}</p>
<button onclick="checkTF(true)">True</button>
<button onclick="checkTF(false)">False</button>
<div id="fb1"></div>

<script>
const RATE = {rate};
const DONE_KEY = "done_{date}";

function speak(t) {{
  let u = new SpeechSynthesisUtterance(t);
  u.rate = RATE;
  speechSynthesis.cancel();
  speechSynthesis.speak(u);
}}

function readAll() {{
  speak(document.getElementById("story").innerText);
}}

function toggleDone() {{
  if(localStorage.getItem(DONE_KEY)) {{
    localStorage.removeItem(DONE_KEY);
    alert("달성 해제");
  }} else {{
    localStorage.setItem(DONE_KEY,"1");
    alert("달성 완료!");
  }}
}}

function checkTF(v) {{
  if(v === {ans1}) {{
    document.getElementById("fb1").innerText = "✅ Great!";
  }} else {{
    document.getElementById("fb1").innerText = "❌ Try again!";
  }}
}}
</script>

</body>
</html>
""".format(
        title=esc(data["title"]),
        date=date,
        story="<br>".join(esc(s) for s in data["story"]),
        q1=esc(data["quiz"]["tf"]["q"]),
        ans1=str(data["quiz"]["tf"]["answer"]).lower(),
        rate=TTS_RATE
    )

# ================== MAIN ==================
def main():
    title, link = get_headline()
    try:
        raw = safe_json(call_gemini("Make easy English story for kids"))
        data = raw if raw else fallback()
    except:
        data = fallback()

    fn = os.path.join(DAYS, f"{TODAY}.html")
    with open(fn, "w", encoding="utf-8") as f:
        f.write(day_html(data, TODAY))

    arc = []
    if os.path.exists(ARCHIVE):
        arc = json.load(open(ARCHIVE))
    arc.insert(0, {"date":TODAY,"file":f"days/{TODAY}.html","title":data["title"]})
    json.dump(arc, open(ARCHIVE,"w"), ensure_ascii=False, indent=2)

if __name__ == "__main__":
    main()
