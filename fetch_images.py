#!/usr/bin/env python3
"""Сваля снимки на билките от Wikipedia (pageimages API) в img/<id>.jpg.
Изпълнява се от GitHub Actions (fetch_images.yml). Идемпотентен — прескача наличните."""
import json, os, sys, urllib.request, urllib.parse

# id -> заглавие на английската Wikipedia статия
PLANTS = {
    "laika": "Matricaria chamomilla",
    "menta": "Peppermint",
    "matochina": "Melissa officinalis",
    "valeriana": "Valeriana officinalis",
    "kantarion": "Hypericum perforatum",
    "glog": "Crataegus monogyna",
    "shipka": "Rosa canina",
    "lipa": "Tilia cordata",
    "baz": "Sambucus nigra",
    "mashterka": "Thymus serpyllum",
    "zhivovlyak": "Plantago lanceolata",
    "salvia": "Salvia officinalis",
    "neven": "Calendula officinalis",
    "lavandula": "Lavandula angustifolia",
    "kopriva": "Urtica dioica",
    "gluharche": "Taraxacum officinale",
    "ravnets": "Achillea millefolium",
    "ehinatseya": "Echinacea purpurea",
    "dzhindzhifil": "Ginger",
    "len": "Flax",
    "mecho-grozde": "Arctostaphylos uva-ursi",
    "tsarevichna-kosa": "Corn silk",
    "rozmarin": "Rosemary",
    "byal-tran": "Silybum marianum",
    "pelin": "Artemisia absinthium",
    "mursalski": "Sideritis scardica",
    "iglika": "Primula veris",
    "hmel": "Humulus lupulus",
    "pasiflora": "Passiflora incarnata",
    "anason": "Anise",
    "rezene": "Fennel",
    "cheren-oman": "Symphytum officinale",
    "varbova-kora": "Salix alba",
    "borovinka": "Vaccinium myrtillus",
    "hvoyna": "Juniperus communis",
}

API = "https://en.wikipedia.org/w/api.php"
UA = {"User-Agent": "BILKA-herb-guide/1.0 (github.com/emillion-lab/BILKA)"}
OUT = "img"

def api(params):
    url = API + "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)

def main():
    os.makedirs(OUT, exist_ok=True)
    title_to_id = {v: k for k, v in PLANTS.items()}
    titles = list(PLANTS.values())
    ok, miss = 0, []

    # pageimages връща thumbnail-и на порции — обхождаме с continue
    base = {
        "action": "query", "format": "json", "redirects": 1,
        "prop": "pageimages", "piprop": "thumbnail", "pithumbsize": 640,
        "pilimit": "max", "titles": "|".join(titles),
    }
    pages, remap, cont = {}, {}, {}
    while True:
        data = api({**base, **cont})
        for r in data.get("query", {}).get("normalized", []) + data.get("query", {}).get("redirects", []):
            remap[r["to"]] = remap.get(r["from"], r["from"])
        for pid_, page in data.get("query", {}).get("pages", {}).items():
            if "thumbnail" in page or pid_ not in pages:
                pages[pid_] = page
        cont = data.get("continue")
        if not cont:
            break

    for page in pages.values():
        title = page.get("title", "")
        orig = remap.get(title, title)
        pid = title_to_id.get(orig) or title_to_id.get(title)
        if not pid:
            continue
        thumb = page.get("thumbnail", {}).get("source")
        dest = os.path.join(OUT, f"{pid}.jpg")
        if not thumb:
            miss.append(pid)
            continue
        if os.path.exists(dest) and os.path.getsize(dest) > 1000:
            ok += 1
            continue
        try:
            req = urllib.request.Request(thumb, headers=UA)
            with urllib.request.urlopen(req, timeout=60) as r, open(dest, "wb") as f:
                f.write(r.read())
            ok += 1
            print(f"✓ {pid} <- {thumb}")
        except Exception as e:
            miss.append(pid)
            print(f"✗ {pid}: {e}", file=sys.stderr)

    print(f"\nГотово: {ok}/{len(PLANTS)} снимки. Липсват: {miss or 'няма'}")

if __name__ == "__main__":
    main()
