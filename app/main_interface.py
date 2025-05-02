import streamlit as st
import os
import streamlit.components.v1 as components # 确保导入 components

# 从拆分出的模块导入所需函数和配置
from storage import load_faiss_index, get_redis_connection
from search import search_articles
from ui_utils import (
    load_external_css,
    display_search_results,
    add_wechat_link_fix_script,
    display_sidebar,
    display_footer
)

# --- Streamlit 页面配置 ---
st.set_page_config(
    page_title="📝 EssayHelper",
    layout="wide", # 使用宽布局
    initial_sidebar_state="auto", # 默认展开侧边栏
    menu_items={
        'Report a Bug': 'https://github.com/teacherli07/essayhelper/issues',
        'About': "📝 EssayHelper - 议论文写作助手 | 基于 BGE-M3 的语义检索系统"
    }
)

# --- 加载 CSS ---
# CSS 文件相对于当前脚本的路径
css_file_path = os.path.join(os.path.dirname(__file__), "style.css")
load_external_css(css_file_path)

# --- 主页面布局 ---
st.title("📝 EssayHelper - 议论文写作助手")
st.caption("输入作文题或论点，快速查找相关参考文章")

# --- 加载核心资源 ---
# 使用 st.spinner 提供加载状态反馈
with st.spinner("⏳ 正在加载索引和连接数据库..."):
    faiss_index, faiss_id_map = load_faiss_index()
    redis_conn = get_redis_connection()

# 检查资源加载是否成功，如果失败则显示错误并禁用搜索
resources_loaded = faiss_index is not None and redis_conn is not None and faiss_id_map is not None
if not resources_loaded:
    st.error("⚠️ 系统核心资源加载失败，无法提供服务。请检查后台日志或联系管理员。")

# --- 搜索输入区域 ---
col1, col2 = st.columns([3, 1]) # 调整列比例

with col1:
    query = st.text_area("输入作文题或论点进行文章检索:", 
                        placeholder="我们的劳动使大地改变了模样，在大地的模样里我们看到了自己。", 
                        help="若直接以作文题搜索，可能因观点不明确导致相关度较低。建议列出提纲或分论点检索，最长支持8k字符。",
                        height=120, # 调整输入框高度
                        key="query_input", # 为组件添加 key
                        disabled=not resources_loaded # 如果资源未加载，禁用输入框
                        )
    
with col2:
    # 滑动条选择返回结果数量
    num_results = st.slider(
        "返回文章数量:",
        min_value=1,
        max_value=30, 
        value=10, # 默认值
        help="相关度由高到低排序",
        key="num_results_slider",
        disabled=not resources_loaded
    )

# 搜索按钮
search_button = st.button(
    "🔍 开始检索",
    type="primary", # 设置为主要按钮样式
    key="search_button",
    disabled=not resources_loaded, # 资源未加载或查询为空时禁用
    use_container_width=True # 让按钮宽度适应容器
)

# --- 显示搜索结果 ---
if search_button and query: # 只有点击按钮且查询不为空时执行
    with st.spinner("🧠 正在检索相关文章，请稍候..."):
        # 调用搜索函数
        search_results, search_time = search_articles(
            query, faiss_index, faiss_id_map, redis_conn, k=num_results
        )

    # 显示搜索信息
    if search_results:
        st.success(f"✅ 在 {search_time:.2f} 秒内找到 {len(search_results)} 篇相关文章。")

    # 渲染结果或提示信息
    if search_results:
        display_search_results(search_results)
        # 添加用于修复微信链接问题的脚本
        add_wechat_link_fix_script()
    else:
        st.warning("🤔 未能找到与您的查询高度相关的文章。请尝试调整关键词或论点表述。")

elif search_button and not query: # 如果点击按钮但查询为空
    st.warning("⚠️ 请先输入查询内容后再点击检索。")

# --- 侧边栏 ---
display_sidebar(faiss_index, redis_conn)

# --- 页脚 ---
display_footer()