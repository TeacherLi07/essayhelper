import smtplib
import email
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.header import Header
from email.utils import formataddr, formatdate, make_msgid
import os
import json
import datetime
import logging
from dotenv import load_dotenv

# 加载环境变量
# 假设 .env 文件在项目根目录 (/opt/essayhelper)
dotenv_path = os.path.join(os.path.dirname(__file__), '..', '.env')
load_dotenv(dotenv_path=dotenv_path, verbose=True)

# 从环境变量获取邮件配置，提供默认值或提示
SMTP_HOST = os.getenv("SMTP_HOST", "smtpdm.aliyun.com") # 阿里云 SMTP 服务器地址
SMTP_PORT = int(os.getenv("SMTP_PORT", 80)) # 阿里云 SMTP 端口 (非 SSL)
SMTP_USERNAME = os.getenv("SMTP_USERNAME") # 阿里云控制台创建的发信地址
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD") # 阿里云控制台创建的 SMTP 密码
SMTP_SENDER_NICKNAME = os.getenv("SMTP_SENDER_NICKNAME", "EssayHelper Feedback") # 发件人昵称
ADMIN_EMAIL = os.getenv("ADMIN_EMAIL", "tumbleweed00@163.com") # 管理员接收反馈的邮箱

# 配置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def send_feedback_email(feedback_text: str) -> bool:
    """
    使用 SMTP 发送反馈邮件给管理员。

    Args:
        feedback_text: 用户提交的反馈内容。

    Returns:
        True 如果邮件发送成功，否则 False。
    """
    if not all([SMTP_USERNAME, SMTP_PASSWORD, ADMIN_EMAIL]):
        logging.error("邮件发送失败：缺少必要的 SMTP 配置环境变量 (SMTP_USERNAME, SMTP_PASSWORD, ADMIN_EMAIL)。请检查 .env 文件。")
        return False

    try:
        # 构建邮件内容
        msg = MIMEMultipart('alternative')
        subject = f"来自 EssayHelper 的新用户反馈 - {datetime.datetime.now().strftime('%Y-%m-%d %H:%M')}"
        msg['Subject'] = Header(subject, 'utf-8')
        msg['From'] = formataddr([SMTP_SENDER_NICKNAME, SMTP_USERNAME], 'utf-8')
        msg['To'] = ADMIN_EMAIL
        msg['Message-id'] = make_msgid()
        msg['Date'] = formatdate()

        # 邮件正文 (HTML 格式)
        html_content = f"""
        <html>
        <body>
            <p>收到一条来自 EssayHelper 应用的新用户反馈：</p>
            <pre style="background-color: #f0f0f0; padding: 10px; border: 1px solid #ccc;">{feedback_text}</pre>
            <p>提交时间: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
        </body>
        </html>
        """
        texthtml = MIMEText(html_content, _subtype='html', _charset='utf-8')
        msg.attach(texthtml)

        # 连接 SMTP 服务器并发送
        # 注意：这里使用非 SSL 端口 80，如果需要 SSL (端口 465)，请使用 smtplib.SMTP_SSL
        # 并确保 SMTP_PORT 环境变量设置为 465
        if SMTP_PORT == 465:
             # 如果需要 SSL，可以使用 smtplib.SMTP_SSL
             # import ssl
             # context = ssl.create_default_context()
             # client = smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT, timeout=10, context=context)
             # 暂时不支持 SSL，如果需要请取消注释并安装 ssl 模块（通常是内置的）
             logging.warning("当前配置为端口 465，但代码未启用 SMTP_SSL。将尝试普通 SMTP 连接。")
             client = smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=10) # 设置超时
        else:
            client = smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=10) # 设置超时

        # client.set_debuglevel(1) # 取消注释以启用调试输出
        client.login(SMTP_USERNAME, SMTP_PASSWORD)
        client.sendmail(SMTP_USERNAME, [ADMIN_EMAIL], msg.as_string())
        client.quit()
        logging.info(f"反馈邮件已成功发送至 {ADMIN_EMAIL}")
        return True

    except smtplib.SMTPAuthenticationError as e:
        logging.error(f"SMTP 认证错误 (请检查 SMTP_USERNAME 和 SMTP_PASSWORD): {e}")
    except smtplib.SMTPConnectError as e:
        logging.error(f"SMTP 连接错误 (请检查 SMTP_HOST 和 SMTP_PORT): {e}")
    except smtplib.SMTPException as e:
        logging.error(f"SMTP 错误，邮件发送失败: {e}")
    except Exception as e:
        logging.error(f"发送反馈邮件时发生未知错误: {e}")
    return False

