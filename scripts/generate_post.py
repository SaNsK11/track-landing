#!/usr/bin/env python3
"""
Track Blog Publisher
Generates and publishes a fitness blog post to trytrack.app/blog/.
Runs twice daily via GitHub Actions.
"""

import json
import os
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path

import anthropic

ROOT = Path(__file__).parent.parent
BLOG_DIR = ROOT / "blog"
POSTS_JSON = BLOG_DIR / "posts.json"
TOPICS_JSON = Path(__file__).parent / "topics.json"

APPSTORE_URL = "https://apps.apple.com/app/id6816988239"
SITE_URL = "https://trytrack.app"


# ── Data helpers ──────────────────────────────────────────────────────────────

def load_topics():
    with open(TOPICS_JSON) as f:
        return json.load(f)


def load_posts():
    if POSTS_JSON.exists():
        with open(POSTS_JSON) as f:
            return json.load(f)
    return []


def save_posts(posts):
    BLOG_DIR.mkdir(parents=True, exist_ok=True)
    with open(POSTS_JSON, "w") as f:
        json.dump(posts, f, indent=2)


def get_next_topic(topics, posts):
    published = {p["slug"] for p in posts}
    for t in topics:
        if t["slug"] not in published:
            return t
    # All published — refresh the oldest post
    slug_to_date = {p["slug"]: p["date"] for p in posts}
    return min(topics, key=lambda t: slug_to_date.get(t["slug"], "9999"))


# ── Content generation ────────────────────────────────────────────────────────

def generate_post(topic):
    client = anthropic.Anthropic()

    prompt = f"""Write a comprehensive, SEO-optimised fitness blog post for the Track workout app blog.

TARGET KEYWORD: {topic["keyword"]}
ARTICLE TITLE: {topic["title"]}
CATEGORY: {topic["category"]}

AUDIENCE: Men and women aged 20-40 who want to build their dream physique. Motivated but need practical, no-BS guidance. Beginner to intermediate lifters.

CONTENT REQUIREMENTS:
- 1,500-1,800 words
- Tone: direct, authoritative, like a knowledgeable training partner — not a textbook
- Practical, actionable advice throughout — specific sets, reps, timeframes where relevant
- Structure with H2 and H3 headings (use ## and ### markers)
- Naturally include the target keyword and 4-6 related terms
- No fluff — every sentence earns its place
- Do not make medical claims or guarantee specific results

STRUCTURE:
1. Hook intro (2-3 punchy sentences about the reader's goal)
2. 4-6 H2 sections (some with H3 subsections)
3. Brief conclusion + 1 CTA mentioning "Track" app for logging workouts and tracking progress

OUTPUT — return ONLY valid JSON, no markdown fences, no extra text:
{{"meta_description":"155-character meta description with keyword","read_time":<integer minutes>,"content_markdown":"full article in markdown"}}"""

    message = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=4096,
        messages=[{"role": "user", "content": prompt}]
    )

    raw = message.content[0].text.strip()
    # Strip code fences if model wrapped the JSON
    raw = re.sub(r"^```[a-z]*\n?", "", raw)
    raw = re.sub(r"\n?```$", "", raw)

    return json.loads(raw)


# ── Markdown → HTML ───────────────────────────────────────────────────────────

def inline(text):
    text = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", text)
    text = re.sub(r"\*(.+?)\*", r"<em>\1</em>", text)
    return text


def md_to_html(md):
    blocks = re.split(r"\n\n+", md.strip())
    parts = []
    for block in blocks:
        block = block.strip()
        if not block:
            continue
        lines = block.split("\n")
        first = lines[0].strip()

        if first.startswith("### "):
            parts.append(f"<h3>{inline(first[4:])}</h3>")
        elif first.startswith("## "):
            parts.append(f"<h2>{inline(first[3:])}</h2>")
        elif first.startswith("# "):
            parts.append(f"<h2>{inline(first[2:])}</h2>")
        elif all(re.match(r"^[-*]\s", l.strip()) for l in lines if l.strip()):
            li_parts = []
            for l in lines:
                if l.strip():
                    text = re.sub(r"^[-*]\s", "", l.strip())
                    li_parts.append("<li>" + inline(text) + "</li>")
            parts.append("<ul>" + "".join(li_parts) + "</ul>")
        elif all(re.match(r"^\d+\.\s", l.strip()) for l in lines if l.strip()):
            li_parts = []
            for l in lines:
                if l.strip():
                    text = re.sub(r"^\d+\.\s", "", l.strip())
                    li_parts.append("<li>" + inline(text) + "</li>")
            parts.append("<ol>" + "".join(li_parts) + "</ol>")
        else:
            para = " ".join(l.strip() for l in lines)
            parts.append(f"<p>{inline(para)}</p>")

    return "\n".join(parts)


