#!/usr/bin/python3
# -*- coding: utf-8 -*-

import os
import json
import logging
import time
import threading
import concurrent.futures
from typing import Dict, Any, List, Optional, Tuple
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv(dotenv_path=".env", verbose=True)

# 设置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(threadName)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# 从api_handler导入速率限制器
try:
    from core.api_handler import rate_limiter, handle_429_error
except ImportError:
    # 如果导入失败，创建自己的速率限制器
    logger.warning("无法导入api_handler中的速率限制器，将创建本地版本")
    
    class ApiRateLimiter:
        """简化版的API速率限制器，用于控制API调用频率"""
        def __init__(self):
            self.last_call_time = 0
            self.interval_lock = threading.Lock()
            self.rate_limit_event = threading.Event()
            self.rate_limit_event.set()  # 初始状态：允许调用
            self.retrier_lock = threading.RLock()
            self.retrier_id = None
            
        def wait_for_interval(self, interval: float, verbose: bool = False) -> None:
            """等待满足两次API调用之间的最小时间间隔要求"""
            with self.interval_lock:
                current_time = time.time()
                time_since_last_call = current_time - self.last_call_time
                
                if time_since_last_call < interval:
                    wait_time = interval - time_since_last_call
                    if verbose:
                        logger.info(f"线程 {threading.current_thread().name} - 等待 {wait_time:.2f} 秒以满足 API 调用间隔...")
                    time.sleep(wait_time)
                
                # 更新最后调用时间
                self.last_call_time = time.time()
        
        def wait_for_rate_limit_release(self, verbose: bool = False, timeout: float = 300) -> bool:
            """等待全局速率限制解除，带有超时机制"""
            if not self.rate_limit_event.is_set():
                thread_name = threading.current_thread().name
                if verbose:
                    logger.info(f"线程 {thread_name} - 检测到全局速率限制，进入等待(最长{timeout}秒)...")
                
                return self.rate_limit_event.wait(timeout)
            return True
        
        def is_rate_limited(self) -> bool:
            """检查全局速率限制是否已激活"""
            return not self.rate_limit_event.is_set()
        
        def get_retrier_id(self) -> Optional[int]:
            """获取当前负责429重试的线程ID"""
            with self.retrier_lock:
                return self.retrier_id
        
        def try_become_retrier(self, thread_id: int) -> bool:
            """尝试将当前线程设置为429错误的重试者"""
            with self.retrier_lock:
                if not self.is_rate_limited():
                    self.rate_limit_event.clear()
                    self.retrier_id = thread_id
                    return True
                else:
                    return self.retrier_id == thread_id
        
        def release_rate_limit(self, thread_id: int) -> bool:
            """解除全局速率限制，但只有当前重试者才能执行此操作"""
            with self.retrier_lock:
                if self.is_rate_limited() and self.retrier_id == thread_id:
                    self.retrier_id = None
                    self.rate_limit_event.set()
                    return True
                return False
    
    # 创建速率限制器实例
    rate_limiter = ApiRateLimiter()
    
    def handle_429_error(thread_id: int, retry_delay: float, verbose: bool = False) -> bool:
        """处理429（速率限制）错误"""
        thread_name = threading.current_thread().name
        is_retrier = rate_limiter.try_become_retrier(thread_id)
        
        if is_retrier:
            logger.warning(f"线程 {thread_name} (重试者) - 等待 {retry_delay:.2f} 秒后重试 (429)...")
            time.sleep(retry_delay)
            return True
        else:
            if verbose:
                logger.info(f"线程 {thread_name} - 遭遇429错误，但另一线程正在处理重试，进入等待...")
            rate_limiter.wait_for_rate_limit_release(verbose)
            if verbose:
                logger.info(f"线程 {thread_name} - 全局速率限制解除，重新检查")
            return False


