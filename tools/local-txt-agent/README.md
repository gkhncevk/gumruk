# txt-file agent (tamamen yerel, ücretsiz)

Bilgisayarında çalışan, internete ve ücretli hiçbir API'ye ihtiyaç duymayan
bir "agent". Ollama üzerinden yerel bir açık kaynak modeli kullanır, sen
doğal dilde bir klasördeki `.txt`, `.md` ve `.csv` dosyalarıyla ne yapmak
istediğini söylersin (yeniden adlandır, içeriği düzenle, birleştir, böl,
klasörlere ayır), agent bir plan önerir, sen onaylarsın, ancak öyle uygulanır.

Agent sadece bu üç dosya türünü görür ve dokunabilir — `agent.py` içindeki
`SUPPORTED_EXTENSIONS` listesi bunu belirliyor. Başka bir dosya türüne
(`.py`, `.pdf`, `.png` vb.) yazmaya/yeniden adlandırmaya çalışan bir işlem
önerilse bile, uygulama aşamasında otomatik reddedilir — model bir hata
yapsa bile bu tür dosyalara asla dokunamaz.

Hiçbir dosya, senin onayın olmadan değişmez.

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

- Farklı dosya türleri (`.md`, `.csv`) desteği
- "Geri al" düğmesi (son işlemi tersine çevirme)
- Ücretsiz bulut API'ye (Groq/Gemini) geçiş seçeneği — internetin varken
  daha güçlü bir modelle çalışmak istersen `agent.py` içindeki
  `_ollama_chat` fonksiyonunun yerine geçecek küçük bir alternatif
  yazılabilir.
- Model bir işlemi yanlış önerirse, tekrar mesaj yazıp düzeltmesini
  isteyebilirsin — konuşma geçmişi (son 20 mesaj) hatırlanıyor.