# ── HTML builders ─────────────────────────────────────────────────────────────

IN_ARTICLE_CTA = f"""
<div class="in-article-cta">
  <p>Log every set, track every PR, and stay on the path to your dream physique.</p>
  <a href="{APPSTORE_URL}" target="_blank" rel="noopener" class="cta-btn">Download Track Free →</a>
</div>"""


def inject_cta(content_html, after_h2=3):
    """Insert the in-article CTA after the Nth h2 tag."""
    count = 0
    result = []
    for line in content_html.split("\n"):
        result.append(line)
        if "<h2>" in line:
            count += 1
            if count == after_h2:
                result.append(IN_ARTICLE_CTA)
    return "\n".join(result)


POST_CSS = """
    *,*::before,*::after{box-sizing:border-box;margin:0;padding:0}
    :root{--accent:#C1EA1C;--bg:#0f0f0e;--surface:#1a1b19;--border:#2a2b29;--text:#fff;--muted:#7a7a7a}
    body{background:var(--bg);color:var(--text);font-family:'Inter',sans-serif;line-height:1.7}
    a{color:var(--accent);text-decoration:none}a:hover{text-decoration:underline}
    nav{padding:16px 32px;border-bottom:1px solid var(--border);display:flex;align-items:center;justify-content:space-between;position:sticky;top:0;background:rgba(15,15,14,.92);backdrop-filter:blur(12px);z-index:100}
    .nav-brand{font-family:'Archivo Black',sans-serif;font-size:18px;color:var(--text)}
    .nav-brand span{color:var(--accent)}
    .nav-back{font-size:13px;color:var(--muted);transition:color .15s}.nav-back:hover{color:var(--text);text-decoration:none}
    .wrap{max-width:740px;margin:0 auto;padding:60px 24px 100px}
    .article-category{display:inline-block;font-size:11px;font-weight:700;color:var(--accent);letter-spacing:.1em;text-transform:uppercase;margin-bottom:20px}
    h1{font-family:'Archivo Black',sans-serif;font-size:clamp(28px,5vw,44px);letter-spacing:-1.5px;line-height:1.08;margin-bottom:20px}
    .byline{font-size:13px;color:var(--muted);display:flex;align-items:center;gap:16px;flex-wrap:wrap;padding-top:20px;border-top:1px solid var(--border);margin-bottom:48px}
    .byline strong{color:var(--text);font-weight:600}
    .body h2{font-family:'Archivo Black',sans-serif;font-size:clamp(20px,3vw,26px);letter-spacing:-.5px;margin:48px 0 16px}
    .body h3{font-size:18px;font-weight:700;margin:32px 0 12px}
    .body p{font-size:16px;color:#c8c8c8;line-height:1.78;margin-bottom:20px}
    .body ul,.body ol{margin:0 0 20px;padding-left:0;list-style:none;display:flex;flex-direction:column;gap:10px}
    .body ul li,.body ol li{font-size:15px;color:#c8c8c8;padding-left:24px;position:relative;line-height:1.65}
    .body ul li::before{content:'';position:absolute;left:0;top:10px;width:6px;height:6px;border-radius:50%;background:var(--accent)}
    .body ol{counter-reset:ol-c}.body ol li{counter-increment:ol-c}
    .body ol li::before{content:counter(ol-c);position:absolute;left:0;top:1px;width:18px;height:18px;background:rgba(193,234,28,.1);border:1px solid rgba(193,234,28,.2);border-radius:50%;display:flex;align-items:center;justify-content:center;font-size:10px;font-weight:700;color:var(--accent);line-height:18px;text-align:center}
    .body strong{color:var(--text);font-weight:700}
    .in-article-cta{background:var(--surface);border:1px solid var(--border);border-left:3px solid var(--accent);border-radius:12px;padding:24px 28px;margin:40px 0;display:flex;align-items:center;justify-content:space-between;gap:20px;flex-wrap:wrap}
    .in-article-cta p{font-size:15px;color:var(--muted);margin:0;flex:1}
    .cta-btn{display:inline-flex;align-items:center;background:var(--accent);color:#000;font-size:13px;font-weight:800;padding:10px 20px;border-radius:100px;white-space:nowrap;transition:transform .15s}
    .cta-btn:hover{transform:translateY(-1px);text-decoration:none}
    .footer-cta{margin-top:72px;padding:48px 40px;background:var(--surface);border-radius:20px;border:1px solid var(--border);text-align:center}
    .footer-cta h2{font-family:'Archivo Black',sans-serif;font-size:clamp(22px,4vw,32px);letter-spacing:-1px;margin-bottom:12px}
    .footer-cta p{font-size:15px;color:var(--muted);margin-bottom:28px}
    .btn-dl{display:inline-flex;align-items:center;gap:10px;background:var(--accent);color:#000;font-size:15px;font-weight:800;padding:14px 32px;border-radius:100px;transition:transform .15s,box-shadow .15s;box-shadow:0 8px 24px rgba(193,234,28,.25)}
    .btn-dl:hover{transform:translateY(-2px);box-shadow:0 12px 36px rgba(193,234,28,.35);text-decoration:none}
    .back-link{display:inline-flex;align-items:center;gap:6px;font-size:13px;color:var(--muted);margin-top:48px;transition:color .15s}
    .back-link:hover{color:var(--text);text-decoration:none}
    @media(max-width:600px){nav{padding:12px 20px}.wrap{padding:40px 20px 80px}.in-article-cta{flex-direction:column;align-items:flex-start}.footer-cta{padding:36px 24px}}
"""

