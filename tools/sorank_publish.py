#!/usr/bin/env python3
"""Publication des articles SoRank sur le blog.

Le worker Cloudflare (voir sorank-worker/) depose chaque livraison du
webhook SoRank dans blog/_queue/*.json. Ce script, lance par le workflow
GitHub Actions "Publication SoRank" :

  1. lit les fichiers de la file d'attente dans l'ordre d'arrivee ;
  2. cree ou met a jour blog/<slug>/index.html dans le design du site ;
  3. tient le registre blog/articles.json (id SoRank -> slug, revision...) ;
  4. regenere l'index du blog (blog/index.html) et sitemap.xml ;
  5. supprime les fichiers traites de la file d'attente.

Contrat SoRank v2 : un event "article.updated" ne cree jamais d'article,
une revision plus ancienne que celle deja publiee est ignoree, et chaque
page publiee porte <meta name="sorank-operation-id"> avec l'Idempotency-Key
de la derniere operation appliquee (c'est ce que SoRank verifie).

Lance sans file d'attente, le script regenere simplement index + sitemap.
"""

import html
import json
import re
import sys
import unicodedata
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BLOG = ROOT / "blog"
QUEUE = BLOG / "_queue"
REGISTRY = BLOG / "articles.json"
SITEMAP = ROOT / "sitemap.xml"

SITE = "https://vincentcoachpoker.com"

MONTHS_FR = ["janvier", "fevrier", "mars", "avril", "mai", "juin", "juillet",
             "aout", "septembre", "octobre", "novembre", "decembre"]
MONTHS_FR_ACCENT = ["janvier", "février", "mars", "avril", "mai", "juin",
                    "juillet", "août", "septembre", "octobre", "novembre",
                    "décembre"]

GA_SNIPPET = """<!-- Google tag (gtag.js) -->
<script async src="https://www.googletagmanager.com/gtag/js?id=G-CPT7XVET5W"></script>
<script>
  window.dataLayer = window.dataLayer || [];
  function gtag(){dataLayer.push(arguments);}
  gtag('js', new Date());

  gtag('config', 'G-CPT7XVET5W');
</script>"""

HEAD_COMMON = """<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Playfair+Display:wght@500;600&family=Inter:wght@400;500;600&display=swap" rel="stylesheet">
<link rel="stylesheet" href="/assets/style.css">"""

NAV = """<header class="nav" id="nav">
  <div class="wrap nav-inner">
    <a class="brand" href="/">Vincent Coach Poker</a>
    <button class="nav-toggle" type="button" aria-expanded="false" aria-controls="nav-menu" aria-label="Ouvrir le menu">
      <span></span><span></span><span></span>
    </button>
    <ul class="nav-menu" id="nav-menu">
      <li><a href="/">Accueil</a></li>
      <li><a href="/mon-parcours/">Mon parcours</a></li>
      <li><a href="/la-salle-du-temps/">La Salle du Temps</a></li>
      <li><a class="btn" href="/#formation-offerte">Découvrir la formation offerte</a></li>
    </ul>
  </div>
</header>"""

FOOTER = """<footer class="footer">
  <div class="wrap">
    <div class="footer-grid">
      <div>
        <a class="footer-brand" href="/">Vincent Coach Poker</a>
        <p>Ma mission, aider les joueurs de poker à générer un revenu régulier et durable aux tables grâce à la méthode de L'Équation 3D.</p>
      </div>
      <div>
        <h3>Réseaux</h3>
        <ul>
          <li><a href="https://www.youtube.com/" rel="noopener">YouTube</a></li>
          <li><a href="https://www.instagram.com/" rel="noopener">Instagram</a></li>
        </ul>
      </div>
      <div>
        <h3>Liens</h3>
        <ul>
          <li><a href="/">Accueil</a></li>
          <li><a href="/mon-parcours/">Mon parcours</a></li>
          <li><a href="/la-salle-du-temps/">La Salle du Temps</a></li>
          <li><a href="/blog/">Blog</a></li>
        </ul>
      </div>
    </div>
    <div class="footer-bottom">
      <span>© 2026 Vincent Coach Poker</span>
      <span class="footer-legal">
        <a href="/cgv/">CGV</a> · <a href="/mentions-legales/">Mentions légales</a>
      </span>
    </div>
  </div>
</footer>

<script>
  const nav = document.getElementById('nav');
  const toggle = nav.querySelector('.nav-toggle');
  const menu = document.getElementById('nav-menu');
  toggle.addEventListener('click', () => {
    const open = menu.classList.toggle('is-open');
    nav.classList.toggle('menu-open', open);
    toggle.setAttribute('aria-expanded', open);
  });
</script>"""

