"""
Faz 3 - Risk skorlama katmani.

Mantik: beyan edilen GTIP ile motorun onerdigi en iyi GTIP'in 4 haneli
pozisyon seviyesinde karsilastirilmasi. Ayni pozisyondaysa risk dusuk,
farkliysa (ve oneri yeterince guvenilirse) risk yuksek olarak isaretlenir.

Onemli not: buradaki benzerlik esigi (CONFIDENCE_THRESHOLD) elle
konulmus bir deger - gercek etiketlenmis "riskli/risksiz" beyanname
verisi olmadigi icin istatistiksel olarak tam kalibre edilemedi.
Ileride gercek beyanname/denetim sonucu verisiyle bu esik ayarlanmali.

FAZ 8 GUNCELLEMESI: 41 kayitlik leave-one-out testinde (evaluate.py,
hibrit TF-IDF 0.7 / embedding 0.3 agirlikla) gozlemlenen gercek skor
dagilimi:
  - Dogru tahminlerin benzerlik skorlari : 0.241 - 0.961 arasi (genis)
  - Yanlis tahminlerin benzerlik skorlari: 0.257 - 0.651 arasi

Bu iki grup buyuk olcude CAKISIYOR - yanlis bir tahmin 0.651 gibi
yuksek skor alabiliyor, dogru bir tahmin 0.241 gibi dusuk skor
alabiliyor. Yani "dusuk skor = sistem kararsiz" varsayimi embedding'le
artik eskisi kadar temiz calismiyor: eski TF-IDF'te alakasiz metin
skoru sifira yakin duserdi, semantik embedding'te ise alakasiz bile
olsa skor nadiren cok dusuyor (genel anlamda "ayni kategori" sinyali
hep bir miktar benzerlik uretiyor).

Bu nedenle esik, iki grubu net ayiran matematiksel bir "optimum nokta"
degil - sadece en zayif yanlis tahminleri (0.257-0.35 civari) yakalayip
"belirsiz" olarak isaretlemeyi hedefleyen, kucuk veri setine gore
temkinli secilmis bir deger. 0.30'un altinda bir baglantisiz durumu
tamamen "belirsiz"e cekmez - 41 kayitlik test, kesin bir esik
belirlemek icin cok kucuk. Gercek denetim verisi biriktikce
yeniden olculmeli.
"""

from app.rag import gerekce_uret

CONFIDENCE_THRESHOLD = 0.30  # Faz 8: hibrit skor dagilimina gore kalibre edildi, yukaridaki uyariya bak


def risk_hesapla(beyan_edilen_gtip: str, esya_tanimi: str, motor, top_k: int = 3) -> dict:
    oneriler = motor.oner(esya_tanimi, top_k=top_k)
    en_iyi = oneriler[0]

    beyan_pozisyon = beyan_edilen_gtip[:4]
    onerilen_pozisyon = en_iyi["onerilen_gtip"][:4]

    if beyan_pozisyon == onerilen_pozisyon:
        risk_seviyesi = "dusuk"
        aciklama = (
            f"Beyan edilen pozisyon ({beyan_pozisyon}) ile sistemin en yakin "
            f"onerisi ayni. Uyumlu gorunuyor."
        )
    elif en_iyi["benzerlik_skoru"] < CONFIDENCE_THRESHOLD:
        risk_seviyesi = "belirsiz"
        aciklama = (
            f"Sistem bu esya tanimi icin guclu bir emsal/kod eslesmesi bulamadi "
            f"(benzerlik skoru: {en_iyi['benzerlik_skoru']}). Guvenilir bir risk "
            f"degerlendirmesi yapilamiyor - manuel inceleme onerilir."
        )
    else:
        risk_seviyesi = "yuksek"
        aciklama = (
            f"Beyan edilen pozisyon ({beyan_pozisyon}) ile sistemin onerdigi "
            f"pozisyon ({onerilen_pozisyon}) farkli. Hatali siniflandirma "
            f"riski olabilir, incelenmesi onerilir."
        )

    return {
        "risk_seviyesi": risk_seviyesi,
        "aciklama": aciklama,
        "beyan_edilen_gtip": beyan_edilen_gtip,
        "onerilen_gtip": en_iyi["onerilen_gtip"],
        "benzerlik_skoru": en_iyi["benzerlik_skoru"],
        "gerekceli_aciklama": gerekce_uret(en_iyi),
        "diger_emsaller": oneriler[1:],
    }