INDEX_CSS = """
    *,*::before,*::after{box-sizing:border-box;margin:0;padding:0}
    :root{--accent:#C1EA1C;--bg:#0f0f0e;--surface:#1a1b19;--surface2:#242522;--border:#2a2b29;--text:#fff;--muted:#7a7a7a}
    body{background:var(--bg);color:var(--text);font-family:'Inter',sans-serif}
    a{color:inherit;text-decoration:none}
    nav{padding:16px 32px;border-bottom:1px solid var(--border);display:flex;align-items:center;justify-content:space-between;position:sticky;top:0;background:rgba(15,15,14,.92);backdrop-filter:blur(12px);z-index:100}
    .nav-brand{font-family:'Archivo Black',sans-serif;font-size:18px;color:var(--text)}.nav-brand span{color:var(--accent)}
    .nav-home{font-size:13px;color:var(--muted);transition:color .15s}.nav-home:hover{color:var(--text)}
    .blog-header{padding:72px 48px 60px;max-width:1100px;margin:0 auto}
    .blog-label{font-size:11px;font-weight:700;color:var(--accent);letter-spacing:.1em;text-transform:uppercase;margin-bottom:20px}
    .blog-header h1{font-family:'Archivo Black',sans-serif;font-size:clamp(36px,6vw,64px);letter-spacing:-2px;line-height:1.0;margin-bottom:16px}
    .blog-header p{font-size:17px;color:var(--muted);line-height:1.6;max-width:480px}
    .posts-grid{max-width:1100px;margin:0 auto;padding:0 48px 100px;display:grid;grid-template-columns:repeat(3,1fr);gap:1px;overflow:hidden}
    .post-card{background:var(--surface);transition:background .2s}.post-card:hover{background:var(--surface2)}
    .post-link{display:block;padding:32px 28px;height:100%}
    .post-category{font-size:10px;font-weight:700;color:var(--accent);letter-spacing:.1em;text-transform:uppercase;display:block;margin-bottom:14px}
    .post-title{font-family:'Archivo Black',sans-serif;font-size:18px;letter-spacing:-.3px;line-height:1.25;margin-bottom:12px}
    .post-desc{font-size:14px;color:var(--muted);line-height:1.6;margin-bottom:24px}
    .post-meta{font-size:12px;color:var(--muted);display:flex;gap:16px}
    .empty-state{grid-column:1/-1;padding:80px 40px;text-align:center;color:var(--muted);font-size:15px}
    footer{border-top:1px solid var(--border);padding:32px 48px;display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:16px}
    .footer-brand{font-family:'Archivo Black',sans-serif;font-size:16px;color:var(--text)}.footer-brand span{color:var(--accent)}
    footer p{font-size:13px;color:var(--muted)}
    @media(max-width:860px){.posts-grid{grid-template-columns:1fr 1fr;padding:0 32px 80px}.blog-header{padding:60px 32px 48px}}
    @media(max-width:600px){.posts-grid{grid-template-columns:1fr;padding:0 20px 72px}.blog-header{padding:48px 20px 36px}nav{padding:12px 20px}footer{padding:28px 20px}}
"""


