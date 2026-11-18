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
    "https://www.hollywoodreporter.com/feed/"
]

KEYWORDS = [
    "movie", "film", "cinema", "actor", "actress",
    "director", "hollywood", "netflix", "hbo",
    "amazon", "prime video", "disney", "marvel",
    "series", "season", "trailer", "casting",
    "oscar", "golden globe", "box office",
    "streaming", "warner bros", "paramount",
    "tv", "television", "filmmaker", "festival"
]

# =====================================
# DATABASE
# =====================================

def load_database():

    try:
        with open(DATABASE, "r", encoding="utf-8") as file:
            data = json.load(file)

            if isinstance(data, list):
                return data

            return []

    except (FileNotFoundError, json.JSONDecodeError):
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

def clean_text(text):

    text = re.sub(r"<[^>]+>", " ", text)

    text = html.unescape(text)

    text = re.sub(r"\s+", " ", text)

    return text.strip()


# =====================================
# NEWS FILTER
# =====================================

def is_movie_news(article):

    text = (
        article.get("title", "") + " " +
        article.get("summary", "")
    ).lower()

    return any(
        keyword in text
        for keyword in KEYWORDS
    )


# =====================================
# TRANSLATION - MYMEMORY
# =====================================

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

    translated_parts = []

    for chunk in chunks:

        translated = False

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

                translated_parts.append(clean_text(result))

                translated = True

                time.sleep(2)

                break

            except Exception as error:

                print(
                    "Translation error:",
                    str(error)
                )

                time.sleep(5 * (attempt + 1))

        if not translated:

            print("Translation failed after 3 attempts.")

            return None

    return " ".join(translated_parts)


# =====================================
# RSS NEWS ENGINE
# =====================================

def get_news():

    articles = []

    for source in SOURCES:

        try:

            print("Reading source:", source)

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
                "Articles found
