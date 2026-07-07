# Git Safety Guidelines

## 核心规则

### 绝对禁止
- **绝不更新 git config** - 不要修改用户的 git 配置
- **绝不运行破坏性 git 命令** - 如 push --force, hard reset 等，除非用户明确要求
- **绝不跳过 hooks** - 不要使用 --no-verify, --no-gpg-sign 等参数
- **绝不 force push 到 main/master** - 即使用户要求，也要警告
- **避免 git commit --amend** - 仅在以下条件全部满足时才使用：
  1. 用户明确要求 amend，或者 commit 成功但 pre-commit hook 自动修改了文件
  2. HEAD commit 是本次对话中你创建的（验证：git log -1 --format='%an %ae'）
  3. commit 尚未推送到远程（验证：git status 显示 "Your branch is ahead"）
- **如果 commit 失败或被 hook 拒绝，绝不 amend** - 修复问题后创建新的 commit
- **如果已经推送到远程，绝不 amend** - 除非用户明确要求（需要 force push）

### 重要原则
- **绝不提交更改，除非用户明确要求** - 这非常重要，只在明确要求时才提交
- 如果没有更改需要提交，不要创建空 commit

## 提交流程

### 创建 Commit 的步骤
1. 运行 `git status` 查看未跟踪文件
2. 运行 `git diff` 查看已暂存和未暂存的更改
3. 运行 `git log` 查看最近的 commit 消息，了解仓库的 commit 风格
4. 分析所有更改，起草 commit 消息
5. 添加相关的未跟踪文件到暂存区
6. 创建 commit
7. 运行 `git status` 验证成功

### Commit 消息格式
- 聚焦 "why" 而非 "what" - 说明为什么做这个修改
- 1-2 句话，简洁明了
- 确保消息准确反映更改及其目的
- 使用以下关键词：
  - "add" - 全新功能
  - "update" - 增强现有功能
  - "fix" - 修复 bug
  - "refactor" - 代码重构
  - "test" - 测试相关
  - "docs" - 文档相关

### 文件安全
- 不要提交可能包含 secrets 的文件（.env, credentials.json 等）
- 如果用户要求提交此类文件，发出警告

## 推送规则

- 不要推送到远程仓库，除非用户明确要求
- 推送前确认所有更改已正确提交
- 如果推送失败，不要自动重试，与用户确认

## 分支操作

- 不要使用 -i 标志（如 git rebase -i），因为需要交互输入
- 创建 PR 时使用 `gh` 命令
- 检查当前分支是否跟踪远程分支并保持同步
