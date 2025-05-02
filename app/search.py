import time
import numpy as np
import streamlit as st
from embedding import get_embedding

def search_articles(query: str, index, id_map, redis_client, k: int):
    """
    根据用户查询在 FAISS 索引中搜索相关文章，并从 Redis 获取详细信息。

    Args:
        query (str): 用户的查询语句。
        index (faiss.Index): 加载的 FAISS 索引对象。
        id_map (dict): FAISS 索引 ID 到文章 ID 的映射。
        redis_client (redis.Redis): Redis 连接对象。
        k (int): 用户希望返回的文章数量。

    Returns:
        tuple[list, float]: 返回包含搜索结果字典的列表和搜索耗时（秒）。
                            失败或无结果时列表为空。
    """
    if index is None or redis_client is None or id_map is None:
        st.error("搜索无法进行。索引或 Redis 连接缺失。")
        return [], 0.0

    start_time = time.time()

    print(f"开始搜索与 '{query}' 相关的文章，请求数量: {k}")

    # 1. 生成查询向量
    print("正在为查询生成向量嵌入...")
    query_embedding = get_embedding(query)
    if query_embedding is None:
        st.error("无法为查询生成向量嵌入，搜索中止。")
        return [], 0.0

    query_embedding_np = np.array([query_embedding]).astype('float32')
    print("查询向量生成成功。")

    # 2. 在 FAISS 索引中搜索
    print(f"正在 FAISS 索引中搜索 {k} 个最近邻...")
    distances, faiss_indices = index.search(query_embedding_np, k)
    print(f"FAISS 搜索完成。找到 {len(faiss_indices[0])} 个原始索引。")

    results = []
    if len(faiss_indices[0]) > 0:
        # 3. 使用 ID 映射将 FAISS 索引转换为文章 ID，并从 Redis 获取数据
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
                        results.append(article_data)
                    except (ValueError, IndexError):
                        print(f"警告：为文章 {retrieved_ids[i]} 添加分数时出错。")
                        article_data['score'] = 0.0 # 设置默认分数
                        results.append(article_data)
                else:
                    print(f"警告：在 Redis 中未找到文章 ID: {retrieved_ids[i]} 的数据。")

    end_time = time.time()
    search_time = end_time - start_time
    print(f"搜索完成，耗时 {search_time:.2f} 秒。找到 {len(results)} 条结果。")

    return results, search_time