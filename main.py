import os
import json
import html
import requests
import feedparser

from deep_translator import GoogleTranslator
from urllib.parse import quote

# ================= CONFIG =================

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHANNEL_ID = os.getenv("TELEGRAM_CHANNEL_ID")

SOURCES = [
    "https://variety.com/feed/",
    "https://deadline.com/feed/",
    "https://www.hollywoodreporter.com/feed/"
]

DATABASE = "published.json"
MAX_NEWS = 10

translator = GoogleTranslator(source="auto", target="fa")

# ================= DATABASE =================

def load_database():
    try:
        with open(DATABASE, "r", encoding="utf-8") as f:
            return json.load(f)
    except:
        return []

def save_database(data):
    with open(DATABASE, "w", encoding="utf-8") as f:
        json.dump(data[-500:], f, ensure_ascii=False)

# ================= TRANSLATION =================

def translate(text):
    if not text:
        return ""

    try:
        return translator.translate(text[:4500])
    except Exception as e:
        print("Translation error:", e)
        return text

# ================= TELEGRAM =================

def send_message(text):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"

    response = requests.post(
        url,
        data={
            "chat_id": CHANNEL_ID,
            "text": text,
            "parse_mode": "HTML",
            "disable_web_page_preview": False
        },
        timeout=30
    )

    response.raise_for_status()
    return response.json()

# ================= NEWS =================

def get_news():
    articles = []

    for source in SOURCES:
        try:
            feed = feedparser.parse(source)

            for item in feed.entries[:15]:
                articles.append({
                    "id": item.get("id") or item.get("link"),
                    "title": item.get("title", ""),
                    "summary": item.get("summary", ""),
                    "link": item.get("link", ""),
                    "source": feed.feed.get("title", "Cinema News")
                })

        except Exception as e:
            print("Feed error:", e)

    return articles

# ================= PUBLISH =================

def publish(article):

    title = translate(article["title"])
    summary = translate(article["summary"])

    title = html.escape(title)
    summary = html.escape(summary)

    source = html.escape(article["source"])
    link = html.escape(article["link"], quote=True)

    trailer_search = (
        "https://www.youtube.com/results?search_query="
        + quote(article["title"] + " official trailer")
    )

    message = f"""
🎬 <b>IMDB NEWS | اخبار سینما</b>

━━━━━━━━━━━━━━

🎥 <b>{title}</b>

📰 <b>گزارش خبری:</b>

{summary}

━━━━━━━━━━━━━━

🎞 <a href="{trailer_search}">جستجوی تریلر فیلم در یوتیوب</a>

🌐 <a href="{link}">مشاهده خبر اصلی</a>

📡 منبع: {source}

⭐ @IMDBNEWS_FA
"""

    if len(message) > 4000:
        message = message[:3950] + "\n\nادامه مطلب در منبع اصلی."

    send_message(message)

# ================= MAIN =================

def main():

    if not BOT_TOKEN or not CHANNEL_ID:
        raise ValueError("Telegram secrets are missing!")

    published = load_database()

    news = get_news()

    new_count = 0

    for article in reversed(news):

        article_id = article["id"]

        if not article_id or article_id in published:
            continue

        try:
            publish(article)

            published.append(article_id)
            save_database(published)

            new_count += 1

            print("Published:", article["title"])

            if new_count >= MAX_NEWS:
                break

        except Exception as e:
            print("Publish error:", e)

    print("IMDBNEWS finished.")
    print("Published:", new_count)

if __name__ == "__main__":
    main()
