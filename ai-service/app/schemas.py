from pydantic import BaseModel, Field
from typing import List


class OneriRequest(BaseModel):
    esya_tanimi: str = Field(..., description="Siniflandirilmasi istenen esyanin serbest metin tanimi")
    top_k: int = Field(3, ge=1, le=10, description="Kac tane emsal/oneri donsun")


class OneriSonucu(BaseModel):
    benzerlik_skoru: float
    onerilen_gtip: str
    kaynak_tipi: str  # "btb_karari" (gercek emsal) veya "resmi_kod" (sadece pozisyon basligi)
    referans_btb_no: str
    referans_esya_tanimi: str
    gerekce: str


class OneriResponse(BaseModel):
    sorgu: str
    sonuclar: List[OneriSonucu]


class RiskAnaliziRequest(BaseModel):
    beyan_edilen_gtip: str = Field(..., description="Beyannamede beyan edilen GTIP kodu")
    esya_tanimi: str = Field(..., description="Eşyanın serbest metin tanımı")
    top_k: int = Field(3, ge=1, le=10)


class IlgiliKural(BaseModel):
    kural_id: str
    metin: str


class GerekceliAciklama(BaseModel):
    kanit_seviyesi: str  # "guclu" (gercek BTB emsali var) veya "zayif" (sadece resmi kod)
    ozet: str
    btb_gerekcesi: str
    ilgili_genel_kurallar: List[IlgiliKural]
    kaynak_linki: str
    kaynak_notu: str


class RiskAnaliziResponse(BaseModel):
    risk_seviyesi: str  # "dusuk" | "yuksek" | "belirsiz"
    aciklama: str
    beyan_edilen_gtip: str
    onerilen_gtip: str
    benzerlik_skoru: float
    gerekceli_aciklama: GerekceliAciklama
    diger_emsaller: List[OneriSonucu]


class FeedbackRequest(BaseModel):
    esya_tanimi: str = Field(..., description="Degerlendirilen esya tanimi")
    beyan_edilen_gtip: str = Field("", description="Varsa beyan edilen GTIP")
    onerilen_gtip: str = Field(..., description="Sistemin onerdigi GTIP")
    dogru_mu: bool = Field(..., description="Kullanici oneriyi dogru buldu mu")
    dogru_gtip: str = Field("", description="Eger yanlissa, kullanicinin belirttigi dogru GTIP (opsiyonel)")
    notlar: str = Field("", description="Serbest metin not (opsiyonel)")


class FeedbackResponse(BaseModel):
    durum: str
    kayit_id: int