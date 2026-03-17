import os
import re
from datetime import datetime

import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv


GITHUB_TRENDING_URL = "https://github.com/trending"
GEMINI_API_URL = "https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent"


def load_config() -> tuple[str, str, str | None]:
    """
    Ortam değişkenlerinden Telegram yapılandırmasını yükler.
    Gerekli: TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID
    Opsiyonel: GEMINI_API_KEY
    """
    load_dotenv()

    bot_token = os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")
    gemini_api_key = os.getenv("GEMINI_API_KEY")

    if not bot_token or not chat_id:
        raise RuntimeError(
            "TELEGRAM_BOT_TOKEN ve TELEGRAM_CHAT_ID ortam değişkenlerini ayarlayın."
        )

    # Yaygın kurulum hatası: .env içinde placeholder bırakmak veya shell'de eski değerler
    if "BURAYA_BOT_TOKEN" in bot_token or bot_token.strip() == "":
        raise RuntimeError(
            "TELEGRAM_BOT_TOKEN placeholder görünüyor. `.env` içine BotFather'dan aldığınız gerçek token'ı yazın."
        )
    if "BURAYA_CHAT_ID" in chat_id or chat_id.strip() == "":
        raise RuntimeError(
            "TELEGRAM_CHAT_ID placeholder görünüyor. `getUpdates` içindeki chat.id değerini yazın."
        )

    return bot_token, chat_id, gemini_api_key


def fetch_trending_html() -> str:
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/123.0 Safari/537.36"
        )
    }
    response = requests.get(GITHUB_TRENDING_URL, headers=headers, timeout=20)
    response.raise_for_status()
    return response.text


def parse_trending_repos(html: str, limit: int = 10) -> list[dict]:
    """
    GitHub Trending sayfasından depo listesini çıkarır.
    Dönen her öğe:
    {
        "full_name": "owner/repo",
        "url": "https://github.com/owner/repo",
        "description": "...",
        "language": "...",
        "stars_today": 123
    }
    """
    soup = BeautifulSoup(html, "html.parser")
    repo_items = soup.select("article.Box-row")

    repos: list[dict] = []
    for article in repo_items[:limit]:
        # Başlık (owner / repo)
        a_tag = article.select_one("h2 a")
        if not a_tag:
            continue

        full_name = " ".join(a_tag.get_text(strip=True).split())
        full_name = full_name.replace(" / ", "/")
        url = "https://github.com" + a_tag.get("href", "")

        # Açıklama
        desc_tag = article.select_one("p")
        description = desc_tag.get_text(strip=True) if desc_tag else ""

        # Dil
        lang_tag = article.select_one('span[itemprop="programmingLanguage"]')
        language = lang_tag.get_text(strip=True) if lang_tag else ""

        # Bugün eklenen yıldız sayısı
        stars_today = 0
        stars_span = None
        for span in article.select("span"):
            text = span.get_text(strip=True)
            if text.endswith("stars today") or text.endswith("star today"):
                stars_span = text
                break
        if stars_span:
            try:
                stars_today = int(stars_span.split(" ")[0].replace(",", ""))
            except (ValueError, IndexError):
                stars_today = 0

        repos.append(
            {
                "full_name": full_name,
                "url": url,
                "description": description,
                "language": language,
                "stars_today": stars_today,
            }
        )

    return repos


def fetch_readme_excerpt(full_name: str, max_chars: int = 3500) -> str:
    """
    README içeriğinden kısa bir bölüm çekmeye çalışır.
    main/master ve yaygın README isimleri denenir.
    """
    if "/" not in full_name:
        return ""

    owner, repo = full_name.split("/", 1)
    candidates = [
        ("main", "README.md"),
        ("main", "readme.md"),
        ("main", "README.rst"),
        ("main", "README.txt"),
        ("master", "README.md"),
        ("master", "readme.md"),
        ("master", "README.rst"),
        ("master", "README.txt"),
    ]

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/123.0 Safari/537.36"
        )
    }

    for branch, filename in candidates:
        url = f"https://raw.githubusercontent.com/{owner}/{repo}/{branch}/{filename}"
        try:
            r = requests.get(url, headers=headers, timeout=15)
            if r.status_code != 200:
                continue
            text = r.text or ""
            text = text.replace("\r\n", "\n").strip()
            if not text:
                continue
            return text[:max_chars]
        except requests.RequestException:
            continue

    return ""


