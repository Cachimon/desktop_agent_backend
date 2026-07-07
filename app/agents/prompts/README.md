|文件|用途|使用时机|
|---|---|---|
|`system.md`|主系统提示，定义身份、行为规则|始终注入 system prompt|
|`tool_guidelines.md`|所有工具的使用规范|始终注入 system prompt|
|`code_style.md`|代码风格、安全、注释规则|始终注入 system prompt|
|`security.md`|安全规范、HITL 确认流程|始终注入 system prompt|
|`git_safety.md`|Git 操作安全规则|涉及 git 操作时注入|
|`commit_message.md`|Commit 消息格式模板|创建 commit 时注入|
|`pr_description.md`|PR 描述模板和创建流程|创建 PR 时注入|
|`task_agent.md`|子代理行为规范|启动子代理时注入|
|`skill_loading.md`|Skill 两层加载机制说明|含 skill 时注入|
|`human_interaction.md`|人机交互/HITL 确认规范|始终注入 system prompt|
|`review.md`|代码审查维度和输出格式|审查代码时注入|