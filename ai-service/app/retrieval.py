"""
GTIP Oneri Motoru - cekirdek mantik.

Bu modul, main.py (FastAPI servisi) tarafindan import edilir; ayni zamanda
tek basina, tek satirlik komutla test edilebilir (input beklemez):

    python app/retrieval.py "diz bolgesinde kullanilan orme destek bandi"

Tirnak icindeki metni degistirerek istedigin urun tanimini test edebilirsin.

---
NOT (embedding vs TF-IDF karari):
Sentence-transformers (gercek semantik embedding) denendi ama bu ortamda
torch indirmesi tekrar tekrar zaman asimina ugradi (agir bagimlilik).
Ayni sorun kullanicinin kendi bilgisayarinda da yasanabilir - ilk kurulumda
zaten scikit-learn'un numpy/scipy'si yavas kalmisti, torch eklemek isi
daha da kirilgan hale getirir. Bu yuzden pragmatik bir orta yol secildi:
kelime bazli TF-IDF yerine KARAKTER n-gram tabanli TF-IDF (analyzer=char_wb).
Bu, Turkce'nin eklemeli yapisinda ("bant" / "bandi" / "banda" gibi farkli
ceki eklerini) kelime bazli yontemden çok daha iyi yakalar, ve hicbir yeni
bagimlilik gerektirmez. Gercek embedding'e gecis ileride su sekilde
yapilabilir: bu dosyada sadece vectorizer/build_index kismini
sentence-transformers ile degistirmek yeterli, geri kalan mantik ayni kalir.
---
NOT (kapsam genisletme - Faz 7):
Artik iki farkli veri kaynagi birlestiriliyor:
  1) btb_tekstil_61_64.csv - 41 gercek BTB karari (emsal + gerekce icerir),
     kapsam bilerek fasil 61-64 ile sinirli tutuldu (bkz. dosyanin kendi
     aciklamasi - manuel dogrulama gerektirdigi icin genisletmesi pahali).
  2) resmi_kod_listesi_tum_fasillar.csv - TUM gumruk tarifesinin (fasil
     1-97, fasil 77 harici - HS nomanklaturunde rezerve/bos) tam 12 haneli
     GTIP kod + aciklama listesi (~15.700 kayit). Bu artik yazarin
     bilgisinden derlenmis bir tahmin DEGIL: Ticaret Bakanligi'nin resmi
     "Istatistik Pozisyonlarina Bolunmus Turk Gumruk Tarife Cetveli"
     Excel yayinindan (ggm.ticaret.gov.tr, Karar Sayisi 10781, 30 Aralik
     2025 tarihli Resmi Gazete) otomatik parse edilerek uretildi. Parser,
     Excel'deki tire-derinlikli (- / - - / - - -) hiyerarsiyi ve
     kelime-ortasi tire ile bolunmus satir kaymalarini (Excel word-wrap)
     cozup her leaf kod icin tam ata zincirini birlestiriyor
     (scripts/parse_tarife_cetveli.py). Doğrulama: 41 BTB kararinin
     TAMAMININ GTIP kodu bu listede birebir eslesiyor (41/41).
Boylece sistem hicbir BTB emsali olmayan bir urun icin bile (ornegin bir
elektronik kart ya da bir kimyasal madde), tekstil disi olsa dahi, en
azindan doğru resmi kod ailesini onerebiliyor - ama bu oneri her zaman
"zayif kanit" (resmi kod, BTB emsali yok) etiketiyle isaretleniyor.
Gercek BTB gerekceli "guclu kanit" derinligi hala bilinçli olarak sadece
fasil 61-64'te - butun tarifeyi bu derinlikte kapsamak, binlerce karari
tek tek dogrulamak demek, bu asamada gerceklestirilebilir degil.
"""

import csv
import os
import sys
import traceback

print(">>> scikit-learn/numpy/scipy yukleniyor... (ilk calistirmada 30-90 saniye surebilir, donmadi, bekle)", flush=True)
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
print(">>> Kutuphaneler yuklendi.", flush=True)

BASE_DIR = os.path.dirname(__file__)
BTB_PATH = os.path.join(BASE_DIR, "..", "data", "btb_tekstil_61_64.csv")
RESMI_KOD_PATH = os.path.join(BASE_DIR, "..", "data", "resmi_kod_listesi_tum_fasillar.csv")


class GtipOneriMotoru:
    """Iki kaynagi birlikte kullanan retrieval (en yakin komsu) motoru:
    - BTB kararlari: gercek emsal + gerekce (daha guclu kanit)
    - Resmi kod listesi: her zaman bir "kod ailesi" onerebilmek icin
      genis ama yuzeysel kapsama (gerekce icermez)."""

    def __init__(self, btb_path: str = BTB_PATH, resmi_kod_path: str = RESMI_KOD_PATH, exclude_btb_no: str = None):
        self.rows = self._load_btb(btb_path) + self._load_resmi_kod(resmi_kod_path)

        # exclude_btb_no: leave-one-out degerlendirmesi icin - "bu kayit hic
        # yokmus gibi davran" diyerek modelin gercekten genellemeyi yapip
        # yapmadigini olcmemizi saglar (bkz. evaluate.py)
        if exclude_btb_no:
            self.rows = [r for r in self.rows if r["btb_no"] != exclude_btb_no]

        # char_wb: kelime sinirlarini koruyarak karakter n-gramlari cikarir.
        # Turkce ek/cekim varyasyonlarini kelime bazli yontemden daha iyi yakalar.
        self.vectorizer = TfidfVectorizer(lowercase=True, analyzer="char_wb", ngram_range=(3, 5), min_df=1)
        corpus = [r["esya_tanimi"] for r in self.rows]
        self.matrix = self.vectorizer.fit_transform(corpus)

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
        degerlendirmesini, corpus ~15.7k satira cikinca her seferinde
        yeniden vectorizer fit etmeden HIZLI yapabilmek icin - evaluate.py
        artik tek bir motoru bir kere kurup her BTB kaydi icin sadece bu
        parametreyi kullanarak o kaydin kendisini disliyor. Vokabuler/IDF
        agirliklari N-1 yerine N satir uzerinden hesaplanmis oluyor ama
        15758 satirlik corpus'ta tek satirin IDF'e etkisi ihmal edilebilir,
        siralama sonucunu pratikte degistirmiyor.)"""
        query_vec = self.vectorizer.transform([esya_tanimi])
        sims = cosine_similarity(query_vec, self.matrix)[0]
        if haric_index is not None:
            sims[haric_index] = -1.0
        ranked = sorted(range(len(self.rows)), key=lambda i: sims[i], reverse=True)[:top_k]

        results = []
        for idx in ranked:
            r = self.rows[idx]
            results.append({
                "benzerlik_skoru": round(float(sims[idx]), 3),
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