"""
retrieval.py icin testler. GtipOneriMotoru, kurulusunda gercek bir
sentence-transformers modelini (MODEL_ADI) huggingface'den indirmeye
calisir - agi engelli bir ortamda (CI runner haric, bkz. proje notlari)
bu basarisiz olabilir. Bu yuzden motoru bir kere, modul seviyesinde
kurmayi deniyoruz; agdan dolayi basarisiz olursa TUM bu dosyadaki
testler acikca "SKIPPED" olarak isaretlenip gecilir - "sessizce
gecersiz" degil, calistiran kisiye neden atlandigi acikca yazilir."""

import pytest

try:
    from app.retrieval import GtipOneriMotoru
    _motor = GtipOneriMotoru()
    _MOTOR_HATASI = None
except Exception as e:  # model indirilemedi / ag yok / baska bir kurulum hatasi
    _motor = None
    _MOTOR_HATASI = e

pytestmark = pytest.mark.skipif(
    _motor is None,
    reason=f"GtipOneriMotoru kurulamadi (muhtemelen sentence-transformers modeli "
           f"indirilemedi, ag erisimi gerekiyor): {_MOTOR_HATASI}",
)


def test_rows_hem_btb_hem_resmi_kod_iceriyor():
    kaynaklar = {r["kaynak_tipi"] for r in _motor.rows}
    assert "btb_karari" in kaynaklar
    assert "resmi_kod" in kaynaklar


def test_oner_top_k_kadar_sonuc_donuyor():
    sonuclar = _motor.oner("diz bolgesinde kullanilan orme destek bandi", top_k=3)
    assert len(sonuclar) == 3


def test_oner_sonuclari_skora_gore_azalan_sirali():
    sonuclar = _motor.oner("diz bolgesinde kullanilan orme destek bandi", top_k=5)
    skorlar = [s["benzerlik_skoru"] for s in sonuclar]
    assert skorlar == sorted(skorlar, reverse=True)


def test_haric_index_o_satiri_disliyor():
    tum_sonuclar = _motor.oner("diz bolgesinde kullanilan orme destek bandi", top_k=1)
    en_iyi_gtip = tum_sonuclar[0]["onerilen_gtip"]
    en_iyi_idx = next(i for i, r in enumerate(_motor.rows) if r["gtip_no"] == en_iyi_gtip)

    disli_sonuclar = _motor.oner(
        "diz bolgesinde kullanilan orme destek bandi", top_k=1, haric_index=en_iyi_idx
    )
    assert disli_sonuclar[0]["onerilen_gtip"] != en_iyi_gtip or len(_motor.rows) == 1
