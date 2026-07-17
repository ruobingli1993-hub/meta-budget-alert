# 广告投放自动化 V1 项目看板

## 当前状态

- 飞书通知链路 P0 验证已完成。
- 周报自动化 V1 核心开发和 W27 真实数据文件验收已完成，等待业务复核内容与版式。
- Budget Alert 已监控三个账户，并提供只读 Debug。
- Budget Alert 当前为“有条件通过、上线观察”，真实自然触发后的告警送达尚待验证。
- Dashboard V1 作为详情查看和审批记录入口。
- 尚未执行任何真实预算 Apply。

## 最近完成

- 完成 Budget Alert 与 Morning、Daily Close、Early Pulse 三类定时报告的 GitHub Actions 验证。
- 完成三个账户的 Budget Alert 真实只读检查。
- 完成飞书摘要与 Dashboard 详情分离。
- 完成项目文档治理，建立根目录协作规范和单一当前任务文档。
- 使用真实 Google、BI、Meta 样例和只读 Meta API 生成三份 W27 周报产物。
- 素材报告只包含两个指定 Performance 账户，共 63 条有消耗广告；Brand 未进入素材报告。

## 当前唯一任务

完成并交付周报自动化 V1。

- 状态：开发完成，等待业务验收
- 目标：基于真实 Meta 数据生成包含账户表现和 Creative Analysis 的可交付周报。
- 范围：3 个账户分层呈现；Performance 与 Brand 使用不同指标口径。
- 输入：真实 Google 主表、Google 转化明细、BI 数据、Meta 国家/人群样例和历史人工周报已准备。
- 口径：真实日期跨平台拼接；Google Purchase、Meta人群标签和All Clicks漏斗率规则已冻结。
- 安全要求：只读分析；禁止真实预算 Apply。

详细步骤和验收标准见 `CURRENT_TASK.md` 与 `WEEKLY_REPORT_V1_REQUIREMENTS.md`。

## 当前阻塞

- GitHub Actions 可能延迟 8 小时以上，不能作为本周周报交付的唯一入口。
- Brand 账户长期周报口径和 Creative Analysis 判断阈值需要“03”确认；确认前只输出客观数据和相对排名。

## 下一步

打开并复核 W27 的三份真实输出文件，确认内容与版式是否可以交付。

## 安全状态

- 飞书只发送摘要，Dashboard 保存详情。
- 预算调整继续保持 Preview → Approval → Apply。
- 未经明确确认，不执行预算调整、暂停或创建广告。
