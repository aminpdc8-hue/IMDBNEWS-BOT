import os
import json
import time
import html
import re
import requests
import feedparser

# =====================================
# CONFIG
# =====================================

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHANNEL_ID = os.getenv("TELEGRAM_CHANNEL_ID")
TRANSLATION_EMAIL = os.getenv("TRANSLATION_EMAIL", "")

MAX_NEWS = 5
DATABASE = "published.json"

HEADERS = {
    "User-Agent": "Mozilla/5.0 IMDBNEWS BOT"
}

# =====================================
# NEWS SOURCES
# =====================================

SOURCES = [
    {
        "name": "IMDb",
        "url": "https://www.imdb.com/rg/rss/news-channel/news/"
    },
    {
        "name": "Variety",
        "url": "https://variety.com/feed/"
    },
    {
        "name": "Deadline",
        "url": "https://deadline.com/feed/"
    },
    {
        "name": "Hollywood Reporter",
        "url": "https://www.hollywoodreporter.com/feed/"
    }
]

KEYWORDS = [
    "movie", "film", "cinema", "actor", "actress",
    "director", "hollywood", "netflix", "hbo",
    "amazon", "prime video", "disney", "marvel",
    "series", "season", "trailer", "casting",
    "oscar", "golden globe", "box office",
    "streaming", "warner bros", "paramount",
    "television", "filmmaker", "festival",
    "tv", "cinematography", "screenplay"
]

# =====================================
# DATABASE
# =====================================

def load_database():

    try:
        with open(DATABASE, "r", encoding="utf-8") as file:
            data = json.load(file)

        return data if isinstance(data, list) else []

    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return []


def save_database(data):

    with open(DATABASE, "w", encoding="utf-8") as file:

        json.dump(
            data[-1000:],
            file,
            ensure_ascii=False,
            indent=2
        )


# =====================================
# TEXT CLEANER
# =====================================

def clean_text(value):

    value = re.sub(r"<[^>]+>", " ", value or "")
    value = html.unescape(value)

    return re.sub(r"\s+", " ", value).strip()


# =====================================
# IMAGE EXTRACTOR
# =====================================

def get_image(item):

    media = item.get("media_content", [])

    for image in media:

        image_url = image.get("url", "")

        if image_url:
            return image_url

    thumbnails = item.get("media_thumbnail", [])

    for image in thumbnails:

        image_url = image.get("url", "")

        if image_url:
            return image_url

    enclosures = item.get("enclosures", [])

    for image in enclosures:

        image_url = image.get("href", "")
        image_type = image.get("type", "")

        if image_url and image_type.startswith("image/"):
            return image_url

    contents = item.get("content", [])

    for content in contents:

        match = re.search(
            r'<img[^>]+src=["\']([^"\']+)["\']',
            content.get("value", ""),
            re.IGNORECASE
        )

        if match:
            return html.unescape(match.group(1))

    summary = item.get("summary", "")

    match = re.search(
        r'<img[^>]+src=["\']([^"\']+)["\']',
        summary,
        re.IGNORECASE
    )

    if match:
        return html.unescape(match.group(1))

    return None


# =====================================
# NEWS FILTER
# =====================================

def is_movie_news(article):

    text = (
        article.get("title", "") + " " +
        article.get("summary", "")
    ).lower()

    return any(
        word in text
        for word in KEYWORDS
    )


# =====================================
# TRANSLATION
# =====================================

def split_text(text, limit=400):

    words = text.split()

    chunks = []
    current = ""

    for word in words:

        candidate = (current + " " + word).strip()

        if len(candidate) > limit and current:

            chunks.append(current)
            current = word

        else:
            current = candidate

    if current:
        chunks.append(current)

    return chunks


def translate(text):

    text = clean_text(text)

    if not text:
        return ""

    translated_parts = []

    for chunk in split_text(text):

        success = False

        for attempt in range(3):

            try:

                params = {
                    "q": chunk,
                    "langpair": "en|fa"
                }

                if TRANSLATION_EMAIL:
                    params["de"] = TRANSLATION_EMAIL

                response = requests.get(
                    "https://api.mymemory.translated.net/get",
                    params=params,
                    headers=HEADERS,
                    timeout=30
                )

                response.raise_for_status()

                data = response.json()

                if str(data.get("responseStatus")) != "200":
                    raise RuntimeError(
                        data.get("responseDetails", "Translation failed")
                    )

                result = data.get(
                    "responseData", {}
                ).get("translatedText", "")

                if not result:
                    raise RuntimeError("Empty translation")

                translated_parts.append(
                    clean_text(result)
                )

                success = True

                time.sleep(1)

                break

            except Exception as error:

                print("Translation error:", str(error))

                time.sleep(3 * (attempt + 1))

        if not success:
            return None

    return " ".join(translated_parts)


# =====================================
# RSS NEWS ENGINE
# =====================================

