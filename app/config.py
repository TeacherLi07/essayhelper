import os
from dotenv import load_dotenv

# 加载 .env 文件中的环境变量
# verbose=True 会在加载时打印信息，有助于调试
load_dotenv(dotenv_path=".env", verbose=True) # 注意路径调整，因为此文件在 app/ 目录下

# Redis 配置
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
REDIS_PASSWORD = os.getenv("REDIS_PASSWORD") # 如果没有密码，此值为 None

# FAISS 索引文件路径
FAISS_INDEX_PATH = os.getenv("FAISS_INDEX_PATH", "./faiss_index.idx") # 注意路径调整

# SiliconFlow API 密钥 (用于 BGE-M3 模型)
# 注意：环境变量名称可能需要根据 .env 文件调整，这里使用 SF_API_KEY
BAAI_API_KEY = os.getenv("SF_API_KEY")

# 搜索缓存和 FAISS 检索的最大 K 值
# 即使前端请求的 k 值较小，缓存和 FAISS 检索也使用此值，以提高缓存命中率
SEARCH_MAX_K = 30

# 嵌入生成重试次数
EMBEDDING_RETRIES = 3
# 嵌入生成重试间隔（秒）
EMBEDDING_DELAY = 5
# 嵌入生成 API 超时时间（秒）
EMBEDDING_TIMEOUT = 30

# 摘要截断长度
SUMMARY_TRUNCATE_LENGTH = 300