def _clean_llm_text(text: str) -> str:
    text = (text or "").strip()
    # Gemini bazen kod bloğu veya başlık döndürebiliyor; Telegram mesajına uygun sadeleştirelim.
    text = re.sub(r"```[\s\S]*?```", "", text).strip()
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    return text


def gemini_use_cases(
    api_key: str,
    repo: dict,
    readme_excerpt: str,
    timeout_s: int = 25,
) -> list[str]:
    """
    Repo açıklaması + README parçasını Gemini'ye gönderip
    'bu benim ne işime yarar?' odaklı kullanım alanları üretir.
    """
    name = repo.get("full_name", "")
    desc = repo.get("description", "")
    lang = repo.get("language", "")

    prompt = (
        "Aşağıdaki GitHub projesini değerlendir.\n"
        "Amacım: 'Bu benim ne işime yarar?' sorusuna pratik cevaplar.\n\n"
        "Kurallar:\n"
        "- Türkçe yaz.\n"
        "- 3 ila 5 madde üret.\n"
        "- Her madde 1 cümle olsun.\n"
        "- Pazarlama dili kullanma; somut kullanım senaryosu yaz.\n"
        "- Belirsizsen varsayımını madde içinde belirt.\n\n"
        f"Proje adı: {name}\n"
        f"Dil: {lang}\n"
        f"Kısa açıklama: {desc}\n\n"
        "README alıntısı (kısmi):\n"
        f"{readme_excerpt}\n"
    )

    url = f"{GEMINI_API_URL}?key={api_key}"
    payload = {
        "contents": [
            {
                "role": "user",
                "parts": [{"text": prompt}],
            }
        ],
        "generationConfig": {
            "temperature": 0.4,
            "maxOutputTokens": 220,
        },
    }

    try:
        resp = requests.post(url, json=payload, timeout=timeout_s)
        resp.raise_for_status()
        data = resp.json()
        text = (
            data.get("candidates", [{}])[0]
            .get("content", {})
            .get("parts", [{}])[0]
            .get("text", "")
        )
        text = _clean_llm_text(text)
    except (requests.RequestException, ValueError, KeyError, IndexError):
        return []

    if not text:
        return []

    # Çıktıyı maddelere dönüştür (•, -, 1. vs.)
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    bullets: list[str] = []
    for ln in lines:
        ln = re.sub(r"^[-•]\s*", "", ln)
        ln = re.sub(r"^\d+\.\s*", "", ln)
        if ln:
            bullets.append(ln)

    # Çok uzun/az ise kırp
    bullets = bullets[:5]
    return bullets


