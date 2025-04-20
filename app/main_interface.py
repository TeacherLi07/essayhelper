import streamlit as st
import os
import redis
import faiss
import numpy as np
from dotenv import load_dotenv
import json
import time
import requests # Added for API calls
import streamlit.components.v1 as components # Import components
from datetime import datetime

# Assume BGE-M3 embedding function exists (same as in init_db.py)
# from embedding_utils import get_bge_m3_embedding # Placeholder

load_dotenv(dotenv_path=".env", verbose=True)

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
REDIS_PASSWORD = os.getenv("REDIS_PASSWORD") # Load Redis password
FAISS_INDEX_PATH = os.getenv("FAISS_INDEX_PATH", "./faiss_index.idx")
BAAI_API_KEY = os.getenv("SF_API_KEY") # Needed if using SiliconFlow or similar

def load_external_css(file_path):
    with open(file_path) as f:
        st.markdown(f'<style>{f.read()}</style>', unsafe_allow_html=True)

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
        # Use password if provided
        r = redis.Redis.from_url(REDIS_URL, password=REDIS_PASSWORD, decode_responses=True)
        r.ping()
        print("Redis connection successful for app.")
        return r
    except redis.exceptions.ConnectionError as e:
        st.error(f"Error connecting to Redis: {e}")
        print(f"Error connecting to Redis: {e}")
        return None
    except redis.exceptions.AuthenticationError:
        st.error("Redis authentication failed. Please check REDIS_PASSWORD.")
        print("Redis authentication failed for app. Please check REDIS_PASSWORD.")
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
    search_time = end_time - start_time
    print(f"Search completed in {search_time:.2f} seconds. Found {len(results)} results.")
    results.reverse()
    return results, search_time


# --- Streamlit UI ---
st.set_page_config(
    page_title="📝 EssayHelper", 
    layout="wide",
    initial_sidebar_state="expanded",
    menu_items={
        'Get Help': 'https://github.com/teacherli07/essayhelper/issues',
        'Report a bug': 'https://github.com/teacherli07/essayhelper/issues/new',
        'About': "📝 EssayHelper - 议论文写作助手 | 基于 BGE-M3 的语义检索系统"
    }
)

# Load external CSS file
css_file_path = os.path.join(os.path.dirname(__file__), "style.css")
if os.path.exists(css_file_path):
    load_external_css(css_file_path)
else:
    st.warning("style.css not found. Custom styles will not be applied.")

# 主页面标题与简介
col1, col2, col3 = st.columns([4, 1, 1])
with col1:
    st.title("📝 EssayHelper - 议论文写作助手")

# 加载资源（静默加载不显示成功信息）
with st.spinner("正在加载索引和连接数据库..."):
    faiss_index, faiss_id_map = load_faiss_index()
    redis_conn = get_redis_connection()
    if faiss_index is None or redis_conn is None:
        st.error("⚠️ 系统初始化失败，请检查索引文件和数据库连接")

# 简化的搜索区域，直接突出功能
col1, col2 = st.columns([3, 1])
with col1:
    query = st.text_input("输入关键词或论点进行文章检索:", 
                        placeholder="我们的劳动使大地改变了模样，在大地的模样里我们看到了自己。", 
                        help="输入与您议论文相关的主题词或论点描述")
with col2:
    num_results = st.slider("文章数量:", min_value=1, max_value=20, value=10, 
                          help="相关度由高到低排序")

search_button = st.button("🔍 开始检索", 
                        type="primary", 
                        disabled=(faiss_index is None or redis_conn is None),
                        help="点击开始检索")

