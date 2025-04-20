import os
import json
import redis
import faiss
import numpy as np
from dotenv import load_dotenv
import requests
import time

load_dotenv(dotenv_path=".env", verbose=True)

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
REDIS_PASSWORD = os.getenv("REDIS_PASSWORD") # Load Redis password
FAISS_INDEX_PATH = os.getenv("FAISS_INDEX_PATH", "./faiss_index.idx")
DATA_PATH = os.getenv("DATA_PATH", "./data") # Assuming data is stored in files first
BAAI_API_KEY = os.getenv("BAAI_API_KEY") # Needed if using SiliconFlow or similar

# Updated embedding function using SiliconFlow API
def get_embedding(text: str, retries=3, delay=5) -> np.ndarray | None:
    """Generates embeddings using SiliconFlow BGE-M3 API. Returns None on failure."""
    if not BAAI_API_KEY:
        print("Error: BAAI_API_KEY not found in environment variables.")
        return None

    api_url = "https://api.siliconflow.cn/v1/embeddings"
    headers = {
        "Authorization": f"Bearer {BAAI_API_KEY}",
        "Content-Type": "application/json"
    }
    payload = {
        "model": "BAAI/bge-m3",
        "input": text,
        "encoding_format": "float" # Ensure float format
    }

    for attempt in range(retries):
        try:
            response = requests.post(api_url, headers=headers, json=payload, timeout=60)
            response.raise_for_status()

            data = response.json()
            if "data" in data and len(data["data"]) > 0 and "embedding" in data["data"][0]:
                embedding = data["data"][0]["embedding"]
                return np.array(embedding, dtype='float32')
            else:
                print(f"Error: Unexpected API response format: {data}")
                return None

        except requests.exceptions.RequestException as e:
            print(f"Error calling SiliconFlow API (attempt {attempt + 1}/{retries}): {e}")
            if attempt < retries - 1:
                print(f"Retrying in {delay} seconds...")
                time.sleep(delay)
            else:
                print("Max retries reached. Failed to get embedding.")
                return None
        except Exception as e:
            print(f"An unexpected error occurred during embedding generation: {e}")
            return None

    return None

def initialize_database():
    """Loads data, generates embeddings, builds FAISS index, and stores data in Redis."""
    print("Connecting to Redis...")
    try:
        # Use password if provided
        r = redis.Redis.from_url(REDIS_URL, password=REDIS_PASSWORD, decode_responses=True)
        r.ping()
        print("Redis connection successful.")
    except redis.exceptions.ConnectionError as e:
        print(f"Error connecting to Redis: {e}")
        return
    except redis.exceptions.AuthenticationError:
        print("Redis authentication failed. Please check REDIS_PASSWORD.")
        return

    print(f"Looking for data files in: {DATA_PATH}")
    if not os.path.exists(DATA_PATH):
        print(f"Data path {DATA_PATH} not found. Please ensure data files exist.")
        return

    all_embeddings = []
    article_ids = []

    print("Processing data files and generating embeddings...")
    for filename in os.listdir(DATA_PATH):
        if filename.endswith(".json"):
            filepath = os.path.join(DATA_PATH, filename)
            try:
                with open(filepath, 'r', encoding='utf-8') as f:
                    article_data = json.load(f)

                article_id = article_data.get("id")
                content = article_data.get("content", "")
                title = article_data.get("title", "")

                if not article_id or not content:
                    print(f"Skipping file {filename}: missing 'id' or 'content'.")
                    continue

                # --- Serialize complex fields for Redis HSET ---
                redis_key = f"article:{article_id}"
                save_data_redis = {}
                for k, v in article_data.items():
                    if isinstance(v, (dict, list)):
                        try:
                            save_data_redis[k] = json.dumps(v, ensure_ascii=False)
                        except TypeError:
                            print(f"Warning: Could not JSON serialize field '{k}' for Redis in {article_id}. Skipping field.")
                            save_data_redis[k] = str(v) # Fallback
                    else:
                        save_data_redis[k] = v
                # Filter out None values before saving
                filtered_data_redis = {k: v for k, v in save_data_redis.items() if v is not None}
                # --- End Serialization ---

                if filtered_data_redis:
                    r.hset(redis_key, mapping=filtered_data_redis)
                    print(f"Stored article {article_id} in Redis.")
                else:
                    print(f"Skipping storing article {article_id} in Redis due to empty data after filtering/serialization.")
                    continue # Skip embedding if data couldn't be stored properly

                print(f"Generating embedding for {article_id}...")
                embedding = get_embedding(content)
                if embedding is None:
                    print(f"Skipping article {article_id} due to embedding failure.")
                    continue

                all_embeddings.append(embedding)
                article_ids.append(article_id)

            except json.JSONDecodeError:
                print(f"Skipping file {filename}: Invalid JSON.")
            except Exception as e:
                print(f"Error processing file {filename}: {e}")

    if not all_embeddings:
        print("No embeddings generated. Cannot build FAISS index.")
        return

    print(f"Generated {len(all_embeddings)} embeddings.")

    embeddings_np = np.array(all_embeddings).astype('float32')
    dimension = embeddings_np.shape[1]
    if dimension == 0:
        print("Error: Embeddings array is empty or has zero dimension. Cannot build index.")
        return
    print(f"Building FAISS index with dimension {dimension}...")
    index = faiss.IndexFlatL2(dimension)
    index = faiss.IndexIDMap(index)

    id_map = {i: article_id for i, article_id in enumerate(article_ids)}
    faiss_ids = np.array(list(id_map.keys()), dtype='int64')

    index.add_with_ids(embeddings_np, faiss_ids)

    print(f"FAISS index built with {index.ntotal} entries.")

    print(f"Saving FAISS index to {FAISS_INDEX_PATH}...")
    faiss.write_index(index, FAISS_INDEX_PATH)

    id_map_path = FAISS_INDEX_PATH + ".map"
    print(f"Saving ID map to {id_map_path}...")
    with open(id_map_path, 'w', encoding='utf-8') as f:
        json.dump(id_map, f)

    print("Database initialization complete.")

if __name__ == "__main__":
    if not os.path.exists(DATA_PATH):
        os.makedirs(DATA_PATH)
        print(f"Created data directory: {DATA_PATH}")
        dummy_data = {
          "id": "dummy_001",
          "title": "示例文章标题",
          "content": "这是一段示例文本内容，用于测试数据库初始化流程。",
          "publish_date": "2024-01-01",
          "url": "http://example.com/dummy"
        }
        with open(os.path.join(DATA_PATH, "dummy_001.json"), 'w', encoding='utf-8') as f:
            json.dump(dummy_data, f, ensure_ascii=False, indent=2)
        print("Created dummy data file for testing.")

    initialize_database()
