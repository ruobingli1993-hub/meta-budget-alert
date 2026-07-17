# 广告投放自动化 V1 协作规范

## 项目目标

本项目通过 Meta Marketing API 读取广告账户数据，生成预算预警、定时报告和预算调整预览，并通过 Dashboard 支持人工复核。V1 的默认行为是只读分析和预览，不自动修改真实广告。

## 安全边界

- 所有高风险操作必须遵循“先预览、再审批、后执行”。
- 未经用户针对具体运行和具体变更的明确确认，不得调整预算、暂停广告、创建广告、创建 Campaign、创建 Ad Set 或创建 Ad。
- 不得把 Dashboard 中的 Approve 视为真实执行授权；真实执行仍需单独、明确确认。
- 数据缺失、冲突、样本不足、权限异常或 Meta API 失败时，默认 `NO_CHANGE`。
- 未经明确授权，不得运行 `--budget-manager-apply`；不得用含糊确认替代命令要求的精确确认。
- 飞书只发送摘要，详细指标、审批记录、原因和审计信息保存在 Dashboard 或本地审计文件中。
- 不得在代码、文档、终端输出、日志、提交信息或聊天中泄露 Meta Token、飞书 Webhook、GitHub 凭据或包含密钥的完整 URL。

## 开发流程

1. 开始前读取 `PROJECT_CONTEXT.md`、`AI_MEMORY.md`、`PROJECT_STATUS.md`、`CURRENT_TASK.md`、`PROJECT_DASHBOARD.md`、`CHANGELOG.md` 和相关 README。
2. 检查 Git 状态，保留用户已有修改；不得覆盖、回滚或提交无关改动。
3. 只执行当前任务授权范围内的工作。广告写操作不属于普通开发或验证步骤。
4. 对代码修改执行与风险相称的测试；对文档修改至少执行 `git diff --check`。
5. 每次开发任务完成后，必须同步更新 `PROJECT_STATUS.md`、`PROJECT_DASHBOARD.md` 和 `CHANGELOG.md`；当前任务变化时同时更新 `CURRENT_TASK.md`。
6. 默认不提交、不推送，除非用户明确要求。

## 真实广告操作

- Preview 可以生成建议，但不能修改真实预算。
- Approval 只表示人工审核结果，不自动触发 Apply。
- Apply 必须绑定明确的 `RUN_ID`，并获得用户对该次执行的明确确认。
- 执行后必须验证最终状态并保留审计记录；出现异常时停止后续写操作。
