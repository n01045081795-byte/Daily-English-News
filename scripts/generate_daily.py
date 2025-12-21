# Daily English News – stable kid version
# FIXED:
# - illustration always shows (fallback)
# - sentence-by-sentence TTS buttons
# - DONE button toggle on/off
# - quiz wrong = try again (no answer reveal)

import os, json, re, urllib.parse
from datetime import datetime, timezone, timedelta
import requests, feedparser

# ---------- TIME ----------
KST = timezone(timedelta(hours=9))
TODAY = datetime.now(KST).strftime("%Y-%m-%d")

# ---------- PATH ----------
DOCS = "docs"
DAYS = f"{DOCS}/days"
ARCHIVE = f"{DOCS}/archive.json"
os.makedirs(DAYS, exist_ok=True)

# ---------- SITE ----------
SITE_TITLE = "Daily English News (Age 7)"
RSS = "https://news.google.com/rss/headlines/section/topic/SCIENCE?hl=en-US&gl=US&ceid=US:en"

# ---------- GEMINI ----------
API_KEY = os.environ.get("GEMINI_API_KEY", "")
MODEL = "gemini-2.5-flash"
URL = f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL}:generateContent?key={API_KEY}"

# ---------- TTS ----------
TTS_RATE = 0.77   # slower


def esc(s): 
    return str(s).replace("&","&amp;").replace("<","&lt;").replace(">","&gt;")


# ---------- RSS ----------
def get_headline():
    feed = feedparser.parse(RSS)
    e = feed.entries[0]
    return e.title, e.link


# ---------- GEMINI SAFE JSON ----------
def call_gemini(prompt):
    r = requests.post(URL, json={
        "contents":[{"role":"user","parts":[{"text":prompt}]}],
        "generationConfig":{"temperature":0.4,"maxOutputTokens":1500}
    }, timeout=120)
    r.raise_for_status()
    t = r.json()["candidates"][0]["content"]["parts"][0]["text"]
    return t

def extract_json(t):
    m = re.search(r"\{.*\}", t, re.S)
    if not m: return {}
    s = m.group(0)
    s = s.replace("“","\"").replace("”","\"")
    s = re.sub(r",\s*([}\]])", r"\1", s)
    try:
        return json.loads(s)
    except:
        return {}


# ---------- DEFAULT ----------
def fallback():
    return {
        "title":"A Happy Star",
        "image_topic":"cute star",
        "story":[
            "Look! A little star lives in space.",
            "It likes to fly far away.",
            "The star looks at other stars.",
            "Earth is safe and happy!"
        ],
        "words":[
            {"word":"star","ko":"별","en":"a light in the sky"},
            {"word":"space","ko":"우주","en":"the big sky"},
            {"word":"fly","ko":"날다","en":"go in the air"},
            {"word":"look","ko":"보다","en":"see"},
            {"word":"Earth","ko":"지구","en":"our home"}
        ],
        "read_aloud":"Look! / A little star / lives in space. / It likes to fly far away.",
        "quiz":{
            "tf":{"q":"The star lives on Earth.","answer":False},
            "mcq":{"q":"What does the star like to do?","choices":{"A":"Sleep","B":"Fly","C":"Eat"},"answer":"B"},
            "pic":{"q":"Where does the star live?","choices":{"A":"🏠","B":"🌳","C":"🚀"},"answer":"C"}
        },
        "parent_note_ko":"이야기를 천천히 읽고 단어 5개만 익히면 충분합니다."
    }


# ---------- IMAGE ----------
def image_urls(topic):
    seed = urllib.parse.quote(topic)
    return [
        f"https://picsum.photos/seed/{seed}/900/600",
        f"https://source.unsplash.com/900x600/?{seed},kids,illustration",
        "https://placehold.co/900x600/png?text=Daily+English+News"
    ]


