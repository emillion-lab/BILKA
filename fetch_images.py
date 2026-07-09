#!/usr/bin/env python3
"""Сваля снимки на билките от Wikipedia в img/<id>.jpg — по една заявка на билка.
Изпълнява се от GitHub Actions. Идемпотентен — прескача наличните."""
import json, os, sys, time, urllib.request, urllib.parse

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

UA = {"User-Agent": "BILKA-herb-guide/1.0 (github.com/emillion-lab/BILKA)"}
OUT = "img"

def get(url):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=60) as r:
        return r.read()

def main():
    os.makedirs(OUT, exist_ok=True)
    ok, miss = 0, []
    for pid, title in PLANTS.items():
        dest = os.path.join(OUT, f"{pid}.jpg")
        if os.path.exists(dest) and os.path.getsize(dest) > 1000:
            ok += 1
            continue
        try:
            # REST summary endpoint — прост и надежден, следва redirect-и
            url = ("https://en.wikipedia.org/api/rest_v1/page/summary/"
                   + urllib.parse.quote(title.replace(" ", "_")))
            data = json.loads(get(url))
            thumb = (data.get("thumbnail") or {}).get("source")
            if thumb:
                # искаме по-голям размер: заместваме ширината в URL-а на миниатюрата
                import re
                thumb = re.sub(r"/(\d+)px-", "/640px-", thumb)
            if not thumb:
                miss.append(pid)
                print(f"✗ {pid}: няма thumbnail", file=sys.stderr)
                continue
            with open(dest, "wb") as f:
                f.write(get(thumb))
            ok += 1
            print(f"✓ {pid} <- {thumb}")
            time.sleep(0.3)
        except Exception as e:
            miss.append(pid)
            print(f"✗ {pid}: {e}", file=sys.stderr)

    print(f"\nГотово: {ok}/{len(PLANTS)}. Липсват: {miss or 'няма'}")
    # Не проваляме run-а при единични липси, но искаме поне 30
    if ok < 30:
        sys.exit(1)

if __name__ == "__main__":
    main()
