import os
import json
import redis
from dotenv import load_dotenv
import time
import random
import requests
from bs4 import BeautifulSoup

load_dotenv(dotenv_path=".env", verbose=True)

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
REDIS_PASSWORD = os.getenv("REDIS_PASSWORD")  # Load Redis password
DATA_PATH = os.getenv("DATA_PATH", "../essay_data/data")

COLUMN_ID = 9025
API_URL = "https://api.bjnews.com.cn/api/v101/news/column_news.php"
DETAIL_URL_PREFIX = "https://m.bjnews.com.cn/detail/"

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Linux; Android 10; SM-G975F) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/83.0.4103.106 Mobile Safari/537.36',
    'Accept': 'application/json, text/javascript, */*; q=0.01',
    'Accept-Language': 'en-US,en;q=0.9,zh-CN;q=0.8,zh;q=0.7',
    'Connection': 'keep-alive',
    'X-Requested-With': 'XMLHttpRequest'
}

class BjNewsCrawler:
    def __init__(self):
        print("Initializing BjNews Crawler (API v101)...")
        try:
            # Use password if provided
            self.redis_client = redis.Redis.from_url(REDIS_URL, password=REDIS_PASSWORD, decode_responses=True)
            self.redis_client.ping()
            print("Redis connection successful for crawler.")
        except redis.exceptions.ConnectionError as e:
            print(f"Error connecting to Redis in crawler: {e}")
            self.redis_client = None
        except redis.exceptions.AuthenticationError:
            print("Redis authentication failed for crawler. Please check REDIS_PASSWORD.")
            self.redis_client = None

        if not os.path.exists(DATA_PATH):
            os.makedirs(DATA_PATH)
            print(f"Created data directory: {DATA_PATH}")

        self.session = requests.Session()
        self.session.headers.update(HEADERS)

    def fetch_article_list(self, page=1):
        params = {
            'page': page,
            'column_id': COLUMN_ID,
        }
        print(f"Fetching article list page {page} from new API...")
        try:
            response = self.session.get(API_URL, params=params, timeout=20)
            response.raise_for_status()
            data = response.json()
            if data.get('code') == 0 and isinstance(data.get('data'), list):
                articles = data['data']
                print(f"Found {len(articles)} articles metadata on page {page}.")
                return articles
            else:
                print(f"API v101 returned non-zero code or unexpected format on page {page}: {data.get('code')}, {data.get('msg')}")
                return []
        except requests.exceptions.RequestException as e:
            print(f"Error fetching article list page {page} from API v101: {e}")
            return []
        except json.JSONDecodeError:
            print(f"Error decoding JSON response for page {page} from API v101.")
            return []

    def fetch_article_detail(self, article_metadata):
        uuid = article_metadata.get("uuid")
        api_title = article_metadata.get("row", {}).get("title", "Unknown Title")

        if not uuid:
            print(f"Skipping article - missing 'uuid' in metadata: {api_title}")
            return None

        detail_url = f"{DETAIL_URL_PREFIX}{uuid}.html"
        print(f"Fetching detail for: {api_title} ({detail_url})")

        try:
            html_headers = {
                'User-Agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 13_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/13.1.1 Mobile/15E148 Safari/604.1',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.9',
                'Accept-Language': 'en-US,en;q=0.9,zh-CN;q=0.8,zh;q=0.7',
            }
            response = self.session.get(detail_url, headers=html_headers, timeout=30)
            response.raise_for_status()
            response.encoding = response.apparent_encoding

            soup = BeautifulSoup(response.text, 'html.parser')

            # Title from HTML (use as primary if available, fallback to API title)
            title_tag = soup.select_one('h1.detail_title')
            html_title = title_tag.get_text(strip=True) if title_tag else api_title

            # Content extraction (Updated selectors and exclusion logic)
            main_content_container = soup.select_one('body > div:nth-child(3) > div.main')
            content = ""
            if main_content_container:
                # Find and remove unwanted elements before extracting text
                author_div = main_content_container.select_one('div.author')
                if author_div:
                    author_div.decompose()

                invideo_div = main_content_container.select_one('div.invideo')
                if invideo_div:
                    invideo_div.decompose()

                # Extract all remaining text from the container
                content = main_content_container.get_text(separator='\n', strip=True)
            else:
                print(f"Warning: Could not find main content container ('body > div:nth-child(3) > div.main') for {detail_url}")

            if not content:
                print(f"Warning: Extracted empty content for {detail_url} after applying selectors and exclusions.")

            full_article_data = {
                **article_metadata,
                "id": f"bjnews_{uuid}",
                "title": html_title,
                "content": content.strip(),
                "url": detail_url,
                "source": "bjnews"
            }
            if "publish_time" not in full_article_data.get("row", {}):
                print(f"Warning: 'publish_time' missing in API metadata for {uuid}")
                full_article_data["publish_date"] = None
            else:
                full_article_data["publish_date"] = full_article_data.get("row", {}).get("publish_time")

            return full_article_data

        except requests.exceptions.RequestException as e:
            print(f"Error fetching detail page {detail_url}: {e}")
            return None
        except Exception as e:
            print(f"Error parsing detail page {detail_url}: {e}")
            return None

    def save_article(self, article_data):
        if not self.redis_client:
            print("Redis client not available. Cannot save article.")
            return False

        article_id = article_data.get("id")
        if not article_id:
            print("Article data missing standardized 'id'. Cannot save.")
            return False

        redis_key = f"article:{article_id}"
        if self.redis_client.exists(redis_key):
            print(f"Article {article_id} already exists in Redis. Skipping save.")
            return False

        save_data_redis = {}
        for k, v in article_data.items():
            if isinstance(v, (dict, list)):
                try:
                    save_data_redis[k] = json.dumps(v, ensure_ascii=False)
                except TypeError:
                    print(f"Warning: Could not JSON serialize field '{k}' for Redis. Skipping field.")
                    save_data_redis[k] = str(v)
            else:
                save_data_redis[k] = v

        try:
            filtered_data = {k: v for k, v in save_data_redis.items() if v is not None}
            if filtered_data:
                self.redis_client.hset(redis_key, mapping=filtered_data)
                print(f"Saved article {article_id} to Redis.")
            else:
                print(f"Skipping saving article {article_id} to Redis due to empty data after filtering/serialization.")
                return False
        except Exception as e:
            print(f"Error saving article {article_id} to Redis: {e}")
            return False

        filepath = os.path.join(DATA_PATH, f"{article_id}.json")
        try:
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(article_data, f, ensure_ascii=False, indent=2)
            print(f"Saved article {article_id} to {filepath}")
            return True
        except Exception as e:
            print(f"Error saving article {article_id} to JSON file: {e}")
            return False

    def run(self, start_page=1, end_page=50, delay_list_fetch=2, delay_detail_fetch=5):
        print(f"Starting BjNews crawler run for column {COLUMN_ID} (Pages {start_page}-{end_page})...")
        total_saved = 0
        processed_uuids = set()

        for page in range(start_page, end_page + 1):
            print("-" * 20)
            article_metadatas = self.fetch_article_list(page=page)

            if not article_metadatas:
                print(f"No articles found on page {page} or error occurred. Continuing to next page or stopping if last page.")
                if page == end_page:
                    break
                else:
                    time.sleep(delay_list_fetch * 2)
                    continue

            new_articles_found_on_page = 0
            for metadata in article_metadatas:
                uuid = metadata.get("uuid")
                if not uuid or uuid in processed_uuids:
                    if uuid: print(f"Skipping duplicate UUID within this run: {uuid}")
                    continue

                processed_uuids.add(uuid)

                full_article = self.fetch_article_detail(metadata)

                if full_article:
                    if self.save_article(full_article):
                        total_saved += 1
                        new_articles_found_on_page += 1
                else:
                    print(f"Skipping save for article UUID: {uuid}")

                wait_time = delay_detail_fetch + random.uniform(0, 2)
                print(f"Waiting for {wait_time:.2f} seconds before next article detail fetch...")
                time.sleep(wait_time)

            print(f"Finished processing page {page}. Saved {new_articles_found_on_page} new articles from this page.")

            if page < end_page:
                wait_time = delay_list_fetch + random.uniform(0, 1)
                print(f"Waiting for {wait_time:.2f} seconds before fetching page {page + 1}...")
                time.sleep(wait_time)

        print("-" * 20)
        print(f"Crawler run finished. Total new articles saved in this run: {total_saved}")

if __name__ == "__main__":
    crawler = BjNewsCrawler()
    crawler.run(start_page=1, end_page=1, delay_list_fetch=3, delay_detail_fetch=7)