BLOG_CSS = """<style>
  .post-list { display: grid; gap: 1.5rem; margin-top: 3.5rem; }
  .post-card {
    display: block;
    background: var(--card);
    border: 1px solid var(--line);
    border-radius: 10px;
    padding: 1.8rem 2rem;
    text-decoration: none;
    transition: border-color .2s ease, transform .2s ease;
  }
  .post-card:hover { border-color: var(--gold-dim); transform: translateY(-2px); }
  .post-card h2 {
    font-size: 1.45rem;
    color: var(--ivory);
    margin: .35rem 0 .6rem;
  }
  .post-card p { color: var(--muted); margin: 0; }
  .post-date {
    font-family: var(--sans);
    font-size: .78rem;
    letter-spacing: .08em;
    text-transform: uppercase;
    color: var(--gold);
  }
  .post-empty { color: var(--muted); margin-top: 3rem; }
  .post-header { max-width: 760px; margin-inline: auto; }
  .post-header h1 { font-size: clamp(2rem, 4.5vw, 3rem); max-width: none; margin-inline: 0; text-align: left; }
  .post-cover {
    width: 100%;
    max-width: 760px;
    margin: 2.5rem auto 0;
  }
  .post-cover img {
    width: 100%;
    aspect-ratio: 16 / 9;
    object-fit: cover;
    border-radius: 10px;
  }
  .prose img { max-width: 100%; height: auto; border-radius: 8px; }
  .prose h3 { font-size: 1.2rem; margin-top: 2rem; }
  .prose a { color: var(--gold); }
  .prose ul, .prose ol { padding-left: 1.3rem; }
  .prose li { margin-bottom: .4rem; }
  .prose blockquote {
    border-left: 2px solid var(--gold-dim);
    margin: 1.5rem 0;
    padding-left: 1.2rem;
    color: var(--muted);
    font-style: italic;
  }
</style>"""


def esc(s):
    return html.escape(str(s or ""), quote=True)


def fr(s):
    """Echappe puis applique les espaces insecables francaises
    (pas de : ; ! ? » orphelin en debut de ligne)."""
    s = esc(s)
    s = re.sub(r" ([:;!?»])", r"&nbsp;\1", s)
    s = s.replace("« ", "«&nbsp;")
    return s


def slugify(s):
    s = unicodedata.normalize("NFKD", str(s or "")).encode("ascii", "ignore").decode()
    s = re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")
    return s or "article"


def date_fr(iso):
    try:
        d = datetime.fromisoformat(str(iso).replace("Z", "+00:00"))
    except (ValueError, TypeError):
        d = datetime.now(timezone.utc)
    return f"{d.day} {MONTHS_FR_ACCENT[d.month - 1]} {d.year}", d.strftime("%Y-%m-%d")


def load_registry():
    if REGISTRY.exists():
        return json.loads(REGISTRY.read_text(encoding="utf-8"))
    return {}


def save_registry(reg):
    REGISTRY.write_text(json.dumps(reg, ensure_ascii=False, indent=2) + "\n",
                        encoding="utf-8")


