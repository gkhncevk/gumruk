"""
Ticaret Bakanligi'nin resmi "Istatistik Pozisyonlarina Bolunmus Turk Gumruk
Tarife Cetveli" Excel yayinini (ggm.ticaret.gov.tr, her fasil ayri .xls
dosyasi olarak yayimlanir) parse edip duz bir (gtip_pozisyon, aciklama)
CSV'sine ceviren script (Faz 7).

NEDEN BU SCRIPT VAR:
Resmi Excel dosyalari GTIP kodlarini duz bir tabloda vermiyor - hiyerarsik
bir "outline" formatinda: her satirin EŞYANIN TANIMI hucresi, kac tane
"-" ile basladigina gore bir derinlik seviyesini temsil ediyor (orn.
"- Pamuktan:" derinlik 1, "- - Diğerleri" derinlik 2). Tam 12 haneli bir
GTIP kodunun GERCEK anlamli aciklamasi, kendi satirindaki metin DEGIL -
o satira kadarki tum ata basliklarinin birlesimi. Bu script bu hiyerarsiyi
bir stack ile cozup her leaf (12 haneli) kod icin tam "ata zinciri"
aciklamasini uretiyor.

Ayrica Excel'de bazi uzun basliklar birden fazla fiziksel satira
tasiyor (word-wrap), bazen kelime ortasindan tire ile bolunerek
("... ve benze-" / "ri eşya ..."). Script bunu da tespit edip dogru
birlestiriyor (bkz. `birlestir`).

KULLANIM:
    python scripts/parse_tarife_cetveli.py "61 fasil 2025.xls" 62.xls ...
    # veya bir klasordeki TUM .xls dosyalarini isle:
    python scripts/parse_tarife_cetveli.py --klasor /path/to/tgtc/ --cikti data/resmi_kod_listesi_tum_fasillar.csv

DOGRULAMA:
Bu script ile uretilen listede, elimizdeki 41 gercek BTB kararinin
TAMAMININ GTIP kodu birebir eslesiyor (41/41) - yani parser'in ciktisi
gercek resmi verilerle tutarli.
"""

import argparse
import csv
import glob
import os
import re
import sys

import pandas as pd

CODE_RE = re.compile(r"^\d{4}\.\d{2}\.\d{2}\.\d{2}\.\d{2}$")  # tam 12 haneli GTIP (noktali)
DASH_RE = re.compile(r"^((?:-\s*)+)(.*)$")


def temizle_kod(kod):
    if pd.isna(kod):
        return None
    kod = str(kod).strip()
    return re.sub(r"\D", "", kod) if CODE_RE.match(kod) else None


def satiri_ayikla(kod_ham, tanim_ham):
    """Bir satirdan (dash_derinligi, metin, kodu_var_mi) cikarir."""
    if pd.isna(tanim_ham):
        return None, None, None
    metin_ham = str(tanim_ham).strip()
    if not metin_ham:
        return None, None, None
    m = DASH_RE.match(metin_ham)
    if m:
        derinlik = m.group(1).count("-")
        metin = m.group(2).strip(" :")
    else:
        derinlik = 0
        metin = metin_ham.strip(" :")
    kodu_var_mi = not pd.isna(kod_ham) and str(kod_ham).strip() != ""
    return derinlik, metin, kodu_var_mi


def birlestir(eski, yeni):
    """Kelime ortasi tire ile bolunmus satirlari (Excel word-wrap) dogru birlestirir."""
    eski = eski.rstrip()
    if eski.endswith("-") and not eski.endswith("--"):
        return eski[:-1] + yeni.lstrip()
    return eski + " " + yeni.lstrip()


def parse_fasil(path):
    """Tek bir fasil .xls dosyasini parse edip [{gtip_pozisyon, aciklama}, ...] dondurur."""
    df = pd.read_excel(path, header=None)
    stack = {}
    sonuclar = []
    son_derinlik = None
    son_satir_leaf_mi = False

    for _, row in df.iterrows():
        kod_ham = row[0] if len(row) > 0 else None
        tanim_ham = row[1] if len(row) > 1 else None
        derinlik, metin, kodu_var_mi = satiri_ayikla(kod_ham, tanim_ham)
        if metin is None:
            continue

        devam_satiri = (
            derinlik == 0
            and not kodu_var_mi
            and son_derinlik is not None
            and DASH_RE.match(str(tanim_ham).strip()) is None
        )

        if devam_satiri:
            stack[son_derinlik] = birlestir(stack.get(son_derinlik, ""), metin)
            if son_satir_leaf_mi and sonuclar:
                sonuclar[-1]["aciklama"] = birlestir(sonuclar[-1]["aciklama"], metin)
            continue

        stack[derinlik] = metin
        for d in list(stack.keys()):
            if d > derinlik:
                del stack[d]
        son_derinlik = derinlik

        kod = temizle_kod(kod_ham)
        if kod:
            zincir = [stack[d] for d in sorted(stack.keys())]
            sonuclar.append({"gtip_pozisyon": kod, "aciklama": " / ".join(zincir)})
            son_satir_leaf_mi = True
        else:
            son_satir_leaf_mi = False

    return sonuclar


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("dosyalar", nargs="*", help="Parse edilecek .xls dosyalari")
    ap.add_argument("--klasor", help="Icindeki tum .xls dosyalarini isle")
    ap.add_argument("--cikti", default="resmi_kod_listesi_tum_fasillar.csv")
    args = ap.parse_args()

    dosyalar = list(args.dosyalar)
    if args.klasor:
        dosyalar += sorted(glob.glob(os.path.join(args.klasor, "*.xls")))
    if not dosyalar:
        print("En az bir dosya ya da --klasor belirtmelisin.", file=sys.stderr)
        sys.exit(1)

    tum_satirlar = []
    goruldu = set()
    for path in dosyalar:
        fasil_no = os.path.basename(path).split(" ")[0]
        try:
            satirlar = parse_fasil(path)
        except Exception as e:
            print(f"UYARI: {path} parse edilemedi: {e}", file=sys.stderr)
            continue
        for s in satirlar:
            if s["gtip_pozisyon"] in goruldu:
                continue  # bazi fasillar arasinda nadiren tekrar olabiliyor
            goruldu.add(s["gtip_pozisyon"])
            s["fasil"] = fasil_no
            tum_satirlar.append(s)
        print(f"{os.path.basename(path)}: {len(satirlar)} kod")

    with open(args.cikti, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["gtip_pozisyon", "aciklama", "fasil"])
        w.writeheader()
        w.writerows(tum_satirlar)

    print(f"\nToplam {len(tum_satirlar)} kayit -> {args.cikti}")


if __name__ == "__main__":
    main()
