#!/bin/bash

while true; do
    clear
    echo "======== v6回测实时监控（Ctrl+C停止）========"
    echo
    
    current_date=$(grep -E "日期: 2025" logs/backtest_v6_fix_getdata.log | tail -1 | grep -oE "2025-[0-9-]+")
    buy_detect=$(grep "\[买入检测\]" logs/backtest_v6_fix_getdata.log 2>/dev/null | wc -l | tr -d ' ')
    buy_signal=$(grep "买入信号:" logs/backtest_v6_fix_getdata.log 2>/dev/null | wc -l | tr -d ' ')
    
    echo "📅 当前日期: $current_date"
    echo "🔍 买入检测触发: $buy_detect 次"
    echo "✅ 实际买入信号: $buy_signal 次"
    echo
    
    if [ "$buy_detect" -gt "0" ]; then
        echo "📝 最近5次买入检测："
        grep "\[买入检测\]" logs/backtest_v6_fix_getdata.log | tail -5 | sed 's/.*INFO.*- /  /'
        echo
    fi
    
    if [ "$buy_signal" -gt "0" ]; then
        echo "💰 买入信号："
        grep "买入信号:" logs/backtest_v6_fix_getdata.log | sed 's/.*INFO.*- /  /'
        echo
    fi
    
    if grep -q "回测完成" logs/backtest_v6_fix_getdata.log 2>/dev/null; then
        echo "✅ 回测已完成！"
        break
    fi
    
    sleep 5
done
