---
name: csv_viewer
description: 读取 CSV 文件并以表格形式显示前 N 行数据。当用户说"查看CSV文件"、"读取CSV"、"显示CSV前几行"、"预览CSV数据"等情况时触发。支持自定义显示行数（默认为 5 行）。
version: "1.0.0"
author: assistant
---

# Instructions

## 功能
读取指定路径的 CSV 文件，解析其内容，并以可读的表格格式显示前 N 行数据。

## 参数
- `file_path`: string (required) — CSV 文件的完整路径
- `rows`: integer (optional, default: 5) — 要显示的行数

## 使用流程
1. 接收用户传入的 `file_path` 和 `rows` 参数
2. 检查文件是否存在
3. 使用 Python 的 `pandas` 或 `csv` 模块读取 CSV 文件
4. 显示前 `rows` 行数据（包括表头），同时展示数据形状（行数、列数）
5. 如果文件不存在或读取失败，返回友好错误提示

## 返回格式
- 成功时：返回包含表头的前 N 行数据，以及数据形状信息
- 失败时：返回错误消息，说明失败原因（如文件未找到、格式错误等）