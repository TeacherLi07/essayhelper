#!/bin/zsh
# 显式加载系统环境变量（根据你的系统选择正确的配置文件）
source /etc/environment

# 执行爬虫任务
/usr/bin/python3 /opt/essayhelper/modules/crawler/bjnews_crawler_daily.py

# 执行数据库初始化
/usr/bin/python3 /opt/essayhelper/scripts/init_db.py
