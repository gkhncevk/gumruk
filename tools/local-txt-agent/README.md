# txt-file agent (tamamen yerel, ücretsiz)

Bilgisayarında çalışan, internete ve ücretli hiçbir API'ye ihtiyaç duymayan
bir "agent". Ollama üzerinden yerel bir açık kaynak modeli kullanır, sen
doğal dilde bir klasördeki `.txt`, `.md` ve `.csv` dosyalarıyla ne yapmak
istediğini söylersin (yeniden adlandır, içeriği düzenle, birleştir, böl,
klasörlere ayır), agent bir plan önerir, sen onaylarsın, ancak öyle uygulanır.

Agent iki tür dosyayı **değiştirebilir** (yeniden adlandırma, yazma, hedefli
değişiklik, birleştirme, bölme, taşıma, silme) — `agent.py` içindeki
`WRITABLE_EXTENSIONS` listesi (`SUPPORTED_EXTENSIONS` + `CONFIG_WRITABLE_EXTENSIONS`)
bunu belirliyor:

- **Düz metin** (`SUPPORTED_EXTENSIONS`): `.txt`, `.md`, `.csv`
- **Yapılandırılmış config** (`CONFIG_WRITABLE_EXTENSIONS`): `.json`, `.yaml`, `.yml`
  — bunlar için her "yazma"/"hedefli değişiklik" işlemi, uygulamadan önce
  eski/yeni içerik arasında satır satır bir **diff** gösterir (bkz.
  `agent.diff_for_action`), sadece yeni içeriğin tamamını göstermek yerine —
  yanlış bir düzenlemeyi fark etmek çok daha kolay.

İki değişiklik türü var: **`write`** dosyanın tamamını yeniden yazar (yeni
dosya oluştururken ya da içeriğin çoğu değişiyorsa uygun), **`replace`** ise
sadece belirttiğin `find` metnini `replace` ile değiştirir (`agent.compute_replace`)
— dosyanın geri kalanına asla dokunmaz. Küçük, tek-satırlık değişikliklerde
(örn. "portu 5432'den 5433'e değiştir") sistem promptu modele `replace`'i
tercih etmesini söylüyor, çünkü `write` dosyanın tamamını "hafızasından"
yeniden ürettiği için küçük değişikliklerde bile alakasız satırları
(yorumlar, boşluklar) fark ettirmeden değiştirebiliyor — bu gerçekten
gözlemlendi (bkz. aşağıdaki not). `replace`, `find` metni dosyada birebir ve
**tam olarak bir kez** eşleşmezse (hiç yoksa ya da birden fazla yerde
geçiyorsa) işlemi reddeder — belirsiz bir eşleşmeyi asla tahmin etmez.

Başka bir dosya türüne (`.pdf`, `.png` vb.) yazmaya/yeniden adlandırmaya
çalışan bir işlem önerilse bile, uygulama aşamasında otomatik reddedilir —
model bir hata yapsa bile bu tür dosyalara asla dokunamaz.

