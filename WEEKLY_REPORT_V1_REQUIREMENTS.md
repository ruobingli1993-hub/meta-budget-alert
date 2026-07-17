# 周报自动化 V1｜冻结需求与开发计划

## 1. 业务目标

将每周 Meta 素材整理、Meta/Google/BI 拼接、人群与国家分析的人工时间压缩到 30 分钟以内。V1 允许人工下载 Google 两份报表和 BI 一份报表，不追求完全无人值守。

## 2. 输入

- Meta：复用项目现有只读数据能力，读取账户、Campaign、Ad Set、Ad、Creative、素材标识、缩略图、状态、广告指标、人群和国家拆分。
- Google 主表：提供 Customer ID、Campaign ID、Campaign Type、日期、花费、展示和点击。
- Google 转化明细：提供真实 Purchase 和 Purchase Value，不承担花费。
- BI：提供渠道、国家、销售额、订单、营销花费、ROI、支付转化率及历史周/月/年数据。
- 映射：账户、Google 转化操作、Meta 人群标签和报表规则。

## 3. 冻结口径

### 日期

- 周期为 Sunday-Saturday。
- W27 = 2026-07-05 至 2026-07-11。
- W27 仅为业务展示标签。Meta、Google、BI 一律按真实日期匹配，禁止使用平台自动 Week Number 连接。

### BI

- 整体 Meta 使用 `Meta投放流量`。
- 整体 Google 使用 `GOOGLE投放流量`。
- Google 细分渠道只用于拆解，不与总渠道再次相加。

### Google

- `Google Shopping App Purchase (2)`：计入 Purchase 和 Purchase Value。
- `Google Shopping App Page View (2)`、view_item、浏览时间、进入网站：不计入 Purchase 和 Purchase Value。
- Purchase CVR = 真实 Purchase / Clicks。
- Purchase ROAS = Purchase Value / Spend。
- 主表花费只能累计一次，不能因连接转化操作明细而重复。
- Demand Gen 且 Campaign 名称含 `_Brand` → GOOGLE付费YOUTUBE。
- 其他 Demand Gen → GOOGLE付费探索广告。
- Shopping → GOOGLE付费购物广告。
- Search 且名称含 `brand` → GOOGLE付费品牌词。
- Search 且名称含 `product` → GOOGLE付费品类词。
- Performance Max → GOOGLE付费PMAX。
- 无法匹配的新 Campaign 进入复核清单。

### Meta 人群

- `prospecting` → 新客。
- `engaged` → 新客；定义为有互动但过去 730 天未购买。
- `existing` → 老客/再营销；定义为过去 730 天已购买。
- `uncategorized` / `unknown` → 未识别。
- 混合 Campaign 允许同时产生新客和老客数据，不强制把整个 Campaign 归为单一人群。

### Meta 漏斗

- Purchase CVR = Purchase / All Clicks。
- Add to Cart Rate = Add to Cart / All Clicks。
- Checkout Rate = Begin Checkout / All Clicks。
- 报告必须标注 All Clicks 口径。
- 分母为零或缺失时显示不可用，不显示 0%。

### 目标与总结

- 新客 ROAS 3、老客/再营销 ROAS 3.5 仅为待 03 确认的内部参考。
- V1 不输出“未达标”等结论。
- 在规则确认前，只用中性语言说明花费、订单、ROAS、CVR 等变化。
- 不自动输出放量、降预算、停投或更换素材。

## 4. 输出

周报只生成本地文件，不发送飞书消息。

### Weekly_Report.xlsx

至少包含：Overview、Week to Week、Month to Date、渠道/账户表现、Google真实购买、BI对比、Meta人群、Meta国家、数据说明。

### Creative_Report.html

只覆盖以下两个 Performance 账户在报告期内所有有消耗广告：QMDT—20240103 / `750289240467952`，销售三部—新主页账户 / `5600626876733411`。按 Account → Campaign → Ad Set → Ad 组织，各层按花费降序。展示缩略图、状态、Creative ID、可用的 Video ID / Image Hash、指标、匹配方式、匹配置信度和复核状态。Brand 账户不进入素材报告。

### Review_Required.xlsx

至少包含：未识别素材、复杂/多尺寸素材、未识别人群、未知 Google 转化操作、无法匹配的 Google Campaign、BI 映射问题、输入异常和动作待审核项。

## 5. 开发优先级

1. 输入发现与字段校验。
2. 真实日期周期与业务周标签。
3. Google 真实 Purchase 清洗和 BI 拼接。
4. Weekly_Report.xlsx 核心表。
5. Meta 人群与国家表。
6. Meta 全量消耗广告素材清单和基础 HTML。
7. Review_Required.xlsx。
8. 真实数据端到端验收。

如时间不足，先保证 Excel 核心周报、Google Purchase 和复核清单；缩略图相似度、多尺寸素材拆分和展示美化不得阻塞交付。

## 6. 验收标准

- 三份人工输入放入固定目录后，可一次运行生成三份输出。
- W27 精确读取 2026-07-05 至 2026-07-11，跨平台合并不受 Week Number 差异影响。
- Google主表花费与源文件一致，连接转化明细后不重复。
- Page View 等非购买操作不计入 Purchase。
- BI总渠道与Google细分渠道不重复累计。
- Meta人群标签按冻结映射正确汇总，未知标签进入复核。
- 三个Meta漏斗率均以All Clicks为分母。
- 两个指定 Performance 账户中所有报告期有消耗 Meta 广告进入素材报告；Brand 账户不进入素材报告。
- 无法匹配项不丢失，全部进入复核清单。
- 缺失数据不当作零。
- 不执行任何Meta写操作。
- 不调用飞书 Webhook，不发送飞书消息。
- 人工整理和审核时间不超过30分钟。

## 7. 暂不处理

- Google API、BI API。
- 自动修改预算。
- 缩略图相似度自动匹配。
- 多尺寸/灵活素材100%拆分。
- 品牌素材基因分析。
- 完全无人值守。
- 强动作建议和自动策略结论。
