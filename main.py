import os
import re
import json
import time
import html
import hashlib
import requests
import feedparser

from io import BytesIO
from html.parser import HTMLParser
from PIL import Image


# =====================================
# CONFIG
# =====================================

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHANNEL_ID = os.getenv("TELEGRAM_CHANNEL_ID")

DATABASE = "published.json"
MAX_NEWS = 5

API = f"https://api.telegram.org/bot{BOT_TOKEN}"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120 Safari/537.36"
}


# =====================================
# SOURCES
# =====================================

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
        "urls": ["https://variety.com/feed/"]
    },
    {
        "name": "Deadline",
        "urls": ["https://deadline.com/feed/"]
    },
    {
        "name": "Hollywood Reporter",
        "urls": ["https://www.hollywoodreporter.com/feed/"]
    }
]


KEYWORDS = [
    "movie", "film", "cinema", "hollywood",
    "actor", "actress", "director", "producer",
    "trailer", "cast", "release date",
    "netflix", "amazon", "prime video",
    "disney", "warner", "paramount",
    "universal", "box office", "series",
    "season", "horror", "thriller",
    "comedy", "drama", "action",
    "sci-fi", "fantasy", "animation",
    "oscars", "emmy", "golden globe",
    "marvel", "dc studios",
    "friday the 13th", "jason"
]


# =====================================
# HTML ARTICLE EXTRACTOR
# =====================================

class ArticleParser(HTMLParser):

    def __init__(self):
        super().__init__()

        self.paragraphs = []
        self.current = ""
        self.in_paragraph = False
        self.skip = False
        self.description = ""

    def handle_starttag(self, tag, attrs):

        attrs = dict(attrs)

        if tag in ["script", "style", "nav", "footer", "header"]:
            self.skip = True

        if tag == "meta":

            name = (
                attrs.get("property")
                or attrs.get("name")
                or ""
            ).lower()

            if name in [
                "og:description",
                "description",
                "twitter:description"
            ]:

                value = attrs.get("content", "")

                if value and len(value) > len(self.description):
                    self.description = value

        if tag == "p" and not self.skip:
            self.in_paragraph = True
            self.current = ""

    def handle_data(self, data):

        if self.skip:
            return

        if self.in_paragraph:
            self.current += " " + data

    def handle_endtag(self, tag):

        if tag in ["script", "style", "nav", "footer", "header"]:
            self.skip = False

        if tag == "p":

            text = clean_text(self.current)

            if len(text) > 60:
                self.paragraphs.append(text)

            self.current = ""
            self.in_paragraph = False


# =====================================
# TEXT CLEANER
# =====================================

def clean_text(text):

    if not text:
        return ""

    text = re.sub(r"<[^>]+>", " ", text)

    text = html.unescape(text)

    text = re.sub(r"\s+", " ", text)

    return text.strip()


def limit_words(text, maximum=120):

    words = text.split()

    if len(words) <= maximum:
        return text

    return " ".join(words[:maximum]).rstrip(" ,.-") + "..."


# =====================================
# DATABASE
# =====================================

def load_database():

    try:

        with open(DATABASE, "r", encoding="utf-8") as f:
            data = json.load(f)

        return data if isinstance(data, list) else []

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


def make_id(article):

    value = article.get("id") or article["link"]

    return hashlib.sha256(
        value.encode("utf-8")
    ).hexdigest()


# =====================================
# IMAGE EXTRACTION
# =====================================

def get_image(entry):

    for key in ["media_content", "media_thumbnail"]:

        items = entry.get(key, [])

        for item in items:

            url = item.get("url")

            if url and url.startswith("http"):
                return url

    for item in entry.get("enclosures", []):

        url = item.get("href") or item.get("url")

        if url and url.startswith("http"):
            return url

    for item in entry.get("content", []):

        match = re.search(
            r'<img[^>]+src=["\']([^"\']+)',
            item.get("value", ""),
            re.I
        )

        if match:
            return html.unescape(match.group(1))

    match = re.search(
        r'<img[^>]+src=["\']([^"\']+)',
        entry.get("summary", ""),
        re.I
    )

    if match:
        return html.unescape(match.group(1))

    return None


# =====================================
# FETCH ARTICLE DETAILS
# =====================================

def get_article_details(url):

    try:

        response = requests.get(
            url,
            headers=HEADERS,
            timeout=25
        )

        response.raise_for_status()

        parser = ArticleParser()

        parser.feed(response.text)

        description = clean_text(parser.description)

        paragraphs = parser.paragraphs

        # Use publisher description or a short
        # factual excerpt from accessible content.
        details = description

        if not details and paragraphs:
            details = " ".join(paragraphs[:2])

        return limit_words(details, 120)

    except Exception as error:

        print("Article extraction error:", error)

        return ""


# =====================================
# FETCH RSS
# =====================================

def fetch_news():

    articles = []

    for source in SOURCES:

        print("Reading RSS:", source["name"])

        found = []

        for feed_url in source["urls"]:

            try:

                response = requests.get(
                    feed_url,
                    headers=HEADERS,
                    timeout=25
                )

                response.raise_for_status()

                feed = feedparser.parse(response.content)

                for entry in feed.entries:

                    title = clean_text(
                        entry.get("title", "")
                    )

                    link = entry.get("link", "")

                    summary = clean_text(
                        entry.get("summary", "")
                    )

                    if not title or not link:
                        continue

                    if not link.startswith("http"):
                        continue

                    found.append({
                        "id": entry.get("id") or link,
                        "title": title,
                        "summary": summary,
                        "link": link,
                        "source": source["name"],
                        "image": get_image(entry)
                    })

                if found:
                    break

            except Exception as error:

                print("RSS error:", error)

        print(
            "Articles found:",
            len(found),
            source["name"]
        )

        articles.extend(found)

    return articles


