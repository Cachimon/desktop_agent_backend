---
name: clipboard_transport
description: 在应用程序之间传输数据，支持文本、文件路径、图片等数据类型。当用户说"把数据从A传到B"、"复制内容到剪贴板"、"在应用间传输文件"、"把这段文字发到另一个应用"等情况时触发。支持剪贴板操作和基于文件的传输两种方式。
version: "1.0.0"
author: AI Assistant Team
---

# Instructions

## 功能
在不同应用程序或文件位置之间传输数据，支持文本、文件路径和图片三种数据类型。

## 使用流程
1. 接收用户传入的 `source`、`target`、`data_type` 等参数
2. 验证源和目标路径是否有效
3. 根据数据类型选择传输方式：
   - `text`: 直接传输文本内容
   - `file_path`: 复制或移动文件
   - `image`: 传输图片文件
4. 执行传输操作
5. 返回传输结果

## Parameters
- `source`: string (required) — 源应用程序名称或文件路径
- `target`: string (required) — 目标应用程序名称或文件路径
- `data_type`: enum[text|file_path|image] (required) — 要传输的数据类型
- `content`: string (optional) — 直接传输的文本内容（仅 text 类型使用）

## 返回格式
- 成功时：返回传输结果确认信息
- 失败时：返回错误消息，说明失败原因（如源不存在、目标不可达等）
