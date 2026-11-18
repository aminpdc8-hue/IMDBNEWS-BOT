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

SOURCES = [
    "https://variety.com/feed/",
    "https://deadline.com/feed/",
    "https://www.hollywoodreporter.com/feed/",
]

KEYWORDS = [
    "movie", "film", "cinema", "actor", "actress",
    "director", "hollywood", "netflix", "hbo",
    "amazon", "prime video", "disney", "marvel",
    "series", "season", "trailer", "casting",
    "oscar", "golden globe", "box office",
    "streaming", "warner bros", "paramount",
    "television", "filmmaker", "festival",
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

    # 1. Media RSS images

    media = item.get("media_content", [])

    for image in media:

        image_url = image.get("url", "")

        if image_url:
            return image_url

    # 2. Media thumbnails

    thumbnails = item.get("media_thumbnail", [])

    for image in thumbnails:

        image_url = image.get("url", "")

        if image_url:
            return image_url

    # 3. RSS enclosures

    enclosures = item.get("enclosures", [])

    for image in enclosures:

        image_url = image.get("href", "")

        image_type = image.get("type", "")

        if image_url and image_type.startswith("image/"):
            return image_url

    # 4. Images inside article content

    contents = item.get("content", [])

    for content in contents:

        value = content.get("value", "")

        match = re.search(
            r'<img[^>]+src=["\']([^"\']+)["\']',
            value,
            re.IGNORECASE
        )

        if match:
            return html.unescape(match.group(1))

    # 5. Images inside summary

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
                    "langpair": "en|fa",
                }

                if TRANSLATION_EMAIL:
                    params["de"] = TRANSLATION_EMAIL

                response = requests.get(
                    "https://api.mymemory.translated.net/get",
                    params=params,
                    timeout=30,
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

                translated_parts.append(clean_text(result))

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

    for source_url in SOURCES:

        try:

            print("Reading RSS:", source_url)

            response = requests.get(
                source_url,
                headers={
                    "User-Agent": "Mozilla/5.0 IMDBNEWS BOT"
                },
                timeout=30,
            )

            response.raise_for_status()

            feed = feedparser.parse(response.content)

            print("Articles found:", len(feed.entries))

            for item in feed.entries:

                link = item.get("link", "")

                article_id = item.get("id") or link

                title = clean_text(
                    item.get("title", "")
                )

                summary = clean_text(
                    item.get("summary", "")
                    or item.get("description", "")
                )

                if not article_id or not title or not link:
                    continue

                image_url = get_image(item)

                articles.append({

                    "id": article_id,

                    "title": title,

                    "summary": summary,

                    "link": link,

                    "source": clean_text(
                        feed.feed.get(
                            "title",
                            "Cinema News"
                        )
                    ),

                    "image": image_url
                })

        except Exception as error:

            print("RSS error:", str(error))

    return articles


# =====================================
# TELEGRAM TEXT
# =====================================

def send_message(message):

    url = (
        "https://api.telegram.org/bot"
        + BOT_TOKEN
        + "/sendMessage"
    )

    response = requests.post(
        url,
        data={
            "chat_id": CHANNEL_ID,
            "text": message,
            "parse_mode": "HTML",
            "disable_web_page_preview": False,
        },
        timeout=30,
    )

    response.raise_for_status()

    result = response.json()

    if not result.get("ok"):
        raise RuntimeError(str(result))

    return True


# =====================================
# TELEGRAM PHOTO
# =====================================

def send_photo(image_url, caption):

    url = (
        "https://api.telegram.org/bot"
        + BOT_TOKEN
        + "/sendPhoto"
    )

    response = requests.post(
        url,
        data={
            "chat_id": CHANNEL_ID,
            "photo": image_url,
            "caption": caption,
            "parse_mode": "HTML",
        },
        timeout=60,
    )

    response.raise_for_status()

    result = response.json()

    if not result.get("ok"):
        raise RuntimeError(str(result))

    return True


# =====================================
# MESSAGE BUILDER
# =====================================

def build_message(article, title, summary):

    source = html.escape(article["source"])

    link = html.escape(
        article["link"],
        quote=True
    )

    title = html.escape(title)

    summary = html.escape(summary)

    message = (
        "🎬 <b>اخبار سینمای جهان</b>\n\n"
        f"<b>{title}</b>\n\n"
        f"{summary}\n\n"
        f"📰 منبع: {source}\n"
        f'<a href="{link}">🔗 مشاهده خبر اصلی</a>\n\n'
        "📢 @IMDBNEWS_FA"
    )

    return message


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

    print("Previously published:", len(published))

    articles = get_news()

    print("Total articles:", len(articles))

    new_articles = []

    for article in articles:

        article_id = article["id"]

        if article_id in published_ids:
            continue

        if not is_movie_news(article):
            continue

        new_articles.append(article)

        published_ids.add(article_id)

    print("New movie news:", len(new_articles))

    if not new_articles:

        print("No new movie news found.")

        return

    sent_count = 0

    for article in new_articles[:MAX_NEWS]:

        try:

            print("--------------------------------")

            print("Processing:", article["title"])

            # Translate title

            fa_title = translate(
                article["title"]
            )

            if not fa_title:

                print("Title translation failed.")

                continue

            # Translate summary

            fa_summary = translate(
                article["summary"][:1200]
            )

            if not fa_summary:

                print("Summary translation failed.")

                continue

            # Build message

            message = build_message(
                article,
                fa_title,
                fa_summary
            )

            # Telegram caption limit

            if len(message) > 1000:

                message = build_message(
                    article,
                    fa_title,
                    fa_summary[:450]
                )

            # Publish photo if available

            image_url = article.get("image")

            if image_url:

                try:

                    print("Image found:", image_url)

                    send_photo(
                        image_url,
                        message
                    )

                    print("Photo published successfully.")

                except Exception as image_error:

                    print(
                        "Photo failed, sending text:",
                        str(image_error)
                    )

                    send_message(message)

            else:

                print("No image found. Sending text.")

                send_message(message)

            # Save published news

            published.append(article["id"])

            save_database(published)

            sent_count += 1

            print(
                "Published successfully:",
                article["title"]
            )

            time.sleep(3)

        except Exception as error:

            print(
                "PUBLISHING ERROR:",
                str(error)
            )

    print("================================")

    print("Published news:", sent_count)

    print("IMDBNEWS BOT FINISHED")

    print("================================")


# =====================================
# START
# =====================================

if __name__ == "__main__":

    main()
