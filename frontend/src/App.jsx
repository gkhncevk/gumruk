import { useState } from "react";
import "./App.css";

// Iki farkli senaryoyu gostermek icin: biri sadece aciklamayla arama
// (GTIP kutusu bos), digeri hazir bir GTIP'i dogrulama (GTIP kutusu dolu).
const ORNEK_SORGULAR = [
  {
    baslik: "Örnek 1 — sadece açıklama (GTİP bilmiyorum)",
    beyan_edilen_gtip: "",
    esya_tanimi: "Diz bölgesinde kullanılan, örme kumaştan yapılmış, cırt bantla ayarlanan, hareketi tamamen kısıtlamayan hafif destek bandı",
  },
  {
    baslik: "Örnek 2 — yanlış kod doğrulama",
    beyan_edilen_gtip: "902110000019",
    esya_tanimi: "Diz bölgesinde kullanılan, örme kumaştan yapılmış, cırt bantla ayarlanan, hareketi tamamen kısıtlamayan hafif destek bandı",
  },
  {
    baslik: "Örnek 3 — doğru kod doğrulama",
    beyan_edilen_gtip: "630790100019",
    esya_tanimi: "Diz bölgesinde kullanılan, örme kumaştan yapılmış, cırt bantla ayarlanan, hareketi tamamen kısıtlamayan hafif destek bandı",
  },
];

const RISK_ETIKET = {
  dusuk: { renk: "#1a7f37", arkaplan: "#e6f4ea", metin: "DÜŞÜK RİSK" },
  yuksek: { renk: "#c0392b", arkaplan: "#fdecea", metin: "YÜKSEK RİSK" },
  belirsiz: { renk: "#8a6d00", arkaplan: "#fff8e1", metin: "BELİRSİZ" },
};

function KanitRozeti({ kaynakTipi }) {
  const guclu = kaynakTipi === "btb_karari";
  return (
    <span className={`kanit-rozeti ${guclu ? "guclu" : "zayif"}`}>
      {guclu ? "Güçlü kanıt (gerçek BTB kararı)" : "Zayıf kanıt (sadece resmi kod)"}
    </span>
  );
}

