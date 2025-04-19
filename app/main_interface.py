import streamlit as st
import os
import redis
import faiss
import numpy as np
from dotenv import load_dotenv
import json
import time
import requests # Added for API calls

# Assume BGE-M3 embedding function exists (same as in init_db.py)
# from embedding_utils import get_bge_m3_embedding # Placeholder

load_dotenv()

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
FAISS_INDEX_PATH = os.getenv("FAISS_INDEX_PATH", "./faiss_index.idx")
BAAI_API_KEY = os.getenv("SF_API_KEY") # Needed if using SiliconFlow or similar

# --- Updated Embedding Function (SiliconFlow API) ---
# IMPORTANT: Use the *exact same* embedding logic as in init_db.py
def get_embedding(text: str, retries=3, delay=5) -> np.ndarray | None:
    """Generates embeddings using SiliconFlow BGE-M3 API. Returns None on failure."""
    if not BAAI_API_KEY:
        print("Error: BAAI_API_KEY not found in environment variables.")
        st.error("API Key for embedding service is not configured.") # Show error in UI
        return None

    api_url = "https://api.siliconflow.cn/v1/embeddings"
    headers = {
        "Authorization": f"Bearer {BAAI_API_KEY}",
        "Content-Type": "application/json"
    }
    payload = {
        "model": "BAAI/bge-m3",
        "input": text,
        "encoding_format": "float"
    }

    for attempt in range(retries):
        try:
            response = requests.post(api_url, headers=headers, json=payload, timeout=30) # Shorter timeout for interactive use
            response.raise_for_status()

            data = response.json()
            if "data" in data and len(data["data"]) > 0 and "embedding" in data["data"][0]:
                embedding = data["data"][0]["embedding"]
                return np.array(embedding, dtype='float32')
            else:
                print(f"Error: Unexpected API response format: {data}")
                st.error("Failed to get embedding: Invalid response from service.")
                return None

        except requests.exceptions.RequestException as e:
            print(f"Error calling SiliconFlow API (attempt {attempt + 1}/{retries}): {e}")
            if attempt < retries - 1:
                print(f"Retrying in {delay} seconds...")
                time.sleep(delay)
            else:
                print("Max retries reached. Failed to get embedding.")
                st.error(f"Failed to get embedding after multiple retries: {e}")
                return None
        except Exception as e:
             print(f"An unexpected error occurred during embedding generation: {e}")
             st.error(f"An unexpected error occurred while generating embedding: {e}")
             return None
    return None
# --- End Embedding Function ---

@st.cache_resource
def load_faiss_index():
    """Loads the FAISS index from disk."""
    if os.path.exists(FAISS_INDEX_PATH):
        print(f"Loading FAISS index from {FAISS_INDEX_PATH}...")
        try:
            index = faiss.read_index(FAISS_INDEX_PATH)
            print(f"FAISS index loaded successfully with {index.ntotal} entries.")

            # Load the ID map
            id_map_path = FAISS_INDEX_PATH + ".map"
            if os.path.exists(id_map_path):
                 with open(id_map_path, 'r', encoding='utf-8') as f:
                    id_map = json.load(f)
                 # Convert keys back to integers if needed (JSON saves keys as strings)
                 id_map = {int(k): v for k, v in id_map.items()}
                 print("ID map loaded successfully.")
                 return index, id_map
            else:
                st.error(f"FAISS ID map file not found: {id_map_path}")
                print(f"FAISS ID map file not found: {id_map_path}")
                return None, None
        except Exception as e:
            st.error(f"Error loading FAISS index: {e}")
            print(f"Error loading FAISS index: {e}")
            return None, None
    else:
        st.error(f"FAISS index file not found: {FAISS_INDEX_PATH}. Please run scripts/init_db.py first.")
        print(f"FAISS index file not found: {FAISS_INDEX_PATH}")
        return None, None

@st.cache_resource
def get_redis_connection():
    """Establishes connection to Redis."""
    print("Connecting to Redis for app...")
    try:
        r = redis.Redis.from_url(REDIS_URL, decode_responses=True)
        r.ping()
        print("Redis connection successful for app.")
        return r
    except redis.exceptions.ConnectionError as e:
        st.error(f"Error connecting to Redis: {e}")
        print(f"Error connecting to Redis: {e}")
        return None

