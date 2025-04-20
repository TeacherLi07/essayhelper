import os
import redis
import faiss
import json
import streamlit as st
from config import REDIS_URL, REDIS_PASSWORD, FAISS_INDEX_PATH

@st.cache_resource
def load_faiss_index():
    """
    从磁盘加载 FAISS 索引和对应的 ID 映射文件。

    使用 Streamlit 的 cache_resource 装饰器缓存加载结果，避免重复加载。

    Returns:
        tuple[faiss.Index | None, dict | None]: 返回 FAISS 索引对象和 ID 映射字典的元组。
                                                如果加载失败，对应项为 None。
    """
    index_path = FAISS_INDEX_PATH
    id_map_path = index_path + ".map"

    if not os.path.exists(index_path):
        st.error(f"FAISS 索引文件未找到: {index_path}。请先运行初始化脚本。")
        print(f"FAISS 索引文件未找到: {index_path}")
        return None, None

    if not os.path.exists(id_map_path):
        st.error(f"FAISS ID 映射文件未找到: {id_map_path}")
        print(f"FAISS ID 映射文件未找到: {id_map_path}")
        return None, None

    print(f"开始加载 FAISS 索引: {index_path}...")
    try:
        index = faiss.read_index(index_path)
        print(f"FAISS 索引加载成功，包含 {index.ntotal} 条记录。")

        print(f"开始加载 ID 映射文件: {id_map_path}...")
        with open(id_map_path, 'r', encoding='utf-8') as f:
            id_map_str_keys = json.load(f)
        # JSON 加载后 key 是字符串，需要转回整数
        id_map = {int(k): v for k, v in id_map_str_keys.items()}
        print("ID 映射文件加载成功。")
        return index, id_map

    except Exception as e:
        st.error(f"加载 FAISS 索引或 ID 映射时出错: {e}")
        print(f"加载 FAISS 索引或 ID 映射时出错: {e}")
        return None, None

@st.cache_resource
def get_redis_connection():
    """
    建立到 Redis 数据库的连接。

    使用 Streamlit 的 cache_resource 装饰器缓存连接对象。

    Returns:
        redis.Redis | None: 成功时返回 Redis 连接对象，失败时返回 None。
    """
    print("正在连接到 Redis...")
    try:
        # 使用 from_url 方法，并根据需要传递密码
        r = redis.Redis.from_url(
            REDIS_URL,
            password=REDIS_PASSWORD,
            decode_responses=True # 自动将字节解码为字符串
        )
        r.ping() # 测试连接是否成功
        print("Redis 连接成功。")
        return r
    except redis.exceptions.ConnectionError as e:
        st.error(f"连接 Redis 时出错: {e}")
        print(f"连接 Redis 时出错: {e}")
        return None
    except redis.exceptions.AuthenticationError:
        st.error("Redis 认证失败。请检查 REDIS_PASSWORD 配置。")
        print("Redis 认证失败。请检查 REDIS_PASSWORD 配置。")
        return None
    except Exception as e:
        st.error(f"连接 Redis 时发生未知错误: {e}")
        print(f"连接 Redis 时发生未知错误: {e}")
        return None