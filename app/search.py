import hashlib
import json
import time
import numpy as np
import streamlit as st
from embedding import get_embedding
from config import SEARCH_MAX_K

def search_articles(query: str, index, id_map, redis_client, k: int):
    """
    根据用户查询在 FAISS 索引中搜索相关文章，并从 Redis 获取详细信息。
    实现了基于 Redis 的持久化缓存机制。

    Args:
        query (str): 用户的查询语句。
        index (faiss.Index): 加载的 FAISS 索引对象。
        id_map (dict): FAISS 索引 ID 到文章 ID 的映射。
        redis_client (redis.Redis): Redis 连接对象。
        k (int): 用户希望返回的文章数量。

    Returns:
        tuple[list, float, bool]: 返回包含搜索结果字典的列表、搜索耗时（秒）和缓存是否命中的布尔值。
                                  失败或无结果时列表为空。
    """
    if index is None or redis_client is None or id_map is None:
        st.error("搜索无法进行。索引或 Redis 连接缺失。")
        return [], 0.0, False # 返回空列表、耗时 0、未命中缓存

    start_time = time.time()
    cache_hit = False

    # 1. 规范化查询并生成缓存键
    normalized_query = query.strip().lower() # 去除首尾空格并转小写
    query_hash = hashlib.md5(normalized_query.encode('utf-8')).hexdigest()
    # 缓存键始终使用最大 K 值 (SEARCH_MAX_K)，以提高复用性
    cache_key = f"cache:query:{query_hash}:k{SEARCH_MAX_K}"

    print(f"开始搜索与 '{query}' (规范化: '{normalized_query}') 相关的文章，请求数量: {k}")

    # 2. 尝试从 Redis 缓存读取结果
    try:
        cached_results_json = redis_client.get(cache_key)
        if cached_results_json:
            print(f"命中 Redis 持久化缓存，键: {cache_key}")
            cached_results = json.loads(cached_results_json)
            # 从缓存的最多 SEARCH_MAX_K 条结果中，取出用户请求的 k 条
            results = cached_results[:k]
            end_time = time.time()
            search_time = end_time - start_time
            cache_hit = True
            print(f"从缓存完成搜索，耗时 {search_time:.4f} 秒。找到 {len(cached_results)} 条缓存结果，返回前 {len(results)} 条。")
            return results, search_time, cache_hit
        else:
            print(f"Redis 缓存未命中，键: {cache_key}")
    except Exception as e:
        print(f"检查或读取 Redis 缓存时出错: {e}")
        # 如果缓存读取失败，则继续执行正常搜索流程

    # --- 缓存未命中时的逻辑 ---
    # 3. 生成查询向量
    print("正在为查询生成向量嵌入...")
    query_embedding = get_embedding(query)
    if query_embedding is None:
        st.error("无法为查询生成向量嵌入，搜索中止。")
        return [], 0.0, False # 返回空列表、耗时 0、未命中缓存

    query_embedding_np = np.array([query_embedding]).astype('float32')
    print("查询向量生成成功。")

    # 4. 在 FAISS 索引中搜索 (始终搜索 SEARCH_MAX_K 个最近邻)
    print(f"正在 FAISS 索引中搜索 {SEARCH_MAX_K} 个最近邻...")
    distances, faiss_indices = index.search(query_embedding_np, SEARCH_MAX_K)
    print(f"FAISS 搜索完成。找到 {len(faiss_indices[0])} 个原始索引。")

    all_results_for_storage = [] # 用于存储到缓存的完整结果列表
    if len(faiss_indices[0]) > 0:
        # 5. 使用 ID 映射将 FAISS 索引转换为文章 ID，并从 Redis 获取数据
        retrieved_ids = []
        valid_faiss_indices = []
        valid_distances = []

        for i, faiss_idx in enumerate(faiss_indices[0]):
            article_id = id_map.get(int(faiss_idx))
            if article_id is not None:
                retrieved_ids.append(article_id)
                valid_faiss_indices.append(faiss_idx)
                valid_distances.append(distances[0][i])
            else:
                print(f"警告：无法将 FAISS 索引 {faiss_idx} 映射到文章 ID。")

        print(f"有效的 FAISS 索引: {valid_faiss_indices}")
        print(f"映射后的文章 ID: {retrieved_ids}")

        if retrieved_ids:
            # 使用 pipeline 批量从 Redis 获取数据，提高效率
            pipe = redis_client.pipeline()
            for article_id in retrieved_ids:
                redis_key = f"article:{article_id}"
                pipe.hgetall(redis_key)
            
            try:
                redis_results = pipe.execute()
            except Exception as e:
                print(f"从 Redis 批量获取文章数据时出错: {e}")
                redis_results = [None] * len(retrieved_ids) # 出错时置空

            for i, article_data in enumerate(redis_results):
                if article_data:
                    try:
                        # 添加相似度分数到结果字典
                        article_data['score'] = float(valid_distances[i])
                        all_results_for_storage.append(article_data)
                    except (ValueError, IndexError):
                        print(f"警告：为文章 {retrieved_ids[i]} 添加分数时出错。")
                        article_data['score'] = 0.0 # 设置默认分数
                        all_results_for_storage.append(article_data)
                else:
                    print(f"警告：在 Redis 中未找到文章 ID: {retrieved_ids[i]} 的数据。")

    # 6. 将完整结果 (最多 SEARCH_MAX_K 条) 存入 Redis 缓存 (无过期时间)
    if all_results_for_storage:
        try:
            results_json = json.dumps(all_results_for_storage)
            redis_client.set(cache_key, results_json) # 不设置 ex 参数，表示永久存储
            print(f"已将 {len(all_results_for_storage)} 条结果存入 Redis 缓存，键: {cache_key}")
        except Exception as e:
            print(f"将结果存入 Redis 缓存时出错: {e}")

    end_time = time.time()
    search_time = end_time - start_time
    print(f"搜索完成，耗时 {search_time:.2f} 秒。找到 {len(all_results_for_storage)} 条结果。")

    # 7. 从完整结果中，返回用户请求的 k 条
    results = all_results_for_storage[:k]
    print(f"返回前 {len(results)} 条结果给用户。")
    return results, search_time, cache_hit # 此时 cache_hit 为 False