# GTIP Oneri Servisi (ai-service)

Bir esya tanimi (ve istege bagli olarak beyan edilen bir GTIP kodu) alip:
- en yakin GTIP kod onerisini,
- beyan edilen kodla oneri arasinda uyusmazlik varsa risk skorunu,
- ve bu onerinin dayandigi gerekceyi (gercek BTB karari veya genel kural)

donduren servis. Uc kaynagi birlikte kullanir:

1. **41 gercek BTB (Baglayici Tarife Bilgisi) karari** - gercek emsal + resmi gerekce,
   bilerek fasil 61-64 ile sinirli (BTB emsal derinligi manuel dogrulama gerektirir)
2. **Tum gumruk tarifesinin resmi kod listesi (~15.700 kod, fasil 1-97)** - Faz 7'de
   Ticaret Bakanligi'nin resmi Tarife Cetveli Excel yayinindan otomatik parse edildi
   (bkz. `scripts/parse_tarife_cetveli.py`); BTB emsali olmayan urunler icin bile
   en azindan dogru pozisyon ailesini onerebilmek icin
3. **Kucuk bir kural kutuphanesi** (GYK 1-6, Fasil 90 Not 1(b), pozisyon
   notlari) - onerinin "neden" dogru oldugunu aciklamak icin

## Kurulum (kendi bilgisayarinda)

```bash
cd ai-service
python3 -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

## Test yontem 1 - En hizli (sunucu gerekmez)

Terminalde tek komutla calistir, sonucu gor (input beklemez):

```bash
python app/retrieval.py "diz bolgesinde kullanilan orme destek bandi"
```

Tirnak icindeki metni degistirerek istedigin urun tanimini test edebilirsin.
Argument vermezsen ornek bir sorgu ile calisir.

## Test yontem 2 - Gercek servis (Node.js backend'in ileride kullanacagi yol)

```bash
uvicorn app.main:app --reload --port 8000
```

Sonra tarayicida ac: **http://localhost:8000/docs**

Bu, FastAPI'nin otomatik urettigi interaktif Swagger arayuzu. Iki endpoint var:

- **`/oneri`** - sadece GTIP onerisi (risk/gerekce hesaplamaz, saf retrieval)
- **`/risk-analizi`** - asil kullanilacak endpoint: beyan edilen GTIP + esya
  tanimi verirsin, risk seviyesi + gerekceli aciklama + alternatif emsaller doner

`/risk-analizi`'nin yanindaki "Try it out" butonuna tikla, ornegin:
```json
{
  "beyan_edilen_gtip": "902110000019",
  "esya_tanimi": "diz bolgesinde kullanilan orme destek bandi, cirt bantli",
  "top_k": 3
}
```
"Execute" de. Bu ornekte beyan edilen kod (9021, tibbi ortopedik cihaz) ile
sistemin onerdigi kod (6307) farkli oldugu icin `risk_seviyesi: "yuksek"`
donmesini beklersin.

Istersen curl ile de test edebilirsin:

```bash
curl -X POST http://localhost:8000/risk-analizi \
  -H "Content-Type: application/json" \
  -d '{"beyan_edilen_gtip": "902110000019", "esya_tanimi": "diz bolgesinde kullanilan orme destek bandi", "top_k": 3}'
