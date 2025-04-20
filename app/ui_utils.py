import os
import streamlit as st
import streamlit.components.v1 as components
import json
from config import SUMMARY_TRUNCATE_LENGTH
from feedback_utils import handle_feedback  # 使用相对导入


def load_external_css(file_path):
    """
    加载外部 CSS 文件并应用到 Streamlit 应用。

    Args:
        file_path (str): CSS 文件的路径。
    """
    if os.path.exists(file_path):
        try:
            with open(file_path, encoding='utf-8') as f:
                st.markdown(f'<style>{f.read()}</style>', unsafe_allow_html=True)
            print(f"成功加载 CSS 文件: {file_path}")
        except Exception as e:
            st.warning(f"加载 CSS 文件 '{file_path}' 时出错: {e}")
            print(f"加载 CSS 文件 '{file_path}' 时出错: {e}")
    else:
        st.warning(f"CSS 文件未找到: {file_path}。自定义样式将不会应用。")
        print(f"CSS 文件未找到: {file_path}")

def get_article_summary(result: dict) -> str:
    """
    从搜索结果字典中提取文章摘要。
    会尝试解析 'row' 字段（可能是 JSON 字符串或字典），
    如果失败或不存在，则尝试 'content' 字段，最后回退到 '无摘要'。
    摘要会被截断到预设长度。

    Args:
        result (dict): 单条搜索结果的字典。

    Returns:
        str: 提取并处理后的文章摘要。
    """
    desc = '无摘要' # 默认值
    row_data = result.get('row')

    if isinstance(row_data, dict):
        # 如果 'row' 是字典，直接获取 'desc'
        desc = row_data.get('desc', '无摘要')
    elif isinstance(row_data, str):
        # 如果 'row' 是字符串，尝试解析为 JSON
        try:
            parsed_row = json.loads(row_data)
            if isinstance(parsed_row, dict):
                desc = parsed_row.get('desc', '无摘要')
            else:
                # 如果解析后不是字典，直接使用字符串内容
                desc = row_data
        except json.JSONDecodeError:
            # 如果解析 JSON 失败，直接使用原始字符串
            print(f"警告：无法将 'row' 字段解析为 JSON。将使用原始字符串作为摘要。")
            desc = row_data
    else:
        # 如果 'row' 不存在或类型不对，尝试获取 'content'
        content = result.get('content')
        if isinstance(content, str):
            desc = content
        elif content is not None: # 如果 content 不是字符串但存在，转为字符串
             desc = str(content)

    # 如果最终 desc 为空或仅包含空白字符，则重置为 '无摘要'
    if not desc or desc.isspace():
        desc = '无摘要'

    # 截断摘要
    if len(desc) > SUMMARY_TRUNCATE_LENGTH:
        desc = desc[:SUMMARY_TRUNCATE_LENGTH] + "..."

    return desc

def display_search_results(search_results: list):
    """
    在 Streamlit 界面上渲染搜索结果列表。

    Args:
        search_results (list): 包含搜索结果字典的列表。
    """
    for i, result in enumerate(search_results):
        with st.container():
            # 确保 result 是字典类型
            if not isinstance(result, dict):
                st.warning(f"跳过无效的结果项 #{i+1} (预期为字典，实际为 {type(result)})。")
                continue

            # 获取文章摘要
            summary = get_article_summary(result)

            # 获取其他元数据，提供默认值
            title = result.get('title', '无标题')
            publish_date = result.get('publish_date', '未知日期')
            score = result.get('score', None) # 可能为 None 或 float
            url = result.get('url', '#') # 默认链接到页面顶部

            # 格式化相关度分数
            score_display = f"{score:.4f}" if isinstance(score, (float, int)) else "N/A"

            # 使用 st.html 显示格式化的卡片
            # 使用 f-string 嵌入变量，注意 HTML 属性中的引号
            st.html(f"""
            <div class="article-card">
                <div class="article-header">
                    <h3>{i+1}. {title}</h3>
                    <div class="article-meta">
                        <span>📅 {publish_date}</span>
                        <span>相关度: {score_display}</span>
                    </div>
                </div>
                <div class="article-content">
                    <div class="article-summary">
                        <p>{summary}</p>
                    </div>
                    <div class="article-actions">
                        <a href="{url}" target="_blank" rel="noopener noreferrer" class="action-button conditional-link">阅读原文</a>
                    </div>
                </div>
            </div>
            """)