# =====================================
# FILTER
# =====================================

def is_movie_news(article):

    text = (
        article["title"] + " " +
        article["summary"]
    ).lower()

    return any(
        keyword in text
        for keyword in KEYWORDS
    )


# =====================================
# TRANSLATION
# =====================================

def translate_text(text):

    if not text:
        return ""

    try:

        response = requests.get(
            "https://api.mymemory.translated.net/get",
            params={
                "q": text[:4500],
                "langpair": "en|fa"
            },
            headers=HEADERS,
            timeout=30
        )

        response.raise_for_status()

        data = response.json()

        result = data.get(
            "responseData", {}
        ).get("translatedText", "")

        return html.unescape(result).strip()

    except Exception as error:

        print("Translation error:", error)

        return ""


# =====================================
# IMAGE DOWNLOAD AND RESIZE
# =====================================

def download_image(url):

    if not url:
        return None

    try:

        response = requests.get(
            url,
            headers=HEADERS,
            timeout=30
        )

        response.raise_for_status()

        if not response.headers.get(
            "Content-Type", ""
        ).lower().startswith("image/"):

            return None

        if len(response.content) > 9 * 1024 * 1024:
            return None

        image = Image.open(
            BytesIO(response.content)
        )

        image = image.convert("RGB")

        image.thumbnail((1280, 1280))

        output = BytesIO()

        image.save(
            output,
            format="JPEG",
            quality=88,
            optimize=True
        )

        output.seek(0)

        return output

    except Exception as error:

        print("Image error:", error)

        return None


# =====================================
# TELEGRAM PHOTO
# =====================================

def send_photo(image):

    if image is None:
        return False

    try:

        response = requests.post(
            API + "/sendPhoto",
            data={
                "chat_id": CHANNEL_ID
            },
            files={
                "photo": ("news.jpg", image, "image/jpeg")
            },
            timeout=60
        )

        if not response.ok:

            print(
                "Photo error:",
                response.text
            )

            return False

        return response.json().get("ok", False)

    except Exception as error:

        print("Photo send error:", error)

        return False


# =====================================
# TELEGRAM MESSAGE
# =====================================

def send_message(message):

    try:

        response = requests.post(
            API + "/sendMessage",
            data={
                "chat_id": CHANNEL_ID,
                "text": message,
                "parse_mode": "HTML",
                "disable_web_page_preview": True
            },
            timeout=45
        )

        if not response.ok:

            print(
                "Message error:",
                response.text
            )

            return False

        return response.json().get("ok", False)

    except Exception as error:

        print("Message send error:", error)

        return False


# =====================================
# BUILD POST
# =====================================

def build_post(article, english, persian_title, persian):

    title_en = html.escape(article["title"])

    title_fa = html.escape(persian_title)

    english = html.escape(english)

    persian = html.escape(persian)

    source = html.escape(article["source"])

    link = html.escape(
        article["link"],
        quote=True
    )

    return (
        "🎬 <b>IMDBNEWS | اخبار سینمای جهان</b>\n\n"

        "🇬🇧 <b>ORIGINAL NEWS</b>\n\n"

        f"<b>{title_en}</b>\n\n"

        f"{english}\n\n"

        "━━━━━━━━━━━━━━\n\n"

        "🇮🇷 <b>ترجمه فارسی</b>\n\n"

        f"<b>{title_fa}</b>\n\n"

        f"{persian}\n\n"

        f"📰 منبع: {source}\n\n"

        f'🔗 <a href="{link}">مشاهده خبر اصلی | Read Original News</a>\n\n'

        "📢 @IMDBNEWS_FA"
    )


# =====================================
# PROCESS ARTICLE
# =====================================

def process_article(article):

    print("Processing:", article["title"])

    # Get additional accessible details
    details = get_article_details(
        article["link"]
    )

    english = article["summary"]

    if details and len(details) > len(english):
        english = details

    if not english:
        english = article["title"]

    english = limit_words(english, 120)

    persian_title = translate_text(
        article["title"]
    )

    persian = translate_text(english)

    if not persian_title or not persian:
        print("Translation failed")
        return False

    message = build_post(
        article,
        english,
        persian_title,
        persian
    )

    if len(message) > 4000:
        print("Message too long")
        return False

    image = download_image(
        article.get("image")
    )

    if image:
        if send_photo(image):
            print("Photo published")
        else:
            print("Photo failed; text fallback")

    if send_message(message):

        print("Published:", article["title"])

        return True

    return False


# =====================================
# MAIN
# =====================================

def main():

    print("================================")
    print("IMDBNEWS BOT STARTED")
    print("================================")

    if not BOT_TOKEN or not CHANNEL_ID:

        print("Missing Telegram secrets")

        return

    published = load_database()

    print(
        "Previously published:",
        len(published)
    )

    articles = fetch_news()

    print("Total articles:", len(articles))

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

        if process_article(article):

            published.append(
                article["unique_id"]
            )

            save_database(published)

            count += 1

        time.sleep(3)

    print("================================")
    print("Published news:", count)
    print("IMDBNEWS BOT FINISHED")


if __name__ == "__main__":
    main()
