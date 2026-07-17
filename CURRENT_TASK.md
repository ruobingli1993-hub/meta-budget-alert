# 当前任务

## 状态摘要

- 当前唯一 P0：周报自动化 V1。
- 开发状态：核心实现和 W27 真实数据文件验收已完成，等待业务打开产物复核内容与版式。
- 原因：本周必须交付周报，交付时点优先于原 Roadmap 顺序。
- Budget Alert 转为“已完成只读与运行链路验证，真实触发待生产观察”，不再阻塞周报。
- GitHub Actions 严重延迟登记为未解决风险，按独立可靠性计划处理。

## P0 目标

自动生成一份可以直接用于业务汇报的广告周报。周报只生成本地文件，不发送飞书消息；必须明确数据周期、账户范围、核心表现和素材表现，数据不足时必须如实标记，不能把缺失数据当作零。

本次重新设计的核心不是重复制作数据透视表，而是将以下高耗时工作自动化：

1. Meta 全量消耗广告的素材整理、指标匹配和异常复核。
2. Meta、Google 与 BI 数据拼接及统一口径。
3. Meta 新客/老客和国家表现分析。

目标是将每周人工整理与审核时间压缩到 30 分钟以内。

## 周报自动化 V1 范围

1. 使用完整 Sunday-Saturday 周期，并在报告中显示明确起止日期。W27 对应 2026-07-05 至 2026-07-11；内部周标签只用于展示，跨平台拼接必须使用真实日期，不使用平台 Week Number。
2. 覆盖当前配置的 3 个账户，其中 2 个 Performance 账户与 1 个 Brand 账户分开呈现。
3. 读取 Google 广告表现主表、Google 转化操作明细和 BI 原始报表，并输出输入校验与未匹配清单。
4. 整体渠道表现直接使用 BI 的 `Meta投放流量` 和 `GOOGLE投放流量`，Google 细分渠道不得与总渠道重复相加。
5. Google 仅将 `Google Shopping App Purchase (2)` 计入真实 Purchase 和 Purchase Value；所有 Page View / view_item / 浏览时间 / 进入网站操作均不计入 Purchase。
6. 输出整体花费与账户级核心指标。
7. Performance 账户展示 Purchase、Revenue、ROAS、CPA、CTR。
8. Brand 账户展示 Spend、Reach、Impressions、Frequency、CTR；不使用 Purchase ROAS 判断其健康状态。
9. Meta 人群映射固定为：`prospecting` / `engaged` = 新客，`existing` = 老客/再营销，`uncategorized` / `unknown` = 未识别。
10. Meta Purchase CVR、Add to Cart Rate 和 Checkout Rate 均使用 All Clicks 作为分母；分母为零或缺失时显示不可用。
11. Creative Analysis 只覆盖 QMDT—20240103 / `750289240467952` 和销售三部—新主页账户 / `5600626876733411` 两个 Performance 账户中报告期内所有有消耗广告；Brand 账户不进入素材报告。输出层级、缩略图、素材标识、指标、匹配方式和复核状态。
12. 生成 `Weekly_Report.xlsx`、`Creative_Report.html` 和 `Review_Required.xlsx`。
13. 支持人工立即生成，定时触发不是本次交付的前置条件。

## 明确不包含

- 不调整真实预算，不暂停、创建或修改广告。
- 不开发 Budget Apply、Google Ads 或新的 Dashboard 能力。
- 不建立复杂 AI 策略或自动优化闭环。
- 不因 GitHub Actions 调度问题阻塞人工生成和交付本周周报。
- 不把 Brand 账户按 Purchase、Revenue、ROAS 与 Performance 账户做同一健康判断。

## 需要 03 确认

- Brand 账户是否长期纳入周报，以及它的业务目标和健康指标。
- Creative Top/Bottom 的最低花费、最低展示量和排序指标。
- Performance 账户的 ROAS/CPA 状态阈值和结论措辞。
- 国家机会/风险判断的数据门槛。
- 动作建议的最低样本、观察周期和触发规则。

当前内部参考目标为新客 ROAS 3、老客/再营销 ROAS 3.5。在 03 确认前，目标不得用于“未达标”等负面总结，也不得用于自动输出放量、降预算、停投或更换素材。V1 使用中性语言描述客观变化。

## 验收标准

- 可以人工触发并生成一份真实周报。
- 报告明确显示数据起止日期、生成时间和账户时区口径。
- 3 个账户均有结果；单账户失败时其他账户仍正常输出并明确标记失败账户。
- Performance 与 Brand 使用不同指标口径。
- Creative Analysis 的每个排名都能追溯到素材名称/ID和对应数据。
- 缺失数据展示为不可用，不展示为 0。
- 周报不调用飞书 Webhook，不发送飞书消息。
- 不执行任何 Meta 写操作，不修改真实广告预算或状态。
- 本周能够基于真实数据完成一次实际交付。

## Budget Alert 暂定状态

- 已通过：真实只读数据读取、阈值计算、去重逻辑测试、手动 GitHub Actions 运行和非触发场景。
- 尚未通过：真实账户进入告警范围后的端到端飞书告警送达。
- 当前结论：有条件通过，上线观察；不得声称完整生产验收通过。
- 生产观察通过条件：首次自然进入阈值后，30 分钟内完成检查并发送一次正确告警；消息数据正确，24 小时内不重复轰炸；持续低余额满 24 小时后允许再次提醒。
- 生产观察失败条件：应告警未告警、错误账户/金额、异常重复、任务漏跑且无补偿、或数据异常被当作正常结果。
- 不允许为了制造告警而修改真实预算、阈值、账户配置或状态文件。

## GitHub Actions 调度风险

- 状态：未解决。
- 已知现象：计划任务可能延迟 8 小时以上。
- 产品目标：从计划时间到检查完成不超过 30 分钟。
- 详细止血与迁移计划见 `SCHEDULING_RELIABILITY_PLAN.md`。

## 本轮开发验收记录

- 真实输入：`C:\Users\shzhe\Desktop\Weekly_Report_V1_Input`。
- 输出目录：`outputs/weekly_report/W27-live`。
- 已生成：`Weekly_Report.xlsx`、`Creative_Report.html`、`Review_Required.xlsx`。
- 三个 Meta 账户均有账户级结果；Brand 使用 Reach、Impressions、Frequency、CTR，不使用 Purchase ROAS。
- 素材报告共 63 条，仅包含两个指定 Performance 账户：QMDT—20240103 56 条，销售三部—新主页账户 7 条。
- Google 共 96 个 Campaign；未知转化操作 0，无法映射 Campaign 0。
- 复核项为 4 条 Meta 未识别人群；未发现素材或账户读取错误。
- 真实生成耗时约 57 秒；未调用飞书，未执行任何 Meta 写操作。
