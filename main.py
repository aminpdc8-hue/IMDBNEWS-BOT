import os
import re
import json
import time
import html
import hashlib
import requests
import feedparser

from urllib.parse import urlparse


# ==========================================
# IMDBNEWS BOT - CONFIG
# ==========================================

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHANNEL_ID = os.getenv("TELEGRAM_CHANNEL_ID")
TRANSLATION_EMAIL = os.getenv("TRANSLATION_EMAIL", "")

MAX_NEWS = 5
DATABASE = "published.json"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120 Safari/537.36"
}

TELEGRAM_API = f"https://api.telegram.org/bot{BOT_TOKEN}"


# ==========================================
# NEWS SOURCES
# ==========================================

SOURCES = [
    {
        "name": "IMDb",
        "urls": [
            "https://www.imdb.com/rg/rss/news-channel/news/",
            "https://www.imdb.com/news/rss/"
        ]
    },
    {
        "name": "Variety",
        "urls": [
            "https://variety.com/feed/"
        ]
    },
    {
        "name": "Deadline",
        "urls": [
            "https://deadline.com/feed/"
        ]
    },
    {
        "name": "Hollywood Reporter",
        "urls": [
            "https://www.hollywoodreporter.com/feed/"
        ]
    }
]


# ==========================================
# MOVIE KEYWORDS
# ==========================================

KEYWORDS = [
    "movie", "film", "cinema", "hollywood",
    "actor", "actress", "director", "producer",
    "trailer", "cast", "release date",
    "netflix", "amazon", "prime video",
    "disney", "warner", "paramount",
    "universal", "sony pictures",
    "box office", "series", "season",
    "horror", "thriller", "comedy",
    "drama", "action", "sci-fi",
    "fantasy", "animation",
    "oscars", "emmy", "golden globe",
    "friday the 13th", "jason",
    "marvel", "dc studios"
]


# ==========================================
# DATABASE
# ==========================================

def load_database():
    if not os.path.exists(DATABASE):
        return []

    try:
        with open(DATABASE, "r", encoding="utf-8") as file:
            data = json.load(file)

        if isinstance(data, list):
            return data

        return []

    except Exception:
        return []


def save_database(data):
    try:
        data = data[-1000:]

        with open(DATABASE, "w", encoding="utf-8") as file:
            json.dump(data, file, ensure_ascii=False, indent=2)

    except Exception as error:
        print("Database save error:", error)


# ==========================================
# TEXT CLEANING
# ==========================================

def clean_text(text):
    if not text:
        return ""

    text = re.sub(
        r"<script.*?</script>",
        "",
        text,
        flags=re.I | re.S
    )

    text = re.sub(
        r"<style.*?</style>",
        "",
        text,
        flags=re.I | re.S
    )

    text = re.sub(r"<[^>]+>", " ", text)

    text = html.unescape(text)

    text = re.sub(r"\s+", " ", text)

    return text.strip()


def telegram_safe(text):
    return html.escape(str(text or ""), quote=False)


# ==========================================
# IMAGE EXTRACTION
# ==========================================

def get_image(entry):

    # media:content / media:thumbnail
    for key in ["media_content", "media_thumbnail"]:

        items = entry.get(key, [])

        if isinstance(items, list):

            for item in items:

                url = item.get("url")

                if url and url.startswith("http"):
                    return url

    # Enclosure
    enclosures = entry.get("enclosures", [])

    for item in enclosures:

        url = item.get("href") or item.get("url")

        if url and url.startswith("http"):
            return url

    # RSS thumbnail
    thumbnail = entry.get("image")

    if isinstance(thumbnail, dict):

        url = thumbnail.get("href") or thumbnail.get("url")

        if url and url.startswith("http"):
            return url

    # HTML content
    content = entry.get("content", [])

    for item in content:

        value = item.get("value", "")

        match = re.search(
            r'<img[^>]+src=["\']([^"\']+)["\']',
            value,
            re.I
        )

        if match:
            return html.unescape(match.group(1))

    # Summary image
    summary = entry.get("summary", "")

    match = re.search(
        r'<img[^>]+src=["\']([^"\']+)["\']',
        summary,
        re.I
    )

    if match:
        return html.unescape(match.group(1))

    return None


