# 广告投放自动化 V1 项目看板

## 当前状态

- 飞书通知链路 P0 验证已完成。
- Budget Alert 已监控三个账户，并提供只读 Debug。
- Dashboard V1 作为详情查看和审批记录入口。
- 当前没有正在进行的 P0 开发。
- 尚未执行任何真实预算 Apply。

## 最近完成

- 完成 Budget Alert 与 Morning、Daily Close、Early Pulse 三类定时报告的 GitHub Actions 验证。
- 完成三个账户的 Budget Alert 真实只读检查。
- 完成飞书摘要与 Dashboard 详情分离。
- 完成项目文档治理，建立根目录协作规范和单一当前任务文档。

## 当前唯一任务

完成 Budget Alert 运营验证。

- 状态：待开始
- 负责人：Ruobing（运营确认）／Codex（只读技术协助）
- 目标：逐账户核对余额、7 日平均花费、预计可用天数、阈值和去重判断。
- 安全要求：只运行只读 Debug；禁止真实预算 Apply。

详细步骤和验收标准见 `CURRENT_TASK.md`。

## 当前阻塞

- 没有阻塞任务开始的技术问题。
- 运营验证需要人工登录 Meta 后台，对照三个账户的真实数据。

## 下一步

运行只读 Budget Alert Debug，并完成逐账户运营核验。

## 安全状态

- 飞书只发送摘要，Dashboard 保存详情。
- 预算调整继续保持 Preview → Approval → Apply。
- 未经明确确认，不执行预算调整、暂停或创建广告。
