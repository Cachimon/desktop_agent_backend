import json
import sys
import os
import shutil
from pathlib import Path
from datetime import datetime

CATEGORY_MAP = {
    "images": {".jpg", ".jpeg", ".png", ".gif", ".bmp", ".svg", ".webp", ".ico"},
    "documents": {".pdf", ".doc", ".docx", ".txt", ".rtf", ".odt", ".xls", ".xlsx", ".ppt", ".pptx", ".csv"},
    "videos": {".mp4", ".avi", ".mkv", ".mov", ".wmv", ".flv", ".webm"},
    "audio": {".mp3", ".wav", ".flac", ".aac", ".ogg", ".wma", ".m4a"},
    "archives": {".zip", ".rar", ".7z", ".tar", ".gz", ".bz2"},
    "code": {".py", ".js", ".ts", ".html", ".css", ".java", ".cpp", ".c", ".go", ".rs"},
}


def organize_by_type(folder_path: str) -> dict:
    base = Path(folder_path)
    if not base.exists() or not base.is_dir():
        return {"error": f"Folder not found: {folder_path}"}

    results = {"moved": 0, "skipped": 0, "categories_created": [], "errors": []}

    for item in base.iterdir():
        if item.is_dir():
            continue

        ext = item.suffix.lower()
        category = "other"
        for cat, exts in CATEGORY_MAP.items():
            if ext in exts:
                category = cat
                break

        target_dir = base / category
        if not target_dir.exists():
            target_dir.mkdir()
            results["categories_created"].append(category)

        target_path = target_dir / item.name
        if target_path.exists():
            results["skipped"] += 1
            continue

        try:
            shutil.move(str(item), str(target_path))
            results["moved"] += 1
        except Exception as e:
            results["errors"].append(str(e))

    return results


def main():
    input_data = json.loads(sys.stdin.read())
    folder_path = input_data.get("folder_path", "")
    rule_type = input_data.get("rule_type", "type")

    if rule_type == "type":
        result = organize_by_type(folder_path)
    else:
        result = {"error": f"Rule type '{rule_type}' not yet implemented"}

    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
