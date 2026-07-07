#!/usr/bin/env python3
"""
csv_viewer skill — 读取 CSV 文件并显示前 N 行数据
"""
import json
import sys
import os
import csv
import traceback
from io import StringIO


def format_table(headers, rows, max_col_width=50):
    """将数据格式化为对齐的表格字符串"""
    if not rows:
        return "(空数据)"

    # 计算每列宽度
    col_widths = []
    for i, h in enumerate(headers):
        col_data = [str(h)] + [str(r[i]) if i < len(r) else "" for r in rows]
        max_len = max(len(c) for c in col_data)
        col_widths.append(min(max_len, max_col_width))

    # 分隔线
    separator = "+" + "+".join("-" * (w + 2) for w in col_widths) + "+"

    # 表头行
    header_cells = []
    for i, h in enumerate(headers):
        header_cells.append(f" {str(h).ljust(col_widths[i])} ")
    header_line = "|" + "|".join(header_cells) + "|"

    # 数据行
    data_lines = [header_line, separator]
    for row in rows:
        cells = []
        for i in range(len(headers)):
            val = str(row[i]) if i < len(row) else ""
            if len(val) > max_col_width:
                val = val[:max_col_width - 3] + "..."
            cells.append(f" {val.ljust(col_widths[i])} ")
        data_lines.append("|" + "|".join(cells) + "|")

    return "\n".join([separator] + data_lines + [separator])


def csv_viewer(file_path: str, rows: int = 5) -> dict:
    """
    读取 CSV 文件并显示前 rows 行数据。

    Args:
        file_path: CSV 文件路径
        rows: 要显示的行数（默认 5）

    Returns:
        dict: 包含状态和数据的字典
    """
    # 检查文件是否存在
    if not os.path.exists(file_path):
        return {
            "status": "error",
            "message": f"文件未找到: {file_path}"
        }

    if not file_path.lower().endswith('.csv'):
        return {
            "status": "error",
            "message": f"文件不是 CSV 格式: {file_path}"
        }

    try:
        # 尝试使用 csv 模块读取
        with open(file_path, 'r', encoding='utf-8') as f:
            # 读取前几行来判断分隔符
            sample = f.read(4096)
            f.seek(0)

            sniffer = csv.Sniffer()
            try:
                dialect = sniffer.sniff(sample)
                delimiter = dialect.delimiter
            except csv.Error:
                delimiter = ','  # 默认逗号分隔

            reader = csv.reader(f, delimiter=delimiter)
            all_data = list(reader)

        if not all_data:
            return {
                "status": "error",
                "message": "CSV 文件为空"
            }

        headers = all_data[0]
        data_rows = all_data[1:]
        total_rows = len(data_rows)
        total_cols = len(headers)

        # 取前 N 行
        show_rows = min(rows, total_rows)
        display_data = data_rows[:show_rows]

        # 格式化表格
        table = format_table(headers, display_data)

        return {
            "status": "success",
            "message": f"成功读取文件: {file_path}",
            "data": {
                "shape": f"{total_rows} 行 × {total_cols} 列",
                "total_rows": total_rows,
                "total_cols": total_cols,
                "display_rows": show_rows,
                "headers": headers,
                "preview": display_data,
                "table": table
            }
        }

    except UnicodeDecodeError:
        try:
            # 尝试其他编码
            with open(file_path, 'r', encoding='gbk') as f:
                reader = csv.reader(f)
                all_data = list(reader)

            if not all_data:
                return {"status": "error", "message": "CSV 文件为空"}

            headers = all_data[0]
            data_rows = all_data[1:]
            show_rows = min(rows, len(data_rows))
            display_data = data_rows[:show_rows]
            table = format_table(headers, display_data)

            return {
                "status": "success",
                "message": f"成功读取文件 (GBK编码): {file_path}",
                "data": {
                    "shape": f"{len(data_rows)} 行 × {len(headers)} 列",
                    "total_rows": len(data_rows),
                    "total_cols": len(headers),
                    "display_rows": show_rows,
                    "headers": headers,
                    "preview": display_data,
                    "table": table
                }
            }
        except Exception as e2:
            return {
                "status": "error",
                "message": f"读取 CSV 失败 (尝试 UTF-8 和 GBK 编码均失败): {str(e2)}"
            }

    except Exception as e:
        return {
            "status": "error",
            "message": f"读取 CSV 文件失败: {str(e)}",
            "detail": traceback.format_exc()
        }


def main():
    """从 stdin 读取 JSON 输入并执行"""
    try:
        input_data = json.loads(sys.stdin.read())
        file_path = input_data.get("file_path", "")
        rows = input_data.get("rows", 5)

        if not file_path:
            result = {"status": "error", "message": "缺少必填参数 file_path"}
        else:
            result = csv_viewer(file_path, rows)

        print(json.dumps(result, ensure_ascii=False))

    except json.JSONDecodeError:
        print(json.dumps({
            "status": "error",
            "message": "输入格式错误，需要 JSON 格式"
        }, ensure_ascii=False))
    except Exception as e:
        print(json.dumps({
            "status": "error",
            "message": f"执行失败: {str(e)}"
        }, ensure_ascii=False))


if __name__ == "__main__":
    main()