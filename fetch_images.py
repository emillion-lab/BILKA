#!/usr/bin/env python3
"""Сваля снимки на билките от Wikipedia в img/<id>.jpg.
Retry с изчакване срещу rate limiting; пише fetch_log.txt; идемпотентен."""
import json, os, time, urllib.request, urllib.parse

PLANTS = {
    "laika": "Matricaria chamomilla", "menta": "Peppermint",
    "matochina": "Melissa officinalis", "valeriana": "Valeriana officinalis",
    "kantarion": "Hypericum perforatum", "glog": "Crataegus monogyna",
    "shipka": "Rosa canina", "lipa": "Tilia cordata",
    "baz": "Sambucus nigra", "mashterka": "Thymus serpyllum",
    "zhivovlyak": "Plantago lanceolata", "salvia": "Salvia officinalis",
    "neven": "Calendula officinalis", "lavandula": "Lavandula angustifolia",
    "kopriva": "Urtica dioica", "gluharche": "Taraxacum officinale",
    "ravnets": "Achillea millefolium", "ehinatseya": "Echinacea purpurea",
    "dzhindzhifil": "Ginger", "len": "Flax",
    "mecho-grozde": "Arctostaphylos uva-ursi", "tsarevichna-kosa": "Corn silk",
    "rozmarin": "Rosemary", "byal-tran": "Silybum marianum",
    "pelin": "Artemisia absinthium", "mursalski": "Sideritis scardica",
    "iglika": "Primula veris", "hmel": "Humulus lupulus",
    "pasiflora": "Passiflora incarnata", "anason": "Anise",
    "rezene": "Fennel", "cheren-oman": "Symphytum officinale",
    "varbova-kora": "Salix alba", "borovinka": "Vaccinium myrtillus",
    "hvoyna": "Juniperus communis",
    "orehovi-lista": "Juglans regia", "tikveno-seme": "Cucurbita pepo",
    "tuchenitsa": "Portulaca oleracea", "treven-zdravets": "Geranium macrorrhizum",
    "rigan": "Oregano", "isop": "Hyssopus officinalis",
    "komuniga": "Melilotus officinalis", "sporezh": "Solidago virgaurea",
    "byal-oman": "Inula helenium",
}

UA = {"User-Agent": "BILKA-herb-guide/1.0 (https://github.com/emillion-lab/BILKA; contact via repo issues)"}
OUT, LOG = "img", []

def log(msg):
    print(msg)
    LOG.append(msg)

def get(url, tries=4):
    delay = 3
    for attempt in range(1, tries + 1):
        try:
            req = urllib.request.Request(url, headers=UA)
            with urllib.request.urlopen(req, timeout=60) as r:
                return r.read()
        except Exception as e:
            if attempt == tries:
                raise
            log(f"  retry {attempt} след {delay}s: {e}")
            time.sleep(delay)
            delay *= 2

def main():
    os.makedirs(OUT, exist_ok=True)
    ok = skipped = 0
    miss = []
    for pid, title in PLANTS.items():
        dest = os.path.join(OUT, f"{pid}.jpg")
        if os.path.exists(dest) and os.path.getsize(dest) > 1000:
            skipped += 1
            continue
        try:
            q = urllib.parse.urlencode({
                "action": "query", "format": "json", "redirects": 1,
                "prop": "pageimages", "piprop": "thumbnail",
                "pithumbsize": 640, "titles": title,
            })
            data = json.loads(get("https://en.wikipedia.org/w/api.php?" + q))
            pages = data.get("query", {}).get("pages", {})
            thumb = None
            for p in pages.values():
                thumb = (p.get("thumbnail") or {}).get("source")
            if not thumb:
                miss.append(pid)
                log(f"✗ {pid} ({title}): няма thumbnail в отговора")
                continue
            blob = get(thumb)
            with open(dest, "wb") as f:
                f.write(blob)
            ok += 1
            log(f"✓ {pid} ({len(blob)//1024} KB)")
            time.sleep(1.2)
        except Exception as e:
            miss.append(pid)
            log(f"✗ {pid} ({title}): {e}")
            time.sleep(2)

    log(f"Резултат: нови {ok}, налични {skipped}, липсват {len(miss)}: {miss or '—'}")
    with open("fetch_log.txt", "w") as f:
        f.write("\n".join(LOG) + "\n")

if __name__ == "__main__":
    main()
