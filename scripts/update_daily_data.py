#!/usr/bin/env python3
"""
更新 qlib 数据：从 investment_data GitHub releases 下载最新数据
支持全量更新，自动下载、解压并覆盖到 qlib_data/cn_data
每天: python update_daily_data.py
"""

import time
import argparse
import tarfile
import requests
import shutil
from pathlib import Path

# ============ 配置 ============
DEFAULT_QLIB_DIR = Path.home() / "GolandProjects/stock/qlib_data/cn_data"
GITHUB_REPO = "chenditc/investment_data"
DOWNLOAD_DIR = Path.home() / "GolandProjects/stock/.cache"


# ================================================================
#  工具函数
# ================================================================
def load_calendar(qlib_dir):
    """读取 calendar 文件"""
    cal_file = Path(qlib_dir).expanduser() / "calendars" / "day.txt"
    if not cal_file.exists():
        return [], {}
    dates = [line.strip() for line in cal_file.read_text().strip().split("\n") if line.strip()]
    return dates, {d: i for i, d in enumerate(dates)}


# ================================================================
#  从 GitHub releases 下载数据
# ================================================================
def get_latest_release_info():
    """获取最新 release 的信息"""
    url = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"
    print(f"📡 检查最新 release...")
    
    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        data = response.json()
        
        tag_name = data["tag_name"]
        assets = data.get("assets", [])
        
        # 查找 qlib_bin.tar.gz 文件
        download_url = None
        for asset in assets:
            if "qlib_bin.tar.gz" in asset["name"]:
                download_url = asset["browser_download_url"]
                break
        
        if not download_url:
            print("❌ 未找到 qlib_bin.tar.gz 文件")
            return None, None
        
        print(f"✅ 最新版本: {tag_name}")
        return tag_name, download_url
    
    except Exception as e:
        print(f"❌ 获取 release 信息失败: {e}")
        return None, None


def download_file(url, save_path):
    """下载文件并显示进度"""
    print(f"⬇️  开始下载...")
    print(f"    URL: {url}")
    
    try:
        response = requests.get(url, stream=True, timeout=30)
        response.raise_for_status()
        
        total_size = int(response.headers.get('content-length', 0))
        save_path.parent.mkdir(parents=True, exist_ok=True)
        
        with open(save_path, 'wb') as f:
            downloaded = 0
            start_time = time.time()
            last_print = 0
            
            for chunk in response.iter_content(chunk_size=8192):
                if chunk:
                    f.write(chunk)
                    downloaded += len(chunk)
                    
                    # 每 10MB 显示一次进度
                    if downloaded - last_print >= 10 * 1024 * 1024 or downloaded == total_size:
                        percent = downloaded / total_size * 100 if total_size > 0 else 0
                        speed = downloaded / (time.time() - start_time) / 1024 / 1024
                        print(f"    进度: {percent:.1f}% ({downloaded / 1024 / 1024:.1f}MB / {total_size / 1024 / 1024:.1f}MB) - {speed:.2f}MB/s")
                        last_print = downloaded
        
        print(f"✅ 下载完成: {save_path}")
        return True
    
    except Exception as e:
        print(f"❌ 下载失败: {e}")
        if save_path.exists():
            save_path.unlink()
        return False


def extract_tar_gz(tar_path, extract_to):
    """解压 tar.gz 文件"""
    print(f"📦 解压中...")
    
    try:
        extract_to.mkdir(parents=True, exist_ok=True)
        
        with tarfile.open(tar_path, 'r:gz') as tar:
            # 获取解压后的根目录名（通常是 qlib_bin）
            members = tar.getmembers()
            if not members:
                print("❌ 压缩包为空")
                return None
            
            # 提取根目录名
            root_dir = members[0].name.split('/')[0]
            print(f"    根目录: {root_dir}")
            
            # 解压所有文件
            tar.extractall(extract_to)
            
            print(f"✅ 解压完成")
            return extract_to / root_dir
    
    except Exception as e:
        print(f"❌ 解压失败: {e}")
        return None


def sync_data(source_dir, target_dir):
    """同步数据：将 source_dir 的内容覆盖到 target_dir"""
    print(f"🔄 同步数据...")
    print(f"    源目录: {source_dir}")
    print(f"    目标目录: {target_dir}")
    
    try:
        # 确保目标目录存在
        target_dir.mkdir(parents=True, exist_ok=True)
        
        # 复制所有内容
        for item in source_dir.iterdir():
            target_item = target_dir / item.name
            
            if item.is_dir():
                if target_item.exists():
                    shutil.rmtree(target_item)
                shutil.copytree(item, target_item)
                print(f"      📁 {item.name}/")
            else:
                shutil.copy2(item, target_item)
                print(f"      📄 {item.name}")
        
        print(f"✅ 同步完成")
        return True
    
    except Exception as e:
        print(f"❌ 同步失败: {e}")
        return False


def download_and_update(qlib_dir):
    """下载最新数据并更新"""
    qlib_dir = Path(qlib_dir).expanduser()
    
    # 1. 获取最新 release
    tag_name, download_url = get_latest_release_info()
    if not download_url:
        return False
    
    # 2. 下载到临时目录
    DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)
    download_file_path = DOWNLOAD_DIR / "qlib_bin.tar.gz"
    
    if not download_file(download_url, download_file_path):
        return False
    
    # 3. 解压
    extract_dir = DOWNLOAD_DIR / "extract"
    extracted_path = extract_tar_gz(download_file_path, extract_dir)
    if not extracted_path:
        return False
    
    # 4. 同步到 qlib_dir
    if not sync_data(extracted_path, qlib_dir):
        return False
    
    # 5. 清理所有临时文件
    print("🧹 清理临时文件...")
    if DOWNLOAD_DIR.exists():
        shutil.rmtree(DOWNLOAD_DIR)
    
    print(f"\n✅ 数据更新完成！")
    return True


# ================================================================
#  入口
# ================================================================
def update_daily(qlib_dir=None):
    """
    从 GitHub releases 下载最新数据并更新
    qlib_dir: qlib 数据目录
    """
    qlib_dir = Path(qlib_dir).expanduser() if qlib_dir else DEFAULT_QLIB_DIR
    print("=" * 60)
    print("📦 从 GitHub 下载最新 qlib 数据")
    print("=" * 60)
    print(f"📁 目标目录: {qlib_dir}\n")
    
    success = download_and_update(qlib_dir)
    
    if not success:
        print("\n❌ 更新失败")
        return None
    
    # 读取最新日期
    calendar, _ = load_calendar(qlib_dir)
    if calendar:
        latest_date = calendar[-1]
        print(f"\n✅ 最新交易日: {latest_date}")
        return latest_date
    else:
        print("\n⚠ 无法读取 calendar")
        return None


def main():
    parser = argparse.ArgumentParser(description="从 GitHub 下载最新 qlib 数据")
    parser.add_argument("--qlib-dir", default=str(DEFAULT_QLIB_DIR), 
                        help="qlib 数据目录")
    args = parser.parse_args()

    latest = update_daily(qlib_dir=args.qlib_dir)
    if latest:
        print(f"\n💡 config.yaml end_time 应设置为: {latest}")


if __name__ == "__main__":
    main()
