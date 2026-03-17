# GitHub Trending Telegram Botu

Bu script, her çalıştırıldığında `https://github.com/trending` sayfasını tarar, öne çıkan depoları bulur ve size Telegram üzerinden özet bir mesaj gönderir.

İsterseniz **yapay zeka anlamlandırma** da açabilirsiniz: repo açıklaması + README’den kısa bir alıntı Gemini’ye gönderilir ve mesajlarda **“Bu benim ne işime yarar?”** sorusuna odaklı 3–5 maddelik kullanım önerileri üretilir.

## Kurulum

1. **Depoyu / klasörü hazırlayın**

Bu klasörün içinde `main.py` ve `requirements.txt` zaten mevcut olmalı.

2. **Python sanal ortamı oluşturun (isteğe bağlı ama tavsiye edilir)**

```bash
python -m venv venv
source venv/bin/activate  # Windows için: venv\Scripts\activate
```

3. **Bağımlılıkları yükleyin**

```bash
pip install -r requirements.txt
```

4. **Telegram Bot Token ve Chat ID alın**

- Telegram'da `@BotFather` ile konuşup yeni bir bot oluşturun, verdiği **bot token**'ı not edin.
- Bot'unuzdan mesaj almak istediğiniz hesaptan / gruptan bir kez botunuza mesaj atın.
- `chat_id`'nizi bulmak için:
  - Basit yol: `https://api.telegram.org/bot<YOUR_BOT_TOKEN>/getUpdates` adresine tarayıcıdan gidin, dönen JSON içinde `chat` nesnesindeki `id` değeri sizin `chat_id`'nizdir.

5. **.env dosyasını oluşturun**

Bu klasörün köküne `.env` adında bir dosya ekleyin:

```bash
TELEGRAM_BOT_TOKEN=buraya_bot_token
TELEGRAM_CHAT_ID=buraya_chat_id
```

### Opsiyonel: Gemini ile “Bu benim ne işime yarar?” anlamlandırması

1. Google AI Studio üzerinden bir **Gemini API key** alın.
2. `.env` içine şunu ekleyin:

```bash
GEMINI_API_KEY=buraya_gemini_api_key
```

Model adınız 404 verirse (bazı hesaplarda model isimleri farklı olabiliyor) `.env` içine şunu da ekleyin:

```bash
GEMINI_MODEL=gemini-flash-latest
```

`GEMINI_API_KEY` doluysa, script her repo için README’den kısa bir bölüm çekip Gemini’ye göndererek daha anlamlı kullanım önerileri üretir. Anahtar yoksa otomatik olarak basit (kural-tabanlı) tahminlere geri döner.

## Çalıştırma

```bash
python main.py
```

Her çalıştırdığınızda, o anki GitHub Trending listesinden ilk 10 depoyu alıp, ne işe yarayabileceği hakkında kısa notlarla birlikte Telegram hesabınıza gönderir.

## Her gün otomatik çalıştırma (cron)

macOS / Linux için:

```bash
crontab -e
```

İçine örneğin her gün sabah 09:00'da çalıştırmak için şu satırı ekleyin (yolu kendinize göre güncelleyin):

```bash
0 9 * * * /usr/bin/env PATH=$PATH:/usr/local/bin cd "/Users/soneratalay/Desktop/GitHub Trending Repo" && /usr/bin/env python main.py >> cron.log 2>&1
```

Bu sayede her gün belirlediğiniz saatte Telegram'da yeni trending projelerin özeti ve olası kullanım alanlarını içeren bir mesaj alırsınız.

