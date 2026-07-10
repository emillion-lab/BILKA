#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
embed_poison_photos.py
----------------------
Сваля ПРАВИЛНАТА снимка за всеки отровен вид от Wikimedia/Wikipedia,
смалява я, компресира я и я вгражда като base64 директно в index.html.
След пускане index.html остава ЕДИН файл, работи офлайн, снимките са вътре.

Как да пуснеш (локално или в GitHub Actions):
    pip install requests pillow
    python3 embed_poison_photos.py

Пуска се само веднъж (или пак, ако искаш да опресниш снимките).
Кредитът към автора и лицензът се вграждат заедно със снимката (изискване на CC лиценза).
"""

import base64
import io
import json
import re
import sys
import time

try:
    import requests
except ImportError:
    sys.exit("Липсва 'requests'.  Пусни:  pip install requests pillow")
try:
    from PIL import Image
except ImportError:
    sys.exit("Липсва 'Pillow'.  Пусни:  pip install requests pillow")

HTML_FILE = "index.html"
MAX_PX = 700          # най-дълга страна на снимката
JPEG_QUALITY = 78     # компресия — по-ниско = по-малък файл
USER_AGENT = "BILKA-herb-guide/1.0 (offline first-aid herbal; educational)"

# id в приложението  ->  статия в Wikipedia (латинско име = точният вид).
# "wiki" е езиковата версия; "title" е заглавието на статията.
# По желание "file" налага конкретен файл от Commons (когато водещата снимка
# е рисунка, а искаме реална снимка с ясен разпознавателен белег).
SPECIES = {
    "ludo-bile":        {"wiki": "en", "title": "Atropa belladonna"},
    "tatul":            {"wiki": "en", "title": "Datura stramonium"},
    "blyan":            {"wiki": "en", "title": "Hyoscyamus niger"},
    "buchinish":        {"wiki": "en", "title": "Conium maculatum"},
    "voden-buchinish":  {"wiki": "en", "title": "Cicuta virosa"},
    "naprastnik":       {"wiki": "en", "title": "Digitalis purpurea"},
    "momina-salza":     {"wiki": "en", "title": "Convallaria majalis"},
    "esenen-minzuhar":  {"wiki": "en", "title": "Colchicum autumnale"},
    "samakitka":        {"wiki": "en", "title": "Aconitum napellus"},
    "chemerika":        {"wiki": "en", "title": "Veratrum album"},
    "tis":              {"wiki": "en", "title": "Taxus baccata"},
    "kukuryak":         {"wiki": "en", "title": "Helleborus niger"},
}


def api(wiki, params):
    url = f"https://{wiki}.wikipedia.org/w/api.php"
    params = dict(params, format="json")
    r = requests.get(url, params=params, headers={"User-Agent": USER_AGENT}, timeout=30)
    r.raise_for_status()
    return r.json()


def commons_api(params):
    url = "https://commons.wikimedia.org/w/api.php"
    params = dict(params, format="json")
    r = requests.get(url, params=params, headers={"User-Agent": USER_AGENT}, timeout=30)
    r.raise_for_status()
    return r.json()


def lead_image_title(wiki, title):
    """Връща името на водещия файл (File:...) на статията."""
    data = api(wiki, {
        "action": "query", "prop": "pageimages",
        "piprop": "name", "titles": title,
    })
    pages = data.get("query", {}).get("pages", {})
    for p in pages.values():
        name = p.get("pageimage")
        if name:
            return "File:" + name
    return None


def image_info(file_title):
    """Връща (url, автор, лиценз, страница) за даден File: от Commons."""
    data = commons_api({
        "action": "query", "prop": "imageinfo", "titles": file_title,
        "iiprop": "url|extmetadata", "iiurlwidth": MAX_PX,
    })
    pages = data.get("query", {}).get("pages", {})
    for p in pages.values():
        ii = p.get("imageinfo")
        if not ii:
            continue
        info = ii[0]
        url = info.get("thumburl") or info.get("url")
        meta = info.get("extmetadata", {})
        artist_html = (meta.get("Artist", {}) or {}).get("value", "")
        artist = re.sub("<[^>]+>", "", artist_html).strip() or "Wikimedia Commons"
        artist = re.sub(r"\s+", " ", artist)
        lic = (meta.get("LicenseShortName", {}) or {}).get("value", "").strip()
        page = info.get("descriptionshorturl") or info.get("descriptionurl") or ""
        return url, artist, lic, page
    return None, None, None, None


def fetch_and_encode(url):
    r = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=60)
    r.raise_for_status()
    im = Image.open(io.BytesIO(r.content))
    if im.mode not in ("RGB", "L"):
        im = im.convert("RGB")
    im.thumbnail((MAX_PX, MAX_PX))
    buf = io.BytesIO()
    im.save(buf, format="JPEG", quality=JPEG_QUALITY, optimize=True)
    b64 = base64.b64encode(buf.getvalue()).decode("ascii")
    return "data:image/jpeg;base64," + b64, len(buf.getvalue())


def main():
    photos = {}
    total = 0
    for pid, spec in SPECIES.items():
        try:
            file_title = spec.get("file")
            if not file_title:
                file_title = lead_image_title(spec["wiki"], spec["title"])
            if not file_title:
                print(f"  ✗ {pid}: не намерих снимка за {spec['title']}")
                continue
            url, artist, lic, page = image_info(file_title if file_title.startswith("File:") else "File:" + file_title)
            if not url:
                print(f"  ✗ {pid}: няма URL за {file_title}")
                continue
            data_uri, nbytes = fetch_and_encode(url)
            photos[pid] = {
                "src": data_uri,
                "credit": artist,
                "license": lic,
                "source": page,
            }
            total += nbytes
            print(f"  ✓ {pid}: {spec['title']}  ({nbytes // 1024} KB)  — {artist}, {lic}")
            time.sleep(0.5)  # учтивост към Wikimedia
        except Exception as e:
            print(f"  ✗ {pid}: грешка — {e}")

    if not photos:
        sys.exit("Не свалих нито една снимка — прекратявам без промяна на HTML.")

    # Вгражда в index.html: слага скрипт-блок, който дефинира window.POISON_PHOTOS
    # ПРЕДИ първия <script> с данните, за да е наличен при зареждане.
    block = ('<script id="poison-photos">\nwindow.POISON_PHOTOS = '
             + json.dumps(photos, ensure_ascii=False) + ';\n</script>')

    html = open(HTML_FILE, encoding="utf-8").read()
    if 'id="poison-photos"' in html:
        html = re.sub(r'<script id="poison-photos">.*?</script>', block, html, flags=re.S)
    else:
        # вмъкваме точно преди първия <script>
        idx = html.find("<script>")
        html = html[:idx] + block + "\n" + html[idx:]

    open(HTML_FILE, "w", encoding="utf-8").write(html)
    print(f"\nГотово: вградих {len(photos)} снимки (~{total // 1024} KB) в {HTML_FILE}.")
    print("Файлът остава един, работи офлайн, снимките са вътре.")


if __name__ == "__main__":
    main()
