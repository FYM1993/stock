#!/bin/bash

# A股量化策略框架 - 启动脚本

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo "========================================"
echo "  A股量化策略框架 v2.0"
echo "========================================"
echo ""

# 检查 Python 环境
echo "检查 Python 环境..."
if ! command -v python &> /dev/null; then
    echo -e "${RED}错误: 未找到 Python${NC}"
    exit 1
fi

PYTHON_VERSION=$(python --version)
echo -e "${GREEN}✓ $PYTHON_VERSION${NC}"
echo ""

# 检查依赖
echo "检查依赖包..."
python -c "import qlib" 2>/dev/null
if [ $? -ne 0 ]; then
    echo -e "${YELLOW}警告: Qlib 未安装${NC}"
    echo "正在安装依赖..."
    pip install -r requirements.txt
else
    echo -e "${GREEN}✓ Qlib 已安装${NC}"
fi
echo ""

# 辅助函数：检查数据完整性
check_data_coverage() {
    local start_date=$1
    local end_date=$2
    python scripts/check_data.py --start "$start_date" --end "$end_date" --json
}

# 辅助函数：获取现有数据范围
get_existing_data_range() {
    local calendar_file="qlib_data/cn_data/calendars/day.txt"
    if [ -f "$calendar_file" ] && [ -s "$calendar_file" ]; then
        local first_date=$(head -1 "$calendar_file")
        local last_date=$(tail -1 "$calendar_file")
        echo "$first_date|$last_date"
    else
        echo "|"
    fi
}

# 辅助函数：日期格式转换 YYYY-MM-DD -> YYYYMMDD
date_to_compact() {
    echo "$1" | sed 's/-//g'
}

# 辅助函数：日期格式转换 YYYYMMDD -> YYYY-MM-DD
date_to_dash() {
    echo "$1" | sed 's/\([0-9]\{4\}\)\([0-9]\{2\}\)\([0-9]\{2\}\)/\1-\2-\3/'
}

# ========================================
# 主流程：询问回测时间
# ========================================
echo ""
echo "========================================"
echo "  📅 回测时间设置"
echo "========================================"
echo ""

# 获取现有数据范围
data_range=$(get_existing_data_range)
existing_start=$(echo "$data_range" | cut -d'|' -f1)
existing_end=$(echo "$data_range" | cut -d'|' -f2)

if [ -n "$existing_start" ] && [ -n "$existing_end" ]; then
    echo -e "${GREEN}✓ 检测到已有数据${NC}"
    echo "  时间范围: $existing_start ~ $existing_end"
    echo ""
fi

# 推荐时间范围（最近1年）
recommended_end=$(date +%Y-%m-%d)
recommended_start=$(date -v-1y +%Y-%m-%d 2>/dev/null || date -d "1 year ago" +%Y-%m-%d)

echo "📌 推荐使用最近1年数据："
echo "   开始: $recommended_start"
echo "   结束: $recommended_end"
echo ""
echo "请输入回测时间范围（格式: YYYYMMDD）"
echo ""

# 输入开始日期
while true; do
    read -p "回测开始日期 [默认: $(date_to_compact $recommended_start)]: " input_start
    input_start=${input_start:-$(date_to_compact $recommended_start)}
    
    # 验证格式
    if [[ ! "$input_start" =~ ^[0-9]{8}$ ]]; then
        echo -e "${RED}错误: 日期格式不正确，请使用 YYYYMMDD 格式${NC}"
        continue
    fi
    
    backtest_start=$(date_to_dash "$input_start")
    break
done

# 输入结束日期
while true; do
    read -p "回测结束日期 [默认: $(date_to_compact $recommended_end)]: " input_end
    input_end=${input_end:-$(date_to_compact $recommended_end)}
    
    # 验证格式
    if [[ ! "$input_end" =~ ^[0-9]{8}$ ]]; then
        echo -e "${RED}错误: 日期格式不正确，请使用 YYYYMMDD 格式${NC}"
        continue
    fi
    
    backtest_end=$(date_to_dash "$input_end")
    
    # 验证结束日期 >= 开始日期
    if [[ "$backtest_end" < "$backtest_start" ]]; then
        echo -e "${RED}错误: 结束日期不能早于开始日期${NC}"
        continue
    fi
    
    break
done

echo ""
echo -e "${BLUE}✓ 回测时间范围已设置: $backtest_start ~ $backtest_end${NC}"
echo ""

