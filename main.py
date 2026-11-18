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
    "television", "filmmaker", "festival"
]

# =====================================
# DATABASE
# =====================================

def load_database():

    try:
        with open(D
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
                    raise RuntimeError("Translation failed")

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

            print("Reading:", source["name"])

            response = requests.get(
                source["url"],
                headers=HEADERS,
                timeout=30
            )

            response.raise_for_status()

            feed = feedparser.parse(response.content)

            print(
                "Articles found:",
                len(feed.entries)
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
