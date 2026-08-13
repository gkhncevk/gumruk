"""
GTIP Oneri Motoru - cekirdek mantik.

Bu modul, main.py (FastAPI servisi) tarafindan import edilir; ayni zamanda
tek basina, tek satirlik komutla test edilebilir (input beklemez):

    python app/retrieval.py "diz bolgesinde kullanilan orme destek bandi"

Tirnak icindeki metni degistirerek istedigin urun tanimini test edebilirsin.

---
NOT (Faz 8 - hibrit arama: TF-IDF + semantik embedding):
Once (Faz 2) sadece karakter n-gram TF-IDF kullanildi. Faz 7'de resmi kod
listesi ~15.700 kayda cikinca TF-IDF'in gercek sinirini gorduk: "cep
telefonu kilifi" gibi gundelik sorgular, resmi tarife dilindeki "silikon
yaglari" gibi HAM MADDE satirlarina kayabiliyordu - TF-IDF kelime/harf
benzerligine bakiyor, ANLAMA degil (kelime dagarcigi uyusmazligi).

Bunun uzerine gercek semantik embedding'e (sentence-transformers)
gecildi. Ama tek basina embedding'in de kendi zayifligi ortaya cikti -
yerel testlerde (bkz. proje sohbet gecmisi) iki farkli model denendi:
  - paraphrase-multilingual-MiniLM-L12-v2 (50+ dil): uzun/detayli BTB
    dilini iyi yakaliyordu ("diz bandi" tam cumlesiyle dogru BTB karari
    buluyordu, sim ~0.68), AMA kisa/nadir Turkce kelimelerde bozuluyordu
    ("corap" sorgusu "kopra" - kurutulmus hindistan cevizi - ile
    eslesiyordu, sim ~0.84, tamamen yanlis).
  - emrecan/bert-base-turkish-cased-mean-nli-stsb-tr (Turkce'ye ozel):
    kisa kelimede DUZELDI ("corap" dogru pozisyona eslesti), AMA ayni
    "diz bandi" uzun cumlesinde BTB karari kayboldu, hic ust siraya
    gelmedi (skor ~0.63'e dustu, hicbiri BTB degildi).

Yani IKI modelin de birbirini tamamlayan zayifliklari var - biri uzun/
teknik dilde iyi, digeri kisa/gunluk dilde iyi. Bunun icin TEK bir model
secmek yerine HIBRIT bir yaklasim kullanilyor: TF-IDF (kelime/harf
benzerligi, teknik/uzun ifadelerde guclu) ve semantik embedding (anlam
benzerligi, kisa/gunluk ifadelerde guclu) skorlari birlikte hesaplanip
normalize edilip ortalanıyor. Bu, modern arama sistemlerinde ("hybrid
search") standart bir teknik - tek bir yontemin korlugune guvenmek
yerine iki farkli sinyali birlestirmek.

NOT (dogrulama): Bu kod, gelistirme ortaminda (sandbox) huggingface.co/
pytorch.org agi engellendigi icin BURADA calistirilamadi - kullanicinin
kendi bilgisayarinda test edildi. Tekil sorgularda sonuclar olumlu:
"diz bandi" (uzun/teknik ifade) BTB kararina %87-94 benzerlikle dogru
eslesti; "corap" (kisa ifade) resmi koda dogru eslesti; ayrica "cep
telefonu kilifi", "laptop sarj adaptoru", "plastik su sisesi", "kadin
cantasi" gibi daha once (TF-IDF ve tek-model embedding'de) basarisiz
olan sorgular da dogru fasila/pozisyona yonlendi.

AMA objektif evaluate.py (41 kayit, leave-one-out) sonucu farkli bir
resim gosterdi: ilk denenen 0.5/0.5 (TF-IDF/embedding) agirligi ile
Top-1 dogruluk %65.9'a dustu - eski saf TF-IDF'in %73.2'sinin altinda,
hatta cogunluk-tahmini baseline'ini (%65.9) bile gecemedi. Sebep: bu
test seti BTB'nin kendi teknik/BUYUK HARF diline dayaniyor - tam olarak
TF-IDF'in guclu oldugu senaryo. Embedding'i %50 agirlikla katmak bu dar
teknik alanda TF-IDF'in kesinligini seyreltti; kazanc ("cep telefonu
kilifi" gibi gundelik sorgular) evaluate.py'nin olctugu seyden farkli
bir eksende.

Duzeltme: agirlik TFIDF_AGIRLIK=0.7 / EMBEDDING_AGIRLIK=0.3'e cekildi.
Bu ayarla evaluate.py sonucu: Top-1 %73.2 (30/41), Top-3 %75.6 (31/41),
yeterli veri (n>=2) %88.2 (30/34), cogunluk baseline'inin +7.3 puan
uzerinde - yani eski saf TF-IDF seviyesini yakaladik, gundelik sorgu
iyilestirmesini byuk olcude koruyarak. Skor dagilimi da onemli bir not:
dogru tahminlerin benzerligi 0.24-0.96, yanlislarinki 0.26-0.65 arasinda
- bu iki grup buyuk olcude cakisiyor, yani tek basina benzerlik skoru
"dogru mu yanlis mi" sorusunu net ayirmiyor (bkz. risk.py'deki
CONFIDENCE_THRESHOLD notu). Ileri duzey ince ayar (feedback verisiyle,
daha buyuk test setiyle) gelecekte yapilabilir.
---
NOT (kapsam genisletme - Faz 7):
Iki farkli veri kaynagi birlestiriliyor:
  1) btb_tekstil_61_64.csv - 41 gercek BTB karari (emsal + gerekce icerir),
     kapsam bilerek fasil 61-64 ile sinirli tutuldu (manuel dogrulama
     gerektirdigi icin genisletmesi pahali).
  2) resmi_kod_listesi_tum_fasillar.csv - TUM gumruk tarifesinin (fasil
     1-97, fasil 77 harici) tam 12 haneli GTIP kod + aciklama listesi
     (~15.700 kayit). Ticaret Bakanligi'nin resmi Tarife Cetveli Excel
     yayinindan otomatik parse edildi (scripts/parse_tarife_cetveli.py).
Sistem hicbir BTB emsali olmayan bir urun icin bile en azindan doğru resmi
kod ailesini onerebiliyor - ama bu oneri her zaman "zayif kanit" (resmi
kod, BTB emsali yok) etiketiyle isaretleniyor.
"""