def strip_leading_h1(content):
    """Le titre vient de article.title ; on retire un eventuel <h1> duplique
    en tete du corps."""
    return re.sub(r"^\s*<h1[^>]*>.*?</h1>\s*", "", content, count=1,
                  flags=re.S | re.I)


def newer_revision(stored, incoming):
    """True si la revision entrante est plus ancienne que celle stockee."""
    try:
        return int(incoming) < int(stored)
    except (ValueError, TypeError):
        return False


def page_head(title, description, canonical, operation_id=None):
    parts = [
        "<!DOCTYPE html>",
        '<html lang="fr">',
        "<head>",
        GA_SNIPPET,
        '<meta charset="utf-8">',
        '<meta name="viewport" content="width=device-width, initial-scale=1">',
        f"<title>{esc(title)} · Vincent Coach Poker</title>",
        f'<meta name="description" content="{esc(description)}">',
        f'<link rel="canonical" href="{esc(canonical)}">',
    ]
    if operation_id:
        parts.append(f'<meta name="sorank-operation-id" content="{esc(operation_id)}">')
    parts += [HEAD_COMMON, BLOG_CSS, "</head>", "<body>", "", NAV]
    return "\n".join(parts)


def render_article(entry, content):
    slug = entry["slug"]
    canonical = f"{SITE}/blog/{slug}/"
    display, _ = date_fr(entry.get("published_at"))
    date_line = f"Publié le {display}"
    if entry.get("updated_at") and entry["updated_at"][:10] != str(entry.get("published_at", ""))[:10]:
        upd, _ = date_fr(entry["updated_at"])
        date_line += f" · mis à jour le {upd}"

    cover = ""
    fi = entry.get("featured_image") or {}
    if fi.get("url"):
        cover = (f'\n    <div class="post-cover"><img src="{esc(fi["url"])}" '
                 f'alt="{esc(fi.get("alt", ""))}" loading="lazy"></div>')

    return f"""{page_head(entry["title"], entry.get("meta_description", ""), canonical, entry.get("operation_id"))}

<main>
  <section class="hero wrap">
    <div class="post-header">
      <span class="post-date">{esc(date_line)}</span>
      <h1>{fr(entry["title"])}</h1>
    </div>{cover}
  </section>
  <article class="section wrap prose">
{content}
  </article>
  <section class="section wrap center">
    <a class="btn" href="/#formation-offerte">Découvrir la formation offerte</a>
  </section>
</main>

{FOOTER}

</body>
</html>
"""


def render_index(reg):
    entries = sorted(reg.values(), key=lambda e: str(e.get("published_at", "")),
                     reverse=True)
    if entries:
        cards = []
        for e in entries:
            display, _ = date_fr(e.get("published_at"))
            cards.append(f"""      <a class="post-card" href="/blog/{esc(e["slug"])}/">
        <span class="post-date">{esc(display)}</span>
        <h2>{fr(e["title"])}</h2>
        <p>{fr(e.get("meta_description", ""))}</p>
      </a>""")
        body = '<div class="post-list">\n' + "\n".join(cards) + "\n    </div>"
    else:
        body = '<p class="post-empty">Les premiers articles arrivent bientôt.</p>'

    return f"""{page_head("Blog", "Stratégie, mental et bankroll : les articles de Vincent Coach Poker pour devenir rentable au poker.", f"{SITE}/blog/")}

<main>
  <section class="hero wrap">
    <h1>Le blog</h1>
    <p class="lead">Stratégie, mental, bankroll : tout pour progresser vers la rentabilité.</p>
  </section>
  <section class="section wrap">
    {body}
  </section>
</main>

{FOOTER}

</body>
</html>
"""