Ayrıca gerçek kod dosyalarını (`.py`, `.cs`, `.ts`/`.tsx`, `.js`/`.jsx`, `.html`,
`.css`) **salt-okunur bağlam** olarak görebilir (`CONTEXT_ONLY_EXTENSIONS`) —
gümrük projesinin artık üç dilde (Python, C#, TypeScript) yazılmış olması bunu
gerektirdi. Bu, "README'deki şu değer koddakiyle uyumlu mu" gibi soruları
cevaplayabilmesi için var (bkz. aşağıdaki "Gerçek kullanım örneği"). Ama bu
dosyalara **asla** yazamaz/yeniden adlandıramaz/silemez — `apply_actions`'daki
`safe_new_path` kontrolü sadece `WRITABLE_EXTENSIONS`'ı kabul ediyor. Bilinçli
bir tercih: gerçek kaynak kodu, config dosyalarından bile daha kırılgan —
yanlış bir düzenleme derlemeyi sessizce bozabilir ve fark edilmesi daha zor
olur. Config dosyalarına yazma izni (diff önizlemesiyle) kademeli genişlemenin
ilk adımı; kaynak koduna yazma izni, bu adım kendini kanıtladıktan sonra
düşünülecek bir sonraki adım.

15.7k satırlık bir CSV gibi çok büyük dosyalar (`MAX_PREVIEW_FILE_SIZE`,
varsayılan 200KB) otomatik atlanır — küçük yerel modeli boğmasın diye. Atlanan
dosyalar isim/boyutuyla listede görünür, sadece içeriği modele gösterilmez.

Hiçbir dosya, senin onayın olmadan değişmez.

Bir uygulamadan pişman olursan, "Seçilenleri uygula" sonrası çıkan **"Geri al"**
butonuna basarak o işlem grubunu tersine çevirebilirsin — `apply_actions`
işlemleri gerçekleştirmeden önce, grubun dokunacağı her dosyanın mevcut halini
(var mıydı, içeriği neydi) otomatik olarak kaydeder (`agent._snapshot`); "Geri
al" bu kaydı birebir geri yükler (`agent.restore_snapshot`). Sadece **en son**
uygulanan grup geri alınabilir (tek seviyeli undo) — yeni bir işlem
uyguladığında bir önceki "Geri al" butonu otomatik olarak devre dışı kalır, o
artık farklı bir grubu geri alacağı için yanıltıcı olurdu.

## Kurulum (bir kere yapılır)

1. **Ollama'yı kur** (yerel modeli çalıştıran ücretsiz araç):
   ```bash
   brew install ollama
   ```
   (Homebrew yoksa https://ollama.com adresinden Mac için doğrudan indirebilirsin.)

2. **Ollama'yı başlat** (arka planda çalışır, terminali açık tutmana gerek yok):
   ```bash
   ollama serve
   ```
   Zaten menü çubuğunda Ollama uygulaması olarak çalışıyorsa bu adımı atlayabilirsin.

3. **Bir model indir** (ilk seferde ~2GB inip diskte kalır, sonrasında tamamen offline çalışır):
   ```bash
   ollama pull llama3.2:3b
   ```
   MacBook Air'inin RAM'i 16GB veya üzeriyse daha güçlü bir model deneyebilirsin:
   ```bash
   ollama pull qwen2.5:7b-instruct
   ```
   ve `app.py`'yi çalıştırırken arayüzdeki "model" kutusuna o ismi yazman yeterli.

4. **Python bağımlılıklarını kur:**
   ```bash
   cd txt-file-agent
   python3 -m venv .venv
   source .venv/bin/activate
   pip install -r requirements.txt
   ```

## Çalıştırma

```bash
source .venv/bin/activate   # her yeni terminalde
python app.py
```

Sonra tarayıcında **http://localhost:5001** adresini aç.

## Kullanım

1. Sağ üstteki durum noktası yeşilse Ollama'ya bağlanmış demektir; "Model"
   kutusu bilgisayarında indirdiğin modelleri otomatik listeler, birini seç.
2. Klasör kutusuna tam yol yazmak yerine **"Gözat"** butonuna basıp
   klasörlerinde tıklayarak gezebilir, işlem yapmak istediğin klasörü
   seçebilirsin. Son kullandığın klasör ve model bir sonraki açılışta
   otomatik hatırlanır.
3. Alt kutuya doğal dilde ne istediğini yaz — örnekler:
   - "bu klasördeki dosyaları içeriklerine göre yeniden adlandır"
   - "hepsini temizle, fazla boşlukları kaldır"
   - "toplantı notlarını bir, market listelerini başka bir alt klasöre ayır"
   - "şu iki dosyayı birleştir: a.txt ve b.txt"
4. Agent önerdiği değişiklikleri (yeniden adlandırma, birleştirme vb.) bir
   liste olarak gösterir; içerik güncellemelerinde yeni içeriğin önizlemesini
   de görürsün. İstemediğin bir maddenin kutucuğunu kaldırıp sadece kalanları
   uygulayabilirsin.
5. "Seçilenleri uygula" dediğinde değişiklikler gerçekten diskte yapılır.
6. "Sohbeti temizle" ekrandaki geçmişi temizler (dosyalarına dokunmaz).

## Gerçek kullanım örneği — gümrük projesinde dokümantasyon kontrolü

Bu agent, `../..` (yani `gumruk/` reposunun kökü) gibi bir klasöre yöneltilip
dokümantasyon-kod tutarsızlığı yakalamak için kullanılabilir:

1. `python app.py`, tarayıcıda `http://localhost:5001` aç.
2. Klasör olarak `gumruk` reposunun kökünü (ya da sadece `README.md` +
   `ai-service/README.md` + `ai-service/app/risk.py`'yi içeren küçük bir alt
   klasörü) seç.
3. Şunu yaz: *"README.md ve ai-service/README.md'deki risk eşiği (CONFIDENCE_THRESHOLD)
   ile ilgili ifadeler, risk.py'deki gerçek değerle tutarlı mı?"*

Agent artık `risk.py`'yi salt-okunur olarak görebildiği için (Faz B öncesi
göremiyordu), gerçek kod değerini `.md` dosyalarındaki iddialarla karşılaştırıp
bir tutarsızlık varsa `reply` alanında bunu söyleyebilir — hiçbir dosyaya
dokunmadan, sadece bir bulgu raporu olarak.

## Nasıl çalışıyor (kısaca)

- `agent.py` klasördeki dosyaların bir önizlemesini alır, modele
  (Ollama üzerinden, tamamen yerel) gönderir ve modelden kesin bir JSON
  formatında "plan" ister (`{"reply": ..., "actions": [...]}`).
- Model asla dosyalara doğrudan dokunmaz — sadece plan önerir.
- `app.py` bu planı tarayıcıya gösterir; sen onaylayınca `apply_actions`
  fonksiyonu gerçek dosya işlemlerini yapar (yeniden adlandırma, yazma,
  birleştirme, bölme, taşıma, silme).
- Tüm dosya yolları verdiğin klasörün dışına çıkamaz (güvenlik kontrolü
  `agent.py` içinde `safe_path`).
- Model dropdown'ı ve klasör gözatma penceresi, `app.py` içindeki
  `/api/models` ve `/api/browse` endpoint'leri üzerinden çalışır — biri
  Ollama'nın indirdiğin modelleri listelemesini, diğeri de bilgisayarındaki
  klasörleri gezmeni sağlar.

## Geliştirme fikirleri (istersen sonra ekleriz)

- [x] `.py` dosyalarını salt-okunur bağlam olarak görme (dokümantasyon-kod
      tutarlılık kontrolü için)
- [x] Çok büyük dosyaları (>200KB) otomatik atlama
- [x] `CONTEXT_ONLY_EXTENSIONS`'ı `.cs`/`.ts`/`.tsx`/`.js`/`.jsx`/`.html`/`.css`'e
      genişletmek — artık gümrük projesinin .NET (`backend-dotnet/`) ve
      Next.js (`frontend-nextjs/`) tarafını da görebiliyor
- [x] `.json`/`.yaml`/`.yml` config dosyalarına yazma izni (diff önizlemesiyle,
      `CONFIG_WRITABLE_EXTENSIONS`) — kod dosyalarına yazma iznine kademeli
      ilk adım
- [x] Hedefli `replace` eylem türü — canlı kullanımda gözlemlendi: diff
      önizlemesi eklendikten hemen sonra, "SADECE portu değiştir, başka
      hiçbir satıra dokunma" gibi açık bir talimata rağmen model `write` ile
      dosyanın tamamını yeniden yazarken alakasız bir yorum satırındaki
      Türkçe karakterleri de "düzeltti". `find`/`replace` çiftiyle çalışan ve
      `find` dosyada tam olarak bir kez eşleşmezse reddeden `replace` eylemi,
      bu sınıf hatayı yapısal olarak imkansız hale getiriyor (bkz.
      `agent.compute_replace`) — modele "dikkatli ol" demek yerine.
- [ ] Gerçek kaynak koduna (`.py`/`.cs`/`.ts`) yazma izni — config tarafı
      kendini kanıtladıktan sonra değerlendirilecek, muhtemelen ek bir
      güvenlik katmanıyla (örn. her dosya türü için ayrı onay adımı)
- [ ] Word (`.docx`) desteği — bu, düz metin değil, ZIP içinde XML barındıran
      yapılandırılmış bir format. `python-docx` kütüphanesi ve düz metinden
      farklı bir okuma/yazma kod yolu gerektiriyor (paragraf yapısını koruma).
      Ayrı bir adımda ele alınacak, salt "SUPPORTED_EXTENSIONS'a ekle" kadar
      basit değil.
- [x] "Geri al" düğmesi (son uygulanan işlem grubunu tersine çevirme --
      `agent.restore_snapshot`, tek seviyeli)
- Ücretsiz bulut API'ye (Groq/Gemini) geçiş seçeneği — internetin varken
  daha güçlü bir modelle çalışmak istersen `agent.py` içindeki
  `_ollama_chat` fonksiyonunun yerine geçecek küçük bir alternatif
  yazılabilir.
- Model bir işlemi yanlış önerirse, tekrar mesaj yazıp düzeltmesini
  isteyebilirsin — konuşma geçmişi (son 20 mesaj) hatırlanıyor.