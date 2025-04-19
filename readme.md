# 📝 EssayHelper - 议论文写作智能助手

**基于BGE-M3的全文本语义检索系统** | [在线演示](#) 


## 🌟 项目简介
本系统通过自动化采集新京报书评周刊公众号文章，构建基于BAAI/bge-m3模型的语义检索系统。输入议论文主题或提纲，快速获取相关高质量书评文章，为议论文写作提供权威参考文献支持。

## 🚀 核心功能
### 已实现功能
- **公众号文章爬取**：自动化采集全文数据（含标题/正文/发布时间/原文链接）
- **全文本语义检索**：基于bge-m3模型的全文本向量化匹配
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
- Redis 6.2+ （用于存储原始数据）
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
# - 微信公众号账号（爬虫使用）
# - BAAI_API_KEY = your_silliconflow_key
# - REDIS_URL = redis://localhost:6379

# 数据初始化
python scripts/init_db.py  # 首次运行需构建向量库
```

### 运行系统
```bash
# 启动爬虫组件（可选）
python modules/crawler/wechat_crawler.py

# 启动检索服务
streamlit run app/main_interface.py
```

## 📖 使用说明
1. 访问 `http://localhost:8501` 打开交互界面
2. 在输入框键入论题描述（示例："讨论人工智能伦理问题"）
3. 通过滑动条选择需要返回的文章数量（默认5篇）
4. 点击「开始检索」查看结果
5. 点击文章链接直接跳转公众号原文

## 🔧 技术细节
### 核心模块
**1. 数据采集模块**
- 基于[wechat_articles_spider](https://github.com/wnma3mz/wechat_articles_spider)的微信公众号爬虫
- 数据存储格式：
```json
{
  "id": "2024_0012",
  "title": "在算法时代重思人文价值",
  "content": "全文文本...", 
  "publish_date": "2024-03-15",
  "url": "https://mp.weixin.qq.com/xxx"
}
```

**2. 向量数据库构建**

使用SiliconCloud提供的BAAI/BGE-M3嵌入模型

**3. 检索系统**
- 余弦相似度计算
- 结果排序策略：纯向量相似度排序

## ⚠️ 注意事项
1. 遵守微信公众号平台爬虫协议，建议控制采集频率
3. 搜索结果仅作学术参考，禁止商用

## 📜 许可协议
- 代码部分采用 [MIT License](LICENSE)
- 数据内容版权归新京报书评周刊所有

---

**让思想碰撞激发写作灵感** ✨📚🖋️