def add_wechat_link_fix_script():
    """
    添加一段 JavaScript 脚本，用于修复在微信内置浏览器中链接无法在新标签页打开的问题。
    """
    script_component = """
    <script>
    // 延迟执行以确保 DOM 元素加载完成
    setTimeout(function() {
        try {
            // 在父级文档中查找所有带有 'conditional-link' 类名的链接
            var links = window.parent.document.querySelectorAll('.conditional-link');
            console.log('[Component Script] 在父文档中找到条件链接数量:', links.length);

            // 检测是否在微信浏览器中
            if (/MicroMessenger/i.test(navigator.userAgent)) {
                console.log('[Component Script] 检测到微信环境，修改链接 target 为 _self');
                links.forEach(function(link) {
                    link.target = '_self'; // 将 target 设置为 _self，在当前页面打开
                    link.removeAttribute('rel'); // 移除 rel 属性
                    console.log('[Component Script] 已修改链接 target:', link.href);
                });
            } else {
                console.log('[Component Script] 非微信环境，保持 target _blank');
            }
        } catch (e) {
            // 捕获并打印访问父文档或修改链接时可能发生的错误
            console.error('[Component Script] 访问父文档或修改链接时出错:', e);
        }
    }, 500); // 延迟 500 毫秒执行
    </script>
    """
    # 使用 Streamlit components.html 将脚本注入页面，设置 height=0 使其不可见
    components.html(script_component, height=0)

def display_sidebar(faiss_index, redis_conn):
    """
    渲染 Streamlit 应用的侧边栏内容。

    Args:
        faiss_index: FAISS 索引对象或 None。
        redis_conn: Redis 连接对象或 None。
    """
    with st.sidebar:
        st.markdown("## 📋 使用指南")
        st.info(
            """
            **使用说明:**

            1. 在主界面的输入框键入作文题目、论点或关键词。
            2. 通过滑动条选择希望返回的相关文章数量。
            3. 点击「开始检索」按钮。
            4. 结果将按相关度从高到低显示。
            5. 点击“阅读原文”可跳转至原始文章链接（如果可用）。
            """
        )

        # --- 新增：用户反馈区域 ---
        st.markdown("## 💬 问题反馈")
        # 只有当 Redis 连接正常时才显示反馈表单
        if redis_conn:
            with st.form("feedback_form", clear_on_submit=True):
                feedback_text = st.text_area(
                    "有问题？有建议？",
                    height=150,
                    placeholder="都可以谈，有什么不能谈的.jpg",
                    help="我们会认真听取每一条建议"
                )
                submitted = st.form_submit_button("提交反馈")

                if submitted:
                    # 调用 feedback_utils 中的处理函数
                    success, message = handle_feedback(redis_conn, feedback_text)
                    if success:
                        st.success(message)
                    else:
                        st.error(message)
        else:
            # 如果 Redis 连接失败，显示提示信息而不是表单
            st.warning("⚠️ 反馈功能当前不可用，因为数据库连接失败。")
        # --- 反馈区域结束 ---

        st.markdown("---") # 分隔线

        st.markdown("## 🔧 系统状态")
        # 显示 FAISS 索引状态
        if faiss_index:
            st.success(f"✅ 索引已加载 (共 {faiss_index.ntotal} 篇文章)")
        else:
            st.error("❌ 索引未加载")

        # 显示 Redis 连接状态
        if redis_conn:
            st.success("✅ Redis 数据库已连接")
        else:
            st.error("❌ Redis 数据库未连接")

        st.markdown("---") # 分隔线

        st.markdown("## ℹ️ 关于项目")
        st.markdown("EssayHelper 是一款基于 BGE-M3 模型的开源议论文写作智能辅助工具。")
        st.markdown("它可以帮助用户快速查找与特定论点相关的参考文章。")
        st.markdown("[GitHub 项目仓库](https://github.com/TeacherLi07/essayhelper)")
        st.caption("Version 1.1 (Refactored)") # 可以添加版本信息

def display_footer():
    """
    渲染页面底部的页脚信息。
    """
    footer_html = """
    <div class="footer">
        <p>© 2025 TeacherLi | 基于 BGE-M3 的议论文语义检索系统 | <a href="https://github.com/TeacherLi07/essayhelper" target="_blank">GitHub</a></p>
    </div>
    """
    st.markdown(footer_html, unsafe_allow_html=True)
