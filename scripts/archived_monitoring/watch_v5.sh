#!/bin/bash

echo "持续监控v5回测（Ctrl+C停止）..."
echo

while true; do
    current_date=$(grep -E "日期: 2025" logs/backtest_v5_percentile.log | tail -1 | grep -oE "2025-[0-9-]+")
    buy_detect=$(grep "\[买入检测\]" logs/backtest_v5_percentile.log 2>/dev/null | wc -l | tr -d ' ')
    buy_signal=$(grep "买入信号:" logs/backtest_v5_percentile.log 2>/dev/null | wc -l | tr -d ' ')
    
    clear
    echo "======== v5回测实时监控 ========"
    echo
    echo "当前日期: $current_date"
    echo "买入检测触发: $buy_detect 次"
    echo "实际买入信号: $buy_signal 次"
    echo
    
    if [ "$buy_detect" -gt "0" ]; then
        echo "最近买入检测："
        grep "\[买入检测\]" logs/backtest_v5_percentile.log | tail -5
        echo
    fi
    
    if grep -q "回测完成" logs/backtest_v5_percentile.log 2>/dev/null; then
        echo "✅ 回测已完成！"
        break
    fi
    
    sleep 10
done
