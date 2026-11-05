# M12 新素材视觉解析流程（本地最小版）

## 自动登记与复用

- 每次生成 M12 时，`weekly_report_module_12.py` 会扫描本次素材，写入同目录 `M12_visual_analysis_queue.json`。
- 以原素材文件 SHA-256 为复用依据。相同文件跨账户、人群复用一份解析；同名但文件变动则重新待解析；找不到原文件时不得冒用同名旧结论。
- 页面显示所选 7 天或近 30 天的“已完成 / 待解析”记录数。待解析不表示 AI 已看过素材。
- 本流程不调用付费模型、不接 Meta 写接口、不自动调整广告。

## 完成一条解析

1. 打开队列里的原文件及可用关键帧，核对画面；视频若无关键帧，应先抽帧或看原视频，不可仅凭文件名写结论。
2. 写结构化 JSON：`status` 为 `complete`，`source` 说明核对范围；`hook`、`core_promise`、`product_solution`、`product_proof`、`trust_proof`、`offer`、`cta`、`content_gap` 每项均有 `time` 与 `evidence`。未见到的内容应明确写“未见”，不要臆测。
3. 运行 `python tools/m12_visual_workflow.py record --queue <M12_visual_analysis_queue.json> --task-id <task_id> --analysis <分析JSON>`。记录前会重新核对文件指纹；原文件变化则拒绝写入。
4. 重新生成 M12，或对已有 payload 运行 `python tools/m12_visual_workflow.py scan --payload <M12_payload.json>` 并重新生成 HTML。线上版还须按仓库 M12 发布门槛打包、部署和校验。

## 当前边界

自动化的是发现、去重、待解析排队、严格复用和页面状态；视觉内容本身仍需 Agent 基于原文件完成。没有后台无人值守的 AI 自动解析任务，也不会把待解析冒充已完成。若今后要完全自动生成解析，需另定模型调用、费用、质检与失败重试规则。
