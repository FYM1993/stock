#!/bin/bash

LOG_FILE="logs/backtest_v4_relaxed.log"

echo "======== 回测v4状态 ========"
echo

# 当前进度
current_date=$(grep -E "日期: 2025" "$LOG_FILE" | tail -1 | grep -oE "2025-[0-9-]+")
echo "当前日期: $current_date"

# 买入统计
buy_detect_count=$(grep "\[买入检测\]" "$LOG_FILE" 2>/dev/null | wc -l | tr -d ' ')
buy_signal_count=$(grep "买入信号:" "$LOG_FILE" 2>/dev/null | wc -l | tr -d ' ')

echo "买入检测触发: $buy_detect_count 次"
echo "实际买入信号: $buy_signal_count 次"
echo

# 最近的买入检测
if [ "$buy_detect_count" -gt "0" ]; then
    echo "最近5次买入检测:"
    grep "\[买入检测\]" "$LOG_FILE" | tail -5
    echo
fi

# 检查是否完成
if grep -q "回测完成" "$LOG_FILE" 2>/dev/null; then
    echo "✅ 回测已完成！"
    echo
    echo "最终结果："
    grep -A 5 "回测结果分析" "$LOG_FILE"
else
    echo "⏳ 回测进行中..."
fi
