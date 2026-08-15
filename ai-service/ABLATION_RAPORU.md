# Ablation Raporu - Arama Konfigurasyonu Karsilastirmasi

Ayni leave-one-out yontemi (bkz. `evaluate.py`, `DEGERLENDIRME_RAPORU.md`), 3 farkli arama konfigurasyonuyla calistirildi. Amac: hibrit (0.7/0.3) agirligin secilme gerekcesini bir anlatiya degil, olculmus bir karsilastirmaya dayandirmak (bkz. `app/retrieval.py` basindaki Faz 8 notu).

| Konfigurasyon | Top-1 doğruluk | Top-3 doğruluk | Yeterli veri (n≥2) doğruluk |
|---|---|---|---|
| Sadece TF-IDF | %73.2 | %78.0 | %88.2 |
| Sadece semantik embedding | %63.4 | %68.3 | %76.5 |
| Hibrit (uretimde kullanilan, 0.7/0.3) | %73.2 | %75.6 | %88.2 |

Test seti büyüklüğü: n=41 (küçük örneklem, bkz. `DEGERLENDIRME_RAPORU.md`'deki güven aralığı notu).