class SummaryGenerator:
    """使用LLM为文章生成摘要并更新JSON文件"""
    
    def __init__(self, api_key: Optional[str] = None):
        """
        初始化摘要生成器
        
        Args:
            api_key: OpenAI API密钥，如果为None则尝试从环境变量获取
        """
        self.client = OpenAI(api_key=api_key, base_url="https://api.deepseek.com")
        self.max_retries = 10
        self.retry_delay = 2.0  # 初始重试延迟（秒）
        self.api_call_interval = 1  # API调用间隔（秒）
        self.verbose = False  # 详细日志模式
    
    def generate_summary(self, content: str) -> Tuple[bool, str, str]:
        """
        调用LLM生成文章摘要，包含重试和错误处理逻辑
        
        Args:
            content: 文章内容
            
        Returns:
            (success, summary, error_msg): 处理结果、摘要内容、错误信息的元组
        """
        current_thread_id = threading.get_ident()
        thread_name = threading.current_thread().name
        is_429_retrier = False
        attempt = 0
        
        try:
            while True:
                # 检查API调用间隔
                rate_limiter.wait_for_interval(self.api_call_interval, self.verbose)
                
                # 检查全局速率限制状态
                current_retrier = rate_limiter.get_retrier_id()
                if rate_limiter.is_rate_limited() and current_thread_id != current_retrier:
                    if self.verbose:
                        logger.info(f"线程 {thread_name} - 全局速率限制已激活，等待解除...")
                    wait_success = rate_limiter.wait_for_rate_limit_release(self.verbose, timeout=300)
                    if not wait_success:
                        logger.warning(f"线程 {thread_name} - 等待超时，将作为新线程继续...")
                    continue
                
                try:
                    # 再次检查速率限制状态
                    if rate_limiter.is_rate_limited() and current_thread_id != rate_limiter.get_retrier_id():
                        if self.verbose:
                            logger.info(f"线程 {thread_name} - 双重检查：速率限制已激活，且本线程不是重试者，跳过请求...")
                        continue
                    
                    if self.verbose:
                        logger.info(f"线程 {thread_name} - 发送摘要生成请求...")
                    
                    response = self.client.chat.completions.create(
                        model="deepseek-chat",
                        messages=[
                            {"role": "user", "content": f"从当下的时代背景出发，为此文章生成一个清晰、全面的摘要。\n\n{content}"}
                        ],
                        temperature=1.0,
                    )
                    
                    summary = response.choices[0].message.content.strip()
                    
                    # 请求成功，如果当前线程是429重试者，解除限制
                    if is_429_retrier:
                        if self.verbose:
                            logger.info(f"线程 {thread_name} (重试者) - 请求成功，解除全局速率限制...")
                        rate_limiter.release_rate_limit(current_thread_id)
                        is_429_retrier = False
                    
                    return True, summary, ""
                
                except Exception as e:
                    # 检查是否为速率限制错误(429)
                    if hasattr(e, 'code') and e.code == 429 or \
                       (hasattr(e, 'status_code') and e.status_code == 429) or \
                       '429' in str(e):
                        # 处理429错误
                        was_retrier = handle_429_error(current_thread_id, self.retry_delay, self.verbose)
                        if was_retrier:
                            is_429_retrier = True
                            if self.verbose:
                                logger.info(f"线程 {thread_name} - 已成为重试者，将继续尝试...")
                        continue  # 无论是否为重试者，都重新开始循环
                    
                    # 其他错误
                    error_msg = f"生成摘要时出错 (尝试 {attempt+1}/{self.max_retries}): {str(e)}"
                    logger.error(error_msg)
                    attempt += 1
                    
                    if attempt >= self.max_retries:
                        logger.error(f"达到最大重试次数 ({self.max_retries})，放弃摘要生成")
                        return False, "", error_msg
                    
                    # 非429错误的重试等待
                    logger.info(f"线程 {thread_name} - {self.retry_delay} 秒后重试...")
                    time.sleep(self.retry_delay)
        
        finally:
            # 清理逻辑：如果当前线程是429重试者，但函数即将退出，释放全局限制
            if is_429_retrier and rate_limiter.is_rate_limited():
                logger.info(f"线程 {thread_name} (重试者) - 在finally块中解除速率限制")
                rate_limiter.release_rate_limit(current_thread_id)
    
    def process_file(self, file_path: str) -> bool:
        """
        处理单个JSON文件，生成摘要并更新文件
        
        Args:
            file_path: JSON文件路径
            
        Returns:
            处理是否成功
        """
        thread_name = threading.current_thread().name
        try:
            # 读取JSON文件
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            # 检查是否已有摘要
            if 'summary' in data and data['summary']:
                logger.info(f"线程 {thread_name} - 文件 {file_path} 已有摘要，跳过")
                return True
            
            # 获取文章内容
            if 'content' not in data or not data['content']:
                logger.warning(f"线程 {thread_name} - 文件 {file_path} 没有content字段或为空")
                return False
            
            content = data['content']
            
            # 生成摘要
            logger.info(f"线程 {thread_name} - 正在为 {file_path} 生成摘要...")
            success, summary, error_msg = self.generate_summary(content)
            
            if not success or not summary:
                logger.warning(f"线程 {thread_name} - 文件 {file_path} 摘要生成失败: {error_msg}")
                return False
            
            # 更新JSON文件
            data['summary'] = summary
            # 使用临时文件写入方式，保证多线程安全
            temp_file = f"{file_path}.temp"
            with open(temp_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            
            # 重命名临时文件为原文件
            os.replace(temp_file, file_path)
            
            logger.info(f"线程 {thread_name} - 文件 {file_path} 摘要生成并更新成功")
            return True
        
        except Exception as e:
            logger.error(f"线程 {thread_name} - 处理文件 {file_path} 时出错: {e}")
            return False
    
    def process_directory(self, data_path: str, max_workers: int = 5) -> Dict[str, int]:
        """
        使用多线程处理目录中的所有JSON文件
        
        Args:
            data_path: 数据目录路径
            max_workers: 最大工作线程数
            
        Returns:
            处理结果统计
        """
        results = {
            "total": 0,
            "success": 0,
            "failed": 0
        }
        
        # 收集所有要处理的文件路径
        file_paths = []
        for root, _, files in os.walk(data_path):
            for file in files:
                if file.endswith('.json'):
                    results["total"] += 1
                    file_paths.append(os.path.join(root, file))
        
        # 使用线程池进行并发处理
        with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
            # 提交所有文件处理任务
            future_to_file = {executor.submit(self.process_file, file_path): file_path for file_path in file_paths}
            
            # 收集结果
            for future in concurrent.futures.as_completed(future_to_file):
                file_path = future_to_file[future]
                try:
                    success = future.result()
                    if success:
                        results["success"] += 1
                    else:
                        results["failed"] += 1
                except Exception as exc:
                    logger.error(f"处理文件 {file_path} 时发生异常: {exc}")
                    results["failed"] += 1
        
        logger.info(f"摘要生成统计: 总计: {results['total']}, 成功: {results['success']}, 失败: {results['failed']}")
        return results


def generate_summaries_for_essays(data_path: str, api_key: Optional[str] = None, max_workers: int = 5) -> Dict[str, int]:
    """
    为指定目录下所有JSON文件中的文章生成摘要（多线程版本）
    
    Args:
        data_path: 数据目录路径
        api_key: API密钥
        max_workers: 最大工作线程数
        
    Returns:
        处理结果统计
    """
    generator = SummaryGenerator(api_key=api_key)
    return generator.process_directory(data_path, max_workers=max_workers)


if __name__ == "__main__":
    import os
    import sys
    from datetime import datetime
    
    # 设置日志输出到文件
    work_dir = os.getcwd()
    log_file = os.path.join(work_dir, "summary.log")
    file_handler = logging.FileHandler(log_file)
    file_handler.setFormatter(logging.Formatter('%(asctime)s - %(threadName)s - %(levelname)s - %(message)s'))
    logger.addHandler(file_handler)
    
    # 从环境变量获取参数
    data_path = os.environ.get("DATA_PATH")
    api_key = os.environ.get("DS_API_KEY")
    max_workers = 8
    
    start_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    logger.info(f"===== 摘要生成任务开始 - {start_time} =====")
    
    if not data_path:
        logger.error("未设置环境变量DATA_PATH，请设置后重试")
        sys.exit(1)
    if not api_key:
        logger.error("未设置环境变量DS_API_KEY，请设置后重试")
        sys.exit(1)
    
    try:
        results = generate_summaries_for_essays(
            data_path=data_path,
            api_key=api_key,
            max_workers=max_workers
        )
        
        summary_msg = f"摘要生成已完成。总计处理: {results['total']}, 成功: {results['success']}, 失败: {results['failed']}"
        logger.info(summary_msg)
        print(summary_msg)
    except Exception as e:
        error_msg = f"摘要生成过程中发生错误: {str(e)}"
        logger.error(error_msg)
        print(error_msg)
        sys.exit(1)
    finally:
        end_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        logger.info(f"===== 摘要生成任务结束 - {end_time} =====")
