# 快速入门

## 一、发 Issue
1. 在本仓库 **Issues → New issue** 新建 Issue，写清目标、范围和验收标准。
2. 在正文中 `@fuyuan-agent` 提及代理；代理会在同一 Issue 下回复结果或 PR 链接。

## 二、在 Harness 客户端看工单
1. 打开 DeepSeek Harness Web（本机 `http://127.0.0.1:3083`）。
2. 进入侧边栏 **Superagent** 面板的 **执行** 页签，按状态查看工单；点开可看触发、授权与执行记录。
3. **概览** 页集中显示待处理的工单。

## 三、审查 PR
1. 从 Issue 回复或 GitHub **Pull requests** 打开 PR，先读说明，再在 **Files changed** 查看改动。
2. 有问题在对应行留言或 Request changes；确认无误后 Approve。
3. 合并由人决定；需要时用 `gh pr checkout <编号>` 在本地验证。

## 四、没收到工单怎么办
1. 确认 Issue 正文包含 `@fuyuan-agent`，且发送者有仓库权限；提交后在同一 Issue 下等代理回复。
2. 在 **Superagent** 面板查 **概览** 的待处理工单和 **执行** 的工单列表，并确认 **来源** 页的 GitHub 来源已开启、无报错。
