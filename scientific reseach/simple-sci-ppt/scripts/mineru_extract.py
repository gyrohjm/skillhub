import requests
import time
import os
import zipfile
import io
import json
import argparse
from pathlib import Path

# --- 基础配置 ---
# 配置文件路径（与脚本同目录，已被 .gitignore 忽略，不会提交到 GitHub）
_CONFIG_PATH = Path(__file__).parent / "mineru_config.json"


def _load_config():
    """加载配置文件（如果存在）。"""
    if _CONFIG_PATH.exists():
        with open(_CONFIG_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


_CONFIG = _load_config()

# Token 读取顺序：环境变量 MINERU_API_TOKEN > 配置文件 mineru_config.json > 报错
TOKEN = os.environ.get("MINERU_API_TOKEN") or _CONFIG.get("token", "")
if not TOKEN:
    print("错误：未找到 MinerU API Token。")
    print("请通过以下方式之一配置：")
    print("  1. 设置环境变量 MINERU_API_TOKEN")
    print("  2. 在 scripts/mineru_config.json 中填写 token 字段")
    print("     （参考 scripts/mineru_config.example.json）")
    raise SystemExit(1)

BASE_URL = os.environ.get("MINERU_BASE_URL") or _CONFIG.get("base_url", "https://mineru.net/api/v4")
HEADERS = {
    "Content-Type": "application/json",
    "Authorization": f"Bearer {TOKEN}"
}

def download_and_extract(zip_url, original_path, output_root):
    """下载解析包并解压，保持 MD 和图片文件夹结构"""
    folder_name = original_path.stem
    final_path = output_root / folder_name
    final_path.mkdir(parents=True, exist_ok=True)

    try:
        r = requests.get(zip_url, timeout=30)
        if r.status_code == 200:
            with zipfile.ZipFile(io.BytesIO(r.content)) as zip_ref:
                zip_ref.extractall(final_path)
            print(f"  [√] 结果保存至: {final_path}")
        else:
            print(f"  [×] 下载压缩包失败: {r.status_code}")
    except Exception as e:
        print(f"  [×] 解压过程出错: {e}")

def process_single_file(file_path, output_dir, model_version="vlm"):
    """处理单个文件的完整生命周期"""
    file_path = Path(file_path)
    if not file_path.exists():
        print(f"文件不存在: {file_path}")
        return

    print(f"\n>>> 正在处理: {file_path.name}")

    # 1. 申请上传链接
    apply_payload = {
        "files": [
            {
                "name": file_path.name,
                "data_id": f"idx_{int(time.time())}",
                "is_ocr": True
            }
        ],
        "model_version": model_version,
        "language": "en", # 默认英文
        "enable_formula": True,
        "enable_table": True
    }

    try:
        resp = requests.post(f"{BASE_URL}/file-urls/batch", headers=HEADERS, json=apply_payload)
        res_data = resp.json()
        if res_data.get("code") != 0:
            print(f"  [×] 接口申请失败: {res_data.get('msg')}")
            return

        batch_id = res_data["data"]["batch_id"]
        upload_url = res_data["data"]["file_urls"][0]

        # 2. 上传文件
        with open(file_path, 'rb') as f:
            up_resp = requests.put(upload_url, data=f)
            if up_resp.status_code != 200:
                print("  [×] 文件上传至云端失败")
                return

        # 3. 轮询结果
        print(f"  [i] 任务提交成功 (BatchID: {batch_id})，等待解析...")
        check_url = f"{BASE_URL}/extract-results/batch/{batch_id}"

        while True:
            time.sleep(5)
            status_resp = requests.get(check_url, headers=HEADERS)
            status_data = status_resp.json()

            # 获取第一个文件的处理状态
            result_info = status_data["data"]["extract_result"][0]
            state = result_info["state"]

            if state == "done":
                zip_url = result_info.get("full_zip_url")
                download_and_extract(zip_url, file_path, output_dir)
                break
            elif state == "failed":
                print(f"  [×] 解析失败: {result_info.get('err_msg')}")
                break
            else:
                print(f"  [.] 当前状态: {state}...", end="\r")

    except Exception as e:
        print(f"  [! ] 程序运行异常: {e}")

def main():
    parser = argparse.ArgumentParser(description="MinerU PDF 批量解析工具")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("-f", "--file", type=str, help="单个 PDF 文件路径")
    group.add_argument("-d", "--dir", type=str, help="包含 PDF 的文件夹路径")

    parser.add_argument("--limit", type=int, default=100, help="文件夹模式下的最大处理文件数 (默认 100)")
    parser.add_argument("-m", "--model", type=str, default=_CONFIG.get("model_version", "vlm"), choices=["vlm", "pipeline"], help="使用模型版本")
    parser.add_argument("-o", "--output", type=str, default=_CONFIG.get("output_root", r"D:\yychen\MinerU\output"), help="输出根目录")

    args = parser.parse_args()
    output_root = Path(args.output).resolve()

    if args.file:
        process_single_file(args.file, output_root, args.model)

    elif args.dir:
        dir_path = Path(args.dir)
        # 使用 pathlib 扫描所有 pdf (忽略大小写)
        pdf_files = list(dir_path.glob("*.pdf")) + list(dir_path.glob("*.PDF"))

        # 限制数量
        process_list = pdf_files[:args.limit]
        print(f"找到 {len(pdf_files)} 个文件，计划处理前 {len(process_list)} 个。")

        for f in process_list:
            process_single_file(f, output_root, args.model)

if __name__ == "__main__":
    main()