def render_sitemap(reg):
    urls = [
        (f"{SITE}/", "1.0", None),
        (f"{SITE}/la-salle-du-temps/", "0.9", None),
        (f"{SITE}/mon-parcours/", "0.8", None),
        (f"{SITE}/cgv/", "0.3", None),
        (f"{SITE}/mentions-legales/", "0.3", None),
    ]
    entries = sorted(reg.values(), key=lambda e: str(e.get("published_at", "")),
                     reverse=True)
    if entries:
        urls.append((f"{SITE}/blog/", "0.7", None))
        for e in entries:
            _, lastmod = date_fr(e.get("updated_at") or e.get("published_at"))
            urls.append((f"{SITE}/blog/{e['slug']}/", "0.6", lastmod))

    out = ['<?xml version="1.0" encoding="UTF-8"?>',
           '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']
    for loc, prio, lastmod in urls:
        out.append("  <url>")
        out.append(f"    <loc>{esc(loc)}</loc>")
        if lastmod:
            out.append(f"    <lastmod>{lastmod}</lastmod>")
        out.append(f"    <priority>{prio}</priority>")
        out.append("  </url>")
    out.append("</urlset>")
    return "\n".join(out) + "\n"


def unique_slug(base, reg, article_id):
    slug = base
    taken = {e["slug"] for i, e in reg.items() if i != article_id}
    n = 2
    while slug in taken:
        slug = f"{base}-{n}"
        n += 1
    return slug


def process_record(record, reg):
    event = record.get("event")
    article = record.get("article") or {}
    article_id = str(article.get("id") or "")
    if not article_id or not article.get("title"):
        print(f"  ignore : payload incomplet (event={event})")
        return False

    op_id = record.get("idempotency_key") or record.get("delivery_id") or ""
    revision = record.get("revision") or ""
    received = record.get("received_at") or record.get("timestamp") or \
        datetime.now(timezone.utc).isoformat()

    entry = reg.get(article_id)

    if event == "article.updated" and entry is None:
        print(f"  ATTENTION : mise a jour pour un article inconnu ({article_id}), "
              "ignoree (une mise a jour ne cree jamais d'article).")
        return False

    if entry and revision and entry.get("revision") and \
            newer_revision(entry["revision"], revision):
        print(f"  ignore : revision {revision} plus ancienne que "
              f"{entry['revision']} pour {article_id}")
        return False

    if entry is None:
        slug = unique_slug(slugify(article.get("slug") or article["title"]),
                           reg, article_id)
        entry = {"slug": slug, "published_at": received}
        reg[article_id] = entry
        print(f"  publie : {article['title']!r} -> /blog/{slug}/")
    else:
        entry["updated_at"] = received
        print(f"  met a jour : {article['title']!r} -> /blog/{entry['slug']}/")

    entry["title"] = article["title"]
    entry["meta_description"] = article.get("meta_description") or ""
    if article.get("featured_image"):
        entry["featured_image"] = {
            "url": article["featured_image"].get("url", ""),
            "alt": article["featured_image"].get("alt", ""),
        }
    if revision:
        entry["revision"] = revision
    if op_id:
        entry["operation_id"] = op_id

    content = strip_leading_h1(article.get("content") or "")
    page_dir = BLOG / entry["slug"]
    page_dir.mkdir(parents=True, exist_ok=True)
    (page_dir / "index.html").write_text(render_article(entry, content),
                                         encoding="utf-8")
    return True


def main():
    reg = load_registry()
    changed = False

    queue = sorted(QUEUE.glob("*.json")) if QUEUE.exists() else []
    for path in queue:
        print(f"traitement de {path.name}")
        try:
            record = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            print(f"  ATTENTION : JSON invalide ({exc}), fichier supprime.")
            path.unlink()
            continue
        if process_record(record, reg):
            changed = True
        path.unlink()

    save_registry(reg)
    BLOG.mkdir(exist_ok=True)
    (BLOG / "index.html").write_text(render_index(reg), encoding="utf-8")
    SITEMAP.write_text(render_sitemap(reg), encoding="utf-8")
    print(f"{len(queue)} livraison(s) traitee(s), "
          f"{len(reg)} article(s) au total.")
    return 0 if (changed or not queue) else 0


if __name__ == "__main__":
    sys.exit(main())
