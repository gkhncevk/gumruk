"""
Feedback mekanizmasi - kullanicinin oneriyi dogru/yanlis olarak
isaretlemesini basit bir CSV dosyasina kaydeder.

Onemli: bu "fine-tuning" yapmiyor, sadece VERI TOPLUYOR. Su an elimizde
41 BTB kaydi var - bir modeli fine-tune etmek icin bu cok az. Bunun yerine
gercekci hedef: zamanla biriken feedback verisiyle (a) risk esigini
(CONFIDENCE_THRESHOLD, bkz. risk.py) kalibre etmek, (b) hangi urun
turlerinde sistemin sik yanildigini gormek, (c) yeterince biriktiginde
yeni BTB emsali gibi kullanmak. Bu dosya sadece 1. adimin altyapisi.
"""

import csv
import os
from datetime import datetime, timezone

FEEDBACK_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "feedback_log.csv")
FIELDS = ["id", "zaman", "esya_tanimi", "beyan_edilen_gtip", "onerilen_gtip", "dogru_mu", "dogru_gtip", "notlar"]


def _dosyayi_hazirla():
    if not os.path.exists(FEEDBACK_PATH):
        with open(FEEDBACK_PATH, "w", newline="", encoding="utf-8") as f:
            csv.DictWriter(f, fieldnames=FIELDS).writeheader()


def _sonraki_id():
    _dosyayi_hazirla()
    with open(FEEDBACK_PATH, encoding="utf-8") as f:
        satirlar = list(csv.DictReader(f))
    return len(satirlar) + 1


def feedback_kaydet(esya_tanimi, beyan_edilen_gtip, onerilen_gtip, dogru_mu, dogru_gtip, notlar):
    _dosyayi_hazirla()
    kayit_id = _sonraki_id()
    with open(FEEDBACK_PATH, "a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writerow({
            "id": kayit_id,
            "zaman": datetime.now(timezone.utc).isoformat(),
            "esya_tanimi": esya_tanimi,
            "beyan_edilen_gtip": beyan_edilen_gtip,
            "onerilen_gtip": onerilen_gtip,
            "dogru_mu": dogru_mu,
            "dogru_gtip": dogru_gtip,
            "notlar": notlar,
        })
    return kayit_id