import csv
import hashlib
import os
import sys
import traceback

print(">>> sklearn + sentence-transformers/torch yukleniyor... (ilk calistirmada model de "
      "indirilecekse birkac dakika surebilir, donmadi, bekle)", flush=True)
import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
from sentence_transformers import SentenceTransformer
print(">>> Kutuphaneler yuklendi.", flush=True)

BASE_DIR = os.path.dirname(__file__)
BTB_PATH = os.path.join(BASE_DIR, "..", "data", "btb_tekstil_61_64.csv")
RESMI_KOD_PATH = os.path.join(BASE_DIR, "..", "data", "resmi_kod_listesi_tum_fasillar.csv")
EMBEDDING_CACHE_DIR = os.path.join(BASE_DIR, "..", "data", ".embedding_cache")

MODEL_ADI = "emrecan/bert-base-turkish-cased-mean-nli-stsb-tr"

# TF-IDF ve embedding skorlarini birlestirirken her birine verilen agirlik.
# Ilk deneme 0.5/0.5 idi, ama evaluate.py (41 BTB kaydiyla leave-one-out)
# bunun BTB-tarzi TEKNIK sorgularda dogrulugu dusurdugunu gosterdi
# (%73.2 -> %65.9) - cunku evaluate.py'nin test ettigi sorgular zaten
# BTB'nin kendi resmi/teknik diliyle yazili, ki bu TF-IDF'in en guclu
# oldugu senaryo. Embedding'in asil faydasi gundelik dildeki sorgularda
# (evaluate.py bunu olcmuyor). Bu yuzden TF-IDF'e daha fazla agirlik
# verildi - teknik dogrulugu geri kazanirken gundelik dil faydasini
# tamamen kaybetmemeyi hedefliyor. Bu deger evaluate.py ile tekrar
# olculup ayarlanmali.
TFIDF_AGIRLIK = 0.7
EMBEDDING_AGIRLIK = 0.3


# NOT: Once burada sorgu-bazli min-max normalizasyon vardi (her sorgunun
# kendi en iyi/en kotu adayina gore 0-1'e olcekleniyordu). Bu YANLIS -
# gercek testte "corap" sorgusu %99 gibi asiri yuksek bir "guven" skoru
# aldi, ama bu skor sadece "bu sorgunun EN IYI adayi, AYNI sorgunun EN
# KOTU adayina gore" anlamina geliyordu - adayin kendisi objektif olarak
# iyi mi kotu mu, bunu hic yansitmiyordu. Sorgu-bazli normalizasyonda EN
# IYI aday matematiksel olarak HER ZAMAN ~1.0'a yakin cikar, ne kadar
# kotu olursa olsun - bu da risk.py'deki CONFIDENCE_THRESHOLD mantigini
# (dusuk skor = "belirsizim" de) anlamsizlastirir. Duzeltme: sorguya gore
# DEGIL, SABIT bir olcekte (ham cosine similarity degerleri, ikisi de
# zaten dogal olarak ~0-1 araliginda) agirlikli ortalama aliniyor -
# boylece bir sorgunun "en iyi" adayi objektif olarak kotu bir esleşmeyse
# skoru da dusuk kalir, farkli sorgular arasinda karsilastirilabilir olur.


