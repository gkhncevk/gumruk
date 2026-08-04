# GTİP Risk & Gerekçelendirme Asistanı

**Bir beyannamedeki eşya tanımı ve beyan edilen GTİP kodunu analiz eden, gerçek Bağlayıcı Tarife Bilgisi (BTB) kararlarına ve resmi sınıflandırma kurallarına dayanarak risk skoru + hukuki gerekçe üreten bir gümrük karar destek sistemi.**

Sistem sadece "bu ürün X kodudur" demiyor — **neden** olduğunu, hangi gerçek BTB kararına veya hangi Genel Yorum Kuralı'na dayandığını açıkça gösteriyor. Bu, bir "demo script"ten çok bir karar destek aracı gibi davranmasını sağlıyor.

---

## 1. Problem

Gümrük beyannamelerinde yanlış GTİP (Gümrük Tarife İstatistik Pozisyonu) seçimi, işletmeler için iki yönlü risk taşır: ya gereğinden fazla vergi ödenir, ya da eksik beyan nedeniyle sonradan ceza/faiz riski doğar. Binlerce kalemlik beyannamelerde bu hataları manuel yakalamak pratik değildir. Gümrük müşavirleri genelde geçmiş emsal kararlara (BTB) ve Tarife Cetveli'nin genel yorum kurallarına bakarak karar verir — bu proje, bu süreci kısmen otomatikleştirmeyi hedefliyor.

## 2. Ne yapıyor

Bir eşya tanımı (serbest metin) ve isteğe bağlı olarak beyan edilen bir GTİP kodu verildiğinde:

1. **GTİP önerisi** — eşyaya en yakın gerçek BTB kararlarını ve/veya resmi pozisyon başlıklarını bulup bir kod önerir.
2. **Risk skoru** — beyan edilen kod ile öneri farklıysa, ne kadar güvenilir bir uyuşmazlık olduğunu (düşük / yüksek / belirsiz) hesaplar.
3. **Gerekçeli açıklama** — önerinin dayandığı gerçek BTB kararını (varsa) ve ilgili genel sınıflandırma kurallarını (GYK 1-6, ilgili fasıl notları) birlikte sunar; kaynağı doğrulaman için resmi BTB arama sistemine link verir.
4. **Geri bildirim döngüsü** — kullanıcı öneriyi doğru/yanlış olarak işaretleyebilir; bu veri ileride sistemi kalibre etmek için biriktirilir.

## 3. Mimari

```
tarayıcı  →  React (frontend/)  →  Node.js / Express (backend/)  →  Python / FastAPI (ai-service/)
                                          :3000                            :8000
```

| Katman | Teknoloji | Görev |
|---|---|---|
| `frontend/` | React (Vite) | Beyan formu, risk/gerekçe görselleştirme, geri bildirim butonları |
| `backend/` | Node.js / Express | AI servisini proxy'ler, frontend build'ini sunar, CORS/güvenlik katmanı |
| `ai-service/` | Python / FastAPI | GTİP öneri motoru, risk skorlama, gerekçelendirme (RAG-lite) |

Bu ayrım bilinçli: kurumsal backend (Node.js/.NET) ile AI servisini (Python) ayrı mikroservisler olarak tutmak, hem her katmanı bağımsız test edilebilir kılıyor hem de gümrük/dış ticaret sektöründeki şirketlerin (örn. Atez Yazılım) kullandığı tipik mimariyle örtüşüyor.

## 4. Teknik kararlar ve neden öyle verildiği

Bu proje boyunca alınan her mimari karar bilinçli bir trade-off'un sonucu — bunları gizlemek yerine burada açıkça belgeliyorum, çünkü "neden bunu seçtim" sorusuna cevap verebilmek "nasıl yaptım"dan daha değerli:

