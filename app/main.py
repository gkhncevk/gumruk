"""
FastAPI servisi. Node.js backend'i ileride bu servisi HTTP uzerinden
cagiracak (Faz 5). Simdilik tek basina calisip test edebilmen yeterli.

Calistirmak icin:
    uvicorn app.main:app --reload --port 8000

Sonra taraycida:
    http://localhost:8000/docs
adresine git, interaktif Swagger arayuzunden /oneri endpoint'ini
"Try it out" ile test edebilirsin. Sunucu/curl kurmadan da calisir.
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.schemas import (
    OneriRequest, OneriResponse, RiskAnaliziRequest, RiskAnaliziResponse,
    FeedbackRequest, FeedbackResponse,
)
from app.retrieval import GtipOneriMotoru
from app.risk import risk_hesapla
from app.feedback import feedback_kaydet

app = FastAPI(
    title="GTIP Oneri ve Gerekcelendirme Servisi",
    description="Esya tanimindan GTIP onerisi + risk skoru + BTB/kural emsaline dayali gerekce ureten servis",
    version="0.3.0",
)

# Node.js backend (farkli port) ve tarayicidan dogrudan cagirilar icin CORS.
# Gelistirme asamasinda "*" acik, gercek deploy'da sadece backend'in
# adresine kisitlanmali (bkz. README - Faz 6 notlari).
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Servis ayaga kalkarken veri bir kere yuklenir, her istekte yeniden yuklenmez.
motor = GtipOneriMotoru()


@app.get("/")
def health_check():
    return {"durum": "calisiyor", "yuklu_kayit_sayisi": len(motor.rows)}


@app.post("/oneri", response_model=OneriResponse)
def gtip_oner(request: OneriRequest):
    """Sadece oneri - risk/gerekce hesabi yapmaz, saf retrieval sonucu doner."""
    sonuclar = motor.oner(request.esya_tanimi, top_k=request.top_k)
    return OneriResponse(sorgu=request.esya_tanimi, sonuclar=sonuclar)


@app.post("/risk-analizi", response_model=RiskAnaliziResponse)
def risk_analizi(request: RiskAnaliziRequest):
    """Ana uc nokta: beyan edilen GTIP ile esya tanimini karsilastirir,
    risk seviyesi + gerekceli aciklama + alternatif emsaller doner.
    Frontend'in beyanname kontrol ekrani icin cagiracagi endpoint budur."""
    sonuc = risk_hesapla(request.beyan_edilen_gtip, request.esya_tanimi, motor, top_k=request.top_k)
    return sonuc


@app.post("/feedback", response_model=FeedbackResponse)
def feedback_gonder(request: FeedbackRequest):
    """Kullanicinin oneriyi dogru/yanlis olarak isaretlemesi. Sadece
    veri toplar - otomatik fine-tuning yapmaz (bkz. app/feedback.py notu)."""
    kayit_id = feedback_kaydet(
        esya_tanimi=request.esya_tanimi,
        beyan_edilen_gtip=request.beyan_edilen_gtip,
        onerilen_gtip=request.onerilen_gtip,
        dogru_mu=request.dogru_mu,
        dogru_gtip=request.dogru_gtip,
        notlar=request.notlar,
    )
    return FeedbackResponse(durum="kaydedildi", kayit_id=kayit_id)