def store_feedback(redis_conn, feedback_text: str) -> bool:
    """
    将反馈内容存储到 Redis 数据库。

    Args:
        redis_conn: Redis 连接对象。
        feedback_text: 用户提交的反馈内容。

    Returns:
        True 如果存储成功，否则 False。
    """
    if redis_conn is None:
        logging.error("无法存储反馈：Redis 连接不可用。")
        return False
    try:
        feedback_entry = {
            "timestamp": datetime.datetime.now().isoformat(),
            "feedback": feedback_text
        }
        # 使用 List 数据结构存储反馈，键名为 "essayhelper:feedback"
        # 将字典转换为 JSON 字符串进行存储
        redis_conn.rpush("essayhelper:feedback", json.dumps(feedback_entry))
        logging.info("用户反馈已成功存入 Redis。")
        return True
    except Exception as e:
        logging.error(f"存储反馈到 Redis 时出错: {e}")
        return False

def handle_feedback(redis_conn, feedback_text: str) -> tuple[bool, str]:
    """
    处理用户提交的反馈，包括存储和发送邮件通知。

    Args:
        redis_conn: Redis 连接对象。
        feedback_text: 用户提交的反馈内容。

    Returns:
        一个元组 (success, message)，success 为布尔值表示是否成功，message 为提示信息。
    """
    if not feedback_text or not feedback_text.strip():
        return False, "反馈内容不能为空。"

    # 尝试存储到 Redis
    stored_ok = store_feedback(redis_conn, feedback_text)

    # 尝试发送邮件
    email_sent_ok = send_feedback_email(feedback_text)

    # 根据结果返回不同的消息
    if stored_ok and email_sent_ok:
        return True, "感谢反馈！我们已收到。"
    elif stored_ok and not email_sent_ok:
        return True, "感谢您的反馈！我们已收到。（管理员邮件通知发送失败，请检查后台日志）"
    elif not stored_ok and email_sent_ok:
        # 这种情况理论上不应阻塞用户，但需要记录错误
        logging.error("反馈邮件已发送，但存储反馈到 Redis 时遇到问题。")
        return False, "抱歉，提交反馈时遇到存储问题，但我们已尝试通知管理员。请稍后再试或联系管理员。"
    else: # 两者都失败
        return False, "抱歉，提交反馈时遇到问题（存储和邮件通知均失败），请稍后再试或联系管理员。"

# 可以在这里添加一些测试代码（确保在生产环境中注释掉）
# if __name__ == '__main__':
#     # 测试邮件发送 (需要设置好环境变量)
#     test_feedback_mail = "这是一个来自 feedback_utils.py 的邮件发送测试。"
#     print(f"测试发送邮件至 {ADMIN_EMAIL}...")
#     sent = send_feedback_email(test_feedback_mail)
#     print(f"邮件发送测试结果: {sent}")

#     # 测试 Redis 存储 (需要有效的 Redis 连接)
#     # import redis
#     # try:
#     #     test_redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
#     #     test_redis_password = os.getenv("REDIS_PASSWORD")
#     #     test_redis_conn = redis.from_url(test_redis_url, password=test_redis_password, decode_responses=True)
#     #     test_redis_conn.ping() # 测试连接
#     #     print("连接到 Redis 进行测试...")
#     #     test_feedback_store = "这是一个 Redis 存储测试。"
#     #     stored = store_feedback(test_redis_conn, test_feedback_store)
#     #     print(f"Redis 存储测试结果: {stored}")
#     #     # 可以选择性地检查 Redis 中的数据
#     #     # feedback_list = test_redis_conn.lrange("essayhelper:feedback", -1, -1)
#     #     # print("最后一条反馈:", feedback_list[0] if feedback_list else "无")
#     # except Exception as e:
#     #     print(f"连接或测试 Redis 时出错: {e}")

#     # 测试 handle_feedback (需要 Redis 连接和环境变量)
#     # try:
#     #     if 'test_redis_conn' in locals() and test_redis_conn:
#     #         print("测试 handle_feedback...")
#     #         test_feedback_handle = "这是一个完整的 handle_feedback 测试。"
#     #         success, message = handle_feedback(test_redis_conn, test_feedback_handle)
#     #         print(f"handle_feedback 测试结果: success={success}, message='{message}'")
#     #     else:
#     #         print("跳过 handle_feedback 测试，因为 Redis 连接不可用。")
#     # except NameError:
#     #      print("跳过 handle_feedback 测试，因为 Redis 连接不可用。")
