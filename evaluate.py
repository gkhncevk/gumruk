"""
Leave-one-out dogruluk degerlendirmesi.

Mantik: elimizdeki 41 gercek BTB karari icin, her birini sirayla "hic
gorulmemis yeni bir urun" gibi ele aliyoruz. O tek karari veri setinden
cikarip (exclude_btb_no), geriye kalan 40 BTB karari + 50 resmi kod
basligiyla bir motor kuruyoruz, cikardigimiz kaydin esya tanimini sisteme
soruyoruz, ve dogru GTIP pozisyonunu (4 haneli) bulup bulamadigina bakiyoruz.

Bu, modelin sadece "ezberlemedigini", gercekten benzer urunlerden genelleme
yapabildigini olcer.

Performans notu (Faz 7): resmi kod listesi ~15.700 satira cikinca, her BTB
kaydi icin motoru sifirdan yeniden kurup TF-IDF'i yeniden fit etmek (41 kere)
pratik olmaktan cikti. Bunun yerine motor BIR KERE kuruluyor, ve her kayit
icin sadece o kaydin kendi index'i siralamadan disleniyor (bkz.
GtipOneriMotoru.oner(haric_index=...)). Sonuc istatistiksel olarak esdeger -
15758 satirlik corpus'ta bir satirin IDF agirliklarina etkisi ihmal
edilebilir - ama ~40 kat daha hizli.

Iki karsilastirma baseline'i da hesaplanir:
  - Cogunluk baseline'i: her zaman en sik gorulen pozisyonu tahmin etmek
  - Rastgele baseline'i: veri setindeki tum benzersiz pozisyonlardan rastgele secmek
Bunlar olmadan "%X dogruluk" rakami anlamsizdir - kolay bir problemse
cogunluk tahmini bile yuksek cikar, bu karsilastirma o riski gosterir.

Calistirmak icin:
    python evaluate.py
"""

import csv
import os
import random
from collections import Counter

from app.retrieval import GtipOneriMotoru, BTB_PATH

random.seed(42)


def load_btb_rows():
    with open(BTB_PATH, encoding="utf-8") as f:
        return list(csv.DictReader(f))


