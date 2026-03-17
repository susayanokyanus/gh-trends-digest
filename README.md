# GitHub Trending → Telegram (Gemini destekli)

Her gün GitHub Trending’den **ilk 5 projeyi** alır, her proje için **“Bu benim ne işime yarar?”** odaklı kısa bir özet + fikirler üretir ve Telegram’a gönderir.

- **Hızlı**: İlk 5 repo ile limitli (maliyet kontrolü)
- **Anlamlı**: Repo açıklaması + README’den kısa alıntı + Gemini ile yorumlama
- **Pratik**: Her repo **ayrı Telegram mesajı** (kırpılma/limit sorunları minimize)

## İndir / Kur

- **GitHub repo**: `https://github.com/susayanokyanus/gh-trends-digest`
- **ZIP indir**: `https://github.com/susayanokyanus/gh-trends-digest/archive/refs/heads/main.zip`
- **Clone (HTTPS)**:

```bash
git clone https://github.com/susayanokyanus/gh-trends-digest.git
cd gh-trends-digest
```

- **Clone (SSH)**:

```bash
git clone git@github.com:susayanokyanus/gh-trends-digest.git
cd gh-trends-digest
```

## Ne gönderiyor?

Her gün Telegram’da şuna benzer 6 mesaj görürsünüz:

- 1 mesaj: günün başlığı (`📌 GitHub Trending - gg.aa.yyyy`)
- 5 mesaj: her repo için ayrı içerik:
  - Repo adı + dil
  - Kısa açıklama + bugün yıldız
  - **Özet** (3–4 cümle)
  - **Fikirler** (en fazla 4 madde) — *“Fikirler olmadan asla bitirme” kuralı aktif*

## Kurulum (lokalde)

### 1) Python sanal ortam

```bash
python -m venv venv
source venv/bin/activate
```

### 2) Bağımlılıklar

```bash
pip install -r requirements.txt
```

### 3) Telegram değerleri

- Telegram’da `@BotFather` ile bot oluşturun → **bot token**
- Botunuza mesaj atın → `getUpdates` ile **chat_id** bulun:
  - `https://api.telegram.org/bot<YOUR_BOT_TOKEN>/getUpdates`

### 4) `.env` oluştur

```bash
TELEGRAM_BOT_TOKEN=buraya_bot_token
TELEGRAM_CHAT_ID=buraya_chat_id

# Opsiyonel ama önerilir (Gemini ile anlamlandırma)
GEMINI_API_KEY=buraya_gemini_api_key

# Bazı hesaplarda çalışan model ismi (sende bu çalışıyorsa bunu kullan)
GEMINI_MODEL=gemini-flash-latest
```

## Çalıştırma

```bash
./venv/bin/python main.py
```

## GitHub Actions ile her gün çalıştırma

Evet, bu bot GitHub Actions ile her gün otomatik çalıştırılabilir.

1) Repo ayarlarından **Secrets** ekleyin:
- `TELEGRAM_BOT_TOKEN`
- `TELEGRAM_CHAT_ID`
- `GEMINI_API_KEY` (opsiyonel)
- `GEMINI_MODEL` (opsiyonel)

2) `.github/workflows/daily.yml` ekleyin (örnek):

```yaml
name: Daily GitHub Trending Digest

on:
  schedule:
    - cron: "0 9 * * *" # UTC; TR saati için ayarlayın
  workflow_dispatch:

jobs:
  run:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.11"
      - run: pip install -r requirements.txt
      - run: python main.py
        env:
          TELEGRAM_BOT_TOKEN: ${{ secrets.TELEGRAM_BOT_TOKEN }}
          TELEGRAM_CHAT_ID: ${{ secrets.TELEGRAM_CHAT_ID }}
          GEMINI_API_KEY: ${{ secrets.GEMINI_API_KEY }}
          GEMINI_MODEL: ${{ secrets.GEMINI_MODEL }}
```

## Güvenlik

- `.env` git’e **eklenmez** (`.gitignore` içinde).
- Telegram/Gemini anahtarlarını **asla README’ye veya issue’lara koymayın**; sadece Secrets/`.env`.