- **Hibrit arama — TF-IDF + gerçek semantik embedding (Faz 8):** Kapsam tüm tarifeye (~15.700 kod) genişleyince, karakter n-gram TF-IDF'in gerçek sınırı ortaya çıktı: "cep telefonu kılıfı" gibi gündelik bir sorgu, resmi tarife dilindeki "silikon yağları" gibi bir ham madde satırına kayabiliyordu — TF-IDF kelime/harf benzerliğine bakıyor, anlama değil. Buna karşılık tek başına semantik embedding'in de kendi zayıflığı çıktı: iki farklı model denendi, biri uzun/teknik BTB dilinde iyiydi ama kısa/günlük kelimelerde bozuluyordu ("çorap" sorgusu "kopra" — kurutulmuş hindistan cevizi — ile eşleşti), diğeri tam tersi. Çözüm: iki sinyali birlikte kullanan hibrit bir puanlama (`ai-service/app/retrieval.py`) — modern arama sistemlerinin ("hybrid search") standart yaklaşımı. Gerçek testte doğrulandı: hem uzun/teknik hem kısa/günlük sorgular artık doğru pozisyona yöneliyor, skorlar yapay şekilde şişirilmeden (%25-95 arası, sorgunun gerçek belirsizliğini yansıtacak şekilde) geliyor.
- **RAG-lite (LLM'siz) gerekçelendirme:** Doğal dilde gerekçe üretimi için bir LLM (OpenAI/Anthropic) kullanmak yerine, retrieval + şablon tabanlı deterministik formatlama tercih edildi. Gerekçe, LLM'in "uydurması" değil, gerçek BTB metninin veya gerçek kural metninin doğrudan kendisi — bu, hukuki/mali sonucu olan bir alanda "halüsinasyon" riskini sıfırlıyor. LLM entegrasyonu ileride `ai-service/app/rag.py`'deki çıktının üzerine ince bir "akıcılaştırma" katmanı olarak eklenebilir.
- **İki katmanlı kapsam (Faz 7 — kod listesi geniş, BTB derin):** Sistem iki farklı veri katmanını bilinçli olarak ayrı tutuyor. (1) **Resmi kod listesi**: artık fasıl 61-64 ile sınırlı değil, Ticaret Bakanlığı'nın resmi Tarife Cetveli'nden (aşağıya bkz.) parse edilen **tüm gümrük tarifesini** (fasıl 1-97, ~15.700 kod) kapsıyor — Mod 1 (öneri) her ürün kategorisi için makul bir kod ailesi önerebiliyor. (2) **BTB kararları (gerçek emsal + gerekçe)**: bilinçli olarak fasıl 61-64'te derin tutuldu — binlerce kararı manuel doğrulamak bu aşamada gerçekleştirilebilir değil. Sistem bu ayrımı kullanıcıdan gizlemiyor: `kanit_seviyesi` alanı her zaman hangi katmandan geldiğini şeffafça işaretliyor ("güçlü kanıt" vs "zayıf kanıt, sadece resmi kod").
- **Resmi kod listesinin kaynağı — artık tahmine dayanmıyor:** İlk versiyonda `resmi_kod_listesi_61_64.csv` yazarın bilgisinden elle derlenmiş ~50 satırlık bir listeydi (README'de açıkça "doğrulanmalı" diye işaretlenmişti). Faz 7'de bu, Ticaret Bakanlığı'nın resmi "İstatistik Pozisyonlarına Bölünmüş Türk Gümrük Tarife Cetveli" Excel yayınından (`ggm.ticaret.gov.tr`, Karar Sayısı 10781, 30 Aralık 2025 tarihli Resmi Gazete) otomatik parse edilerek üretildi (`ai-service/scripts/parse_tarife_cetveli.py`). Script, Excel'in tire-derinlikli hiyerarşisini (`- / - - / - - -`) ve kelime ortasından tire ile bölünmüş satırları (Excel word-wrap) çözüp her 12 haneli kod için tam ata-zinciri açıklamasını üretiyor. Doğrulama: elimizdeki 41 gerçek BTB kararının **tamamının** GTİP kodu bu listede birebir eşleşiyor (41/41).
- **Bilinçli dar kapsam (BTB emsal derinliği, fasıl 61-64):** Gerçek, gerekçeli BTB kararı derinliği tekstil giyim + diğer hazır tekstil eşyası + ayakkabı aksamına bilerek sınırlı tutuldu. Mimari fasıl-bağımsız çalıştığı için genişletmek yeni kod değil, yeni veri (daha fazla BTB kararı) eklemek demek.
- **Veri kaynağının doğrulanmış eksiksizliği:** Kullanılan 41 BTB kararı rastgele bir örneklem değil — resmi BTB arama sisteminde ilgili fasıllar için mevcut olan **kararların tamamı** (exhaustive search ile doğrulandı, tahmine dayanmıyor).

## 5. Ölçülmüş doğruluk (leave-one-out değerlendirme)

`ai-service/evaluate.py`, her BTB kararını sırayla veri setinden çıkarıp "hiç görülmemiş yeni ürün" gibi test ediyor (tam rapor: `ai-service/DEGERLENDIRME_RAPORU.md`).

| Metrik | Değer |
|---|---|
| Genel Top-1 doğruluk | %73.2 (30/41) |
| Genel Top-3 doğruluk | %78.0 (32/41) |
| Çoğunluk baseline'ı | %65.9 |
| **Yeterli emsali olan pozisyonlarda (n≥2) doğruluk** | **%88.2 (30/34)** |
| Tek örnekli pozisyonlarda | 0/7 (yapısal olarak beklenen, aşağıda açıklanıyor) |

**Önemli bulgu:** Veri setindeki 7 pozisyonun sadece 1'er BTB kararı var. Leave-one-out o tek kararı çıkarınca geriye hiç emsal kalmıyor — bu düşük performans model kalitesizliği değil, **veri azlığının yapısal ve kanıtlanmış bir sonucu** (BTB arama sisteminde bu pozisyonlar için başka kayıt olmadığı doğrulandı). Bu ayrımı yapmadan tek bir doğruluk rakamı vermek yanıltıcı olurdu; segmentli analiz gerçek performansı gösteriyor.

**Kapsam genişletmesinin doğruluğa maliyeti (dürüstçe):** Faz 7'de resmi kod listesi ~50 satırdan ~15.700 satıra çıkınca (bkz. bölüm 4), yeterli-veri doğruluğu %91.2'den %88.2'ye düştü. Nedenini tek tek inceledim: sorun resmi kod satırlarının BTB sonuçlarını "sistematik olarak" bastırması değil — motoru bir kere kurup BTB satırlarına yapay bir öncelik vermeyi (ağırlıklandırma) denedim, hiçbir ağırlık değeri sonucu değiştirmedi. Gerçek neden, birkaç zor sorguda artık daha geniş kelime dağarcığındaki bir resmi kod satırının (örn. "temizleme süngeri" sorgusu için "ev eşyaları" pozisyonu) doğru BTB emsalinden yüzeysel olarak daha fazla n-gram paylaşması. Bu, karakter n-gram TF-IDF'in zaten bilinen semantik-olmama sınırının, havuz büyüdükçe daha sık görünür hale gelmesi — yapay olarak "düzeltilmedi", çünkü gerçek çözüm (semantik embedding) zaten bilinen bir sonraki adım (bkz. bölüm 4). %88.2 hâlâ çoğunluk baseline'ının (%65.9) belirgin şekilde üzerinde.

## 6. API

Backend üzerinden (`http://localhost:3000/api/...`) veya doğrudan AI servisinden (`http://localhost:8000/...`, Swagger: `/docs`) erişilebilir.

| Endpoint | Metod | Açıklama |
|---|---|---|
| `/risk-analizi` | POST | Ana uç nokta — beyan edilen GTİP + eşya tanımı → risk skoru + gerekçeli açıklama + alternatif emsaller |
| `/oneri` | POST | Sadece GTİP önerisi (risk/gerekçe hesaplamaz) |
| `/feedback` | POST | Kullanıcının öneriyi doğru/yanlış işaretlemesi |
| `/` | GET | Health check |

## 7. Kurulum ve çalıştırma

**1. Python AI servisi:**
```bash
cd ai-service
python3 -m venv venv && source venv/bin/activate   # Windows: venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --port 8000
```

**2. Node.js backend** (frontend build'i ile birlikte gelir):
```bash
cd backend
npm install
npm start
```

**3. Tarayıcıda aç:** `http://localhost:3000`

Frontend kaynağını değiştirirsen tekrar build etmen gerekir: `cd frontend && npm install && npm run build`

## 8. Demo senaryosu

1. Arayüzde **"Örnek 1"** — beyan edilen kod `9021` (tıbbi ortopedik cihaz), eşya bir diz destek bandı → **YÜKSEK RİSK**: sistem 63.07 öneriyor, gerekçe olarak gerçek bir BTB kararına (Ottobock diz bandı) ve Tarife Cetveli İzahnamesi'nin 90. Fasıl 1(b) notuna atıf yapıyor.
2. **"Örnek 2"** — aynı ürün, bu sefer doğru kod (6307) beyan edilmiş → **DÜŞÜK RİSK**.
3. **"Örnek 3"** — hiç BTB emsali olmayan bir ürün (düz tişört) → sistem yine bir öneri veriyor ama "zayıf kanıt" etiketiyle, dürüstçe emsalsizliği belirtiyor.
4. Anlatılacak nokta: sistem sadece kod tahmin etmiyor, kanıt seviyesini de açıkça ayırıyor — bu, gümrük müşavirleri için asıl değerli olan kısım.

## 9. Proje yapısı

```
├── ai-service/          # Python/FastAPI - öneri motoru, risk skorlama, gerekçelendirme
│   ├── app/              # retrieval.py, risk.py, rag.py, feedback.py, main.py, schemas.py
│   ├── data/              # BTB kararları, resmi kod listesi (tüm fasıllar), kural kütüphanesi, feedback log
│   ├── scripts/           # parse_tarife_cetveli.py - resmi Tarife Cetveli Excel'lerini parse eden script
│   ├── evaluate.py         # leave-one-out değerlendirme scripti
│   ├── DEGERLENDIRME_RAPORU.md
│   └── README.md          # ai-service'e özel derinlemesine teknik dokümantasyon
├── backend/              # Node.js/Express - proxy + statik dosya sunumu
└── frontend/             # React (Vite) - kullanıcı arayüzü
```

## 10. Bilinen sınırlar (dürüstçe)

- Kural kütüphanesindeki GYK 1-6 artık Ticaret Bakanlığı'nın resmi "yorum kuralları" yayınından birebir (verbatim) alındı — yazarın özeti değil. Ama pozisyona özel notlar (`FASIL90-NOT1B`, `POZ-6307` vb.) hâlâ elle derlendi, resmi metinle birebir doğrulanmadı.
- Hibrit arama (Faz 8) TF-IDF'in saf semantik sınırını büyük ölçüde giderdi, ama kombinasyon ağırlığı (0.5/0.5 TF-IDF/embedding) hâlâ elle konulmuş bir ilk tahmin — gerçek feedback verisiyle ince ayar yapılabilir.
- Risk eşiği (0.15) artık eski TF-IDF-only skor dağılımına göre konulmuştu; hibrit skorlarla (gözlemlenen aralık ~%25-95) yeniden kalibre edilmesi gerekiyor — bu adım henüz yapılmadı.
- Değerlendirme veri seti küçük (n=41) — istatistiksel güç sınırlı, güven aralığı geniş.
- BTB kararları (güçlü kanıt katmanı) hâlâ sadece fasıl 61-64'te; tüm tarife için bu derinliği sağlamak manuel doğrulama gerektiriyor, ölçeklenebilir değil.

Bu sınırların hepsi ilgili kod dosyalarında ve `ai-service/README.md`'de daha ayrıntılı belgelendi.

## 11. Yol haritası

- [x] Resmi kod listesini tüm fasıllara genişletmek (Faz 7 — bkz. bölüm 4, mimari fasıl-bağımsız çalıştığı için kod değişikliği gerekmedi)
- [x] TF-IDF'ten hibrit (TF-IDF + semantik embedding) aramaya geçiş (Faz 8 — bkz. bölüm 4)
- [ ] BTB emsal derinliğini kademeli olarak başka fasıllara da yaymak
- [ ] Risk eşiğini (CONFIDENCE_THRESHOLD) yeni hibrit skor dağılımına göre kalibre etmek
- [ ] `evaluate.py`'yi hibrit motorla yeniden çalıştırıp güncel doğruluk rakamlarını raporlamak
- [ ] İsteğe bağlı LLM katmanıyla gerekçe metnini akıcılaştırmak
- [ ] Görsel/multimodal sınıflandırma (bilerek şimdilik ertelendi — bkz. tasarım notları)

---

*Güncel ve kullanılan her şey `ai-service/`, `backend/`, `frontend/` içindedir.*