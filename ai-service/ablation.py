"""
Ablation calismasi: TF-IDF-only / embedding-only / hibrit (0.7/0.3) arama
konfigurasyonlarini ayni leave-one-out yontemiyle karsilastirir.

Faz 8'de hibrit agirligin (0.7/0.3) neden secildigi retrieval.py'nin
basindaki yorumda ANLATI olarak var, ama uc konfigurasyonu yan yana
gosteren bir TABLO yoktu - bu script tam olarak o tabloyu uretir, boylece
"neden 0.7/0.3" sorusunun cevabi bir iddia degil, olculmus bir sonuc olur.

GtipOneriMotoru artik agirliklari constructor parametresi olarak kabul
ediyor (varsayilan hala 0.7/0.3, uretim davranisi degismedi) - bu script
sadece ayni motoru 3 farkli agirlikla kurup evaluate.py'deki ile ayni
leave-one-out mantigini calistiriyor. Embedding'ler agirliktan bagimsiz
oldugu icin (bkz. retrieval.py _embeddings_yukle_veya_hesapla - cache
anahtari MODEL_ADI + corpus icerigine gore, agirliga gore degil), 3
motoru kurmak embedding'i 3 kere hesaplamiyor - ilk kurulumdan sonraki
ikisi cache'ten okuyor, hizli.

Calistirmak icin:
    python ablation.py
"""

import csv
import os

from app.retrieval import GtipOneriMotoru, BTB_PATH

KONFIGURASYONLAR = [
    ("Sadece TF-IDF", 1.0, 0.0),
    ("Sadece semantik embedding", 0.0, 1.0),
    ("Hibrit (uretimde kullanilan, 0.7/0.3)", 0.7, 0.3),
]


def load_btb_rows():
    with open(BTB_PATH, encoding="utf-8") as f:
        return list(csv.DictReader(f))


def leave_one_out_dogruluk(motor, btb_rows, btb_no_to_index):
    """evaluate.py'deki ile ayni leave-one-out mantigi - Top-1/Top-3
    dogruluk ve 'yeterli veri (n>=2)' segment dogrulugunu dondurur."""
    n = len(btb_rows)
    pozisyonlar = [r["gtip_no"][:4] for r in btb_rows]
    from collections import Counter
    pozisyon_sayilari = Counter(pozisyonlar)
    tekil_pozisyonlar = {p for p, c in pozisyon_sayilari.items() if c == 1}

    top1_dogru = 0
    top3_dogru = 0
    yeterli_n = 0
    yeterli_dogru = 0

    for row in btb_rows:
        dogru_pozisyon = row["gtip_no"][:4]
        haric_index = btb_no_to_index[row["btb_no"]]
        oneriler = motor.oner(row["esya_tanimi"], top_k=3, haric_index=haric_index)

        top1_pozisyon = oneriler[0]["onerilen_gtip"][:4]
        top3_pozisyonlar = [o["onerilen_gtip"][:4] for o in oneriler]

        is_top1 = top1_pozisyon == dogru_pozisyon
        is_top3 = dogru_pozisyon in top3_pozisyonlar

        top1_dogru += int(is_top1)
        top3_dogru += int(is_top3)

        if dogru_pozisyon not in tekil_pozisyonlar:
            yeterli_n += 1
            yeterli_dogru += int(is_top1)

    return {
        "n": n,
        "top1_acc": top1_dogru / n,
        "top3_acc": top3_dogru / n,
        "yeterli_n": yeterli_n,
        "yeterli_acc": (yeterli_dogru / yeterli_n) if yeterli_n else 0.0,
    }


def main():
    btb_rows = load_btb_rows()
    print(f">>> {len(btb_rows)} BTB karari uzerinde {len(KONFIGURASYONLAR)} konfigurasyon test edilecek.\n")

    sonuclar = []
    for isim, tfidf_w, emb_w in KONFIGURASYONLAR:
        print(f">>> Kuruluyor: {isim} (tfidf={tfidf_w}, embedding={emb_w})...")
        motor = GtipOneriMotoru(tfidf_agirlik=tfidf_w, embedding_agirlik=emb_w)
        btb_no_to_index = {r["btb_no"]: i for i, r in enumerate(motor.rows) if r["btb_no"]}
        sonuc = leave_one_out_dogruluk(motor, btb_rows, btb_no_to_index)
        sonuc["isim"] = isim
        sonuclar.append(sonuc)
        print(f"    Top-1: {sonuc['top1_acc']:.1%}  Top-3: {sonuc['top3_acc']:.1%}  "
              f"Yeterli veri (n>=2): {sonuc['yeterli_acc']:.1%}\n")

    print("=" * 78)
    print("ABLATION SONUC TABLOSU")
    print("=" * 78)
    baslik = f"{'Konfigurasyon':<40}{'Top-1':>10}{'Top-3':>10}{'n>=2':>10}"
    print(baslik)
    print("-" * 78)
    for s in sonuclar:
        print(f"{s['isim']:<40}{s['top1_acc']:>9.1%} {s['top3_acc']:>9.1%} {s['yeterli_acc']:>9.1%}")

    rapor_path = os.path.join(os.path.dirname(__file__), "ABLATION_RAPORU.md")
    with open(rapor_path, "w", encoding="utf-8") as f:
        f.write("# Ablation Raporu - Arama Konfigurasyonu Karsilastirmasi\n\n")
        f.write(
            "Ayni leave-one-out yontemi (bkz. `evaluate.py`, `DEGERLENDIRME_RAPORU.md`), "
            "3 farkli arama konfigurasyonuyla calistirildi. Amac: hibrit (0.7/0.3) agirligin "
            "secilme gerekcesini bir anlatiya degil, olculmus bir karsilastirmaya dayandirmak "
            "(bkz. `app/retrieval.py` basindaki Faz 8 notu).\n\n"
        )
        f.write("| Konfigurasyon | Top-1 doğruluk | Top-3 doğruluk | Yeterli veri (n≥2) doğruluk |\n")
        f.write("|---|---|---|---|\n")
        for s in sonuclar:
            f.write(
                f"| {s['isim']} | %{s['top1_acc']*100:.1f} | %{s['top3_acc']*100:.1f} | "
                f"%{s['yeterli_acc']*100:.1f} |\n"
            )
        f.write(
            f"\nTest seti büyüklüğü: n={sonuclar[0]['n']} (küçük örneklem, "
            f"bkz. `DEGERLENDIRME_RAPORU.md`'deki güven aralığı notu).\n"
        )

    print(f"\n>>> Rapor yazildi: {rapor_path}")


if __name__ == "__main__":
    main()
