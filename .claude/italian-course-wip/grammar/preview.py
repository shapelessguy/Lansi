"""Build preview.html: every page of every Italian lesson rendered as Theory
renders it, 720 px wide, with window.REPORT of the heights. ?dark for dark,
?lesson=<id> for one lesson alone."""

import json
from pathlib import Path

ROOT = Path("/home/claudio/Documents/Lansi/checker")
import sys
LANG = sys.argv[1] if len(sys.argv) > 1 else "italian"
LESSONS = ROOT / f"languages/{LANG}/grammar/lessons"
OUT = Path(__file__).parent / ("preview.html" if LANG == "italian" else f"preview-{LANG}.html")

markdown = (ROOT / "exercises/theory/ui/markdown.js").read_text().replace("export ", "")
css = (ROOT / "exercises/kit.css").read_text() + (ROOT / "exercises/theory/ui/style.css").read_text()
lessons = {
    path.stem: json.loads(path.read_text())["more_info"]
    for path in sorted(LESSONS.glob("*.json"))
}

OUT.write_text(f"""<!doctype html>
<html><head><meta charset="utf-8"><title>Lesson preview</title>
<style>
:root {{ --bg:#fff; --panel:#f6f6f4; --border:#e2e1dc; --text:#1d1d1b; --muted:#6d6c66;
  --accent:#2f6fde; --accent-text:#fff; --radius:10px; --danger:#b3261e; --danger-bg:#fdecea; --done-bg:rgb(46 160 67 / 14%); }}
:root.dark {{ --bg:#1b1b1a; --panel:#232322; --border:#3a3a37; --text:#ecebe6; --muted:#a3a29b; --accent:#6ea0f5; --accent-text:#10141c; }}
body {{ background: var(--bg); color: var(--text); margin: 16px; font-family: system-ui; }}
h2.lesson {{ font-size: 14px; }}
</style></head><body>
<div id="out"></div>
<script>
{markdown}
const LESSONS = {json.dumps(lessons, ensure_ascii=False)};
const CSS = {json.dumps(css)};
const params = new URLSearchParams(location.search);
if (params.has("dark")) document.documentElement.classList.add("dark");
const only = params.get("lesson");
const out = document.getElementById("out");
const REPORT = {{}};
for (const [id, text] of Object.entries(LESSONS)) {{
  if (only && id !== only) continue;
  const title = document.createElement("h2");
  title.className = "lesson"; title.textContent = id;
  const host = document.createElement("div");
  out.append(title, host);
  const shadow = host.attachShadow({{mode: "open"}});
  const style = document.createElement("style");
  style.textContent = CSS;
  shadow.append(style);
  const pages = text.split(/\\n---\\n/).map((p) => p.trim()).filter(Boolean);
  REPORT[id] = pages.map((page, n) => {{
    const div = document.createElement("div");
    div.className = "rendered card page";
    div.style.width = "720px";
    div.innerHTML = render(page);
    shadow.append(div);
    const overflow = [...div.querySelectorAll("table")].some((t) => t.scrollWidth > div.clientWidth - 40);
    return {{n: n + 1, h: div.offsetHeight, overflow, title: page.split("\\n")[0]}};
  }});
}}
window.REPORT = REPORT;
</script></body></html>
""")
print("wrote", OUT, len(lessons), "lessons")