class GtipOneriMotoru:
    """Iki kaynagi birlikte kullanan hibrit retrieval motoru:
    - BTB kararlari: gercek emsal + gerekce (daha guclu kanit)
    - Resmi kod listesi: her zaman bir "kod ailesi" onerebilmek icin
      genis ama yuzeysel kapsama (gerekce icermez).

    Faz 8: benzerlik, TF-IDF (kelime/harf benzerligi) ve semantik
    embedding (anlam benzerligi) skorlarinin normalize edilip agirlikli
    ortalamasi alinarak hesaplaniyor - bkz. dosyanin ustundeki not."""

    def __init__(self, btb_path: str = BTB_PATH, resmi_kod_path: str = RESMI_KOD_PATH, exclude_btb_no: str = None,
                 tfidf_agirlik: float = TFIDF_AGIRLIK, embedding_agirlik: float = EMBEDDING_AGIRLIK):
        # Agirliklar constructor parametresi olarak da verilebilir - varsayilan
        # (0.7/0.3) uretimde kullanilan deger, ama ablation.py bu parametreyi
        # kullanarak ayni motoru farkli agirliklarla (orn. saf TF-IDF icin
        # 1.0/0.0, saf embedding icin 0.0/1.0) kurup karsilastirabiliyor -
        # kod degismiyor, sadece agirlik degisiyor.
        self.tfidf_agirlik = tfidf_agirlik
        self.embedding_agirlik = embedding_agirlik
        self.rows = self._load_btb(btb_path) + self._load_resmi_kod(resmi_kod_path)

        # exclude_btb_no: leave-one-out degerlendirmesi icin - "bu kayit hic
        # yokmus gibi davran" diyerek modelin gercekten genellemeyi yapip
        # yapmadigini olcmemizi saglar (bkz. evaluate.py)
        if exclude_btb_no:
            self.rows = [r for r in self.rows if r["btb_no"] != exclude_btb_no]

        # BTB kararlarinin esya_tanimi metinleri BUYUK HARFLE yazili (gercek
        # karar belgelerinden birebir alindigi icin), resmi kod aciklamalari
        # ve kullanici sorgulari ise normal harfle. Hem TF-IDF hem embedding
        # icin HER ZAMAN kucuk harfe cevrilmis bir kopya kullaniyoruz -
        # goruntulenen orijinal metin (self.rows icindeki) degismez.
        corpus = [r["esya_tanimi"].lower() for r in self.rows]

        # --- TF-IDF katmani (kelime/harf benzerligi) ---
        self.vectorizer = TfidfVectorizer(lowercase=True, analyzer="char_wb", ngram_range=(3, 5), min_df=1)
        self.tfidf_matrix = self.vectorizer.fit_transform(corpus)

        # --- Embedding katmani (anlam benzerligi) ---
        self.model = SentenceTransformer(MODEL_ADI)
        self.embeddings = self._embeddings_yukle_veya_hesapla(corpus)

    def _embeddings_yukle_veya_hesapla(self, corpus):
        """~15.7k satirin embedding'ini her sunucu baslangicinda yeniden
        hesaplamak yavas olur. Diskte cache'liyoruz - corpus icerigi VEYA
        model adi degisirse hash de degisir, otomatik yeniden hesaplanir
        (bayat/uyumsuz cache kullanma riski yok)."""
        os.makedirs(EMBEDDING_CACHE_DIR, exist_ok=True)
        icerik_hash = hashlib.md5(
            (MODEL_ADI + "\n" + "\n".join(corpus)).encode("utf-8")
        ).hexdigest()[:16]
        cache_path = os.path.join(EMBEDDING_CACHE_DIR, f"{icerik_hash}.npy")

        if os.path.exists(cache_path):
            print(f">>> Embedding cache bulundu, diskten yukleniyor ({cache_path})", flush=True)
            return np.load(cache_path)

        print(f">>> Cache yok, {len(corpus)} satir icin embedding hesaplaniyor "
              f"(ilk seferde birkac dakika surebilir)...", flush=True)
        embeddings = self.model.encode(
            corpus,
            batch_size=64,
            show_progress_bar=True,
            normalize_embeddings=True,
            convert_to_numpy=True,
        )
        np.save(cache_path, embeddings)
        print(f">>> Embedding hesaplandi ve cache'lendi.", flush=True)
        return embeddings

    @staticmethod
    def _load_btb(path):
        with open(path, encoding="utf-8") as f:
            rows = list(csv.DictReader(f))
        for r in rows:
            r["kaynak_tipi"] = "btb_karari"
        return rows

    @staticmethod
    def _load_resmi_kod(path):
        with open(path, encoding="utf-8") as f:
            raw = list(csv.DictReader(f))
        rows = []
        for r in raw:
            rows.append({
                "btb_no": "",
                "gtip_no": r["gtip_pozisyon"],
                "gecerlilik_baslangic_tarihi": "",
                "siniflandirma_gerekcesi": "",
                "esya_tanimi": r["aciklama"],
                "kaynak_tipi": "resmi_kod",
            })
        return rows

    def oner(self, esya_tanimi: str, top_k: int = 3, haric_index: int = None):
        """haric_index: siralama sirasinda bu index'i yok say (leave-one-out
        degerlendirmesi icin)."""
        query_lower = esya_tanimi.lower()

        tfidf_query_vec = self.vectorizer.transform([query_lower])
        tfidf_sims = cosine_similarity(tfidf_query_vec, self.tfidf_matrix)[0]

        emb_query = self.model.encode([query_lower], normalize_embeddings=True, convert_to_numpy=True)[0]
        emb_sims = self.embeddings @ emb_query

        # Sorguya gore DEGIL, sabit agirlikla birlestir (bkz. yukaridaki not
        # - sorgu-bazli normalizasyon "en iyi ama objektif olarak kotu"
        # adaylari yapay olarak yuksek gosteriyordu).
        birlesik = self.tfidf_agirlik * tfidf_sims + self.embedding_agirlik * emb_sims

        if haric_index is not None:
            birlesik[haric_index] = -1.0
        ranked = sorted(range(len(self.rows)), key=lambda i: birlesik[i], reverse=True)[:top_k]

        results = []
        for idx in ranked:
            r = self.rows[idx]
            results.append({
                "benzerlik_skoru": round(float(birlesik[idx]), 3),
                "onerilen_gtip": r["gtip_no"],
                "kaynak_tipi": r["kaynak_tipi"],
                "referans_btb_no": r["btb_no"],
                "referans_esya_tanimi": r["esya_tanimi"],
                "gerekce": r["siniflandirma_gerekcesi"] or "(resmi kod listesi - BTB emsali yok, sadece pozisyon basligi)",
            })
        return results


