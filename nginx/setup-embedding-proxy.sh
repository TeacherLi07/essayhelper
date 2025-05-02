#!/bin/bash

# 检查是否以root权限运行
if [ "$EUID" -ne 0 ]; then
  echo "请使用sudo或root权限运行此脚本"
  exit 1
fi

# 安装Nginx（如果尚未安装）
if ! command -v nginx &> /dev/null; then
    echo "安装Nginx..."
    apt-get update
    apt-get install -y nginx
fi

# 创建缓存目录
echo "创建缓存目录..."
mkdir -p /var/cache/nginx/embedding_cache
chmod 700 /var/cache/nginx/embedding_cache
chown www-data:www-data /var/cache/nginx/embedding_cache

# 复制配置文件
echo "复制Nginx配置文件..."
cp /opt/essayhelper/nginx/embedding-proxy.conf /etc/nginx/conf.d/

# 检查配置有效性
echo "验证Nginx配置..."
nginx -t

# 应用配置（如果检查通过）
if [ $? -eq 0 ]; then
    echo "Nginx配置有效，重启服务..."
    systemctl restart nginx
    systemctl enable nginx
    echo "Nginx服务已重启并设置为开机启动"
    
    # 测试代理是否正常工作
    echo "测试代理健康状态..."
    sleep 2  # 等待Nginx完全启动
    if curl -s http://localhost:8502/health | grep -q "embedding_proxy_running"; then
        echo "✅ 嵌入代理服务运行正常!"
        echo "向量嵌入代理已在 http://localhost:8502/v1/embeddings 上启动"
    else
        echo "❌ 代理服务检查失败，请检查Nginx日志"
    fi
else
    echo "❌ Nginx配置无效，请检查配置文件"
    exit 1
fi
