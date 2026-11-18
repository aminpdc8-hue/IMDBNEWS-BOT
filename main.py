import os
import json
import time
import html
import re
import requests
import feedparser

# ============== CONFIG ==============

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHANNEL_ID = os.getenv("TELEGRAM_CHANNEL_ID")
TRANSLATION_EMAIL = os.getenv("TRANSLATION_EMAIL", "")

MAX_NEWS = 5
DATABASE = "published.json"

SOURCES = [
    "https://variety.com/feed/",
    "https://deadline.com/feed/",
    "https://www.hollywoodreporter.com/feed/"
]

KEYWORDS = [
    "movie", "film", "cinema", "actor", "actress",
    "director", "hollywood", "netflix", "hbo",
    "amazon", "prime video", "disney", "marvel",
    "series", "season", "trailer", "casting",
    "oscar", "golden globe", "box office",
    "streaming", "warner bros", "paramount"
]

# ============== DATABASE ==============

def load_database():
    try:
        with open(DATABASE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []


def save_database(data):
    with open(DATABASE, "w", encoding="utf-8") as f:
        json.dump(
            data[-1000:],
            f,
            ensure_ascii=False,
            indent=2
        )


# ============== TEXT CLEANER ==============

def clean_text(text):

    text = re.sub(r"<[^>]+>", " ", text)

    text = html.unescape(text)

    text = re.sub(r"\s+", " ", text)

    return text.strip()


# ============== NEWS FILTER ==============

def is_movie_news(article):

    text = (
        article.get("title", "") + " " +
        article.get("summary", "")
    ).lower()

    return any(word in text for word in KEYWORDS)


# ============== TRANSLATION ==============

def translate(text):

    if not text:
        return ""

    words = text.split()

    chunks = []
    current = ""

    for word in words:

        if len(current) + len(word) + 1 > 400:

            if current:
                chunks.append(current)

            current = word

        else:
            current = (current + " " + word).strip()

    if current:
        chunks.append(current)

    translated = []

    for chunk in chunks:

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
                    timeout=30
                )

                response.raise_for_status()

                data = response.json()

                if str(data.get("responseStatus")) != "200":
                    raise Exception(
                        data.get("responseDetails", "Translation failed")
                    )

                result = data.get(
                    "responseData", {}
                ).get("translatedText", "")

                if not result:
                    raise Exception("Empty translation")

                translated.append(clean_text(result))

                success = True

                time.sleep(2)

                break

            except Exception as e:

                print("Translation error:", str(e))

                time.sleep(5 * (attempt + 1))

        if not success:

            print("Translation failed permanently.")

            return None

    return " ".join(translated)


# ============== RSS NEWS ENGINE ==============

def get_news():

    articles = []

    for source in SOURCES:

        try:

            print("Reading RSS:", source)

            response = requests.get(
                source,
                headers={
                    "User-Agent": "Mozilla/5.0 IMDBNEWS BOT"
                },
                timeout=30
            )

            response.raise_for_status()

            feed = feedparser.parse(response.content)

            print(
                "Articles found:",
                len(feed.entries)
            )

            for item in feed.entries:

                article_id = (
                    item.get("id")
                    or item.get("link", "")
                )

                if not article_id:
                    continue

                summary = item.get("summary", "")

                if not summary:
                    summary = item.get("description", "")

                article = {

                    "id": article_id,

                    "title": clean_text(
                        item.get("title", "")
                    ),

                    "summary": clean_text(summary),

                    "link": item.get("link", ""),

                    "source": feed.feed.get(
                        "title",
                        "Cinema News"
                    )
                }

                articles.append(article)

        except Exception as e:

            print("RSS error:", str(e))

    return articles


# ============== TELEGRAM ==============

def send_message(message):

    if not BOT_TOKEN or not CHANNEL_ID:

        raise Exception(
            "Telegram settings are missing!"
        )

    url = (
        f"https://api.telegram.org/"
        f"bot{BOT_TOKEN}/sendMessage"
    )

    response = requests.post(

        url,

        data={

            "chat_id": CHANNEL_ID,

            "text": message,

            "parse_mode": "HTML",

            "disable_web_page_preview": False
        },

        timeout=30
    )

    response.raise_for_status()

    result = response.json()

    if not result.get("ok"):

        raise Exception(str(result))

    return True


# ============== MAIN ENGINE ==============

def main():

    print("================================")
    print("IMDBNEWS BOT STARTED")
    print("================================")

    if not BOT_TOKEN or not CHANNEL_ID:

        print("ERROR: Telegram configuration missing")

        return

    published = load_database()

    print("Published database:", len(published))

    print("Getting latest cinema news...")

    articles = get_news()

    print("Total articles:", len(articles))

    new_articles = []

    seen = set(published)

    for article in articles:

        article_id = article["id"]

        if article_id in seen:
            continue

        if not article["title"]:
            continue

        if not is_movie_news(article):
            continue

        new_articles.append(article)

        seen.add(article_id)

    print("New movie news:", len(new_articles))

    if not new_articles:

        print("No new movie news found.")

        return

    sent_count = 0

    for article in new_articles[:MAX_NEWS]:

        try:

            print("--------------------------------")
            print("Translating:", article["title"])

            title = translate(article["title"])

            if not title:

                print("Skipping article: title translation failed")

                continue

            summary = translate(
                article["summary"][:1200]
            )

            if not summary:

                print("Skipping article: summary translation failed")

                continue

            title = html.escape(title)

            summary = html.escape(summary)

            source = html.escape(article["source"])

            link = html.escape(
                article["link"],
                quote=True
            )

            message = (

                "🎬 <b>اخبار سینمای جهان</b>\n\n"

                f"<b>{title}</b>\n\n"

                f"{summary}\n\n"

                f"📰 منبع: {source}\n"

                f'🔗 <a href="{link}">مشاهده خبر اصلی</a>\n\n'

                "📢 @IMDBNEWS_FA"
            )

            send_message(message)

            published.append(article["id"])

            save_database(published)

            sent_count += 1

            print(
                "SUCCESSFULLY PUBLISHED:",
                article["title"]
            )

            time.sleep(5)

        except Exception as e:

            print(
                "PUBLISHING ERROR:",
                str(e)
            )

    print("================================")

    print("Published news
