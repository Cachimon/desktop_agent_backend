import json
import shutil
import sys
from pathlib import Path


def transport_file(source: str, target: str) -> dict:
    src = Path(source)
    tgt = Path(target)

    if not src.exists():
        return {"error": f"Source not found: {source}"}

    if src.is_file():
        if tgt.is_dir():
            tgt = tgt / src.name
        shutil.copy2(str(src), str(tgt))
        return {
            "status": "success",
            "operation": "file_copy",
            "source": str(src),
            "target": str(tgt),
            "size": src.stat().st_size,
        }

    if src.is_dir():
        if tgt.exists() and tgt.is_dir():
            tgt = tgt / src.name
        shutil.copytree(str(src), str(tgt))
        file_count = sum(1 for _ in tgt.rglob("*") if _.is_file())
        return {
            "status": "success",
            "operation": "directory_copy",
            "source": str(src),
            "target": str(tgt),
            "file_count": file_count,
        }

    return {"error": f"Unsupported source type: {source}"}


def transport_text(content: str, target: str) -> dict:
    tgt = Path(target)

    try:
        tgt.parent.mkdir(parents=True, exist_ok=True)
        tgt.write_text(content, encoding="utf-8")
        return {
            "status": "success",
            "operation": "text_write",
            "target": str(tgt),
            "size": len(content.encode("utf-8")),
        }
    except Exception as e:
        return {"error": str(e)}


def transport_image(source: str, target: str) -> dict:
    src = Path(source)
    tgt = Path(target)

    image_exts = {
        ".jpg",
        ".jpeg",
        ".png",
        ".gif",
        ".bmp",
        ".svg",
        ".webp",
        ".tiff",
        ".ico",
    }
    if src.suffix.lower() not in image_exts:
        return {"error": f"Not an image file: {source}"}

    if not src.exists():
        return {"error": f"Source not found: {source}"}

    if tgt.is_dir():
        tgt = tgt / src.name

    try:
        shutil.copy2(str(src), str(tgt))
        return {
            "status": "success",
            "operation": "image_copy",
            "source": str(src),
            "target": str(tgt),
            "size": src.stat().st_size,
        }
    except Exception as e:
        return {"error": str(e)}


def main():
    input_data = json.loads(sys.stdin.read())
    source = input_data.get("source", "")
    target = input_data.get("target", "")
    data_type = input_data.get("data_type", "file_path")
    content = input_data.get("content", "")

    if not source and not content:
        print(json.dumps({"error": "source or content is required"}))
        sys.exit(1)

    if not target:
        print(json.dumps({"error": "target is required"}))
        sys.exit(1)

    if data_type == "text" and content:
        result = transport_text(content, target)
    elif data_type == "image":
        result = transport_image(source, target)
    else:
        result = transport_file(source, target)

    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
