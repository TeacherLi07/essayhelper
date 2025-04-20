import requests
import numpy as np
import time
import streamlit as st
from config import BAAI_API_KEY, EMBEDDING_RETRIES, EMBEDDING_DELAY, EMBEDDING_TIMEOUT

def get_embedding(text: str) -> np.ndarray | None:
    """
    使用 SiliconFlow BGE-M3 API 生成文本的向量嵌入。

    Args:
        text (str): 需要生成嵌入的文本。

    Returns:
        np.ndarray | None: 成功时返回 float32 类型的 NumPy 数组，失败时返回 None。
    """
    if not BAAI_API_KEY:
        print("错误：环境变量中未找到 BAAI_API_KEY。")
        st.error("嵌入服务的 API Key 未配置。") # 在 UI 中显示错误
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

    for attempt in range(EMBEDDING_RETRIES):
        try:
            response = requests.post(api_url, headers=headers, json=payload, timeout=EMBEDDING_TIMEOUT)
            response.raise_for_status() # 检查 HTTP 错误状态

            data = response.json()
            # 检查 API 返回的数据结构是否符合预期
            if "data" in data and len(data["data"]) > 0 and "embedding" in data["data"][0]:
                embedding = data["data"][0]["embedding"]
                return np.array(embedding, dtype='float32')
            else:
                print(f"错误：API 返回格式不符合预期: {data}")
                st.error("获取嵌入失败：服务返回无效响应。")
                return None

        except requests.exceptions.RequestException as e:
            print(f"调用 SiliconFlow API 时出错 (尝试 {attempt + 1}/{EMBEDDING_RETRIES}): {e}")
            if attempt < EMBEDDING_RETRIES - 1:
                print(f"将在 {EMBEDDING_DELAY} 秒后重试...")
                time.sleep(EMBEDDING_DELAY)
            else:
                print("已达到最大重试次数。获取嵌入失败。")
                st.error(f"多次重试后获取嵌入失败: {e}")
                return None
        except Exception as e:
             print(f"生成嵌入时发生意外错误: {e}")
             st.error(f"生成嵌入时发生意外错误: {e}")
             return None
    return None # 所有重试失败后返回 None