# 检查数据完整性
echo "检查数据完整性..."
check_result=$(check_data_coverage "$backtest_start" "$backtest_end")

has_data=$(echo "$check_result" | python -c "import sys, json; print(json.load(sys.stdin)['price_data']['has_data'])")
full_coverage=$(echo "$check_result" | python -c "import sys, json; print(json.load(sys.stdin)['price_data']['full_coverage'])")
need_download=$(echo "$check_result" | python -c "import sys, json; print(json.load(sys.stdin)['price_data']['need_download'])")

if [ "$full_coverage" = "True" ]; then
    echo -e "${GREEN}✓ 数据完整，可以直接回测${NC}"
    echo ""
    
    # 更新配置文件
    python << EOF
import yaml
config_file = 'configs/strategy_config.yaml'
with open(config_file, 'r', encoding='utf-8') as f:
    config = yaml.safe_load(f)
config['start_time'] = '$backtest_start'
config['end_time'] = '$backtest_end'
with open(config_file, 'w', encoding='utf-8') as f:
    yaml.dump(config, f, allow_unicode=True, sort_keys=False)
print("✓ 配置已更新")
EOF
    
    echo ""
    echo "========================================"
    echo "  🚀 运行回测"
    echo "========================================"
    read -p "按回车键开始回测..." dummy
    python scripts/run_backtest.py
    exit 0
fi

# 需要下载数据
echo ""
echo -e "${YELLOW}⚠️  数据不完整${NC}"
echo ""

if [ "$has_data" = "True" ]; then
    existing_start=$(echo "$check_result" | python -c "import sys, json; print(json.load(sys.stdin)['price_data']['existing_start'])")
    existing_end=$(echo "$check_result" | python -c "import sys, json; print(json.load(sys.stdin)['price_data']['existing_end'])")
    echo "现有数据: $existing_start ~ $existing_end"
    
    # 显示缺失范围
    missing_ranges=$(echo "$check_result" | python -c "import sys, json; ranges = json.load(sys.stdin)['price_data']['missing_ranges']; print('\n'.join([f'{r[0]} ~ {r[1]}' for r in ranges]))")
    echo "缺失数据:"
    echo "$missing_ranges" | while read range; do
        echo "  - $range"
    done
else
    echo "当前无任何数据"
fi

echo ""
read -p "是否下载缺失的数据？[Y/n]: " download_choice
download_choice=${download_choice:-Y}

if [[ ! "$download_choice" =~ ^[Yy] ]]; then
    echo "已取消"
    exit 0
fi

# ========================================
# 下载数据
# ========================================
echo ""
echo "========================================"
echo "  📥 下载数据"
echo "========================================"
echo ""

# 选择下载模式
echo "请选择下载模式："
echo ""
echo "  [1] 后台下载（推荐）"
echo "      - 不影响使用，可以继续其他工作"
echo "      - 预计 40 分钟完成"
echo "      - 完成后重新运行 ./start.sh"
echo ""
echo "  [2] 前台下载"
echo "      - 等待下载完成，直接进入回测"
echo "      - 预计 40 分钟"
echo ""
read -p "请输入选项 [1]: " download_mode
download_mode=${download_mode:-1}

mkdir -p logs

case $download_mode in
    1)
        # 后台下载
        echo ""
        echo "步骤 1/2: 启动股票数据下载..."
        nohup python scripts/update_data.py --auto \
            --start "$(date_to_compact $backtest_start)" \
            --end "$(date_to_compact $backtest_end)" \
            > logs/stock_data.log 2>&1 &
        STOCK_PID=$!
        
        echo "步骤 2/2: 启动情绪数据下载..."
        nohup python scripts/download_emotion_data.py \
            --start "$backtest_start" \
            --end "$backtest_end" \
            > logs/emotion_data.log 2>&1 &
        EMOTION_PID=$!
        
        echo ""
        echo -e "${GREEN}✓ 后台下载已启动${NC}"
        echo ""
        echo "进程信息："
        echo "  股票数据: PID $STOCK_PID (日志: logs/stock_data.log)"
        echo "  情绪数据: PID $EMOTION_PID (日志: logs/emotion_data.log)"
        echo ""
        echo "💡 查看进度："
        echo "  tail -f logs/stock_data.log"
        echo "  tail -f logs/emotion_data.log"
        echo ""
        echo "💡 下载完成后："
        echo "  1. 运行数据转换: python scripts/convert_data.py"
        echo "  2. 重新运行 ./start.sh 进行回测"
        ;;
        
    2)
        # 前台下载
        echo ""
        echo "步骤 1/3: 下载股票数据..."
        python scripts/update_data.py --auto \
            --start "$(date_to_compact $backtest_start)" \
            --end "$(date_to_compact $backtest_end)"
        
        if [ $? -ne 0 ]; then
            echo -e "${RED}股票数据下载失败${NC}"
            exit 1
        fi
        
        echo ""
        echo "步骤 2/3: 下载情绪数据..."
        python scripts/download_emotion_data.py \
            --start "$backtest_start" \
            --end "$backtest_end"
        
        if [ $? -ne 0 ]; then
            echo -e "${RED}情绪数据下载失败${NC}"
            exit 1
        fi
        
        echo ""
        echo "步骤 3/3: 转换数据为 Qlib 格式..."
        python scripts/convert_data.py
        
        if [ $? -ne 0 ]; then
            echo -e "${RED}数据转换失败${NC}"
            exit 1
        fi
        
        echo ""
        echo -e "${GREEN}✓ 数据准备完成${NC}"
        echo ""
        
        # 更新配置并运行回测
        python << EOF