# ---------- HTML ----------
def day_html(date, headline, link, d):
    story = "<br>".join(esc(x) for x in d["story"])
    word_cards = "".join(
        f"<div class='word'><b>{esc(w['word'])}</b><span>{esc(w['ko'])}</span></div>"
        for w in d["words"]
    )

    sentence_btns = "".join(
        f"<button class='btn small' data-say='{esc(s)}'>🔊 문장{i}</button>"
        for i,s in enumerate(d["story"],1)
    )

    imgs = json.dumps(image_urls(d["image_topic"]))

    return f"""<!doctype html>
<html>
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{SITE_TITLE}</title>
<link rel="stylesheet" href="../style.css">
</head>
<body>

<h1>{esc(d["title"])}</h1>
<p>{date}</p>

<div id="imgBox"><img id="hero"></div>

<div id="story">{story}</div>
<div>{sentence_btns}</div>

<button id="readAll">🔊 전체 읽기</button>
<button id="doneBtn">🏁 달성</button>

<h2>WORDS</h2>
<div class="words">{word_cards}</div>

<h2>QUIZ</h2>

<p>{esc(d["quiz"]["tf"]["q"])}</p>
<button data-q="tf" data-a="true">True</button>
<button data-q="tf" data-a="false">False</button>
<div id="fb_tf"></div>

<p>{esc(d["quiz"]["mcq"]["q"])}</p>
<button data-q="mcq" data-a="A">A</button>
<button data-q="mcq" data-a="B">B</button>
<button data-q="mcq" data-a="C">C</button>
<div id="fb_mcq"></div>

<p>{esc(d["quiz"]["pic"]["q"])}</p>
<button data-q="pic" data-a="A">🏠</button>
<button data-q="pic" data-a="B">🌳</button>
<button data-q="pic" data-a="C">🚀</button>
<div id="fb_pic"></div>

<p>{esc(d["parent_note_ko"])}</p>

<script>
const RATE={TTS_RATE};
const DONE_KEY="done_{date}";
const answers={{tf:{str(d["quiz"]["tf"]["answer"]).lower()},mcq:"{d["quiz"]["mcq"]["answer"]}",pic:"{d["quiz"]["pic"]["answer"]}"}};

let imgs={imgs},i=0;
const img=document.getElementById("hero");
function loadImg(){{ if(i<imgs.length) img.src=imgs[i++]; }}
img.onerror=loadImg; loadImg();

function speak(t){{
  let u=new SpeechSynthesisUtterance(t);
  u.rate=RATE; speechSynthesis.cancel(); speechSynthesis.speak(u);
}}

document.getElementById("readAll").onclick=()=>speak(document.getElementById("story").innerText);
document.querySelectorAll("[data-say]").forEach(b=>b.onclick=()=>speak(b.dataset.say));

const doneBtn=document.getElementById("doneBtn");
function refreshDone(){{ doneBtn.textContent=localStorage.getItem(DONE_KEY)?"✅ 완료":"🏁 달성"; }}
doneBtn.onclick=()=>{{ localStorage.getItem(DONE_KEY)?localStorage.removeItem(DONE_KEY):localStorage.setItem(DONE_KEY,1); refreshDone(); }};
refreshDone();

document.querySelectorAll("[data-q]").forEach(b=>b.onclick=()=>{
  let q=b.dataset.q, pick=b.dataset.a;
  if(pick==answers[q]){{ document.getElementById("fb_"+q).innerText="✅ Great!"; }}
  else{{ document.getElementById("fb_"+q).innerText="❌ Try again!"; }}
});
</script>

</body>
</html>
"""


# ---------- MAIN ----------
def main():
    headline, link = get_headline()
    prompt = f"Make easy English worksheet for 7-year-old about: {headline}. Return ONLY JSON."
    try:
        raw = extract_json(call_gemini(prompt))
        data = raw if raw else fallback()
    except:
        data = fallback()

    fn = f"days/{TODAY}.html"
    with open(f"{DOCS}/{fn}","w",encoding="utf-8") as f:
        f.write(day_html(TODAY, headline, link, data))

    arc = []
    if os.path.exists(ARCHIVE):
        arc=json.load(open(ARCHIVE))
    arc=[a for a in arc if a["date"]!=TODAY]
    arc.insert(0,{"date":TODAY,"file":fn,"title":data["title"]})
    json.dump(arc, open(ARCHIVE,"w"), ensure_ascii=False, indent=2)

if __name__=="__main__":
    main()
