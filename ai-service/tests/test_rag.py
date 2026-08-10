"""
rag.py icin testler. Gercek kurallar_kutuphanesi.csv'yi kullanir (network
gerektirmez, hafif bir CSV okuma) - GtipOneriMotoru'na ihtiyac yok.
"""

from app.rag import gerekce_uret, ilgili_kurallari_bul


def _oneri(kaynak_tipi, gtip="630790100019", btb_no="TR340000250155", gerekce="gercek BTB gerekcesi"):
    return {
        "onerilen_gtip": gtip,
        "kaynak_tipi": kaynak_tipi,
        "referans_btb_no": btb_no,
        "referans_esya_tanimi": "test esya tanimi",
        "gerekce": gerekce,
    }


def test_btb_karari_guclu_kanit():
    sonuc = gerekce_uret(_oneri("btb_karari"))
    assert sonuc["kanit_seviyesi"] == "guclu"
    assert sonuc["btb_gerekcesi"] == "gercek BTB gerekcesi"
    assert "TR340000250155" in sonuc["ozet"]


def test_resmi_kod_zayif_kanit():
    sonuc = gerekce_uret(_oneri("resmi_kod"))
    assert sonuc["kanit_seviyesi"] == "zayif"
    assert "emsali bulunamadi" in sonuc["btb_gerekcesi"]


def test_pozisyona_ozel_kural_eslesiyor():
    kurallar = ilgili_kurallari_bul("6307")
    kural_idler = {k["kural_id"] for k in kurallar}
    assert "POZ-6307" in kural_idler


def test_gyk_tum_pozisyonlarda_gosteriliyor_regresyon():
    """Faz 7'de duzeltilen bug: GYK 1-6 eskiden sadece 61-64 pozisyonlarina
    hardcode'luydu, kod listesi tum tarifeye genisleyince (orn. 8501 gibi
    tekstil-disi bir pozisyonda) GYK hic gosterilmiyordu. Bu test o
    duzeltmenin geri gelmemesini garantiliyor."""
    kurallar = ilgili_kurallari_bul("8501")
    kural_idler = {k["kural_id"] for k in kurallar}
    assert "GYK-1" in kural_idler
    assert "GYK-6" in kural_idler


def test_ilgisiz_pozisyona_ozel_not_eklenmiyor():
    kurallar = ilgili_kurallari_bul("8501")
    kural_idler = {k["kural_id"] for k in kurallar}
    assert "POZ-6307" not in kural_idler
