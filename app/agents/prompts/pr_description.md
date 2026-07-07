# Pull Request Description Prompt

## PR 描述模板

使用 HEREDOC 格式传递 body，确保正确格式化：

```bash
gh pr create --title "the pr title" --body "$(cat <<'EOF'
## Summary
<1-3 bullet points>

## Changes
- <key change 1>
- <key change 2>
- <key change 3>

## Testing
- <how you tested>
- <test commands run>
EOF
)"
```

## 各部分说明

### Summary
- 1-3 个要点，概括 PR 的核心目的
- 聚焦 **为什么** 做这些更改
- 让审查者快速理解 PR 的意图

### Changes
- 列出关键变更
- 包括所有重要的 commit，不只是最新的
- 按逻辑分组，而非按时间顺序

### Testing
- 你是如何测试的
- 运行了哪些测试命令
- 测试结果如何

## PR 创建流程

1. 查看当前分支状态（git status, git diff, git log）
2. 理解从 base branch 分叉以来的所有 commit
3. 分析所有将包含在 PR 中的更改
4. 起草 PR 标题和描述
5. 如果需要，创建新分支并推送
6. 使用 `gh pr create` 创建 PR
7. 返回 PR URL

## 注意事项

- 不要推送远程仓库，除非用户明确要求
- PR 描述应全面覆盖所有相关 commit
- 使用 `gh` 命令处理所有 GitHub 相关任务
- 查看 PR 评论使用 `gh api repos/foo/bar/pulls/123/comments`