# ---- Terminalden hizli test icin (input beklemez, tek komutla calisir) ----
if __name__ == "__main__":
    try:
        print(">>> Script basladi", flush=True)
        print(">>> Calisma dizini:", os.getcwd(), flush=True)
        print(">>> BTB verisi araniyor:", os.path.abspath(BTB_PATH), flush=True)
        print(">>> Resmi kod listesi araniyor:", os.path.abspath(RESMI_KOD_PATH), flush=True)

        motor = GtipOneriMotoru()
        print(f">>> {len(motor.rows)} toplam kayit yuklendi (BTB + resmi kod listesi).\n", flush=True)

        if len(sys.argv) > 1:
            query = " ".join(sys.argv[1:])
        else:
            query = "diz bolgesinde kullanilan orme destek bandi, cirt bantli"
            print(f"(Argument verilmedi, ornek sorgu kullaniliyor: \"{query}\")\n", flush=True)

        print(f"SORGU: {query}\n", flush=True)
        for i, res in enumerate(motor.oner(query), 1):
            kaynak = "BTB karari" if res["kaynak_tipi"] == "btb_karari" else "Resmi kod listesi"
            print(f"{i}. Benzerlik: {res['benzerlik_skoru']}  |  GTIP: {res['onerilen_gtip']}  |  Kaynak: {kaynak}", flush=True)
            print(f"   Referans: {res['referans_esya_tanimi'][:110]}...", flush=True)
            print(f"   Gerekce: {res['gerekce'][:150]}...\n", flush=True)

        print(">>> Script bitti.", flush=True)
    except Exception:
        print(">>> HATA OLUSTU:", flush=True)
        traceback.print_exc()
        sys.exit(1)