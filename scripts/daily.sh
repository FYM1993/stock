#!/bin/bash
# 每日收盘后自动执行：更新数据 + 输出次日股票排名
#
# 加入 crontab:
#   crontab -e
#   添加: 5 16 * * 1-5 /Users/yimin.fu/GolandProjects/stock/scripts/daily.sh >> /tmp/stock_daily.log 2>&1
#   (周一到周五 16:05，A股 15:00 收盘)

# cron 环境 PATH 为空，需显式设置（若 conda 在其他路径请修改）
export PATH="/opt/homebrew/anaconda3/bin:/usr/local/bin:/usr/bin:/bin:$PATH"

# 资金(万)，用于过滤买不起的股票、输出建议金额。默认 10 万
CAPITAL_WAN=${CAPITAL_WAN:-10}

cd "$(dirname "$0")/.."

# 更新近 3 天数据（覆盖节假日漏跑）
if date -v-3d +%Y-%m-%d &>/dev/null; then
  START=$(date -v-3d +%Y-%m-%d)   # macOS
else
  START=$(date -d "3 days ago" +%Y-%m-%d)  # Linux
fi
END=$(date +%Y-%m-%d)

echo "[$(date)] 开始每日任务"
echo "[$(date)] [1/2] 更新数据 $START ~ $END"
python scripts/update_data.py --start "$START" --end "$END" || { echo "[$(date)] 更新数据失败"; exit 1; }
echo "[$(date)] [2/2] 实盘信号 (信号日=$END，资金=${CAPITAL_WAN}万，回测选最佳，预计 30-50 分钟)"
PYTHONWARNINGS=ignore::DeprecationWarning python scripts/run_live_signal.py --no-cache --date "$END" --capital "$CAPITAL_WAN" --auto-best || { echo "[$(date)] 实盘信号失败"; exit 1; }
echo "[$(date)] 完成"