# ==========================================
# DOWNLOAD IMAGE
# ==========================================

def download_image(image_url):

    if not image_url:
        return None

    try:

        response = requests.get(
            image_url,
            headers=HEADERS,
            timeout=25,
            stream=True
        )

        response.raise_for_status()

        content_type = response.headers.get(
            "Content-Type", ""
        ).lower()

        if not content_type.startswith("image/"):
            print("Image skipped: invalid content type")
            return None

        image_data = response.content

        if not image_data:
            return None

        # Telegram photo size limit
        if len(image_data) > 9 * 1024 * 1024:
            print("Image skipped: too large")
            return None

        extension = ".jpg"

        if "png" in content_type:
            extension = ".png"

        elif "webp" in content_type:
            extension = ".webp"

        return image_data, extension, content_type

    except Exception as error:

        print("Image download error:", error)

        return None


# ==========================================
# TRANSLATION
# ==========================================

def translate_text(text):

    if not text:
        return ""

    text = text[:4500]

    try:

        url = "https://api.mymemory.translated.net/get"

        params = {
            "q": text,
            "langpair": "en|fa"
        }

        if TRANSLATION_EMAIL:
            params["de"] = TRANSLATION_EMAIL

        response = requests.get(
            url,
            params=params,
            headers=HEADERS,
            timeout=30
        )

        response.raise_for_status()

        data = response.json()

        translated = data.get(
            "responseData", {}
        ).get("translatedText", "")

        translated = html.unescape(translated)

        if translated and translated.strip():
            return translated.strip()

    except Exception as error:

        print("Translation error:", error)

    return ""


# ==========================================
# FETCH RSS
# ==========================================

def fetch_news():

    articles = []

    for source in SOURCES:

        print("Reading RSS:", source["name"])

        source_articles = []

        for feed_url in source["urls"]:

            try:

                response = requests.get(
                    feed_url,
                    headers=HEADERS,
                    timeout=25
                )

                response.raise_for_status()

                feed = feedparser.parse(response.content)

                entries = feed.entries

                if entries:

                    for entry in entries:

                        title = clean_text(
                            entry.get("title", "")
                        )

                        summary = clean_text(
                            entry.get("summary", "")
                        )

                        link = entry.get("link", "")

                        if not title or not link:
                            continue

                        if not link.startswith("http"):
                            continue

                        article_id = entry.get("id") or link

                        image_url = get_image(entry)

                        article = {
                            "id": str(article_id),
                            "title": title,
                            "summary": summary,
                            "link": link,
                            "source": source["name"],
                            "image": image_url
                        }

                        source_articles.append(article)

                    if source_articles:
                        break

            except Exception as error:

                print(
                    "RSS error:",
                    source["name"],
                    error
                )

        print(
            "Articles found:",
            len(source_articles),
            source["name"]
        )

        articles.extend(source_articles)

    return articles


# ==========================================
# MOVIE NEWS FILTER
# ==========================================

def is_movie_news(article):

    text = (
        article["title"] + " " +
        article["summary"]
    ).lower()

    return any(
        keyword in text
        for keyword in KEYWORDS
    )


# ==========================================
# UNIQUE ID
# ==========================================

def make_id(article):

    value = article["id"] or article["link"]

    return hashlib.sha256(
        value.encode("utf-8")
    ).hexdigest()


# ==========================================
# BUILD POST
# ==========================================

def build_message(article, english_summary, persian_title, persian_summary):

    title_en = telegram_safe(article["title"])

    title_fa = telegram_safe(persian_title)

    english = telegram_safe(english_summary)

    persian = telegram_safe(persian_summary)

    source = telegram_safe(article["source"])

    link = html.escape(
        article["link"],
        quote=True
    )

    message = (
        "🎬 <b>IMDBNEWS | اخبار سینمای جهان</b>\n\n"

        "🇬🇧 <b>ORIGINAL NEWS</b>\n\n"

        f"<b>{title_en}</b>\n\n"

        f"{english}\n\n"

        "━━━━━━━━━━━━━━\n\n"

        "🇮🇷 <b>ترجمه فارسی</b>\n\n"

        f"<b>{title_fa}</b>\n\n"

        f"{persian}\n\n"

        f"📰 منبع: {source}\n\n"

        f'🔗 <a href="{link}">مشاهده خبر اصلی</a>\n\n'

        "📢 @IMDBNEWS_FA"
    )

    return message


