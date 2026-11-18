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