import yaml
config_file = 'configs/strategy_config.yaml'
with open(config_file, 'r', encoding='utf-8') as f:
    config = yaml.safe_load(f)
config['start_time'] = '$backtest_start'
config['end_time'] = '$backtest_end'
with open(config_file, 'w', encoding='utf-8') as f:
    yaml.dump(config, f, allow_unicode=True, sort_keys=False)
EOF
        
        echo "========================================"
        echo "  🚀 运行回测"
        echo "========================================"
        read -p "按回车键开始回测..." dummy
        python scripts/run_backtest.py
        ;;
        
    *)
        echo -e "${RED}无效选择${NC}"
        exit 1
        ;;
esac

exit 0

# ========================================
# 下面是旧的代码（保留用于参考）
# ========================================
: <<'OLD_CODE'

# 检查是否已初始化
if [ ! -d "qlib_data/cn_data" ] || [ -z "$(ls -A qlib_data/cn_data 2>/dev/null)" ]; then
    echo "========================================"
    echo "  首次使用 - 需要初始化"
    echo "========================================"
    echo ""
    echo -e "${BLUE}初始化流程：${NC}"
    echo "  1️⃣  下载基准指数数据（沪深300等，几秒）"
    echo "  2️⃣  下载近1年股票价格数据（981只活跃股，约30分钟）"
    echo "  3️⃣  转换数据为 Qlib 格式（自动）"
    echo "  4️⃣  下载市场情绪数据（约5-10分钟）"
    echo ""
    echo -e "${YELLOW}⚠️  说明：${NC}"
    echo "  策略需要：价格数据 + 情绪数据"
    echo "  总下载时间：约40分钟"
    echo "  建议：后台运行，不影响其他操作"
    echo ""
    
    read -p "是否开始初始化？(y/n): " init_confirm
    if [[ ! $init_confirm =~ ^[Yy]$ ]]; then
        echo "已取消"
        exit 0
    fi
    
    echo ""
    echo "========================================"
    echo "  数据下载方式"
    echo "========================================"
    echo ""
    echo "  ${GREEN}1. 后台下载${NC}（推荐）- 不影响使用，40分钟后可回测"
    echo "  ${YELLOW}2. 前台下载${NC} - 等待完成，需保持终端运行"
    echo "  3. 手动下载 - 退出，稍后手动运行"
    echo ""
    
    read -p "请选择 [1-3]: " download_mode
    case $download_mode in
        1)
            echo ""
            echo -e "${GREEN}后台启动数据下载...${NC}"
            mkdir -p logs
            
            # 1. 下载股票数据
            echo "步骤 1/2: 启动股票数据下载..."
            nohup python scripts/update_data.py --auto --recent > logs/stock_data.log 2>&1 &
            STOCK_PID=$!
            
            # 2. 下载情绪数据（并行）
            echo "步骤 2/2: 启动情绪数据下载..."
            nohup python scripts/download_emotion_data.py --start 2025-02-14 --end 2026-02-14 > logs/emotion_data.log 2>&1 &
            EMOTION_PID=$!
            
            sleep 2
            echo ""
            echo -e "${GREEN}✓ 数据下载已在后台启动（两个任务并行）！${NC}"
            echo ""
            echo "状态："
            echo "  任务1: 股票价格数据（981只 × 近1年）"
            echo "    进度: tail -f logs/stock_data.log"
            echo "    PID: $STOCK_PID"
            echo ""
            echo "  任务2: 市场情绪数据（366天）"
            echo "    进度: tail -f logs/emotion_data.log"
            echo "    PID: $EMOTION_PID"
            echo ""
            echo "  预计: 40分钟完成"
            echo ""
            echo -e "${YELLOW}注意：${NC}"
            echo "  - 两个任务都完成后才能回测"
            echo "  - 可以随时查看进度"
            echo "  - 关机/重启后需重新运行"
            ;;
        2)
            echo ""
            echo -e "${GREEN}开始前台下载（保持终端运行）...${NC}"
            echo ""
            echo "步骤 1/2: 下载股票数据..."
            python scripts/update_data.py --auto --recent
            echo ""
            echo "步骤 2/2: 下载情绪数据..."
            python scripts/download_emotion_data.py --start 2025-02-14 --end 2026-02-14
            ;;
        3)
            echo ""
            echo -e "${YELLOW}已跳过初始化${NC}"
            echo ""
            echo "稍后可手动运行："
            echo "  # 股票数据"
            echo "  python scripts/update_data.py --auto --recent"
            echo ""
            echo "  # 情绪数据"
            echo "  python scripts/download_emotion_data.py --start 2025-02-14 --end 2026-02-14"
            exit 0
            ;;
        *)
            echo ""
            echo -e "${RED}无效选项${NC}"
            exit 1
            ;;
    esac
    
    echo ""
    echo "========================================"
    echo -e "  ${GREEN}✅ 初始化完成！${NC}"
    echo "========================================"
    echo ""
    echo "下一步："
    echo "  1. 运行回测: python scripts/run_backtest.py"
    echo "  2. 重新运行此脚本使用交互菜单"
    echo ""
    exit 0
