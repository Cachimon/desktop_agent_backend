import json
import sys
import hashlib
from pathlib import Path
from collections import defaultdict


def compute_md5(file_path: str) -> str:
    hash_md5 = hashlib.md5()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            hash_md5.update(chunk)
    return hash_md5.hexdigest()


def find_duplicates(folder_path: str) -> dict:
    base = Path(folder_path)
    if not base.exists() or not base.is_dir():
        return {"error": f"Folder not found: {folder_path}"}

    hash_map = defaultdict(list)

    for item in base.rglob("*"):
        if not item.is_file():
            continue
        try:
            md5 = compute_md5(str(item))
            hash_map[md5].append(str(item))
        except (OSError, PermissionError):
            continue

    duplicates = {md5: paths for md5, paths in hash_map.items() if len(paths) > 1}

    result = {
        "total_files_scanned": sum(len(v) for v in hash_map.values()),
        "duplicate_groups": len(duplicates),
        "duplicates": duplicates,
    }
    return result


def main():
    input_data = json.loads(sys.stdin.read())
    folder_path = input_data.get("folder_path", "")
    action = input_data.get("action", "list")

    result = find_duplicates(folder_path)
    result["action"] = action

    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
