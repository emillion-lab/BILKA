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

try:
    from requests.adapters import HTTPAdapter
    from urllib3.util.retry import Retry
    SESSION = requests.Session()
    _retry = Retry(total=5, connect=3, read=3, backoff_factor=1.5,
                   status_forcelist=[403, 429, 500, 502, 503, 504],
                   allowed_methods=["GET"], respect_retry_after_header=True)
    SESSION.mount("https://", HTTPAdapter(max_retries=_retry))
except Exception:
    SESSION = requests.Session()

HTML_FILE = "index.html"
MAX_PX = 700          # най-дълга страна на снимката
JPEG_QUALITY = 78     # компресия — по-ниско = по-малък файл
USER_AGENT = "BILKA-herbal/1.0 (https://github.com/emillion-lab/BILKA; educational herbal reference)"

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


RASTER = (".jpg", ".jpeg", ".png")


def _get(url, stream=False):
    return SESSION.get(url, headers={"User-Agent": USER_AGENT},
                       timeout=60, stream=stream, allow_redirects=True)


def _json(url):
    r = _get(url)
    r.raise_for_status()
    return r.json()


def wiki_api(wiki, qs):
    return _json(f"https://{wiki}.wikipedia.org/w/api.php?{qs}&format=json")


def filepath_url(filename):
    """Директен, надежден адрес към файла в Commons (следва редирект към thumb)."""
    from urllib.parse import quote
    fn = filename.replace("File:", "").strip()
    return (f"https://commons.wikimedia.org/wiki/Special:FilePath/"
            f"{quote(fn)}?width={MAX_PX}")


def image_urls(wiki, title, override_file):
    """Списък от (директен_URL, име_на_файл) кандидати — снимки преди рисунки."""
    from urllib.parse import quote, unquote
    cands = []  # (url, filename)

    if override_file:
        fn = override_file.replace("File:", "")
        cands.append((filepath_url(fn), fn))

    # 1) pageimages — връща директния URL на водещата снимка в едно повикване
    try:
        data = wiki_api(wiki, "action=query&prop=pageimages"
                             "&piprop=original|thumbnail|name&pithumbsize=%d"
                             "&titles=%s" % (MAX_PX, quote(title)))
        for p in data.get("query", {}).get("pages", {}).values():
            orig = (p.get("original") or {}).get("source")
            thumb = (p.get("thumbnail") or {}).get("source")
            name = p.get("pageimage")
            url = thumb or orig
            if url and name:
                cands.append((url, name))
    except Exception:
        pass

    # 2) Wikidata P18 — официалната снимка на таксона
    try:
        pp = wiki_api(wiki, "action=query&prop=pageprops&ppprop=wikibase_item"
                            "&titles=%s" % quote(title))
        qid = None
        for p in pp.get("query", {}).get("pages", {}).values():
            qid = (p.get("pageprops") or {}).get("wikibase_item")
        if qid:
            wd = _json("https://www.wikidata.org/w/api.php?action=wbgetclaims"
                       "&entity=%s&property=P18&format=json" % qid)
            for c in wd.get("claims", {}).get("P18", []):
                fn = c["mainsnak"]["datavalue"]["value"]
                cands.append((filepath_url(fn), fn))
    except Exception:
        pass

    # 3) REST summary (резерв)
    try:
        j = _json("https://%s.wikipedia.org/api/rest_v1/page/summary/%s"
                  % (wiki, quote(title, safe="")))
        for key in ("originalimage", "thumbnail"):
            src = (j.get(key) or {}).get("source")
            if src:
                fn = re.sub(r"^\d+px-", "", unquote(src.split("/")[-1]))
                cands.append((src, fn))
    except Exception:
        pass

    seen, raster, other = set(), [], []
    for url, fn in cands:
        key = fn.lower()
        if key in seen:
            continue
        seen.add(key)
        (raster if key.endswith(RASTER) else other).append((url, fn))
    return raster + other


def credit_for(filename):
    """Best-effort автор + лиценз от Commons. Ако се провали — общ кредит."""
    from urllib.parse import quote
    try:
        j = _json("https://commons.wikimedia.org/w/api.php?action=query"
                  "&prop=imageinfo&iiprop=extmetadata|url"
                  f"&titles=File:{quote(filename.replace('File:',''))}&format=json")
        for p in j.get("query", {}).get("pages", {}).values():
            ii = p.get("imageinfo")
            if not ii:
                continue
            meta = ii[0].get("extmetadata", {})
            art = re.sub("<[^>]+>", "", (meta.get("Artist", {}) or {}).get("value", "")).strip()
            art = re.sub(r"\s+", " ", art) or "Wikimedia Commons"
            lic = (meta.get("LicenseShortName", {}) or {}).get("value", "").strip()
            page = ii[0].get("descriptionshorturl", "")
            return art, lic, page
    except Exception:
        pass
    return "Wikimedia Commons", "", ""


def fetch_and_encode(url):
    r = _get(url)
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
            cands = image_urls(spec["wiki"], spec["title"], spec.get("file"))
            if not cands:
                print(f"  \u2717 {pid}: нямам кандидат за {spec['title']}")
                continue
            for url, fn in cands:
                try:
                    data_uri, nbytes = fetch_and_encode(url)
                except Exception:
                    continue
                artist, lic, page = credit_for(fn)
                photos[pid] = {"src": data_uri, "credit": artist,
                               "license": lic, "source": page}
                total += nbytes
                print(f"  \u2713 {pid}: {spec['title']}  ({nbytes // 1024} KB)  \u2014 {artist[:45]}, {lic}")
                got = True
                break
            if not got:
                print(f"  \u2717 {pid}: нито един кандидат не се свали за {spec['title']}")
            time.sleep(1.2)
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
