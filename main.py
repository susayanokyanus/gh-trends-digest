import os
import re
from datetime import datetime
from typing import Optional, Tuple

import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv


GITHUB_TRENDING_URL = "https://github.com/trending"
GEMINI_API_BASE = "https://generativelanguage.googleapis.com/v1beta/models"
AI_ENRICH_LIMIT = 5
GEMINI_DEBUG = os.getenv("GEMINI_DEBUG", "").strip() in {"1", "true", "True", "yes", "YES"}
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-1.5-flash").strip() or "gemini-1.5-flash"
TELEGRAM_MESSAGE_LIMIT = 3900  # Telegram 4096; biraz pay bırakalım
AI_TEXT_MAX_CHARS_PER_REPO = 3000  # tek repo çok uzamasın (5 repo gönderiyoruz)


def _truncate_nicely(text: str, max_chars: int) -> str:
    """
    Metni mümkünse cümle sonundan kırpar; yoksa satır sonu/boşlukla keser.
    """
    text = (text or "").strip()
    if len(text) <= max_chars:
        return text

    head = text[:max_chars].rstrip()
    # Önce cümle sonunu ara
    last_sentence = max(head.rfind(". "), head.rfind("! "), head.rfind("? "))
    if last_sentence > int(max_chars * 0.55):
        return head[: last_sentence + 1].rstrip() + "\n• (Devamı için repoya göz at.)"

    # Sonra çift newline/tek newline/boşluk
    for sep in ["\n\n", "\n", " "]:
        cut = head.rfind(sep)
        if cut > int(max_chars * 0.6):
            return head[:cut].rstrip() + "\n• (Devamı için repoya göz at.)"

    return head.rstrip() + "\n• (Devamı için repoya göz at.)"


def load_config() -> Tuple[str, str, Optional[str]]:
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
    # Basit markdown vurgularını temizle
    text = re.sub(r"\*\*(.*?)\*\*", r"\1", text)
    text = re.sub(r"\*(.*?)\*", r"\1", text)
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    return text


def _split_sentences(text: str) -> list[str]:
    """
    Basit cümle bölücü: . ! ? sonrası böl.
    """
    t = (text or "").strip()
    if not t:
        return []
    parts = re.split(r"(?<=[.!?])\s+", t)
    return [p.strip() for p in parts if p.strip()]


def _parse_gemini_output(text: str) -> tuple[Optional[str], list[str]]:
    """
    Gemini çıktısından 'Özet' ve 'Fikirler' kısmını ayrıştırır.
    """
    t = (text or "").strip()
    if not t:
        return None, []

    # Özet kısmı: "Özet:" sonrası, "Fikirler:" öncesi
    summary = None
    if "Özet:" in t:
        after = t.split("Özet:", 1)[1]
        if "Fikirler:" in after:
            summary = after.split("Fikirler:", 1)[0].strip()
        else:
            summary = after.strip()

    # Fikirler: • ile başlayan satırlar
    bullets: list[str] = []
    for ln in t.splitlines():
        ln = ln.strip()
        if ln.startswith("•"):
            bullets.append(re.sub(r"^•\s*", "", ln).strip())

    return summary, bullets


def _normalize_summary(summary: str) -> Optional[str]:
    """
    Özet 3-4 cümle olacak şekilde normalize eder.
    """
    sentences = _split_sentences(summary)
    if len(sentences) < 3:
        return None
    sentences = sentences[:4]
    merged = " ".join(sentences).strip()
    return merged if merged else None


def _normalize_bullets(bullets: list[str], target: int = 4, max_chars: int = 180) -> list[str]:
    """
    Her fikri tek cümleye indirger, yarım kalmayı engeller ve tam target kadar döndürür.
    """
    cleaned: list[str] = []
    for b in bullets:
        sents = _split_sentences(b)
        one = sents[0] if sents else b.strip()
        one = one.strip()
        if not one:
            continue
        if len(one) > max_chars:
            one = one[:max_chars].rsplit(" ", 1)[0].rstrip()
        if one and one[-1] not in ".!?":
            one += "."
        cleaned.append(one)
        if len(cleaned) >= target:
            break

    return cleaned


def _gemini_generate_content(api_key: str, model: str, prompt: str, timeout_s: int) -> str:
    """
    Gemini REST çağrısı. API key query param yerine header ile gönderilir.
    """
    url = f"{GEMINI_API_BASE}/{model}:generateContent"
    headers = {
        "Content-Type": "application/json",
        "x-goog-api-key": api_key,
    }
    payload = {
        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature": 0.2,
            "maxOutputTokens": 1400,
        },
    }
    resp = requests.post(url, json=payload, headers=headers, timeout=timeout_s)
    resp.raise_for_status()
    data = resp.json()
    return (
        data.get("candidates", [{}])[0]
        .get("content", {})
        .get("parts", [{}])[0]
        .get("text", "")
    )