def build_post_html(topic, post_data, date_str):
    display_date = datetime.strptime(date_str, "%Y-%m-%d").strftime("%B %d, %Y")
    category_label = topic["category"].replace("-", " ").title()

    content_html = md_to_html(post_data["content_markdown"])
    content_html = inject_cta(content_html)

    schema = json.dumps({
        "@context": "https://schema.org",
        "@type": "Article",
        "headline": topic["title"],
        "description": post_data["meta_description"],
        "datePublished": date_str,
        "author": {"@type": "Organization", "name": "Track"},
        "publisher": {"@type": "Organization", "name": "Track", "url": SITE_URL}
    }, indent=2)

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8"/>
  <meta name="viewport" content="width=device-width,initial-scale=1.0"/>
  <title>{topic["title"]} | Track</title>
  <meta name="description" content="{post_data["meta_description"]}"/>
  <link rel="canonical" href="{SITE_URL}/blog/{topic["slug"]}/"/>
  <meta property="og:title" content="{topic["title"]}"/>
  <meta property="og:description" content="{post_data["meta_description"]}"/>
  <meta property="og:url" content="{SITE_URL}/blog/{topic["slug"]}/"/>
  <meta property="og:type" content="article"/>
  <meta name="twitter:card" content="summary"/>
  <meta name="twitter:title" content="{topic["title"]}"/>
  <meta name="twitter:description" content="{post_data["meta_description"]}"/>
  <link rel="preconnect" href="https://fonts.googleapis.com"/>
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin/>
  <link href="https://fonts.googleapis.com/css2?family=Archivo+Black&family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet"/>
  <script type="application/ld+json">{schema}</script>
  <style>{POST_CSS}</style>
</head>
<body>
<nav>
  <a class="nav-brand" href="{SITE_URL}">Tr<span>a</span>ck</a>
  <a class="nav-back" href="{SITE_URL}/blog/">← All articles</a>
</nav>
<main class="wrap">
  <span class="article-category">{category_label}</span>
  <h1>{topic["title"]}</h1>
  <div class="byline">
    <span>By <strong>Sanskar Goyal</strong></span>
    <span>{display_date}</span>
    <span>{post_data["read_time"]} min read</span>
  </div>
  <article class="body">
    {content_html}
  </article>
  <div class="footer-cta">
    <h2>Ready to build your dream physique?</h2>
    <p>Track every lift, break every record, and get AI-powered physique analysis. Free on the App Store.</p>
    <a href="{APPSTORE_URL}" target="_blank" rel="noopener" class="btn-dl">Download Track Free</a>
  </div>
  <a class="back-link" href="{SITE_URL}/blog/">← Back to all articles</a>
