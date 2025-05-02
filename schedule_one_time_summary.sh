#!/bin/bash

# 确保脚本可执行
chmod +x "$(dirname "$0")/schedule_one_time_summary.sh"

# 工作目录
WORK_DIR=$(pwd)
SCRIPT_PATH="${WORK_DIR}/modules/summary_generator.py"

# 确保Python脚本有执行权限
chmod +x "$SCRIPT_PATH"

# 获取明天的日期
TOMORROW=$(date -d "tomorrow" +"%Y-%m-%d")

# 创建要执行的命令
COMMAND="cd $WORK_DIR && python $SCRIPT_PATH >> $WORK_DIR/summary.log 2>&1"

# 使用at命令安排任务在明天凌晨1:00执行一次
echo "$COMMAND" | at "01:00 $TOMORROW"

echo "已设置摘要生成器在 $TOMORROW 01:00 执行一次"
echo "日志文件将保存在: $WORK_DIR/summary.log"

# 显示所有已安排的at任务
echo -e "\n当前已安排的at任务:"
atq