```

## Klasor yapisi

```
ai-service/
├── data/
│   ├── btb_tekstil_61_64.csv               # 41 gercek BTB karari (emsal + gerekce)
│   ├── resmi_kod_listesi_tum_fasillar.csv  # TUM tarife (~15.700 kod, fasil 1-97) - Faz 7
│   ├── resmi_kod_listesi_61_64.csv         # ayni kaynaktan, sadece fasil 61-64 alt kumesi (referans)
│   └── kurallar_kutuphanesi.csv            # GYK 1-6, Fasil 90 Not 1(b), pozisyon notlari
├── scripts/
│   └── parse_tarife_cetveli.py    # Faz 7: resmi Tarife Cetveli .xls'lerini parse eden script
├── app/
│   ├── retrieval.py               # Faz 2: cekirdek mantik (char n-gram TF-IDF + cosine similarity)
│   ├── risk.py                    # Faz 3: risk skorlama
│   ├── rag.py                     # Faz 4: gerekcelendirme (RAG-lite, LLM'siz)
│   ├── schemas.py                 # istek/yanit veri modelleri
│   └── main.py                    # FastAPI servisi (/oneri, /risk-analizi)
├── requirements.txt
└── README.md
```

Yanit artik `kaynak_tipi` alani iceriyor: `"btb_karari"` (gercek emsal +
gerekce var) veya `"resmi_kod"` (sadece pozisyon basligi, emsal yok).
Frontend'de bu ikisini farkli gostermek mantikli olur (mesela emsal varsa
yesil "guclu kanit" etiketi, sadece resmi kod varsa sari "tahmini" etiketi).

## Yol haritasi - Faz 7: kod listesi genisledi, BTB derinligi neden hala 61-64?

Bu bilincli bir kapsam karari, unutulmus bir sinir degil - ve iki farkli
veri katmani birbirinden ayri dusunulmeli:

- **Resmi kod listesi (Katman 1, genis):** Artik fasil 61-64 ile sinirli
  degil. `scripts/parse_tarife_cetveli.py`, Ticaret Bakanligi'nin resmi
  Tarife Cetveli Excel yayinini (tum ~97 fasil) parse edip tek bir CSV'ye
  cevirir - hicbir tahmine dayanmiyor, birebir resmi kaynaktan. Bu sayede
  Mod 1 (oneri) artik tekstil disi bir urun icin de (ornegin bir elektronik
  parca) makul bir kod ailesi onerebiliyor.
- **BTB karari derinligi (Katman 2, dar - bilerek):** Gercek, gerekceli
  emsal derinligi hala fasil 61-64'te - bu fasillar icin BTB arama
  sisteminde ne kadar veri oldugu tam olarak dogrulandi (exhaustive arama
  yapildi). Bunu tum tarifeye yaymak, binlerce karari tek tek manuel
  dogrulamak demek - bu asamada gerceklestirilebilir degil.
- Sistem mimarisi (retrieval + risk skoru + gerekce) fasil-bagimsiz calisir
  - yani BTB derinligini baska bir fasila (ornegin 84-85 elektronik/makine)
    yaymak icin kod degil, sadece yeni veri (daha fazla BTB karari) eklemek
    yeterli.
- **Sonraki adim:** BTB emsal derinligini kademeli olarak baska fasillara da
  yaymak. Kod listesi tarafinda yapilacak bir sey yok - o zaten tum tarifeyi
  kapsiyor.

## Neden gercek embedding (sentence-transformers) degil de TF-IDF?

Denendi ama bu ortamda `sentence-transformers`'in bagimliligi olan `torch`
kutuphanesinin indirmesi defalarca zaman asimina ugradi - agir bir paket.
Ayni sorun senin bilgisayarinda da yasanabilirdi: ilk kurulumda zaten
scikit-learn'un numpy/scipy'si ilk import'ta yavas kalmisti (hatirlarsan
"donmus" sanmistin), torch eklemek bunu daha da kirilgan hale getirirdi.

Bunun yerine kelime bazli TF-IDF'i **karakter n-gram tabanli TF-IDF**'e
cevirdim (`analyzer="char_wb"`). Bu, Turkce'nin eklemeli yapisini ("bant" /
"bandi" / "banda" gibi farkli cekim eklerini) kelime bazli yontemden çok
daha iyi yakaliyor, hicbir yeni bagimlilik gerektirmiyor. Test sonucu da
bunu dogruladi: "diz bandi" sorgusunda dogru emsal artik 1. sirada.

Ileride gercek semantik embedding'e gecmek istersen, sadece `retrieval.py`
icindeki `TfidfVectorizer` kismini `sentence-transformers` ile degistirmen
yeterli - geri kalan mantik (cosine similarity, sonuc formati) ayni kalir.

## Faz 3 - Risk skorlama nasil calisiyor?

`app/risk.py` icindeki `risk_hesapla()`: beyan edilen GTIP'in ilk 4 hanesini
(pozisyon), motorun onerdigi en iyi eslesmenin 4 hanesiyle karsilastirir.

- Ayniysa -> **dusuk risk**
- Farkliysa ve oneri guvenilirse (benzerlik skoru >= 0.15) -> **yuksek risk**
- Farkliysa ama oneri de zayifsa (benzerlik skoru < 0.15) -> **belirsiz**
  (sistem emin degil, manuel inceleme onerilir - "yuksek risk" demek yerine
  durustce "bilmiyorum" demesi onemli, yoksa yanlis alarm cok olur)

0.15 esigi elle konulmus bir baslangic degeri, gercek "riskli/risksiz"
etiketlenmis beyanname verisiyle kalibre edilmedi - bunu unutma.

## Faz 4 - Gerekcelendirme (RAG-lite) nasil calisiyor?

`app/rag.py` icindeki `gerekce_uret()`: LLM kullanmiyor (boyle karar verdik -
maliyet/API anahtari gerektirmesin diye). Bunun yerine:

1. Eger oneri gercek bir BTB kararindansa (`kaynak_tipi: btb_karari`) ->
   `kanit_seviyesi: "guclu"`, gercek BTB gerekce metni gosterilir.
2. Eger oneri sadece resmi kod listesindense (`kaynak_tipi: resmi_kod`) ->
   `kanit_seviyesi: "zayif"`, emsal olmadigi acikca belirtilir.
3. Her iki durumda da, `kurallar_kutuphanesi.csv`'den o pozisyona iliskin
   genel kurallar (GYK 1-6 her zaman, ayrica pozisyona ozel notlar varsa)
   eklenir.

Bu "RAG-lite" - retrieval var (BTB + kurallar), ama "generation" adimi bir
LLM'in dogal dil sentezi degil, sablon tabanli deterministik formatlama.
Gercek LLM tabanli surume gecmek istersen `gerekce_uret()` fonksiyonunun
sonunda bulunan metinleri bir LLM'e (OpenAI/Anthropic API) verip "bunlari
akici bir paragrafa cevir" diye istemen yeterli olur.

## Bilinen sinirlar

- **Kural kutuphanesi** (`kurallar_kutuphanesi.csv`): GYK 1-6 artik
  Ticaret Bakanligi'nin resmi "yorum kurallari" Excel yayinindan birebir
  (verbatim) alindi - yazarin ozeti degil (Faz 7). Ayrica bu duzeltmede
  gercek bir bug da giderildi: eskiden GYK kurallari tek bir satirda,
  sadece fasil 61-64 pozisyonlarina hardcode edilmis bir listeyle
  tutuluyordu - yani resmi kod listesi tum tarifeye genisleyince (yukarida)
  baska bir fasildaki bir sorguda GYK hic gosterilmiyordu. Simdi her GYK
  kurali "ilgili_pozisyonlar: TUM" ile evrensel isaretlendi, her pozisyon
  icin gosteriliyor (`rag.py` -> `ilgili_kurallari_bul()`). Pozisyona ozel
  notlar (`FASIL90-NOT1B`, `POZ-6307` vb.) hala elle derlendi, resmi
  metinle birebir dogrulanmadi.
- **Karakter n-gram TF-IDF hala tam "anlam" anlamiyor** - kelime/ek benzerligine
  dayaniyor, gercek semantik degil. Kapsam ~15.700 satira cikinca bu sinir
  daha sik gorunur hale geldi: leave-one-out dogrulugu %91.2'den %88.2'ye
  dustu, cunku genis kelime dagarcigindaki bazi resmi kod satirlari yuzeysel
  n-gram ortusmesiyle dogru BTB emsalinin onune geciyor (bkz.
  `DEGERLENDIRME_RAPORU.md`). Bu, gercek semantik embedding'e gecisin neden
  hala yol haritasinda oldugunun somut kaniti.
- **Risk esigi (0.15) kalibre edilmedi** - yukarida aciklandi.
- **BTB (guclu kanit) derinligi hala sadece fasil 61-64'te** - resmi kod
  listesi tum tarifeyi kapsasa da, gercek gerekceli emsal sadece bu
  fasillarda var; baska fasillardaki oneriler her zaman "zayif kanit"
  etiketiyle gelir.