# ==========================================
# TELEGRAM SEND MESSAGE
# ==========================================

def send_message(message):

    url = f"{TELEGRAM_API}/sendMessage"

    payload = {
        "chat_id": CHANNEL_ID,
        "text": message,
        "parse_mode": "HTML",
        "disable_web_page_preview": True
    }

    try:

        response = requests.post(
            url,
            data=payload,
            timeout=40
        )

        if not response.ok:

            print(
                "Telegram message error:",
                response.status_code,
                response.text[:1000]
            )

            return False

        result = response.json()

        return result.get("ok", False)

    except Exception as error:

        print("Send message error:", error)

        return False


# ==========================================
# TELEGRAM SEND PHOTO
# ==========================================

def send_photo(image_data):

    url = f"{TELEGRAM_API}/sendPhoto"

    try:

        image_bytes, extension, content_type = image_data

        files = {
            "photo": (
                "news_image" + extension,
                image_bytes,
                content_type
            )
        }

        payload = {
            "chat_id": CHANNEL_ID
        }

        response = requests.post(
            url,
            data=payload,
            files=files,
            timeout=60
        )

        if not response.ok:

            print(
                "Telegram photo error:",
                response.status_code,
                response.text[:1000]
            )

            return False

        return response.json().get("ok", False)

    except Exception as error:

        print("Send photo error:", error)

        return False


# ==========================================
# PROCESS ARTICLE
# ==========================================

def process_article(article):

    print("Processing:", article["title"])

    title_fa = translate_text(
        article["title"]
    )

    if not title_fa:

        print("Skipped: title translation failed")

        return False

    english_summary = article["summary"]

    if not english_summary:
        english_summary = article["title"]

    # Limit original text
    english_summary = english_summary[:2200]

    persian_summary = translate_text(
        english_summary
    )

    if not persian_summary:

        print("Skipped: summary translation failed")

        return False

    persian_summary = persian_summary[:2200]

    message = build_message(
        article,
        english_summary,
        title_fa,
        persian_summary
    )

    # Telegram message limit
    if len(message) > 4000:

        message = message[:3950] + "\n\n📢 @IMDBNEWS_FA"

    # Try photo first
    image_data = download_image(
        article.get("image")
    )

    if image_data:

        photo_sent = send_photo(image_data)

        if photo_sent:
            print("Photo published")

        else:
            print("Photo failed - sending text only")

    # Send complete bilingual post
    message_sent = send_message(message)

    if message_sent:

        print("Published:", article["title"])

        return True

    print("Message publication failed")

    return False


# ==========================================
# MAIN
# ==========================================

def main():

    print("================================")
    print("IMDBNEWS BOT STARTED")
    print("================================")

    if not BOT_TOKEN or not CHANNEL_ID:

        print("ERROR: Telegram secrets are missing")

        return

    published = load_database()

    print(
        "Previously published:",
        len(published)
    )

    articles = fetch_news()

    print(
        "Total articles:",
        len(articles)
    )

    new_articles = []

    for article in articles:

        article_id = make_id(article)

        if article_id in published:
            continue

        if not is_movie_news(article):
            continue

        article["unique_id"] = article_id

        new_articles.append(article)

    print(
        "New movie news:",
        len(new_articles)
    )

    count = 0

    for article in new_articles:

        if count >= MAX_NEWS:
            break

        success = process_article(article)

        if success:

            published.append(
                article["unique_id"]
            )

            save_database(published)

            count += 1

        time.sleep(3)

    print("================================")

    print(
        "Published news:",
        count
    )

    print("IMDBNEWS BOT FINISHED")


if __name__ == "__main__":
    main()
