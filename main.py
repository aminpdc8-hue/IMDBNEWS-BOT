import os
import json
import time
import html
import requests
import feedparser
import re

from deep_translator import GoogleTranslator
from urllib.parse import quote

# ============== CONFIG ==============

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHANNEL_ID = os.getenv("TELEGRAM_CHANNEL_ID")

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

translator = GoogleTranslator(source="auto", target="fa")

# ============== DATABASE ==============

def load_database():
    try:
        with open(DATABASE, "r", encoding="utf-8") as f:
            return json.load(f)
    except:
        return []

def save_database(data):
    with open(DATABASE, "w", encoding="utf-8") as f:
        json.dump(data[-1000:], f, ensure_ascii=False)

# ============== FILTER ==============

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

    for attempt in range(3):
        try:
            result = translator.translate(text[:4500])
            time.sleep(2)
            return result

        except Exception as e:
            print("Translation error:", e)
            time.sleep(10 * (attempt + 1))

    return "ترجمه این بخش موقتاً در دسترس نیست."

# ============== TELEGRAM ==============

def send_message(message):

    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"

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
        raise Exception(result)

# ============== NEWS ENGINE ==============

def get_news():

    articles = []

    for source in SOURCES:

        try:
            feed = feedparser.parse(source)

            for item in feed.entries:

                articles.append({
                    "id": item.get("id") or item.get("link"),
                    "title": item.get("title", ""),
                    "summary": re.sub(
                        r"<[^>]+>", " ",
                        item.get("summary", "")
                    ),
                    "link": item.get("link", ""),
                    "source": feed.feed.get