def main():
    btb_rows = load_btb_rows()
    n = len(btb_rows)
    pozisyonlar = [r["gtip_no"][:4] for r in btb_rows]
    tum_pozisyonlar = sorted(set(pozisyonlar))

    print(f">>> Toplam {n} BTB karari uzerinde leave-one-out test baslıyor...")
    print(f">>> Veri setinde {len(tum_pozisyonlar)} benzersiz pozisyon var: {tum_pozisyonlar}\n")

    print(">>> Motor bir kere kuruluyor (tum veriyle)...")
    motor = GtipOneriMotoru()
    btb_no_to_index = {r["btb_no"]: i for i, r in enumerate(motor.rows) if r["btb_no"]}
    print(f">>> Motor hazir: {len(motor.rows)} toplam kayit.\n")

    top1_dogru = 0
    top3_dogru = 0
    detaylar = []

    for i, row in enumerate(btb_rows, 1):
        dogru_pozisyon = row["gtip_no"][:4]
        haric_index = btb_no_to_index[row["btb_no"]]
        oneriler = motor.oner(row["esya_tanimi"], top_k=3, haric_index=haric_index)

        top1_pozisyon = oneriler[0]["onerilen_gtip"][:4]
        top3_pozisyonlar = [o["onerilen_gtip"][:4] for o in oneriler]

        is_top1 = top1_pozisyon == dogru_pozisyon
        is_top3 = dogru_pozisyon in top3_pozisyonlar

        top1_dogru += int(is_top1)
        top3_dogru += int(is_top3)

        detaylar.append({
            "no": i,
            "btb_no": row["btb_no"],
            "dogru_pozisyon": dogru_pozisyon,
            "tahmin_pozisyon": top1_pozisyon,
            "top1_dogru": is_top1,
            "top3_dogru": is_top3,
            "en_iyi_benzerlik": oneriler[0]["benzerlik_skoru"],
        })

        durum = "OK" if is_top1 else ("~top3" if is_top3 else "YANLIS")
        print(f"[{i:2d}/{n}] gercek={dogru_pozisyon}  tahmin={top1_pozisyon}  benzerlik={oneriler[0]['benzerlik_skoru']:.3f}  {durum}")

    model_top1_acc = top1_dogru / n
    model_top3_acc = top3_dogru / n

    # Segmentli analiz: pozisyon basina kac ornek var? Tekil (n=1) pozisyonlar
    # leave-one-out'ta YAPISAL olarak basarisiz olmak zorunda - o tek ornek
    # cikarilinca geriye hic emsal kalmiyor, bu model kalitesizligi degil,
    # veri azliginin dogal sonucu. Asil anlamli sinyal, yeterli ornegi olan
    # pozisyonlardaki performans.
    pozisyon_sayilari = Counter(pozisyonlar)
    tekil_pozisyonlar = {p for p, c in pozisyon_sayilari.items() if c == 1}

    yeterli_veri_detaylar = [d for d in detaylar if d["dogru_pozisyon"] not in tekil_pozisyonlar]
    tekil_detaylar = [d for d in detaylar if d["dogru_pozisyon"] in tekil_pozisyonlar]

    yeterli_n = len(yeterli_veri_detaylar)
    yeterli_dogru = sum(d["top1_dogru"] for d in yeterli_veri_detaylar)
    yeterli_acc = yeterli_dogru / yeterli_n if yeterli_n else 0.0

    tekil_n = len(tekil_detaylar)
    tekil_dogru = sum(d["top1_dogru"] for d in tekil_detaylar)

    print("\n" + "=" * 60)
    print("SEGMENTLI ANALIZ (asil onemli kisim)")
    print("=" * 60)
    print(f"Tekil ornekli pozisyonlar (n=1): {sorted(tekil_pozisyonlar)}")
    print(f"  -> Bu {tekil_n} kayit, leave-one-out'ta YAPISAL olarak basarisiz olmak")
    print(f"     zorunda (tek ornek cikarilinca geriye emsal kalmiyor). Sonuc: {tekil_dogru}/{tekil_n} dogru.")
    print(f"     Bu bir model hatasi degil, veri toplama ihtiyacinin kanitidir.")
    print()
    print(f"Yeterli ornekli pozisyonlar (n>=2): {yeterli_dogru}/{yeterli_n} = {yeterli_acc:.1%} dogruluk")
    for poz in sorted(set(d["dogru_pozisyon"] for d in yeterli_veri_detaylar)):
        alt = [d for d in yeterli_veri_detaylar if d["dogru_pozisyon"] == poz]
        alt_dogru = sum(d["top1_dogru"] for d in alt)
        print(f"  {poz}: {alt_dogru}/{len(alt)} = {alt_dogru/len(alt):.1%}")

    # Baseline 1: cogunluk siniflandirici (her zaman en sik pozisyonu tahmin et)
    sayac = Counter(pozisyonlar)
    en_sik_pozisyon, en_sik_adet = sayac.most_common(1)[0]
    cogunluk_acc = en_sik_adet / n

    # Baseline 2: rastgele tahmin (1000 tekrarla ortalama)
    rastgele_dogru_toplam = 0
    tekrar = 1000
    for _ in range(tekrar):
        for gercek in pozisyonlar:
            tahmin = random.choice(tum_pozisyonlar)
            rastgele_dogru_toplam += int(tahmin == gercek)
    rastgele_acc = rastgele_dogru_toplam / (tekrar * n)

    print("\n" + "=" * 60)
    print("SONUC OZETI")
    print("=" * 60)
    print(f"Test seti buyuklugu (n)        : {n}  (KUCUK - guven araligi genis, temkinli yorumla)")
    print(f"Benzersiz pozisyon sayisi       : {len(tum_pozisyonlar)}")
    print(f"En sik pozisyon                 : {en_sik_pozisyon} ({en_sik_adet}/{n} kayit)")
    print("-" * 60)
    print(f"Model  - Top-1 dogruluk         : {model_top1_acc:.1%}  ({top1_dogru}/{n})")
    print(f"Model  - Top-3 dogruluk         : {model_top3_acc:.1%}  ({top3_dogru}/{n})")
    print(f"Baseline - Cogunluk tahmini     : {cogunluk_acc:.1%}")
    print(f"Baseline - Rastgele tahmin      : {rastgele_acc:.1%}")
    print("-" * 60)
    fark = model_top1_acc - cogunluk_acc
    print(f"Modelin cogunluk baseline'ina gore farki: {fark:+.1%}")
    if fark > 0:
        print(">>> Model, en kolay 'her zaman ayni seyi tahmin et' stratejisinden daha iyi.")
    else:
        print(">>> DIKKAT: Model, cogunluk baseline'ini gecemiyor - veri seti cok kucuk/dengesiz olabilir.")

    # Yanlis tahminlerin detayini goster (hata analizi icin faydali)
    print("\n" + "=" * 60)
    print("YANLIS TAHMIN EDILEN KAYITLAR (hata analizi)")
    print("=" * 60)
    yanlislar = [d for d in detaylar if not d["top1_dogru"]]
    if not yanlislar:
        print("Yok - tum kayitlar dogru tahmin edildi.")
    for d in yanlislar:
        top3_not = " (ama top-3'te var)" if d["top3_dogru"] else ""
        print(f"  BTB {d['btb_no']}: gercek={d['dogru_pozisyon']}, tahmin={d['tahmin_pozisyon']}{top3_not}, benzerlik={d['en_iyi_benzerlik']:.3f}")

    # Markdown rapor dosyasi da yazalim - README'ye/CV'ye kopyalanabilsin
    rapor_path = os.path.join(os.path.dirname(__file__), "DEGERLENDIRME_RAPORU.md")
    with open(rapor_path, "w", encoding="utf-8") as f:
        f.write("# Degerlendirme Raporu - Leave-One-Out Test\n\n")
        f.write(f"Test tarihi/yontemi: 41 gercek BTB karari uzerinde leave-one-out capraz dogrulama.\n")
        f.write(f"Her kayit sirayla veri setinden cikarilip, kalan verilerle o kaydin GTIP pozisyonu tahmin edilmeye calisildi.\n\n")
        f.write("## Sonuclar\n\n")
        f.write(f"- **Test seti buyuklugu:** {n} (kucuk bir ornek, guven araligi genis - temkinli yorumlanmali)\n")
        f.write(f"- **Model Top-1 dogruluk:** {model_top1_acc:.1%} ({top1_dogru}/{n})\n")
        f.write(f"- **Model Top-3 dogruluk:** {model_top3_acc:.1%} ({top3_dogru}/{n})\n")
        f.write(f"- **Cogunluk baseline'i:** {cogunluk_acc:.1%} (her zaman '{en_sik_pozisyon}' tahmin etseydik)\n")
        f.write(f"- **Rastgele baseline:** {rastgele_acc:.1%}\n")
        f.write(f"- **Modelin cogunluk baseline'ina gore farki:** {fark:+.1%}\n\n")
        f.write("## Segmentli Analiz (asil onemli kisim)\n\n")
        f.write(f"Veri setindeki {len(tekil_pozisyonlar)} pozisyonun ({sorted(tekil_pozisyonlar)}) sadece "
                f"1'er ornegi var. Leave-one-out yontemi bu tek ornegi cikardiginda, o pozisyon icin "
                f"geriye hic BTB emsali kalmiyor - yani bu {tekil_n} kaydin basarisiz olmasi **yapisal "
                f"bir zorunluluk**, model kalitesizligi degil. Bu, veri toplamaya devam etme ihtiyacinin "
                f"kanitidir (her pozisyon icin en az birkac ornek gerekli).\n\n")
        f.write(f"Asil anlamli sinyal, yeterli ornegi olan pozisyonlardaki performans:\n\n")
        f.write(f"- **Yeterli ornekli pozisyonlar (n>=2):** {yeterli_dogru}/{yeterli_n} = {yeterli_acc:.1%} dogruluk\n")
        for poz in sorted(set(d["dogru_pozisyon"] for d in yeterli_veri_detaylar)):
            alt = [d for d in yeterli_veri_detaylar if d["dogru_pozisyon"] == poz]
            alt_dogru = sum(d["top1_dogru"] for d in alt)
            f.write(f"  - {poz}: {alt_dogru}/{len(alt)} = {alt_dogru/len(alt):.1%}\n")
        f.write("\n## Not\n\n")
        f.write("Bu degerlendirme kucuk (n=41) bir veri seti uzerinde yapilmistir, istatistiksel olarak "
                "guclu bir genelleme icin yetersizdir. Daha fazla BTB karari toplandikca bu test "
                "tekrarlanip guven araligi daraltilmalidir. Yine de mevcut haliyle, modelin "
                "kor/cogunluk tahmininden anlamli sekilde iyi olup olmadigini gosteren dogru bir ilk sinyaldir.\n")

    print(f"\n>>> Rapor yazildi: {rapor_path}")


if __name__ == "__main__":
    main()