def guess_use_cases(repo: dict) -> list[str]:
    """
    Depo açıklamasına ve diline göre kaba kullanım alanı tahmini yapar.
    Sadece basit anahtar kelime eşleştirmesi kullanır.
    """
    desc = (repo.get("description") or "").lower()
    lang = (repo.get("language") or "").lower()

    use_cases: list[str] = []

    # Alan bazlı anahtar kelimeler
    if any(k in desc for k in ["ai", "ml", "machine learning", "deep learning"]):
        use_cases.append("Yapay zeka / makine öğrenimi projeleri")
    if any(k in desc for k in ["nlp", "language model", "llm"]):
        use_cases.append("Doğal dil işleme (NLP) uygulamaları")
    if any(k in desc for k in ["api", "microservice", "rest", "graphql"]):
        use_cases.append("Web servisleri ve mikroservis mimarisi")
    if any(k in desc for k in ["web", "frontend", "react", "vue", "next.js", "nuxt"]):
        use_cases.append("Web arayüzü / frontend uygulamaları")
    if any(k in desc for k in ["cli", "command line", "terminal"]):
        use_cases.append("Komut satırı araçları ve otomasyon")
    if any(k in desc for k in ["database", "sql", "nosql", "orm"]):
        use_cases.append("Veritabanı katmanı ve veri yönetimi")
    if any(k in desc for k in ["monitoring", "observability", "logging", "metrics"]):
        use_cases.append("Sistem gözlemlenebilirliği ve izleme")
    if any(k in desc for k in ["security", "auth", "encryption", "jwt"]):
        use_cases.append("Güvenlik, kimlik doğrulama ve yetkilendirme")
    if any(k in desc for k in ["devops", "kubernetes", "docker", "cicd", "ci/cd"]):
        use_cases.append("DevOps, konteyner ve CI/CD süreçleri")
    if any(k in desc for k in ["data", "analytics", "etl", "warehouse"]):
        use_cases.append("Veri analitiği ve veri boru hatları")
    if any(k in desc for k in ["game", "gaming", "unity", "unreal"]):
        use_cases.append("Oyun geliştirme projeleri")

    # Dile göre kaba sınıflandırma
    if not use_cases:
        if lang in ["python"]:
            use_cases.append("Hızlı prototipleme, veri bilimi ve backend servisler")
        elif lang in ["javascript", "typescript"]:
            use_cases.append("Web uygulamaları ve tam yığın (fullstack) geliştirme")
        elif lang in ["go"]:
            use_cases.append("Yüksek performanslı backend servisleri ve altyapı araçları")
        elif lang in ["rust"]:
            use_cases.append("Performans kritik sistemler ve CLI araçları")
        elif lang in ["java", "kotlin"]:
            use_cases.append("Kurumsal backend sistemleri ve Android uygulamaları")
        elif lang in ["c#", "f#"]:
            use_cases.append(".NET tabanlı uygulamalar ve oyun motorları")

    if not use_cases:
        use_cases.append("Genel amaçlı yazılım projeleri (detay için repo açıklamasına bakın)")

    return use_cases


def build_message(repos: list[dict], gemini_api_key: str | None) -> str:
    today_str = datetime.now().strftime("%d.%m.%Y")
    lines: list[str] = []
    lines.append(f"📌 GitHub Trending - {today_str}")
    lines.append("")

    if not repos:
        lines.append("Bugün için trend olan depo bulunamadı.")
        return "\n".join(lines)

    for idx, repo in enumerate(repos, start=1):
        use_cases = guess_use_cases(repo)

        lines.append(f"{idx}. {repo['full_name']} ({repo.get('language') or 'Dil belirtilmemiş'})")
        if repo.get("description"):
            lines.append(f"   - Açıklama: {repo['description']}")
        if repo.get("stars_today"):
            lines.append(f"   - Bugün eklenen yıldız: {repo['stars_today']}")

        # AI varsa: README çek + Gemini ile anlamlandır. Yoksa: kural-tabanlı tahmin.
        ai_bullets: list[str] = []
        if gemini_api_key:
            readme_excerpt = fetch_readme_excerpt(repo["full_name"])
            if readme_excerpt:
                ai_bullets = gemini_use_cases(gemini_api_key, repo, readme_excerpt)

        lines.append("   - Bu benim ne işime yarar?")
        if ai_bullets:
            for b in ai_bullets:
                lines.append(f"     • {b}")
        else:
            for uc in use_cases:
                lines.append(f"     • {uc}")

        lines.append(f"   - Repo: {repo['url']}")
        lines.append("")  # boş satır

    return "\n".join(lines)


def send_telegram_message(bot_token: str, chat_id: str, text: str) -> None:
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": text,
        "disable_web_page_preview": True,
    }
    response = requests.post(url, data=payload, timeout=20)
    response.raise_for_status()


def main() -> None:
    bot_token, chat_id, gemini_api_key = load_config()
    html = fetch_trending_html()
    repos = parse_trending_repos(html, limit=10)
    message = build_message(repos, gemini_api_key)
    send_telegram_message(bot_token, chat_id, message)


if __name__ == "__main__":
    main()