def gemini_use_cases(
    api_key: str,
    repo: dict,
    readme_excerpt: str,
    timeout_s: int = 35,
) -> str:
    """
    Repo açıklaması + README parçasını Gemini'ye gönderip
    'bu benim ne işime yarar?' odaklı kullanım alanları üretir.
    """
    name = repo.get("full_name", "")
    desc = repo.get("description", "")
    lang = repo.get("language", "")

    def is_good(text: str) -> bool:
        summary_raw, bullets_raw = _parse_gemini_output(text)
        if not summary_raw:
            return False
        summary_norm = _normalize_summary(summary_raw)
        bullets_norm = _normalize_bullets(bullets_raw, target=4)
        return bool(summary_norm) and len(bullets_norm) == 4

    def fallback_ideas() -> str:
        """
        Gemini hiç istenen formatta dönmezse, mesajın 'Fikirler' kısmı boş kalmasın diye
        kural-tabanlı tahminlerden 4 kısa fikir üret.
        """
        base = guess_use_cases(repo)
        # 4'e tamamla (aynı olmasın diye basit çeşitlilik)
        expanded: list[str] = []
        for uc in base:
            expanded.append(f"• {uc} için küçük bir PoC/prototip çıkarıp kendi ihtiyacına uyarlayabilirsin.")
            if len(expanded) >= 4:
                break
        while len(expanded) < 4:
            expanded.append("• Repo örneklerini çalıştırıp kendi kullanım senaryona göre bir demo çıkarabilirsin.")

        return (
            "Özet: Bu proje için yapay zeka çıktısı beklenen formatta üretilemedi; aşağıda hızlı kullanım fikirleri var.\n"
            "Fikirler:\n" + "\n".join(expanded[:4])
        )

    prompt = (
        "Aşağıdaki GitHub projesini değerlendir.\n"
        "Amacım: 'Bu benim ne işime yarar?' sorusuna düşünülmüş ve yaratıcı cevaplar.\n\n"
        "Kurallar:\n"
        "- Türkçe yaz.\n"
        "- Pazarlama dili kullanma; somut kullanım senaryosu yaz.\n"
        "- Belirsizsen varsayımını açıkça belirt.\n"
        "- Markdown kullanma.\n\n"
        "Çıktı formatı (aynen uygula):\n"
        "1) 'Özet:' ile başlayan TEK bir paragraf yaz (3-4 cümle).\n"
        "2) 'Fikirler:' satırından sonra EN FAZLA 4 maddelik liste ver; her satır '• ' ile başlasın ve 1 cümle olsun.\n"
        "3) 'Fikirler' bölümünü ASLA atlama.\n\n"
        f"Proje adı: {name}\n"
        f"Dil: {lang}\n"
        f"Kısa açıklama: {desc}\n\n"
        "README alıntısı (kısmi, boş olabilir):\n"
        f"{readme_excerpt}\n"
    )

    try:
        # Bazı hesaplarda model isimleri farklı olabiliyor; 404 alırsak alternatifleri dene.
        model_candidates = [GEMINI_MODEL]
        for alt in ["gemini-1.5-flash-latest", "gemini-flash-latest", "gemini-1.5-flash-002"]:
            if alt not in model_candidates:
                model_candidates.append(alt)

        last_err: Optional[Exception] = None
        text = ""
        for model in model_candidates:
            try:
                text = _gemini_generate_content(api_key, model, prompt, timeout_s)
                if GEMINI_DEBUG and model != GEMINI_MODEL:
                    print(f"[GEMINI_DEBUG] Model fallback ile başarılı: {model}")
                break
            except requests.HTTPError as e:
                last_err = e
                # 404 -> model/method bulunamadı, alternatif dene
                status = getattr(e.response, "status_code", None)
                if GEMINI_DEBUG:
                    print(f"[GEMINI_DEBUG] Gemini HTTPError (model={model}, status={status})")
                if status == 404:
                    continue
                raise
            except requests.RequestException as e:
                last_err = e
                raise

        if not text and last_err:
            raise last_err

        text = _clean_llm_text(text)
    except (requests.RequestException, ValueError, KeyError, IndexError) as e:
        if GEMINI_DEBUG:
            print(f"[GEMINI_DEBUG] Gemini çağrısı başarısız: {e}")
        return ""

    if not text:
        return ""

    text = text.strip()
    if is_good(text):
        summary_raw, bullets_raw = _parse_gemini_output(text)
        summary_norm = _normalize_summary(summary_raw or "")
        bullets_norm = _normalize_bullets(bullets_raw, target=4)
        if summary_norm and len(bullets_norm) == 4:
            return "Özet: " + summary_norm + "\nFikirler:\n" + "\n".join(f"• {b}" for b in bullets_norm)

    # Çıktı eksik geldiyse 2 kez daha, daha sıkı formatla yeniden dene.
    retry_prompt = (
        "Önceki yanıt eksik/format dışı geldi. Lütfen TAM ve belirtilen formatta tekrar yaz.\n"
        "Sadece aşağıdaki formatı kullan:\n"
        "Özet: <tek paragraf, 3-4 cümle>\n"
        "Fikirler:\n"
        "• <madde 1>\n"
        "• <madde 2>\n"
        "• <madde 3>\n"
        "• <madde 4>\n"
        "(En fazla 4 madde. 'Fikirler' olmadan bitirme.)\n\n"
        f"Proje adı: {name}\n"
        f"Dil: {lang}\n"
        f"Kısa açıklama: {desc}\n\n"
        "README alıntısı (kısmi, boş olabilir):\n"
        f"{readme_excerpt}\n"
    )

    try:
        for _ in range(2):
            text2 = ""
            for model in model_candidates:
                try:
                    text2 = _gemini_generate_content(api_key, model, retry_prompt, timeout_s)
                    break
                except requests.HTTPError as e:
                    status = getattr(e.response, "status_code", None)
                    if status == 404:
                        continue
                    raise
            text2 = _clean_llm_text(text2).strip()
            if is_good(text2):
                summary_raw, bullets_raw = _parse_gemini_output(text2)
                summary_norm = _normalize_summary(summary_raw or "")
                bullets_norm = _normalize_bullets(bullets_raw, target=4)
                if summary_norm and len(bullets_norm) == 4:
                    return "Özet: " + summary_norm + "\nFikirler:\n" + "\n".join(
                        f"• {b}" for b in bullets_norm
                    )
    except (requests.RequestException, ValueError, KeyError, IndexError) as e:
        if GEMINI_DEBUG:
            print(f"[GEMINI_DEBUG] Gemini retry başarısız: {e}")

    # Yine kötü geldiyse: Fikirler olmadan asla bitirme => fallback üret
    return fallback_ideas()


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