fi

# 已初始化，显示主菜单
echo "========================================"
echo "  主菜单"
echo "========================================"
echo ""
echo "请选择操作："
echo "  1. 运行回测"
echo "  2. 采集今日数据"
echo "  3. 补充/更新历史数据"
echo "  4. 查看回测结果"
echo "  5. 启动 Jupyter Notebook"
echo "  6. 重新初始化（清理数据）"
echo "  0. 退出"
echo ""

read -p "请输入选项 [0-6]: " choice

case $choice in
    1)
        echo ""
        echo "运行回测..."
        python scripts/run_backtest.py
        ;;
    2)
        echo ""
        echo "采集今日数据..."
        python scripts/collect_data.py --mode daily
        ;;
    3)
        echo ""
        echo "补充/更新历史数据..."
        echo ""
        echo "执行方式："
        echo "  1. 前台运行（等待完成）"
        echo "  2. 后台运行（继续使用）"
        echo ""
        read -p "请选择 [1-2]: " run_mode
        if [ "$run_mode" = "1" ]; then
            python scripts/update_data.py
        elif [ "$run_mode" = "2" ]; then
            mkdir -p logs
            nohup python scripts/update_data.py > logs/update_log.txt 2>&1 &
            echo -e "${GREEN}✓ 已在后台启动${NC}"
            echo "查看进度: tail -f logs/update_log.txt"
        fi
        ;;
    4)
        echo ""
        echo "最近的回测结果："
        ls -lt results/ 2>/dev/null | head -n 6 || echo "暂无回测结果"
        echo ""
        read -p "输入文件名查看详情（或按回车跳过）: " filename
        if [ ! -z "$filename" ]; then
            cat "results/$filename" 2>/dev/null || echo "文件不存在"
        fi
        ;;
    5)
        echo ""
        echo "启动 Jupyter Notebook..."
        jupyter notebook notebooks/
        ;;
    6)
        echo ""
        echo -e "${YELLOW}警告: 这将删除所有已下载的数据${NC}"
        read -p "确认重新初始化？(yes/n): " confirm
        if [ "$confirm" = "yes" ]; then
            echo "清理数据..."
            rm -rf qlib_data/
            rm -rf data/emotion
            rm -rf logs/*.log logs/*.txt
            echo -e "${GREEN}✓ 清理完成${NC}"
            echo "请重新运行此脚本进行初始化"
        else
            echo "已取消"
        fi
        ;;
    0)
        echo "退出"
        exit 0
        ;;
    *)
        echo -e "${RED}无效选项${NC}"
        exit 1
        ;;
esac

echo ""
echo -e "${GREEN}完成！${NC}"
