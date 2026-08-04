# Degerlendirme Raporu - Leave-One-Out Test

Test tarihi/yontemi: 41 gercek BTB karari uzerinde leave-one-out capraz dogrulama.
Her kayit sirayla veri setinden cikarilip, kalan verilerle o kaydin GTIP pozisyonu tahmin edilmeye calisildi.

## Sonuclar

- **Test seti buyuklugu:** 41 (kucuk bir ornek, guven araligi genis - temkinli yorumlanmali)
- **Model Top-1 dogruluk:** 73.2% (30/41)
- **Model Top-3 dogruluk:** 78.0% (32/41)
- **Cogunluk baseline'i:** 65.9% (her zaman '6307' tahmin etseydik)
- **Rastgele baseline:** 11.0%
- **Modelin cogunluk baseline'ina gore farki:** +7.3%

## Segmentli Analiz (asil onemli kisim)

Veri setindeki 7 pozisyonun (['6113', '6116', '6210', '6211', '6212', '6302', '6306']) sadece 1'er ornegi var. Leave-one-out yontemi bu tek ornegi cikardiginda, o pozisyon icin geriye hic BTB emsali kalmiyor - yani bu 7 kaydin basarisiz olmasi **yapisal bir zorunluluk**, model kalitesizligi degil. Bu, veri toplamaya devam etme ihtiyacinin kanitidir (her pozisyon icin en az birkac ornek gerekli).

Asil anlamli sinyal, yeterli ornegi olan pozisyonlardaki performans:

- **Yeterli ornekli pozisyonlar (n>=2):** 30/34 = 88.2% dogruluk
  - 6307: 24/27 = 88.9%
  - 6406: 6/7 = 85.7%

## Not

Bu degerlendirme kucuk (n=41) bir veri seti uzerinde yapilmistir, istatistiksel olarak guclu bir genelleme icin yetersizdir. Daha fazla BTB karari toplandikca bu test tekrarlanip guven araligi daraltilmalidir. Yine de mevcut haliyle, modelin kor/cogunluk tahmininden anlamli sekilde iyi olup olmadigini gosteren dogru bir ilk sinyaldir.