def _build_repo_message(idx: int, repo: dict, gemini_api_key: Optional[str]) -> str:
    use_cases = guess_use_cases(repo)

    lines: list[str] = []
    lines.append(f"{idx}. {repo['full_name']} ({repo.get('language') or 'Dil belirtilmemiş'})")
    if repo.get("description"):
        lines.append(f"- Açıklama: {repo['description']}")
    if repo.get("stars_today"):
        lines.append(f"- Bugün eklenen yıldız: {repo['stars_today']}")

    ai_text = ""
    if gemini_api_key and idx <= AI_ENRICH_LIMIT:
        readme_excerpt = fetch_readme_excerpt(repo["full_name"])
        ai_text = gemini_use_cases(gemini_api_key, repo, readme_excerpt)
        if GEMINI_DEBUG and not readme_excerpt:
            print(f"[GEMINI_DEBUG] README bulunamadı: {repo['full_name']}")

    lines.append("- Bu benim ne işime yarar?")
    if ai_text:
        ai_text = _truncate_nicely(ai_text, AI_TEXT_MAX_CHARS_PER_REPO)
        lines.extend([ln.strip() for ln in ai_text.splitlines() if ln.strip()])
    else:
        for uc in use_cases:
            lines.append(f"• {uc}")

    lines.append(f"- Repo: {repo['url']}")
    return "\n".join(lines).strip()


def build_messages(repos: list[dict], gemini_api_key: Optional[str]) -> list[str]:
    today_str = datetime.now().strftime("%d.%m.%Y")
    messages: list[str] = [f"📌 GitHub Trending - {today_str}"]

    if not repos:
        messages.append("Bugün için trend olan depo bulunamadı.")
        return messages

    for idx, repo in enumerate(repos, start=1):
        messages.append(_build_repo_message(idx, repo, gemini_api_key))

    return messages


def _split_telegram_text(text: str, limit: int = TELEGRAM_MESSAGE_LIMIT) -> list[str]:
    """
    Telegram mesaj limiti için metni parçalar.
    Öncelik: boş satır, sonra satır sonu.
    """
    text = text.strip()
    if len(text) <= limit:
        return [text]

    chunks: list[str] = []
    remaining = text
    while remaining:
        if len(remaining) <= limit:
            chunks.append(remaining.strip())
            break

        candidate = remaining[:limit]
        cut = candidate.rfind("\n\n")
        if cut < 0:
            cut = candidate.rfind("\n")
        if cut < 0 or cut < int(limit * 0.6):
            cut = limit

        chunk = remaining[:cut].strip()
        if chunk:
            chunks.append(chunk)
        remaining = remaining[cut:].lstrip()

    return chunks


def send_telegram_message(bot_token: str, chat_id: str, text: str) -> None:
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    for part in _split_telegram_text(text):
        payload = {
            "chat_id": chat_id,
            "text": part,
            "disable_web_page_preview": True,
        }
        response = requests.post(url, data=payload, timeout=20)
        response.raise_for_status()


def main() -> None:
    bot_token, chat_id, gemini_api_key = load_config()
    html = fetch_trending_html()
    repos = parse_trending_repos(html, limit=5)
    for msg in build_messages(repos, gemini_api_key):
        send_telegram_message(bot_token, chat_id, msg)


if __name__ == "__main__":
    main()

