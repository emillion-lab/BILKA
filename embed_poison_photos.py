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


RASTER = (".jpg", ".jpeg", ".png")  # реални снимки; пропускаме .svg/.pdf/.tif (рисунки/схеми)


def _get(url, **params):
    r = requests.get(url, params=params or None,
                     headers={"User-Agent": USER_AGENT}, timeout=40)
    r.raise_for_status()
    return r


def api(wiki, params):
    return _get(f"https://{wiki}.wikipedia.org/w/api.php",
                **dict(params, format="json")).json()


def commons_api(params):
    return _get("https://commons.wikimedia.org/w/api.php",
                **dict(params, format="json")).json()


def _file_from_url(u):
    """От upload URL вади името File:... (последната част, декодирана)."""
    from urllib.parse import unquote
    name = unquote(u.split("/")[-1])
    # маха евентуален thumb префикс "NNNpx-"
    name = re.sub(r"^\d+px-", "", name)
    return "File:" + name


def candidates(wiki, title, override_file):
    """Връща подредени кандидат-файлове (File:...) за вида, снимки преди рисунки."""
    out = []
    if override_file:
        out.append(override_file if override_file.startswith("File:") else "File:" + override_file)

    # 1) Wikipedia REST summary — водещата снимка от таксобокса (точният вид)
    try:
        r = _get(f"https://{wiki}.wikipedia.org/api/rest_v1/page/summary/"
                 + requests.utils.quote(title, safe=""))
        j = r.json()
        for key in ("originalimage", "thumbnail"):
            src = (j.get(key) or {}).get("source")
            if src:
                out.append(_file_from_url(src))
    except Exception:
        pass

    # 2) Wikidata P18 — официалната снимка на таксона
    try:
        pp = api(wiki, {"action": "query", "prop": "pageprops",
                        "titles": title, "ppprop": "wikibase_item"})
        qid = None
        for p in pp.get("query", {}).get("pages", {}).values():
            qid = (p.get("pageprops") or {}).get("wikibase_item")
        if qid:
            wd = _get("https://www.wikidata.org/w/api.php", action="wbgetclaims",
                      entity=qid, property="P18", format="json").json()
            for c in wd.get("claims", {}).get("P18", []):
                fn = c["mainsnak"]["datavalue"]["value"]
                out.append("File:" + fn)
    except Exception:
        pass

    # 3) pageimages (резерв)
    try:
        data = api(wiki, {"action": "query", "prop": "pageimages",
                          "piprop": "name", "titles": title})
        for p in data.get("query", {}).get("pages", {}).values():
            if p.get("pageimage"):
                out.append("File:" + p["pageimage"])
    except Exception:
        pass

    # подреждане: реални снимки (raster) първо, без дубликати
    seen, raster, other = set(), [], []
    for f in out:
        if f in seen:
            continue
        seen.add(f)
        (raster if f.lower().endswith(RASTER) else other).append(f)
    return raster + other


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
        got = False
        try:
            cands = candidates(spec["wiki"], spec["title"], spec.get("file"))
            if not cands:
                print(f"  \u2717 {pid}: нямам кандидат за {spec['title']}")
                continue
            for file_title in cands:
                try:
                    url, artist, lic, page = image_info(file_title)
                    if not url:
                        continue
                    data_uri, nbytes = fetch_and_encode(url)
                    photos[pid] = {"src": data_uri, "credit": artist,
                                   "license": lic, "source": page}
                    total += nbytes
                    print(f"  \u2713 {pid}: {spec['title']}  ({nbytes // 1024} KB)  \u2014 {artist[:45]}, {lic}")
                    got = True
                    break
                except Exception:
                    continue
            if not got:
                print(f"  \u2717 {pid}: нито един кандидат не се свали за {spec['title']}")
            time.sleep(0.5)
        except Exception as e:
            print(f"  \u2717 {pid}: грешка \u2014 {e}")

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