function App() {
  const [beyanGtip, setBeyanGtip] = useState("");
  const [esyaTanimi, setEsyaTanimi] = useState("");
  const [mod, setMod] = useState(null); // "oneri" | "risk"
  const [oneriSonuc, setOneriSonuc] = useState(null);
  const [sonuc, setSonuc] = useState(null);
  const [yukleniyor, setYukleniyor] = useState(false);
  const [hata, setHata] = useState(null);
  const [feedbackDurum, setFeedbackDurum] = useState(null);

  async function analizEt(e, override) {
    e?.preventDefault();
    const gtip = (override?.gtip ?? beyanGtip).trim();
    const tanim = override?.tanim ?? esyaTanimi;

    setYukleniyor(true);
    setHata(null);
    setSonuc(null);
    setOneriSonuc(null);
    setFeedbackDurum(null);

    try {
      if (gtip === "") {
        // Mod 1: GTIP bilinmiyor - sadece aciklamayla oneri iste.
        const yanit = await fetch("/api/oneri", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ esya_tanimi: tanim, top_k: 3 }),
        });
        const veri = await yanit.json();
        if (!yanit.ok) {
          setHata(veri.hata || "Sunucu hatası oluştu.");
        } else {
          setMod("oneri");
          setOneriSonuc(veri);
        }
      } else {
        // Mod 2: elde bir GTIP var - dogrula/riski olc.
        const yanit = await fetch("/api/risk-analizi", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ beyan_edilen_gtip: gtip, esya_tanimi: tanim, top_k: 3 }),
        });
        const veri = await yanit.json();
        if (!yanit.ok) {
          setHata(veri.hata || "Sunucu hatası oluştu.");
        } else {
          setMod("risk");
          setSonuc(veri);
        }
      }
    } catch (err) {
      setHata("Backend'e ulaşılamıyor. Node sunucusunun (npm start) çalıştığından emin ol.");
    } finally {
      setYukleniyor(false);
    }
  }

  function buKoduDogrula(gtip) {
    setBeyanGtip(gtip);
    analizEt(null, { gtip, tanim: esyaTanimi });
  }

  // "Ilham al" - sistemin bulduğu en yakın (resmi ya da gerçek BTB) tanımı
  // input kutusuna dolduruyor, AMA otomatik göndermiyor. Kullanıcı bunu
  // kendi gerçek ürününe göre düzenleyip öyle gönderir - sistem "yazmıyor",
  // sadece nasıl bir dilde/üslupta tanım yazılması gerektiğine dair örnek
  // gösteriyor. Bilerek otomatik submit yok: sistem elindeki gerçek ürünü
  // görmüyor, üretilen bir tanımı olduğu gibi kullanmak yanlış beyan riski
  // taşır.
  function ornekTanimiIlhamAl(tanim) {
    setEsyaTanimi(tanim);
    setMod(null);
    setOneriSonuc(null);
    setSonuc(null);
  }

  async function feedbackGonder(dogruMu) {
    if (!sonuc) return;
    try {
      await fetch("/api/feedback", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          esya_tanimi: esyaTanimi,
          beyan_edilen_gtip: beyanGtip,
          onerilen_gtip: sonuc.onerilen_gtip,
          dogru_mu: dogruMu,
          dogru_gtip: "",
          notlar: "",
        }),
      });
      setFeedbackDurum(dogruMu ? "Teşekkürler, geri bildirim kaydedildi." : "Anlaşıldı, bu kaydedildi.");
    } catch {
      setFeedbackDurum("Geri bildirim gönderilemedi.");
    }
  }

  function ornekDoldur(ornek) {
    setBeyanGtip(ornek.beyan_edilen_gtip);
    setEsyaTanimi(ornek.esya_tanimi);
    setSonuc(null);
    setOneriSonuc(null);
    setMod(null);
    setHata(null);
  }

  const etiket = sonuc ? RISK_ETIKET[sonuc.risk_seviyesi] : null;

  return (
    <div className="sayfa">
      <header className="baslik">
        <h1>GTİP Risk &amp; Gerekçelendirme Asistanı</h1>
        <p className="alt-baslik">
          İki şekilde kullanılır: (1) sadece eşya tanımı yazıp <strong>hangi GTİP'e girdiğini bulmak</strong> için,
          ya da (2) elindeki bir GTİP kodunu <strong>doğrulamak/riskini ölçmek</strong> için — GTİP kutusunu boş
          bırak ya da doldur, sistem ona göre davranır.
        </p>
      </header>

      <div className="ornekler">
        <span>Hızlı dene:</span>
        {ORNEK_SORGULAR.map((o, i) => (
          <button key={i} type="button" className="ornek-buton" onClick={() => ornekDoldur(o)} title={o.baslik}>
            Örnek {i + 1}
          </button>
        ))}
      </div>

      <form onSubmit={analizEt} className="form">
        <label>
          Beyan edilen GTİP kodu <span className="opsiyonel">(opsiyonel — bilmiyorsan boş bırak)</span>
          <input
            type="text"
            value={beyanGtip}
            onChange={(e) => setBeyanGtip(e.target.value)}
            placeholder="Boş bırakırsan sistem sana öneri sunar"
          />
        </label>
        <label>
          Eşya tanımı
          <textarea
            value={esyaTanimi}
            onChange={(e) => setEsyaTanimi(e.target.value)}
            placeholder="Eşyanın serbest metin tanımını yazın (ör. fatura açıklaması)..."
            rows={4}
            required
          />
        </label>
        <button type="submit" disabled={yukleniyor} className="analiz-buton">
          {yukleniyor ? "Analiz ediliyor..." : beyanGtip.trim() ? "Kodu Doğrula" : "GTİP Öner"}
        </button>
      </form>

      {hata && <div className="hata-kutusu">{hata}</div>}

      {/* MOD 1: sadece aciklamayla oneri listesi */}
      {mod === "oneri" && oneriSonuc && (
        <div className="sonuc">
          <p className="mod-aciklama">
            GTİP kodu belirtmedin — sistem eşya tanımına en yakın {oneriSonuc.sonuclar.length} öneriyi listeledi.
            İçlerinden birini seçip "Bu kodu doğrula" dersen, risk analizini de görebilirsin. "Bu tanımı ilham al"
            dersen, o örnek metni düzenleme kutusuna doldurur — kendi ürününe göre düzenleyip öyle gönder,
            olduğu gibi kullanma (sistem senin ürününü görmüyor, bu sadece nasıl bir dille yazılması gerektiğine
            dair bir örnek).
          </p>
          <ul className="oneri-listesi">
            {oneriSonuc.sonuclar.map((o, i) => (
              <li key={i} className="oneri-karti">
                <div className="oneri-karti-ust">
                  <span className="kod vurgu">{o.onerilen_gtip}</span>
                  <KanitRozeti kaynakTipi={o.kaynak_tipi} />
                  <span className="benzerlik">Benzerlik: {(o.benzerlik_skoru * 100).toFixed(1)}%</span>
                </div>
                <p className="oneri-referans">{o.referans_esya_tanimi.slice(0, 160)}...</p>
                <div className="oneri-butonlar">
                  <button type="button" className="dogrula-buton" onClick={() => buKoduDogrula(o.onerilen_gtip)}>
                    Bu kodu doğrula →
                  </button>
                  <button
                    type="button"
                    className="ilham-buton"
                    onClick={() => ornekTanimiIlhamAl(o.referans_esya_tanimi)}
                    title="Bu tanımı düzenleme kutusuna doldurur, kendi ürününe göre düzenleyip gönderebilirsin"
                  >
                    💡 Bu tanımı ilham al
                  </button>
                </div>
              </li>
            ))}
          </ul>
        </div>
      )}

      {/* MOD 2: GTIP dogrulama / risk analizi */}
      {mod === "risk" && sonuc && (
        <div className="sonuc">
          <div className="risk-satiri">
            <span className="risk-rozeti" style={{ color: etiket.renk, background: etiket.arkaplan }}>
              {etiket.metin}
            </span>
            <span className="benzerlik">Güven skoru: {(sonuc.benzerlik_skoru * 100).toFixed(1)}%</span>
          </div>
          <p className="aciklama">{sonuc.aciklama}</p>

          <div className="kod-karsilastirma">
            <div>
              <span className="etiket-kucuk">Beyan edilen</span>
              <div className="kod">{sonuc.beyan_edilen_gtip}</div>
            </div>
            <div className="ok">→</div>
            <div>
              <span className="etiket-kucuk">Sistemin önerisi</span>
              <div className="kod vurgu">{sonuc.onerilen_gtip}</div>
            </div>
          </div>

          <div className="gerekce-kutusu">
            <div className="gerekce-baslik">
              <strong>Gerekçe</strong>
              <KanitRozeti kaynakTipi={sonuc.gerekceli_aciklama.kanit_seviyesi === "guclu" ? "btb_karari" : "resmi_kod"} />
            </div>
            <p>{sonuc.gerekceli_aciklama.ozet}</p>
            {sonuc.gerekceli_aciklama.kanit_seviyesi === "guclu" && (
              <p className="btb-gerekce">{sonuc.gerekceli_aciklama.btb_gerekcesi}</p>
            )}

            {sonuc.gerekceli_aciklama.ilgili_genel_kurallar.length > 0 && (
              <div className="kurallar">
                <strong>İlgili genel kurallar</strong>
                <ul>
                  {sonuc.gerekceli_aciklama.ilgili_genel_kurallar.map((k) => (
                    <li key={k.kural_id}>
                      <span className="kural-id">{k.kural_id}</span>: {k.metin}
                    </li>
                  ))}
                </ul>
              </div>
            )}

            <p className="kaynak-notu">
              {sonuc.gerekceli_aciklama.kaynak_notu}{" "}
              <a href={sonuc.gerekceli_aciklama.kaynak_linki} target="_blank" rel="noreferrer">
                BTB arama sistemine git ↗
              </a>
            </p>
          </div>

          {sonuc.diger_emsaller.length > 0 && (
            <details className="diger-emsaller">
              <summary>Diğer {sonuc.diger_emsaller.length} alternatif emsal/öneri</summary>
              <ul>
                {sonuc.diger_emsaller.map((e, i) => (
                  <li key={i}>
                    <span className="kod-kucuk">{e.onerilen_gtip}</span>
                    {" — "}
                    {e.referans_esya_tanimi.slice(0, 100)}...
                  </li>
                ))}
              </ul>
            </details>
          )}

          <div className="feedback">
            <span>Bu öneri doğru muydu?</span>
            <button type="button" onClick={() => feedbackGonder(true)}>👍 Doğru</button>
            <button type="button" onClick={() => feedbackGonder(false)}>👎 Yanlış</button>
            {feedbackDurum && <span className="feedback-durum">{feedbackDurum}</span>}
          </div>
        </div>
      )}

      <footer className="alt-bilgi">
        <p>
          Bu bir prototiptir. Öneriler ve gerekçeler bağlayıcı değildir, kesin
          sınıflandırma için yetkili gümrük müşavirine danışılmalıdır.
        </p>
      </footer>
    </div>
  );
}

export default App;