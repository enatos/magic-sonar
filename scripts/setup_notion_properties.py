"""Script to configure properties for the Notion database."""

import sys
import httpx
from src.config import load_config


def setup_properties():
    config = load_config()
    headers = {
        "Authorization": f"Bearer {config.notion_api_key}",
        "Notion-Version": "2022-06-28",
        "Content-Type": "application/json",
    }

    db_id = config.notion_database_id

    # 1. まず現在のDB情報を取得
    res = httpx.get(f"https://api.notion.com/v1/databases/{db_id}", headers=headers)
    if res.status_code != 200:
        print(f"Error fetching database: {res.status_code} {res.text}")
        return False

    db_data = res.json()
    existing_props = db_data.get("properties", {})
    print(f"Current properties: {list(existing_props.keys())}")

    # 2. プロパティ定義
    # Title プロパティの名前を探す（通常 "Name" や "名前" または "title"）
    title_prop_name = None
    for k, v in existing_props.items():
        if v.get("type") == "title":
            title_prop_name = k
            break

    properties_to_update = {
        "URL": {"url": {}},
        "ステータス": {
            "select": {
                "options": [
                    {"name": "未読", "color": "default"},
                    {"name": "相談したい", "color": "green"},
                    {"name": "検討中", "color": "blue"},
                    {"name": "採用", "color": "purple"},
                    {"name": "今回は不要", "color": "gray"},
                    {"name": "定点観測", "color": "yellow"},
                ]
            }
        },
        "判定種別": {
            "select": {
                "options": [
                    {"name": "タグ一致", "color": "blue"},
                    {"name": "未知枠", "color": "orange"},
                ]
            }
        },
        "マッチタグ": {
            "multi_select": {
                "options": [
                    {"name": "記憶 / AIコンテキスト", "color": "purple"},
                    {"name": "ナレッジ", "color": "blue"},
                    {"name": "ハーネス", "color": "red"},
                    {"name": "ループ", "color": "green"},
                    {"name": "意味グラフ", "color": "pink"},
                    {"name": "実行グラフ", "color": "yellow"},
                    {"name": "個人の情報発信", "color": "orange"},
                ]
            }
        },
        "Star数": {"number": {"format": "number"}},
        "Star日速": {"number": {"format": "number"}},
        "日速種別": {
            "select": {
                "options": [
                    {"name": "計測待ち", "color": "default"},
                    {"name": "暫定", "color": "yellow"},
                    {"name": "確定(7日)", "color": "green"},
                ]
            }
        },
        "観測日数": {"number": {"format": "number"}},
        "概要": {"rich_text": {}},
        "主要言語": {"select": {}},
        "初観測日": {"date": {}},
        "最新観測日": {"date": {}},
        "えり・なびメモ": {"rich_text": {}},
    }

    # 既存のTitleプロパティを「Repo名」にリネーム
    if title_prop_name and title_prop_name != "Repo名":
        properties_to_update[title_prop_name] = {"name": "Repo名"}

    patch_payload = {
        "properties": properties_to_update,
    }

    # 3. PATCHでプロパティを一括反映
    update_res = httpx.patch(
        f"https://api.notion.com/v1/databases/{db_id}",
        headers=headers,
        json=patch_payload,
    )

    if update_res.status_code == 200:
        print("✅ Successfully updated all database properties!")
        updated_data = update_res.json()
        print("Configured properties:", list(updated_data.get("properties", {}).keys()))
        return True
    else:
        print(f"Failed to update properties: {update_res.status_code} {update_res.text}")
        return False


if __name__ == "__main__":
    success = setup_properties()
    sys.exit(0 if success else 1)
