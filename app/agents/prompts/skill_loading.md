# Skill Loading Prompt

## Layer 1: Skill 摘要（始终注入 system prompt）

```
## Available Skills

你可以使用以下 skill 来完成用户的需求：

- **batch-rename**: 批量重命名文件，支持按前缀/后缀/序号/日期/正则命名
- **duplicate-cleaner**: 查找和清理重复文件
- **file-organizer**: 按文件类型或日期整理文件到不同目录
- **system-monitor**: 检查系统状态，包括 CPU、内存、磁盘使用情况

**重要规则：**
- 当用户的需求匹配以上某个 skill 的描述时，你应该在回复中说明你正在使用该 skill
- 然后按照该 skill 的工作流程执行操作
- 如果用户需求不匹配任何 skill，正常回复即可，不要强行使用 skill
- 同一个需求可能匹配多个 skill，选择最相关的一个
```

## Layer 2: Skill 完整指令（匹配后按需注入）

```
## Active Skill: {skill_name}

你已激活 skill `{skill_name}`，请严格按照以下指令执行：

### Instructions
{skill 的完整指令内容}

### Parameters
{skill 的参数列表}

请根据以上指令，使用你的工具完成用户的请求。
```

## 匹配机制说明

Claude Code 的 skill 匹配 **不是** 通过工具调用实现的，而是：

1. **启动时**：扫描 `.claude/skills/` 目录，解析所有 skill 的 YAML frontmatter
2. **Layer 1**：将所有 skill 的 `name + description` 注入 system prompt
3. **LLM 自行判断**：LLM 在处理用户输入时，看到 skill 描述，自行判断是否需要激活
4. **Layer 2**：匹配后，将该 skill 的完整 instructions 追加到 system prompt
5. **执行**：LLM 按照 skill 的 instructions 使用工具完成任务

### 为什么这样设计
- **减少 token 消耗**：不是所有 skill 的完整内容都始终在上下文中
- **提高匹配精度**：LLM 先看简短描述判断是否需要，再看详细指令执行
- **无需额外工具**：不需要 skill_match 之类的工具，LLM 天然具备语义理解能力

## Skill 文件格式

### 单文件格式（Claude Code 原生）
```
.claude/skills/
  batch-rename.md
  duplicate-cleaner.md
```

每个 `.md` 文件：
```markdown
---
name: batch-rename
description: 批量重命名文件，支持按前缀/后缀/序号/日期/正则命名
version: "1.0.0"
author: assistant
---

# Instructions
1. 先用 glob 工具找到目标目录下所有文件
2. 根据用户需求确定命名模式
3. 生成预览：旧名称 → 新名称的映射
4. 让用户确认后执行重命名

# Parameters
- folder_path: string (required) - 目标目录路径
- mode: string (required) - 命名模式
```

### 目录格式（扩展，支持脚本）
```
.claude/skills/
  batch-rename/
    SKILL.md
    scripts/
      renamer.py
```