</main>
</body>
</html>"""


def build_index_html(posts):
    year = datetime.now().year

    if posts:
        cards = ""
        for p in posts[:60]:
            cat_label = p["category"].replace("-", " ").title()
            cards += f"""
    <article class="post-card">
      <a class="post-link" href="{SITE_URL}/blog/{p["slug"]}/">
        <span class="post-category">{cat_label}</span>
        <h2 class="post-title">{p["title"]}</h2>
        <p class="post-desc">{p["description"]}</p>
        <div class="post-meta"><span>{p["date"]}</span><span>{p.get("read_time",7)} min read</span></div>
      </a>
    </article>"""
    else:
        cards = '<div class="empty-state">New articles publishing soon. Check back shortly.</div>'

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8"/>
  <meta name="viewport" content="width=device-width,initial-scale=1.0"/>
  <title>Fitness Blog — Workout Tips, Routines &amp; Guides | Track</title>
  <meta name="description" content="Workout routines, muscle-building guides, fat loss tips, and training plans from the Track fitness app. Build your dream physique."/>
  <link rel="canonical" href="{SITE_URL}/blog/"/>
  <meta property="og:title" content="Fitness Blog — Track"/>
  <meta property="og:description" content="Workout routines, muscle-building guides, and fat loss tips from the Track app."/>
  <meta property="og:url" content="{SITE_URL}/blog/"/>
  <link rel="preconnect" href="https://fonts.googleapis.com"/>
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin/>
  <link href="https://fonts.googleapis.com/css2?family=Archivo+Black&family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet"/>
  <style>{INDEX_CSS}</style>
</head>
<body>
<nav>
  <a class="nav-brand" href="{SITE_URL}">Tr<span>a</span>ck</a>
  <a class="nav-home" href="{SITE_URL}">← Back to app</a>
</nav>
<header class="blog-header">
  <div class="blog-label">The Track Blog</div>
  <h1>Build your<br/>dream physique.</h1>
  <p>Workout routines, training guides, and no-BS advice for people serious about their physique.</p>
</header>
<main>
  <div class="posts-grid">{cards}
  </div>
</main>
<footer>
  <span class="footer-brand">Tr<span>a</span>ck</span>
  <p>© {year} Track. Free on the App Store.</p>
</footer>
</body>
</html>"""


# ── Git ───────────────────────────────────────────────────────────────────────

def git_push(files, message):
    subprocess.run(["git", "config", "user.email", "blog-bot@trytrack.app"], cwd=ROOT, check=True)
    subprocess.run(["git", "config", "user.name", "Track Blog Bot"], cwd=ROOT, check=True)
    subprocess.run(["git", "pull", "--rebase", "--autostash", "origin", "main"], cwd=ROOT, check=True)
    for f in files:
        subprocess.run(["git", "add", str(f)], cwd=ROOT, check=True)
    subprocess.run(["git", "commit", "-m", message], cwd=ROOT, check=True)
    subprocess.run(["git", "push"], cwd=ROOT, check=True)


# ── Entry point ───────────────────────────────────────────────────────────────

def main():
    topics = load_topics()
    posts = load_posts()
    topic = get_next_topic(topics, posts)

    print(f"Generating: {topic['title']}")
    post_data = generate_post(topic)

    date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    # Write post file
    post_dir = BLOG_DIR / topic["slug"]
    post_dir.mkdir(parents=True, exist_ok=True)
    post_file = post_dir / "index.html"
    post_file.write_text(build_post_html(topic, post_data, date_str), encoding="utf-8")

    # Update posts.json (remove existing entry for this slug if refreshing, then prepend)
    posts = [p for p in posts if p["slug"] != topic["slug"]]
    posts.insert(0, {
        "slug": topic["slug"],
        "title": topic["title"],
        "description": post_data["meta_description"],
        "date": date_str,
        "category": topic["category"],
        "read_time": post_data["read_time"]
    })
    save_posts(posts)

    # Regenerate blog index
    index_file = BLOG_DIR / "index.html"
    index_file.write_text(build_index_html(posts), encoding="utf-8")

    git_push(
        [post_file, POSTS_JSON, index_file],
        f"Blog: {topic['title']}"
    )

    print(f"Published: {SITE_URL}/blog/{topic['slug']}/")


if __name__ == "__main__":
    main()
