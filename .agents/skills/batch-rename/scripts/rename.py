import json
import os
import sys
from pathlib import Path

if __name__ == "__main__":
    input_data = json.loads(sys.stdin.read())
    item1 = input_data.get("old_file_list", "")
    item2 = input_data.get("new_file_list", "")
    if not item1 or not item2:
        print(json.dumps({"error": "参数错误"}))
        sys.exit(1)

    old_file_list = json.loads(item1)
    new_file_list = json.loads(item2)

    try:
        for i in range(len(old_file_list)):
            old_path = Path(old_file_list[i]).resolve()
            parent = old_path.parent
            suffix = old_path.suffix
            new_path = Path(new_file_list[i]).resolve()
            new_file_name = new_path.stem

            os.rename(old_file_list[i], f"{str(parent)}/{new_file_name}{suffix}")
            print(0)
    except Exception as e:
        print(json.dumps({"error": str(e)}))
        sys.exit(1)