def get_news():

    articles = []
    seen_links = set()

    for source in SOURCES:

        try:

            print("Reading RSS:", source["name"])

            response = requests.get(
                source["url"],
                headers=HEADERS,
                timeout=30
            )

            response.raise_for_status()

            feed = feedparser.parse(response.content)

            print(
                "Articles found:",
                len(feed.entries),
                source["name"]
            )

            for item in feed.entries:

                link = item.get("link", "")

                article_id = (
                    item.get("id")
                    or item.get("guid")
                    or link
                )

                title = clean_text(
                    item.get("title", "")
                )

                summary = clean_text(
                    item.get("summary", "")
                    or item.get("description", "")
                )

                if not article_id or not title or not link:
                    continue

                unique_link = link.rstrip("/").lower()

                if unique_link in seen_links:
                    continue

                seen_links.add(unique_link)

                articles.append({

                    "id": str(article_id),

                    "title": title,

                    "summary": summary,

                    "link": link,

                    "source": source["name"],

                    "image": get_image(item)

                })

        except Exception as error:

            print(
                "RSS ERROR:",
                source["name"],
                str(error)
            )

    return articles


# =====================================
# TELEGRAM API
# =====================================

def telegram_request(method, data):

    url = (
        f"https://api.telegram.org/bot{BOT_TOKEN}/{method}"
    )

    response = requests.post(
        url,
        data=data,
        timeout=60
    )

    response.raise_for_status()

    result = response.json()

    if not result.get("ok"):
        raise RuntimeError(str(result))

    return result


# =====================================
# SEND MESSAGE
# =====================================

def send_message(message):

    telegram_request(
        "sendMessage",
        {
            "chat_id": CHANNEL_ID,
            "text": message,
            "parse_mode": "HTML",
            "disable_web_page_preview": True
        }
    )


# =====================================
# SEND PHOTO
# =====================================

def send_photo(image_url, caption):

    telegram_request(
        "sendPhoto",
        {
            "chat_id": CHANNEL_ID,
            "photo": image_url,
            "caption": caption,
            "parse_mode": "HTML"
        }
    )


# =====================================
# MESSAGE BUILDER
# =====================================

def build_message(article, fa_title, fa_summary):

    original_title = html.escape(article["title"])
    original_summary = html.escape(article["summary"])

    translated_title = html.escape(fa_title)
    translated_summary = html.escape(fa_summary)

    source = html.escape(article["source"])

    link = html.escape(
        article["link"],
        quote=True
    )

    message = (

        "🎬 <b>IMDBNEWS | اخبار سینمای جهان</b>\n\n"

        "🇬🇧 <b>ORIGINAL NEWS</b>\n\n"

        f"<b>{original_title}</b>\n\n"

        f"{original_summary}\n\n"

        "━━━━━━━━━━━━━━\n\n"

        "🇮🇷 <b>ترجمه فارسی</b>\n\n"

        f"<b>{translated_title}</b>\n\n"

        f"{translated_summary}\n\n"

        f"📰 منبع: {source}\n\n"

        f'<a href="{link}">🔗 مشاهده خبر اصلی</a>\n\n'

        "📢 @IMDBNEWS_FA"

    )

    return message


# =====================================
# PUBLISH ARTICLE
# =====================================

def publish_article(article):

    print("Processing:", article["title"])

    fa_title = translate(
        article["title"]
    )

    if not fa_title:

        raise RuntimeError("Title translation failed")

    original_summary = article["summary"][:1200]

    fa_summary = translate(
        original_summary
    ) if original_summary else ""

    if original_summary and not fa_summary:

        raise RuntimeError("Summary translation failed")

    article_for_message = dict(article)

    article_for_message["summary"] = original_summary

    message = build_message(
        article_for_message,
        fa_title,
        fa_summary or ""
    )

    image_url = article.get("image")

    # Telegram photo caption limit

    if image_url and len(message) <= 1000:

        try:

            send_photo(
                image_url,
                message
            )

            print("Photo published successfully")

        except Exception as error:

            print("Photo error:", str(error))

            send_message(message)

    elif image_url:

        try:

            caption = (
                "🎬 <b>IMDBNEWS</b>\n\n"
                f"<b>{html.escape(fa_title)}</b>"
            )

            send_photo(
                image_url,
                caption
            )

            send_message(message)

        except Exception as error:

            print("Photo error:", str(error))

            send_message(message)

    else:

        send_message(message)

    print("Published:", article["title"])


# =====================================
# MAIN ENGINE
# =====================================

def main():

    print("================================")
    print("IMDBNEWS BOT STARTED")
    print("================================")

    if not BOT_TOKEN or not CHANNEL_ID:

        raise RuntimeError(
            "Telegram settings are missing"
        )

    published = load_database()

    published_ids = set(published)

    print(
        "Previously published:",
        len(published_ids)
    )

    articles = get_news()

    print(
        "Total articles:",
        len(articles)
    )

    new_articles = []

    for article in articles:

        if article["id"] in published_ids:
            continue

        if not is_movie_news(article):
            continue

        new_articles.append(article)

    print(
        "New movie news:",
        len(new_articles)
    )

    if not new_articles:

        print("No new movie news found.")

        return

    sent_count = 0

    for article in new_articles[:MAX_NEWS]:

        try:

            publish_article(article)

            # Save only after successful publication

            published.append(
                article["id"]
            )

            published_ids.add(
                article["id"]
            )

            save_database(published)

            sent_count += 1

            time.sleep(3)

        except Exception as error:

            print(
                "PUBLISH ERROR:",
                article["title"],
                str(error)
            )

    print("================================")

    print(
        "Published news:",
        sent_count
    )

    print("IMDBNEWS BOT FINISHED")

    print("================================")


# =====================================
# START
# =====================================

if __name__ == "__main__":

    main()
