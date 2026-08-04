"""
Faz 4 - Gerekcelendirme katmani (RAG-lite, LLM'siz).

Gercek RAG genelde: retrieval + bir LLM'in bulunan metinleri sentezleyip
akici bir aciklama yazmasi. Burada LLM API kullanmama karari alindigi icin
(maliyet/anahtar gerektirmesin diye), "generation" adimi bir LLM yerine
sablon tabanli, deterministik bir formatlama ile yapiliyor. Yani bu bir
"RAG-lite": retrieval var, uretim LLM degil kural tabanli.

Iki kaynaktan besleniyor:
  1) BTB kararinin gercek gerekcesi (varsa) - motor.oner() zaten donduruyor
  2) kurallar_kutuphanesi.csv - GYK ve pozisyon notlarindan derlenen kucuk
     bir kural kutuphanesi (bkz. dosyanin ustundeki not - bu liste yazarin
     bilgisinden derlendi, resmi metnin birebir kopyasi degil, dogrulanmali)
"""

import csv
import os

KURALLAR_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "kurallar_kutuphanesi.csv")

# BTB detay sayfalari ASP.NET WebForms postback ile calisiyor (__doPostBack),
# yani her karara dogrudan tiklanabilir bir URL yok - denedim, dogrulayamadim.
# Bu yuzden sahte/kirik bir link uydurmak yerine, her zaman calisan arama
# sayfasina + BTB numarasina yonlendiriyoruz. Kullanici bir tik uzakta gercek
# kaynaga ulasabiliyor, ama link kirilma riski yok.
BTB_ARAMA_SAYFASI = "https://uygulama.gtb.gov.tr/BTBBasvuru/BtbWebArama"


def _load_kurallar(path=KURALLAR_PATH):
    with open(path, encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    for r in rows:
        r["pozisyonlar"] = set(p.strip() for p in r["ilgili_pozisyonlar"].split(","))
    return rows


_KURALLAR = _load_kurallar()


def ilgili_kurallari_bul(gtip_pozisyon: str):
    """4 haneli pozisyona (orn. '6307') gore ilgili genel kurallari dondurur."""
    poz = gtip_pozisyon[:4]
    return [
        {"kural_id": r["kural_id"], "metin": r["kural_metni"]}
        for r in _KURALLAR
        if poz in r["pozisyonlar"]
    ]


def gerekce_uret(oneri_sonucu: dict) -> dict:
    """Bir oneri sonucunu (motor.oner() ciktisindaki tek bir eleman) alip,
    BTB gerekcesi + ilgili genel kurallari birlestirerek yapilandirilmis
    bir gerekceli aciklama uretir. LLM kullanmaz, tamamen retrieval + format."""

    pozisyon = oneri_sonucu["onerilen_gtip"][:4]
    kurallar = ilgili_kurallari_bul(pozisyon)

    if oneri_sonucu["kaynak_tipi"] == "btb_karari":
        kanit_seviyesi = "guclu"
        ana_gerekce = oneri_sonucu["gerekce"]
        ozet = (
            f"Bu oneri, gercek bir BTB karari (No: {oneri_sonucu['referans_btb_no']}) "
            f"emsal alinarak yapildi. Emsaldeki esya tanimi: "
            f"\"{oneri_sonucu['referans_esya_tanimi'][:150]}...\""
        )
        kaynak_linki = BTB_ARAMA_SAYFASI
        kaynak_notu = f"Bu karari dogrulamak icin BTB arama sisteminde 'BTB No' alanina {oneri_sonucu['referans_btb_no']} yazip aratabilirsin."
    else:
        kanit_seviyesi = "zayif"
        ana_gerekce = "Bu pozisyon icin veri setinde BTB emsali bulunamadi."
        ozet = (
            f"Bu oneri, sadece resmi pozisyon basligina ({pozisyon}) ve genel "
            f"siniflandirma kurallarina dayaniyor - gercek bir emsal karar yok. "
            f"Manuel dogrulama onerilir."
        )
        kaynak_linki = BTB_ARAMA_SAYFASI
        kaynak_notu = f"Bu pozisyon icin emsal yok - {pozisyon} GTIP numarasiyla BTB arama sisteminde kontrol edebilirsin."

    return {
        "kanit_seviyesi": kanit_seviyesi,
        "ozet": ozet,
        "btb_gerekcesi": ana_gerekce,
        "ilgili_genel_kurallar": kurallar,
        "kaynak_linki": kaynak_linki,
        "kaynak_notu": kaynak_notu,
    }