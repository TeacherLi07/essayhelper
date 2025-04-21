# 📝 EssayHelper - 议论文写作智能助手

**基于BGE-M3的全文本语义检索系统** | [在线演示](https://essay.kongjiang.org/) 


## 🌟 项目简介
本系统通过采集特定来源（如新京报）的文章，利用 BAAI/bge-m3 模型构建语义检索系统。用户输入议论文主题或提纲，系统可快速检索相关文章，为写作提供参考。

## 🚀 核心功能
### 已实现功能
- **文章爬取**：包含一个针对特定新闻源（bjnews）的爬虫模块 (`modules/crawler/bjnews_crawler.py`)，用于采集文章数据（标题/正文/发布时间/原文链接等）并保存为 JSON 文件及存入 Redis。
- **全文本语义检索**：基于 BAAI/bge-m3 模型（通过 SiliconFlow API 调用）进行全文本向量化和相似度匹配。
- **参数化搜索**：
  - 可调节返回文章数量（1-20篇）
  - 支持自然语言论点描述
- **结构化输出**：
  - 匹配文章标题
  - 原文直达链接
  - 文章发布时间

### 未来规划（TODO）
- [ ] 段落级语义匹配
- [ ] 历史查询记录功能
- [ ] 多维度排序（相关性+时效性）


## 📦 安装部署

### 环境要求
- Python 3.10+
- Redis 6.2+ （用于存储文章元数据）
- FAISS 1.7.4+ （向量索引引擎）

### 快速启动
```bash
# 克隆仓库
git clone https://github.com/teacherli07/essayhelper.git
cd essayhelper

# 安装依赖
pip install -r requirements.txt

# 环境配置
cp .env.example .env
# 修改.env中的配置：
# - BAAI_API_KEY = your_silliconflow_key  (用于调用 BGE-M3 模型 API)
# - REDIS_URL = redis://localhost:6379/0 (Redis 连接地址)
# - REDIS_PASSWORD = your_redis_password (Redis 密码，如果没有则留空)
# - DATA_PATH = ../essay_data/data (存放爬虫下载的 JSON 数据文件的目录)
# - FAISS_INDEX_PATH = ../essay_data/faiss_index.idx (FAISS 索引文件保存路径)

# 数据初始化
# 确保 DATA_PATH 目录下有爬取的 JSON 文件
python scripts/init_db.py  # 读取 JSON 文件，生成向量，构建 FAISS 索引，并将元数据存入 Redis
```

### 运行系统
```bash
# 启动爬虫组件（可选，如果需要采集新数据）
# python modules/crawler/bjnews_crawler.py # 注意：可能需要额外配置或适配

# 启动检索服务
streamlit run app/main_interface.py
```

## 📖 使用说明
1. 访问 `http://localhost:8501` 打开交互界面
2. 在输入框键入论题描述（示例："讨论人工智能伦理问题"）
3. 通过滑动条选择需要返回的文章数量（默认10篇）
4. 点击「开始检索」查看结果
5. 点击文章链接直接跳转原文（如果原文链接可用）

## 🔧 技术细节
### 核心模块
**1. 数据采集模块 (`modules/crawler/bjnews_crawler.py`)**
- 实现了一个针对特定新闻网站的爬虫。
- 将抓取的文章数据保存为本地 JSON 文件（位于 `DATA_PATH`）。
- 同时将文章元数据存入 Redis。

**2. 数据初始化脚本 (`scripts/init_db.py`)**
- 读取 `DATA_PATH` 目录下的 JSON 文件。
- 调用 SiliconFlow API (`get_embedding` 函数) 为每篇文章内容生成 BGE-M3 向量。
- 将文章元数据（包括标题、链接、发布日期等，复杂字段会 JSON 序列化）存储到 Redis 中，键格式为 `article:{article_id}`。
- 构建 FAISS 索引并将所有文章向量存入，保存索引文件到 `FAISS_INDEX_PATH`。

**3. 向量数据库与索引**
- 使用 Redis 存储文章的文本元数据。
- 使用 FAISS (`faiss-cpu`) 存储和检索文章内容的向量表示。
- 使用 BAAI/BGE-M3 (通过 SiliconFlow API) 作为嵌入模型。

**4. 检索系统 (`app/main_interface.py`)**
- 提供 Streamlit Web 界面。
-接收用户查询，生成查询向量。
- 在 FAISS 索引中执行向量相似度搜索（余弦相似度）。
- 从 Redis 中获取匹配文章的详细信息。
- 结果排序策略：纯向量相似度排序。

## ⚠️ 注意事项
1. 爬虫模块 (`bjnews_crawler.py`) 可能需要根据目标网站的结构变化进行维护。遵守网站的 `robots.txt` 和使用条款，合理控制采集频率。
2. `init_db.py` 脚本依赖于 `DATA_PATH` 目录下的 JSON 文件，运行前请确保数据已存在。
3. BGE-M3 模型 API 调用需要有效的 `BAAI_API_KEY`。
4. 搜索结果仅作学术参考，禁止商用。

## 📜 许可协议
- 代码部分采用 [MIT License](LICENCE)
- 爬取的数据内容版权归原内容提供方所有。

---

**让思想碰撞激发写作灵感** ✨📚🖋️