def search_articles(query: str, index, id_map, redis_client, k: int = 5):
    """Searches for articles using the query."""
    if index is None or redis_client is None or id_map is None:
        st.error("Search cannot proceed. Index or Redis connection missing.")
        return []

    print(f"Searching for top {k} articles related to: '{query}'")
    start_time = time.time()

    # 1. Generate embedding for the query
    query_embedding = get_embedding(query)
    if query_embedding is None:
        st.error("Failed to generate embedding for the query. Cannot perform search.")
        return [] # Return empty list if embedding fails

    query_embedding_np = np.array([query_embedding]).astype('float32')
    # faiss.normalize_L2(query_embedding_np) # Normalize if using IndexFlatIP

    # 2. Search the FAISS index
    # D = distances, I = indices (internal FAISS integer IDs)
    distances, faiss_indices = index.search(query_embedding_np, k)

    results = []
    if len(faiss_indices[0]) > 0:
        # 3. Retrieve original article data from Redis using the mapped IDs
        retrieved_ids = [id_map.get(int(i)) for i in faiss_indices[0] if int(i) in id_map] # Map FAISS int IDs back to string IDs
        print(f"Retrieved FAISS indices: {faiss_indices[0]}")
        print(f"Mapped article IDs: {retrieved_ids}")


        for i, article_id in enumerate(retrieved_ids):
            if article_id: # Check if mapping was successful
                redis_key = f"article:{article_id}"
                article_data = redis_client.hgetall(redis_key)
                if article_data:
                    article_data['score'] = float(distances[0][i]) # Add similarity score
                    results.append(article_data)
                else:
                    print(f"Warning: Article data not found in Redis for ID: {article_id}")
            else:
                 print(f"Warning: Could not map FAISS index {faiss_indices[0][i]} to an article ID.")


    end_time = time.time()
    print(f"Search completed in {end_time - start_time:.2f} seconds. Found {len(results)} results.")
    return results

# --- Streamlit UI ---
st.set_page_config(page_title="📝 EssayHelper", layout="wide")
st.title("📝 EssayHelper - 议论文写作智能助手")
st.caption("基于 BGE-M3 的全文本语义检索系统 | 新京报书评周刊")

# Load resources
faiss_index, faiss_id_map = load_faiss_index()
redis_conn = get_redis_connection()

# Input section
query = st.text_input("输入议论文主题或论点描述:", placeholder="例如：讨论人工智能伦理问题")
num_results = st.slider("选择返回文章数量:", min_value=1, max_value=20, value=5)

if st.button("开始检索", type="primary", disabled=(faiss_index is None or redis_conn is None)):
    if query:
        with st.spinner("正在检索相关文章..."):
            search_results = search_articles(query, faiss_index, faiss_id_map, redis_conn, k=num_results)

        if search_results:
            st.success(f"找到 {len(search_results)} 篇相关文章：")
            for i, result in enumerate(search_results):
                st.subheader(f"{i+1}. {result.get('title', '无标题')}")
                st.markdown(f"**发布日期:** {result.get('publish_date', '未知')} | **相关度得分:** {result.get('score', 'N/A'):.4f}")
                st.markdown(f"[阅读原文]({result.get('url', '#')})", unsafe_allow_html=True)
                # Optionally show a snippet of the content
                # content_snippet = result.get('content', '')[:200] + "..." if result.get('content') else "无内容"
                # st.markdown(f"> {content_snippet}")
                st.divider()
        else:
            st.warning("未能找到与查询相关的文章。")
    else:
        st.warning("请输入查询内容。")

st.sidebar.info(
    """
    **使用说明:**
    1. 在输入框键入论题描述。
    2. 通过滑动条选择返回文章数量。
    3. 点击「开始检索」。
    4. 点击文章链接跳转原文。
    """
)
st.sidebar.caption(f"FAISS Index Status: {'Loaded' if faiss_index else 'Not Loaded'}")
st.sidebar.caption(f"Redis Status: {'Connected' if redis_conn else 'Not Connected'}")
