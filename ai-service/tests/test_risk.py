"""
risk.py icin testler. Gercek GtipOneriMotoru'nu (sentence-transformers,
network gerektirir) kullanmiyoruz - onun yerine motor.oner()'in donmesi
gereken sekle uyan sahte (fake) bir motor kullaniyoruz. risk_hesapla()'nin
kendi mantigi (pozisyon karsilastirmasi, esik kontrolu) motordan bagimsiz
test edilebilir oldugu icin bu yeterli.
"""

from app.risk import risk_hesapla, CONFIDENCE_THRESHOLD


class SahteMotor:
    """motor.oner() ile ayni sekilde davranan, sabit sonuc donen test cifti."""

    def __init__(self, sonuclar):
        self._sonuclar = sonuclar

    def oner(self, esya_tanimi, top_k=3):
        return self._sonuclar[:top_k]


def _oneri(gtip, skor, kaynak_tipi="btb_karari", gerekce="test gerekcesi"):
    return {
        "benzerlik_skoru": skor,
        "onerilen_gtip": gtip,
        "kaynak_tipi": kaynak_tipi,
        "referans_btb_no": "TR000000000000",
        "referans_esya_tanimi": "test esya tanimi",
        "gerekce": gerekce,
    }


def test_ayni_pozisyon_dusuk_risk():
    motor = SahteMotor([_oneri("630790100019", skor=0.85)])
    sonuc = risk_hesapla("630712340019", "test urun", motor)
    assert sonuc["risk_seviyesi"] == "dusuk"
    assert sonuc["onerilen_gtip"] == "630790100019"


def test_farkli_pozisyon_yuksek_skor_yuksek_risk():
    motor = SahteMotor([_oneri("630790100019", skor=CONFIDENCE_THRESHOLD + 0.1)])
    sonuc = risk_hesapla("902110000019", "test urun", motor)
    assert sonuc["risk_seviyesi"] == "yuksek"


def test_farkli_pozisyon_dusuk_skor_belirsiz():
    motor = SahteMotor([_oneri("630790100019", skor=CONFIDENCE_THRESHOLD - 0.05)])
    sonuc = risk_hesapla("902110000019", "test urun", motor)
    assert sonuc["risk_seviyesi"] == "belirsiz"


def test_esik_sinirinda_esitlik_yuksek_risk_sayilir():
    """CONFIDENCE_THRESHOLD'a esit skor 'yuksek' tarafina dusmeli (kod < kullaniyor, <= degil)."""
    motor = SahteMotor([_oneri("630790100019", skor=CONFIDENCE_THRESHOLD)])
    sonuc = risk_hesapla("902110000019", "test urun", motor)
    assert sonuc["risk_seviyesi"] == "yuksek"


def test_diger_emsaller_ilk_sonucu_icermez():
    motor = SahteMotor([
        _oneri("630790100019", skor=0.9),
        _oneri("630711110019", skor=0.5),
        _oneri("630722220019", skor=0.4),
    ])
    sonuc = risk_hesapla("630790100019", "test urun", motor)
    assert len(sonuc["diger_emsaller"]) == 2
    assert sonuc["diger_emsaller"][0]["onerilen_gtip"] == "630711110019"


def test_gerekceli_aciklama_alaninin_var_olmasi():
    motor = SahteMotor([_oneri("630790100019", skor=0.9, kaynak_tipi="btb_karari")])
    sonuc = risk_hesapla("630712340019", "test urun", motor)
    assert sonuc["gerekceli_aciklama"]["kanit_seviyesi"] == "guclu"
