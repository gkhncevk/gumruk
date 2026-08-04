"""
Faz 3 - Risk skorlama katmani.

Mantik: beyan edilen GTIP ile motorun onerdigi en iyi GTIP'in 4 haneli
pozisyon seviyesinde karsilastirilmasi. Ayni pozisyondaysa risk dusuk,
farkliysa (ve oneri yeterince guvenilirse) risk yuksek olarak isaretlenir.

Onemli not: buradaki 0.15 benzerlik esigi (CONFIDENCE_THRESHOLD) elle
konulmus bir baslangic degeri - gercek etiketlenmis "riskli/risksiz"
beyanname verisi olmadigi icin istatistiksel olarak kalibre edilmedi.
Ileride gercek beyanname/denetim sonucu verisiyle bu esik ayarlanmali.
"""

from app.rag import gerekce_uret

CONFIDENCE_THRESHOLD = 0.15


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