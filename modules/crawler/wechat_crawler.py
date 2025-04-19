import os
import json
import redis
from dotenv import load_dotenv
import time
import random
# Import the actual crawler library
from wechat_articles_spider import OfficialAccount, ArticlesInfo

load_dotenv(dotenv_path=".env", verbose=True)

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
DATA_PATH = os.getenv("DATA_PATH", "./data") # Also save raw JSON files
# Load potential cookie/token from .env for the crawler
WECHAT_COOKIE = os.getenv("WECHAT_COOKIE")
WECHAT_TOKEN = os.getenv("WECHAT_TOKEN")

class WechatCrawler:
    def __init__(self):
        print("Initializing Wechat Crawler...")
        # Initialize connection to Redis
        try:
            self.redis_client = redis.Redis.from_url(REDIS_URL, decode_responses=True)
            self.redis_client.ping()
            print("Redis connection successful for crawler.")
        except redis.exceptions.ConnectionError as e:
            print(f"Error connecting to Redis in crawler: {e}")
            self.redis_client = None

        # Initialize the crawler components
        # Check if cookie and token are provided
        if not WECHAT_COOKIE or not WECHAT_TOKEN:
            print("Warning: WECHAT_COOKIE or WECHAT_TOKEN not found in .env. Crawler might not work.")
            # Depending on the library's requirements, might need to handle this more gracefully

        self.account_crawler = OfficialAccount(cookie=WECHAT_COOKIE, token=WECHAT_TOKEN)
        self.article_info_crawler = ArticlesInfo(cookie=WECHAT_COOKIE, token=WECHAT_TOKEN)

        # Ensure data directory exists
        if not os.path.exists(DATA_PATH):
            os.makedirs(DATA_PATH)
            print(f"Created data directory: {DATA_PATH}")

    def fetch_articles(self, account_name="新京报书评周刊", start_page=1, end_page=1):
        """
        Fetches article metadata (links, titles, etc.) for a given account and page range.
        Uses the wechat_articles_spider library.
        """
        print(f"Fetching article list for '{account_name}' from page {start_page} to {end_page}...")
        try:
            # The library's crawl method gets basic info (title, link, date)
            # It might not get full content directly here.
            article_metadatas = self.account_crawler.crawl(account_name, start_page=start_page, end_page=end_page)
            print(f"Found {len(article_metadatas)} article metadata entries.")
            return article_metadatas # Returns a list of dictionaries
        except Exception as e:
            print(f"Error during account crawling for '{account_name}': {e}")
            return []

    def fetch_article_content(self, article_metadata):
        """
        Fetches the full content of a single article using its metadata (specifically the link).
        Uses the wechat_articles_spider library.
        """
        article_link = article_metadata.get("link")
        article_title = article_metadata.get("title", "Unknown Title")
        if not article_link:
            print(f"Skipping article '{article_title}': Missing link.")
            return None

        print(f"Fetching content for: {article_title} ({article_link})")
        try:
            # Use ArticlesInfo to get detailed content
            # The library might return more fields; adjust as needed.
            content_info = self.article_info_crawler.crawl(article_link)
            if content_info and content_info.get("content"): # Check if content was retrieved
                 # Combine metadata with content info
                 full_article_data = {
                     "id": f"wechat_{int(time.time())}_{random.randint(1000, 9999)}", # Generate a unique ID
                     "title": article_metadata.get("title"),
                     "content": content_info.get("content"),
                     "publish_date": article_metadata.get("date"), # Use date from initial crawl
                     "url": article_link,
                     "author": content_info.get("author"),
                     # Add other relevant fields from content_info if available
                 }
                 # Basic cleaning (optional)
                 if full_article_data["content"]:
                     full_article_data["content"] = full_article_data["content"].strip()
                 return full_article_data
            else:
                print(f"Failed to retrieve content for: {article_title}")
                return None
        except Exception as e:
            print(f"Error fetching content for '{article_title}' ({article_link}): {e}")
            return None

    def save_article(self, article_data):
        """Saves a single article to Redis and as a JSON file."""
        if not self.redis_client:
            print("Redis client not available. Cannot save article.")
            return

        article_id = article_data.get("id")
        if not article_id:
            print("Article data missing 'id'. Cannot save.")
            return

        # Save to Redis Hash
        redis_key = f"article:{article_id}"
        try:
            # Filter out None values before saving to Redis Hash
            filtered_data = {k: v for k, v in article_data.items() if v is not None}
            if filtered_data:
                self.redis_client.hset(redis_key, mapping=filtered_data)
                print(f"Saved article {article_id} to Redis.")
            else:
                print(f"Skipping saving article {article_id} to Redis due to empty data after filtering.")
        except Exception as e:
            print(f"Error saving article {article_id} to Redis: {e}")

        # Save as JSON file
        filepath = os.path.join(DATA_PATH, f"{article_id}.json")
        try:
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(article_data, f, ensure_ascii=False, indent=2)
            print(f"Saved article {article_id} to {filepath}")
        except Exception as e:
            print(f"Error saving article {article_id} to JSON file: {e}")

    def run(self, account_name="新京报书评周刊", start_page=1, end_page=1, delay_between_articles=5):
        """Fetches article metadata, then fetches content for each, and saves them."""
        print(f"Starting crawler run for '{account_name}'...")

        article_metadatas = self.fetch_articles(account_name=account_name, start_page=start_page, end_page=end_page)

        if not article_metadatas:
            print("No article metadata fetched.")
            return

        print(f"Fetched {len(article_metadatas)} article metadata entries. Now fetching full content...")
        saved_count = 0
        for metadata in article_metadatas:
            full_article = self.fetch_article_content(metadata)
            if full_article:
                self.save_article(full_article)
                saved_count += 1
            else:
                print(f"Skipping save for article: {metadata.get('title', 'Unknown Title')}")

            # Add delay to respect potential platform limits
            print(f"Waiting for {delay_between_articles} seconds...")
            time.sleep(delay_between_articles + random.uniform(0, 2)) # Add some jitter

        print(f"Crawler run finished. Successfully saved {saved_count} full articles.")

if __name__ == "__main__":
    # IMPORTANT: Ensure WECHAT_COOKIE and WECHAT_TOKEN are set in your .env file
    # You usually obtain these from your browser's developer tools after logging into mp.weixin.qq.com
    if not WECHAT_COOKIE or not WECHAT_TOKEN:
        print("Error: Please set WECHAT_COOKIE and WECHAT_TOKEN in your .env file.")
        print("See documentation for wechat_articles_spider on how to obtain these.")
    else:
        crawler = WechatCrawler()
        # Example: Crawl the first page of the specified account
        crawler.run(account_name="新京报书评周刊", start_page=1, end_page=1, delay_between_articles=10) # Increase delay for real crawling