# 显示检索结果
if search_button:
    if query:
        with st.spinner("🔍 正在检索相关文章..."):
            search_results, search_time = search_articles(query, faiss_index, faiss_id_map, redis_conn, k=num_results)

        if search_results:
            st.success(f"✅ 找到 {len(search_results)} 篇相关文章 (用时 {search_time:.2f} 秒)：")
            
            # 显示每篇文章的卡片
            for i, result in enumerate(search_results):
                with st.container():
                    # Ensure result is a dictionary before proceeding
                    if not isinstance(result, dict):
                        st.warning(f"Skipping invalid result item #{i+1} (expected dict, got {type(result)}).")
                        continue

                    # 准备摘要内容
                    desc = '无摘要' # Default value
                    row_data = result.get('row')

                    if isinstance(row_data, dict):
                        # If 'row' is already a dictionary
                        desc = row_data.get('desc', '无摘要')
                    elif isinstance(row_data, str):
                        # If 'row' is a JSON string, try to parse it
                        try:
                            parsed_row = json.loads(row_data)
                            if isinstance(parsed_row, dict):
                                desc = parsed_row.get('desc', '无摘要')
                            else:
                                # Parsed JSON is not a dict, maybe just use the string itself?
                                desc = row_data[:300] + "..." if len(row_data) > 300 else row_data
                        except json.JSONDecodeError:
                            # If parsing fails, use the string directly as fallback
                            print(f"Warning: Could not parse 'row' field as JSON for result {i+1}. Using raw string.")
                            desc = row_data[:300] + "..." if len(row_data) > 300 else row_data
                    else:
                        # Fallback to 'content' if 'row' is missing or not dict/str
                        content = result.get('content', '无摘要')
                        desc = content[:300] + "..." if len(content) > 300 else content
                    
                    # Ensure desc is not empty before displaying
                    if not desc:
                        desc = '无摘要'

                    # 创建统一的文章卡片
                    # 使用 st.html() 替代 st.markdown() 以确保 HTML 正确渲染
                    st.html(f"""
                    <div class="article-card">
                        <div class="article-header">
                            <h3>{i+1}. {result.get('title', '无标题')}</h3>
                            <div class="article-meta">
                                <span>📅 {result.get('publish_date', '未知')}</span>
                                <span>相关度: {result.get('score', 'N/A'):.4f}</span>
                            </div>
                        </div>
                        
                        <div class="article-content">
                            <div class="article-summary">
                                <p>{desc}</p>
                            </div>
                            <div class="article-actions">
                                <a href="{result.get('url', '#')}" target="_blank" rel="noopener noreferrer" class="action-button">阅读原文</a>
                            </div>
                        </div>
                    </div>
                    """)

            # WeChat链接处理脚本
            script_component = """
            <script>
            setTimeout(function() {
                try {
                    var links = window.parent.document.querySelectorAll('.conditional-link');
                    console.log('[Component Script] Found conditional links in parent:', links.length);

                    if (/MicroMessenger/i.test(navigator.userAgent)) {
                        console.log('[Component Script] WeChat detected, changing target to _self');
                        links.forEach(function(link) {
                            link.target = '_self';
                            link.removeAttribute('rel');
                            console.log('[Component Script] Changed target for:', link.href);
                        });
                    } else {
                        console.log('[Component Script] Not in WeChat, keeping target _blank');
                    }
                } catch (e) {
                    console.error('[Component Script] Error accessing parent document or modifying links:', e);
                }
            }, 500);
            </script>
            """
            components.html(script_component, height=0)

        else:
            st.warning("⚠️ 未能找到与查询相关的文章。请尝试调整关键词。")
    else:
        st.warning("⚠️ 请输入查询内容。")

# 侧边栏设置
with st.sidebar:
    # st.image("https://raw.githubusercontent.com/teacherli07/essayhelper/main/static/logo.png", width=50)
    st.markdown("## 📋 使用指南")
    
    st.info(
        """
**使用说明:**

1. 在输入框键入论题描述。
2. 通过滑动条选择返回文章数量。
3. 点击「开始检索」。
        """
    )

    # 显示系统状态
    st.markdown("## 🔧 系统状态")
    if faiss_index:
        st.success(f"✅ 索引已加载 | 文章总数: {faiss_index.ntotal}")
    else:
        st.error("❌ 索引未加载")
        
    if redis_conn:
        st.success("✅ Redis数据库已连接")
    else:
        st.error("❌ Redis数据库未连接")
    
    # 关于区域
    st.markdown("## ℹ️ 关于")
    st.markdown("[GitHub 项目仓库](https://github.com/TeacherLi07/essayhelper)")
    st.caption("基于 BGE-M3 的开源议论文写作辅助工具")

# 添加页脚
footer = """
<div class="footer">
    <p>© 2025 TeacherLi | 基于 BGE-M3 的议论文语义检索系统</p>
</div>
"""
st.markdown(footer, unsafe_allow_html=True)
