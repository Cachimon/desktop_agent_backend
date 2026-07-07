# Commit Message Prompt

## 格式要求

- 聚焦 **why** 而非 **what** - 说明为什么做这个修改，而不是做了什么
- 1-2 句话，简洁明了
- 确保消息准确反映更改及其目的

## 关键词

| 关键词 | 用途 |
|--------|------|
| `add` | 全新功能 |
| `update` | 增强现有功能 |
| `fix` | 修复 bug |
| `refactor` | 代码重构 |
| `test` | 测试相关 |
| `docs` | 文档相关 |
| `chore` | 构建/工具/依赖变更 |
| `perf` | 性能优化 |

## 示例

### 好的 commit 消息
```
add user authentication with JWT tokens
fix memory leak in connection pool by closing idle connections
update error handling to provide more actionable messages
refactor data processing pipeline for better testability
```

### 不好的 commit 消息
```
update code                          # 太模糊，没说为什么
fix bug                              # 哪个 bug？怎么修的？
changes                              # 完全没有信息
add feature requested by product     # 什么 feature？
WIP                                  # 不应提交 WIP
```

## 注意事项

- 不要提交可能包含 secrets 的文件
- 如果 commit 失败或被 hook 拒绝，修复问题后创建新的 commit，不要 amend
- 如果没有更改需要提交，不要创建空 commit
