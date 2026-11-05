# Changelog

## 2026-11-05｜GitHub Actions云端影子扫描联调

### Changed
- 写飞书从旧webhook方式改为直接写多维表格：新建 `tools/write_recommendations.py`，用飞书自建应用tenant token直接调bitable API写审批表。
- `analyzer.py` 第111-118行：webhook失败不报错，影子扫描本身算成功。

### Fixed
- 修复dataclass不能用`.get()`的AttributeError：改用`getattr()`属性访问。
- 补全飞书审批表28个字段映射：账户、实体层级、预算层级、冷却状态、规则版本、扫描日期、数据快照、总预算检查。
- 补回近7天完整日数据窗口：analyzer.py新增`last_7_complete_days`取数，BudgetRecommendation加7天字段（spend/purchase/roas），数据快照从只写3天ROAS升级为"7天完整表现 + 3天ROAS + 今天漏斗"。

### Known Issues
- 新链路`analyzer.py`只取了近3天/今天/近30天均值，丢了之前旧脚本的**近7天完整日**窗口，待补。
- "决策"字段select选项不全（只有INCREASE_15），其他档位（INCREASE_10/20/25）会报错，待在表里补选项。
- 写完表后缺飞书消息通知，待实现。

## 2026-10-27｜NO_CHANGE 理由说人话：讲清"为什么没达标却不动"

- 修 `human_reason()`：原 NO_CHANGE 只写「→ 暂不调整」，审批人看不懂。现按 shadow-v0.2 规则如实写：近3天弱但昨天回到达标线→「避免单日波动误判，先观察」；近3天在目标95%缓冲→保持观察；ROAS 不可确认→数据不足。
- 4 条 10/26 NO_CHANGE 记录理由已回写。审批侧实测：3 条减预算全部被审批人「已拒绝」，拒绝留档 Workflow 自动写好执行结果。未真调 Meta。

## 2026-10-27｜跑最新影子扫描（数据日 10/26），3 条减预算进待审批

- 重跑 `run_adjustment_shadow_v1.py`（只读，meta_write_calls=0）：7 条建议 = 0 加 / 3 减 / 4 不动，已推「调价审批」表。
- 3 条 DECREASE 进「待审批」：QMDT FB-Daily-CBO $270→$216（-20%）、销售三部 new-creative $100→$80（触地板）、销售三部 bau $250→$200；4 条 NO_CHANGE 标「不调整」留档。
- 修 `human_reason()` 文案 bug：原对加/减都硬写「近3天 ROAS…均达标」，与减预算结论矛盾；现按目标如实标 达标/未达，加减分别说明「跑赢加量/跑输收缩」，3 条待审批理由已回写。
- 待审批记录已带 Meta对象ID + 预算层级（CBO改campaign/ABO改adset），为将来真实执行就绪。未真调 Meta。

## 2026-10-27｜真实调价执行端就绪：外部 Worker 方案拍板，代码干跑待命

- 用户拍板：影子→真实走**外部 Cloudflare Worker**（非飞书内置 HTTP 节点），并确认已有带 ads_management 权限的长期 token。
- Base 「调价审批」表新增 3 个字段：Meta对象ID（fldawL7PlW）、预算层级（fldbjNbKqe：CBO/ABO）、广告账户ID（fldyeq9xi1）。`tools/shadow_to_base.py` 已写入这些字段——CBO 改 campaign、ABO 改 adset，真实执行端据此定位 Meta 对象。
- 新增 `cloudflare_executor/`（src/index.js + wrangler.toml + README runbook）：审批同意→Worker 执行，内置共享密钥校验、KV 幂等、$80 地板/$2500 上限/单次≤50% 门禁、执行前 GET 实时预算重检。**默认 DRY_RUN=true，未部署、未真调 Meta**。
- 上线 runbook 见 `cloudflare_executor/README.md`：先本地干跑单实体演练，确认 Meta 预算真实变动后再翻 DRY_RUN=false 并把飞书 Workflow 的 SetRecordAction 换成 HTTPClientAction。
- 未部署 Worker、未翻真调开关、未修改任何线上预算。

## 2026-10-27｜补齐拒绝/过期分支，清理影子测试残留（仍影子阶段）

- 清理 Base 残留：1 条 NO_CHANGE/「不调整」记录残留了 10/26 端到端测试的「影子执行」结果与执行时间，已清空；现 5 条 NO_CHANGE 全部「不调整」无执行痕迹，2 条 INCREASE「已执行」结果完整。
- 新增并启用云端 Workflow「审批拒绝自动留档」（workflow_id `wkf8AydgZawspPEq`）：审批状态变「已拒绝」→ 自动在执行结果写「审批拒绝：{实体}，不执行预算调整（影子留档，未调用 Meta）」，不改状态、不写执行时间。定义件 `approval_workflow_reject_shadow.json`。
- 端到端实测拒绝分支：建临时记录→待审批→改已拒绝→拒绝 Workflow 自动写结果，且同意 Workflow 不误触发（状态保持已拒绝、未变已执行），测试记录已删除，表回到 7 条。
- `tools/shadow_to_base.py` 增加过期分支：每次新扫描推表时，把仍挂「待审批」但扫描日期早于本轮的旧建议自动标「已过期」并留档（审批人只看最新一批，不会拿隔夜建议批）；过期回写先于写入新建议。选择逻辑已单测（跨日待审批→过期；同日待审批/旧已同意/旧已执行→不动）。
- 未真调 Meta，未改任何线上预算。

## 2026-10-26｜审批流改版：只审有调整的，理由写成业务人话

- 按用户反馈改版审批流：只有 INCREASE/DECREASE（有预算调整动作）进入「待审批」；NO_CHANGE 不再进审批，审批状态改标「不调整」（select 新增该选项），留档供复盘决策对错，审批人无需操作。
- 决策理由从规则黑话改为人话模板：近7天花费/购买/ROAS（含目标与达标/未达）、昨日 ATC率/结账率、健康/冷却状态、结论（建议 ±幅度与前后金额 / 暂不调整原因）。模板固化进 `tools/shadow_to_base.py`（`human_reason()` + `approval_status_for()`），后续新扫描自动套用。
- 存量 7 条记录已全部刷新：5 条 NO_CHANGE →「不调整」+ 新理由；2 条 INCREASE（已执行）仅理由更新。回读验证通过。Workflow「审批同意自动影子执行」不受影响（仅监听「已同意」，不调整/已执行均不触发）。

## 2026-10-26｜「自动盯」改为飞书 Base 云端 Workflow（审批同意→自动影子执行）

- 用户否决本机计划任务方案（关机/周末必须照常跑），改用飞书 Base 内置自动化 Workflow：云端 24/7、审批状态一变即触发，不依赖本机。
- 新建并启用 Workflow「审批同意自动影子执行」（workflow_id `wkfuqxfuMfKUIkIq`）：`ChangeRecordTrigger` 监听「调价审批」表，条件＝审批状态 is 已同意；`SetRecordAction` 回写审批状态→已执行、执行时间→now、执行结果→自动拼接（实体/当前预算/建议预算/决策/幅度% + 「未调用 Meta（影子验证）」）。
- 端到端实测：将 1 条 NO_CHANGE 记录改为「已同意」→ workflow 自动流转为「已执行」并写入执行时间/执行结果，其余待审批记录不受影响；测试记录随后恢复为「待审批」。Workflow 定义件保留为 `approval_workflow_shadow.json`。
- 关键设计：写回「已执行」后不满足触发条件，不会循环触发；真实 Meta 调价仍留待 HTTP/预算模块接入（影子阶段不真调）。

## 2026-10-26｜预算自动化·飞书调价审批（影子阶段闭环）

- 新建「调价审批」多维表格（26 字段）＋「审批看板」kanban 视图（按审批状态分组）＋「调价审批看板」仪表盘（4 指标卡＋账户柱状图＋状态饼图＋实体 Top5，共 7 组件，布局与 get-data 全验收通过）。
- 写入 9/27 影子扫描 7 条建议（2 INCREASE / 5 NO_CHANGE）；新增 `tools/shadow_to_base.py`（影子 JSON→写表，按建议ID幂等去重，实测 7 条全跳过）。
- 新增 `tools/poll_approval_shadow.py`（轮询已同意→影子执行→回写已执行＋执行结果＋执行时间；--real 预留未启用）。
- 端到端影子验证闭环：模拟审批 2 条 INCREASE 为「已同意」→ 轮询脚本影子执行（$120→$144、$180→$207）→ 回写「已执行」；5 条 NO_CHANGE 保持「待审批」；仪表盘联动正确（待审批 7→5、已执行 0→2）。未真调 Meta。
- 关键教训：批量更新 record_id 必须以 record-list 回读的真实 ID 为准（`reczz28RxmhSnNLe` 等 17 位），抄录/拼接 ID 会被 API 校验拒绝；中文 payload 一律由 Python 生成 UTF-8 无 BOM 文件，勿经 PowerShell 内联。

## 2026-10-25｜W42 M11/M12 素材核验与分类修复

- 重建 W42 M11/M12，补回 QMDT 广告表现；M12 44 个素材对象／周 Spend $10,263.52，M11 52 条有花费广告／51 个素材组。
- M11/M12 视频封面改用登记关键帧或 GIF 第一帧，避免将方形素材片尾当首图；42/43 个视频组已匹配真实首帧，剩余 1 个缺源 TOFU 按用户确认暂不解析但保留表现。
- M12 低花费新素材分类固定为首投日期已确认、首投不足 7 天且所选周期花费 <$100；首版可确认首投日期为 0，经用户补充确认后修订为 5 条；首投不确定或满 7 天的低花费素材仍归“需要关注”。
- 31 项 M11/M12 单元测试通过；用户明确授权后已发布 W42 缩略图版至固定 Pages 地址并验证成功；未上传原视频、未修改 Meta、未提交或推送。
- 按用户补充确认将 5 条 W42 新上线、周 Spend<$100 的素材归入“首投不足7天且花费<$100”；周 Spend $102.77 的同期素材未满足门槛，仍列“需要关注”。修订版已重新发布并通过固定链接校验。
- 进一步纠正分类依据：按用户澄清，“不足7天”指 Meta 广告上线时间，不是首次花费时间。M12 现在保存广告 `created_time` 并按同素材最早上线日期分类；W42 核对 7 条近期上线素材后，5 条花费<$100进入新素材观察区，$102.77 与 $163.49 两条仍因达到 $100 门槛留在“需要关注”。
- 修复 W42 页面“数据不足／尚未跑出”旧栏目名与新分类数据键不一致导致栏数为 0 的问题；栏目名已统一为“首投不足7天且花费<$100”，重建文件后应显示 5 条。

## 2026-10-11｜W40 周报与 Meta 国家数据流程

- 新增周报工作流文档，明确 M09 由 Meta 只读 API 获取三个 Performance 账户的 country breakdown，旧国家导出表不是必需输入；同步更新需求和 Roadmap。
- W40 已生成 M01–M11；M02 按用户确认对单日 BI 空结果做运行时零值处理，未修改源表。M09 三账户国家数据读取和对账通过。
- M12 与线上同步尚未完成；未修改广告或预算，未提交或推送。

## 2026-10-10｜M12 在投素材映射核对

- 新增只读核对工具：比较三账户有效在投广告、素材登记表、M12 快照及截止日前后花费，不读取或输出密钥，不执行 Meta 写入。定位 1 条有花费未映射和 1 条截止日前有花费未入旧快照；未修改业务数据。

## 2026-10-09｜素材表现库首图修复

- 增加离线首图补齐工具；按账户、人群、素材名及素材家族／原视频核实后，补齐 25 张缺失图片，重建截至 10 月 7 日本地页面。未重算或改写逐日指标。

## 2026-10-09｜M12 三栏分类校准

- 修正低于 $1 的正花费在卡片上被四舍五入为 $0 的误导显示，修正三栏标题中旧复用门槛与数据不足说明。
- 合并 0918-3L 素材在销售三部账户的 W38 与后续补数两段不重叠日期；本地展示一行，总指标不变。
- 更新复用／关注／数据不足规则，补充首投日期不确定时的保守归类。
- 新增本地快照重算工具，修复 7 天与 30 天有效投放天数，并重建截至 10 月 7 日本地页面；17 项单元测试通过。
- 未部署、未提交、未推送、未修改 Meta。

## 2026-10-09

- M12：新增素材视觉解析队列、SHA-256 指纹缓存、变更与缺源防误复用、结构化解析入库命令和页面完成/待解析计数；补充测试及流程文档。
- M12：修复 Ad Name 路由词差异导致的登记表漏匹配；按原视频/JPG 校正截至 10 月 7 日的两条素材，并合并同素材重复记录。105 条素材家族记录全部有视觉解析；总 Spend、Purchase、Purchase Value 不变。

## 2026-09-28｜调整建议中控今日影子扫描

- 新增 `tools/run_adjustment_shadow_v1.py`，按冻结的 `shadow-v0.2` 规则只读扫描三个Performance账户；输出当前预算、D0、近3天（含D0）、账户近7天、冷却期、预算门禁与版本化影子记录。
- 首次手动扫描产生7条记录（减预算候选2、加预算候选0、NO_CHANGE 5），并写入本地工作台的“今日影子（只读）”入口。扫描结果明确为影子观察，`meta_write_calls: 0`；未发送飞书、未修改广告、预算或账户设置。
- 修复 `打开本地调价工作台.cmd` 启动失败：改用已验证的 PowerShell 启动器，页面与今日影子数据均可由本机 `127.0.0.1` 读取；不向外网提供访问。
- 改进本地工作台首页指引：清楚说明今日影子阶段无需审批或操作，并新增直达今日影子结果的入口；未修改广告、预算或扫描规则。
- 修正当前影子扫描的日期口径：默认只使用广告账户最近完整日，近3天/近7天不再自动混入未开始或未完成日期。9/28首次开放日结果作废；已按9/25–9/27重算，结果为加预算候选2、减预算候选0、NO_CHANGE 5；未修改广告、预算或账户设置。

## 2026-09-27｜模块04双订单/AOS口径冻结

- W38模块04的Meta与Google投放流量表已补入平台订单量和平台AOS，并保留BI订单量/AOS并列展示。
- 冻结后续生成门槛：平台订单量固定取Purchase，平台AOS固定取Purchase Value ÷ Purchase；两张表缺任一BI/平台订单或AOS字段、或缺WoW时不得标记完成。未修改广告或预算。

## 2026-09-27｜W38模块12线上同步与发布门槛

- 已将W38模块12缩略图版部署至固定链接 `https://jelenew-m12-weekly.pages.dev/`，并核验HTTP 200、W38页面内容及“查看拆解”入口。
- 冻结后续发布门槛：本地M12完成后必须自动打包、部署并校验固定链接；线上版不含原始视频，本地版保留原始视频。未修改广告或预算。

## 2026-09-24｜周报产能保护线（文档）

- 新增全项目Token/上下文安全边际：固定周报交付为每周日15:00（北京时间），每周五15:00起自动升为唯一P0；复杂非周报任务在交付前保留至少40%可用额度并设置停止点。
- 本次仅更新协作治理文档；未修改代码、广告、预算、部署、提交或推送。

## 2026-09-24｜低人工跟进项目推进协议（文档）

- 新增`TASK_CARD_OPERATING_PROTOCOL.md`，定义任务卡字段、六种状态、资源锁、静默/通知规则、验收包、角色边界、示例卡与一周试运行指标。
- 本次仅新增协作治理文档；未修改代码、广告规则、广告状态、预算、部署、提交或推送。

## 2026-09-18｜定时调价系统 P0 调度规则（文档）

- 确认北京时间08:00、21:00两次只读扫描；真实执行后24小时冷却，拒绝/未执行不锁死当日晚间复评。
- 明确08:00为美国前一日接近结束的高峰数据窗口，21:00为美国新日趋势/转化高峰窗口；两者均为调价评估窗口，需标注日内数据覆盖范围。
- 明确 Alert 系统为独立 Backlog，不混入定时调价；未修改广告、预算、飞书、提交、推送或部署。

## 2026-09-17｜调整建议中控 V1｜受控线上审批骨架

- 新增 Cloudflare Worker + D1 的受控审批骨架：Access JWT 校验、会话、只读决策读取与人工决定写入；没有 Meta 写操作或预算执行路由。
- 新增独立 Decision Ledger Schema 和静态工作台打包脚本；源代码语法及 Asset 构建通过。
- 未创建 Cloudflare Access/D1 资源、未部署、未发送飞书、未修改广告或预算。

## 2026-09-17｜调整建议中控 V1｜静态 / 影子 Dashboard 界面

- 将旧静态 Demo 升级为 Overview + 建议审阅两层工作台，覆盖两账户合计日预算 / $2,500、整体指标、四组趋势、完整指标表、账户模式覆盖、待审排序、同意/拒绝和已审历史。
- 所有页面数值为固定影子示例；同意/拒绝只更新浏览器内状态，不读取 Meta、不执行预算、不修改既有审批存储。
- 新增字段与验收说明，以及因内置浏览器阻止本地文件截图而记录的视觉 QA blocker；未修改广告、预算、飞书、提交、推送或部署。

## 2026-09-17｜调整建议中控 P1 手机审批与执行路线（文档）

- 新增影子验收后的手机审批/执行路线：飞书跳转、手机审阅、单条二次确认、执行前重检、执行后飞书回执和异议复盘。
- 本次仅更新产品与项目管理文档；未修改业务代码、广告、预算、飞书、提交、推送或部署。

## 2026-09-17｜调整建议中控 V1 Dashboard产品设计（文档）

- 确认 Dashboard 为 Overview + 建议审阅两层：整体趋势/指标比较在 Overview，Campaign/Ad Set 的建议理由与人工决定在审阅页。
- 确认同意/拒绝、强制拒绝理由、审一条少一条、已审历史，以及广告调整工作台/广告上新仅为规划入口。
- 本次仅更新产品与项目管理文档；未修改业务代码、广告、预算、飞书、提交、推送或部署。

## 2026-09-17｜调整建议中控 V1 影子规则确认（文档）

- 记录用户确认的只读影子规则：双 Performance 账户、CBO Campaign／ABO Ad Set、加减预算与 `NO_CHANGE`、账户模式建议、24小时冷却、$10最小调整、$80预算地板和合计每日$2,500上限。
- 下一步仅为28天历史回放；未修改代码、广告、预算、飞书、提交、推送或部署。

## 2026-09-11｜调整建议中控 V1 盘点与静态Demo

- 新增只读盘点与静态Demo，包含一条建议、一条数据健康 `NO_CHANGE` 和一条过期建议，全部使用固定模拟值。
- 未新增建议规则、影子运行、Meta读取/写入、审批流程变更或Dashboard重构。

## 2026-09-11｜调整建议中控 V1 产品Roadmap（文档）

- 新增`ADJUSTMENT_CONTROL_CENTER_V1_ROADMAP.md`：定义现有Dashboard内的只读建议、NO_CHANGE门禁、Decision Ledger、28天历史回放、14天前向影子与单次Apply前门槛。
- 记录模块13保持独立周报模块，只可提供候选输入，不能形成执行入口。
- 本次仅产品与项目管理文档更新；未修改代码、广告、预算、飞书、提交、推送或部署。

## 2026-09-06｜W35逐模块刷新

- 用户要求自动跑完并逐模块交付；W35为2026-08-30至2026-09-05，模块01—12 HTML已生成于outputs/weekly_report/W35/modules。
- 模块03使用临时运行入口，2025趋势延伸W52；Google NonBrand W45因11月2日缺YouTube/探索渠道行保留N/A并标记复核，不修改冻结生成器。
- 模块10为37素材、57广告；花费/购买数对齐，QMDT Purchase Value差0.01美元保留原复核。模块11缺素材国家Breakdown，保留提示。
- 模块12为45对象，复用22项历史拆解、23项待视觉核对；本地链接版已打包，6个超过25MB视频未包含，未发布线上。
- 回归74项中72通过；旧M03测试缺trend_end_week参数，旧M05测试缺Google Spend Share字段。未擅改冻结模板或用例。
- 未修改广告、未发送飞书、未commit/push。下一步为数据缺口与素材拆解复核，不得声称全部内容已验收。

## 2026-08-30 - Module 05 W34 current-week spend share accepted and frozen

- Added the current W34 spend share beside each Google detailed-channel title while retaining the weekly spend-share table column.
- Recorded user acceptance and froze this layout for subsequent weekly refreshes.
- No advertising write, budget change, Feishu send, commit, push, or deployment was performed.

## 2026-08-20 - Module 12 W32 final acceptance and publication

- Recorded final user acceptance and freeze of Module 12; this is the acceptance and publication record, not a new business-rule revision.
- Published the validated W32 output containing 40 unique material objects (25 Video, 15 Picture) and 40/40 structured analyses to the existing read-only Cloudflare Pages site.
- Verified the stable public URL returns HTTP 200 and contains the W32 Module 12 structure: `https://jelenew-m12-weekly.pages.dev/`.
- Modules 01–12 remain frozen. No advertising state, budget, Feishu delivery, commit, or push was performed.

## 2026-08-12 - Module 12 W31 phase-one rebuild (local only)

- Rebuilt Module 12 around Creative/Asset ID aggregation with W31 seven-day and trailing-30-day real Meta data.
- Added Account × prospecting/retargeting benchmarks, effective-spend-day gates, minimum-volume protection, one delivery status, up to three performance labels, and one structured insight per asset.
- Limited video metrics to 3-second play rate, 50% retention, and 95% completion; retained all raw numerators and denominators used by calculated metrics.
- Reused the material registry, extracted frames, and creative-library catalog to achieve 26/26 local previews without new Meta screenshots.
- Generated standalone HTML, reconciliation workbook, and JSON payload. No frozen module, ad, budget, Feishu workflow, deployment, commit, or push was changed.

## 2026-08-12 - Anti-silo review gate (documentation only)

- Added project-level triggers requiring a 05 external-solution review before potentially duplicative or disproportionately heavy implementation.
- Added a shared review queue with statuses, submission fields, 05 findings, and final user decision fields.
- No business code, report output, advertising state, budget, automation schedule, deployment, commit, or push was changed.

## 2026-08-11 - Module 12 W31 first delivery (local only)

- Added a reusable Module 12 generator and tests for the standalone video creative breakdown.
- Generated the W31 HTML for 16 spending video assets, with local previews, available timelines, reviewed mappings, and explicit review items.
- Missing video-view fields remain N/A with reasons. No ad write, budget change, Feishu send, commit, push, or deployment was performed.

## 2026-08-11 - Temporary BI AOS YoY chart (local only)

- Generated a standalone Meta + Google BI weekly AOS comparison for W14–W31 using aggregated Sales / Orders.
- Did not modify or overwrite frozen Module 03. No advertising write, commit, push, or deployment was performed.

## 2026-08-11 - Module 05 W31 enhancement accepted and frozen

- Recorded user acceptance after adding BI UV, Google Clicks, two-week ROAS estimates, and compact two-line target labels.
- Shopping and Category Search use target 1.5; Brand Search uses target 6; PMAX remains without a configured target.
- Module 05 is frozen again. No advertising write, budget change, Feishu send, commit, push, or deployment was performed.

## 2026-08-11 - Module 05 two-week delayed ROAS estimate (local only)

- Added `2 Week ROAS = Platform ROAS × (1.6 / 1.44)` immediately after Platform ROAS for Shopping, Brand Search, Category Search, and PMAX.
- Kept Demand Gen/Discovery and YouTube unchanged with no new column.
- Regenerated the real W31 Module 05 output and added tests for the formula and four-channel display boundary.
- No advertising write, budget change, Feishu send, commit, push, or deployment was performed.

## 2026-08-10 - Module 11 W31 reuse accepted; module remains frozen

- Revalidated the frozen Module 11 against W31 (2026-08-02 through 2026-08-08) instead of the original W30 acceptance dataset.
- Reread the updated creative registry and regenerated the real W31 output: 53 spending ads, 26 creative assets, zero missing images, and zero low-resolution images.
- Confirmed the module remains reusable through report-week and date parameters with no W30/W31 period hard-coding.
- User accepted and froze the complete module. No advertising write, budget change, Feishu send, commit, push, or deployment was performed.

## 2026-08-09 - Module 11 accepted and frozen

- Recorded user acceptance of the compact W30 Creative Detail HTML and its complete report-level PNG download.
- Frozen Module 11 structure, metrics, 80×80 previews, merged hierarchy, current-status column, and single full-report download behavior.
- This is a status-only update; no report logic, advertising data, Meta write, budget change, Feishu send, commit, push, or deployment was performed.

## 2026-08-09 - Module 11 full-table export and compact layout (local only)

- Top-aligned merged Campaign and Ad Set labels.
- Replaced the horizontal-scroll layout with fixed compact columns while retaining all metrics and 80×80 previews.
- Added one report-level PNG download and generated the complete 73-ad W30 table as a 2125×6854 image; no account-level download buttons were added.
- No Meta write, advertising or budget change, Feishu send, commit, push, or deployment was performed.

## 2026-08-09 — Module 11 hierarchy/status revision

- Overwrote the W30 Module 11 output with merged Campaign and Ad Set cells.
- Restricted displayed creative type to Video/Picture and retained all 73 spending-ad rows with 80×80 images.
- Added the final Active/Paused column from a read-only Meta API status check (25 Active, 48 Paused).
- Kept the generator period-driven through required week/start/end arguments; no W30 dates were hard-coded.
- No Meta write, advertising/budget change, Feishu send, commit, push, or deployment was performed.

## 2026-08-06 — Module 11 W30 Creative Detail first delivery

- Added a reusable, explicit-period Module 11 generator and generated the W30 standalone HTML.
- Preserved all 73 spending ads across both Performance accounts and organized them as Account → Campaign → Ad Set → Creative with Spend-descending ordering at every level.
- Reused 69 local creative images without collapsing associated ad records; all image references resolve and use 80×80 contain-mode previews.
- Marked creative-level country breakdown as pending instead of substituting account-level country totals.
- Updated Module 10 previews to 80×80 and compacted its table typography at the user's request.
- Passed 11 focused Module 10/11 tests. No Meta write, advertising change, Feishu send, commit, push, or deployment was performed.

## 2026-08-06 — Module 10 frozen with documented reconciliation exception

- User accepted and froze Module 10 with the five existing creative-attribution reconciliation differences explicitly retained for later review.
- Set Module 11 Creative Detail Performance as the next module; no report logic, Meta data, advertising state, deployment, commit, or push was changed in this status update.

## 2026-08-05 — Module 10 W30 Creative Overview first delivery

- Added W29-to-W30 change display beneath every Module 10 creative metric using fresh read-only Meta data; changes are signed, two-decimal, direction-colored, and emphasized at an absolute 30% threshold.
- Replaced the two missing Sales-account video placeholders with local 1-second square frames. Module 10 now has 31/31 local creative images.
- Normalized Module 10 creative media types to Video or Picture only (22 Video, 9 Picture); Meta delivery labels such as Flexible/Unknown are no longer shown as media types.
- Replaced the undersized FeelFree-training cached thumbnail with its complete local MP4 frame at 1 second so it displays consistently with other creative previews.
- Standardized all reusable Module 10 creative thumbnails to a 60×60 px contain-mode box; local source frames remain square and are not stretched or cropped.
- No Meta write, advertising change, Feishu send, commit, push, or deployment was performed.

- Added a reusable Module 10 generator and focused aggregation tests.
- Generated the W30 standalone creative-overview HTML and formula-driven reconciliation workbook.
- Aggregated 73 spent Performance ads into 35 account-by-creative rows using the local creative mapping and square-preview library; excluded Brand.
- Preserved six missing-image creatives as placeholders and review items instead of dropping rows.
- Recorded five reconciliation differences against frozen Module 06; the module remains pending Level-1 data acceptance and is not frozen.
- No Meta write, ad/budget change, Feishu send, commit, push, or deployment.

## 2026-08-05 — Modules 01–09 reusable report-period parameters

- Removed stale W29/W30, fixed-date, and fixed-year defaults from the nine standalone Weekly Report module generators.
- Required explicit report-period arguments at each command entry point to prevent accidental reuse of old-week data.
- Made Module 03 chart years, week endpoint, headings, legends, and coverage text dynamic.
- Preserved all frozen business definitions, structure, and visual presentation.
- Passed 47 unit tests and syntax checks; Modules 01–03 also regenerated successfully for both W29 and W30 in temporary output.
- Modules 04–05 correctly rejected the currently discovered Google input because required date coverage is missing; no invalid report was generated.
- No Meta write, ad/budget change, Feishu send, commit, push, or deployment.

## 2026-08-05 — Module 09 W30 acceptance verification

- Verified the existing W30 country-performance HTML and reconciliation workbook without regenerating other modules.
- Confirmed 37 countries, 25 passing reconciliation checks, and no Review Required item.
- Added prior-week and prior-four-week-average ROAS values to the country table.
- Added a single W27–W30 chart for W30 Spend Top 5 countries with BI Spend bars, BI ROI, and Meta ROI lines; the reconciliation workbook now includes a `BI Country Trends` sheet.
- User acceptance completed; Module 09 is now frozen and Module 10 is next.
- Parameterized the frozen Module 09 generator so week labels, comparison windows, chart titles, and BI year follow the supplied report week and end date instead of W30-specific constants; structure and business rules are unchanged.
- No Meta write, ad/budget change, Feishu send, commit, push, or deployment.

## 2026-08-03 — W30 creative week-over-week decline analysis

- Added a reusable read-only W29-versus-W30 creative decline report.
- Aggregated duplicated ads by creative × Performance account and ranked results by absolute Spend decrease.
- Added local creative screenshots and W29/W30 Spend, Purchase and CR comparisons; CR is recalculated from aggregated Purchase and All Clicks.
- Added W29-to-W30 ROI, CPC, Frequency, Add to Cart Rate, and Checkout Rate comparisons.
- Generated 22 declining rows from 60 W29 and 73 W30 ads; all 22 rows have local screenshots.
- No Meta write operation, ad/budget change, Feishu send, commit, push, or deployment.

## 2026-08-02 — Module 05 W30 revision frozen

- Generated and froze the W30 Google Channel Performance HTML after user acceptance.
- Kept the existing six-channel structure; changed only the YouTube presentation requested by the user.
- YouTube now prioritizes Spend, Page View Conversion, Page View Conversion Rate, Cost per Page View, Impressions, Clicks, and CPC, with Purchase metrics afterward.
- Renamed the displayed `Purchase ROAS` column to `平台ROAS` across all six channels without changing its calculation.
- Page View reads only `Google Shopping App Page View (2)` conversions and is not mixed with Purchase.
- No ad/budget changes, Feishu send, commit, push, or deployment.

## 2026-07-30 — Module 08 frozen; Module 09 country performance generated

- Frozen Module 08 after user acceptance.
- Added read-only Meta API country breakdown for W25–W29 across both Performance accounts.
- Generated a combined country table with W29 Spend share, W29-versus-W28 and W29-versus-four-week-average comparisons.
- W29 country Spend totals $12,464.22 and exactly reconciles to Module 06; no API or reconciliation review items.
- Did not split country reporting by account, following the user-confirmed combined view.
- No Meta write operation, ad/budget change, Feishu send, commit, push, or deployment.

## 2026-07-30 — Module 08 audience visual overview

- Added a chart-and-table audience overview for combined Performance accounts.
- Added W29 new/old customer spend share and attributable ROAS comparisons against the W25–W28 four-week average.
- Preserved five raw Meta audience segments separately and documented that Meta assigns All Clicks to `uncategorized` in this breakdown.
- Added ROAS data coverage instead of converting missing Purchase Value to zero.
- No Meta write operation, ad/budget change, Feishu send, commit, push, or deployment.
- Removed CTR, CPC and CVR from the audience detail presentation because Meta assigns All Clicks to `uncategorized` under this breakdown.
- Hid the negligible-volume `Unknown` and `Uncategorized` rows from the audience detail presentation while retaining them in source data and reconciliation totals.

## 2026-07-30｜Module 06 frozen and Module 07 started

- Module 06 passed user acceptance and is frozen.
- Started the independent Module 07 Meta Campaign Performance output for W29 versus W28.
- Module 07 now combines the two Performance accounts into one Campaign ranking, excludes Brand, keeps Campaign IDs traceable in reconciliation, and reconciles Campaign Spend to Module 06 Performance account Spend.
- The Module 07 main view uses Spend bars with Campaign, combined-Performance Spend Share and ROI, without account headings. Sales campaigns are marked `Life线`; QMDT Campaign names containing `RTG` are marked as retargeting-focused.
- Module 07 passed user acceptance and is frozen.
- Started Module 08 from the updated real W28/W29 Meta audience workbook.
- Module 08 combines both Performance accounts while preserving five source segments; `existing` is old customer and the other four segments are new customer.
- W29 audience Spend reconciles exactly to Modules 06/07 at $12,464.22. Blank source conversion fields remain N/A.
- Generated the real W29 module output with eight spending Campaigns. Six W28/W29 account-week Campaign Spend checks reconcile to Module 06 with zero difference, and Review Required is empty.
- No Meta write, ad/budget change, Feishu send, commit, push, or deployment occurred.

## 2026-07-30｜Weekly Report Module 06 Meta整体表现

- 冻结用户已通过的模块05。
- 新增Meta整体与三个账户W26–W29、W29对W28独立HTML和对账工作簿。
- 按用户验收反馈，为Meta整体、Performance账户和Brand账户统一增加平台CPC及WoW，计算口径为Spend ÷ All Clicks。
- 按用户验收反馈，在Brand账户表增加Clicks及其WoW。
- Overall ROAS包含三个账户花费及所有可用Purchase Value；Brand自身不使用Purchase ROAS评价。
- 仅执行Meta只读API；未修改广告或预算，未发送飞书，未commit、未push、未部署。

## 2026-07-29｜Weekly Report Module 05 Google分渠道表现

- 用户确认模块04通过；模块04状态更新为已冻结。
- 新增模块05独立HTML与对账工作簿，固定展示六个Google细分渠道W26–W29及W29对W28。
- 复用模块04冻结的真实Purchase、日期、渠道映射和BI完全重复行去重口径。
- Google Overall只作对照，不参与细分渠道重复加总；YouTube单独标记为Upper Funnel。
- 未修改真实广告或预算，未发送飞书，未commit、未push、未部署。

## 2026-07-29 — Module 03 frozen; Module 04 started

- Recorded the user's approval and froze Module 03 without further output changes.
- Started Module 04 Google Overall Performance as the only active module.
- Confirmed both Google input workbooks cover 2026-06-14 through 2026-07-25.
- Module 04 retains the frozen true-Purchase rule: only `Google Shopping App Purchase (2)` counts; Page View actions are excluded.
- No advertising write, budget change, Feishu send, commit, push, or deployment occurred.

## 2026-07-29 — Weekly Report Module 04 Level 1 delivery

- Generated Google Overall W26–W29 platform and BI side-by-side data plus W29 versus W28 changes.
- Purchase and Purchase Value use only `Google Shopping App Purchase (2)`; Page View actions remain excluded.
- Generated `M04_Google_Overall_Performance.html` and `M04_reconciliation.xlsx`.
- Coverage is complete; unknown conversion actions and unmatched campaigns are both zero.
- Twenty-two Module 01–04 tests passed and the workbook formula scan returned no errors.
- Status is `待验收（一级：数据正确）`; Modules 01–03 remain frozen.
- Simplified the module into separate Meta and Google four-week tables, with BI metrics first, platform metrics second, and colored W29-versus-W28 changes.
- Fixed duplicated BI totals by reusing the frozen exact-row de-duplication rule and restricting BI to `Meta投放流量` / `GOOGLE投放流量`; Google W28 BI Spend changed from the incorrect $25,248.66 to $12,624.33.

## 2026-07-29 — Weekly Report Module 03 Level 1 delivery

- Updated BI coverage now includes current-year W14–W29 and prior-year W14–W30; future current-year W30 remains N/A without prediction or line interpolation.
- Added five standalone W14–W30 YoY scopes: Meta＋Google, Meta, Google Overall, Google Brand, and Google NonBrand.
- Per visual review, retained only Cost columns with ROI lines and temporarily removed Sales＋CR from the formal HTML.
- Swapped Cost colors to current-year orange and prior-year yellow, and added numeric labels to every available current-year ROI point.
- NonBrand is restricted to Shopping, Category, PMAX, Discovery, and YouTube; Google Overall and Brand are excluded.
- Generated `M03_BI_Overall_and_Channel_Trends.html`, `M03_reconciliation.xlsx`, and five formally referenced local SVG assets.
- Twenty Module 01–03 tests passed; workbook formula-error scan returned no matches.
- Status is `待验收（一级：数据正确）`. Modules 01 and 02 remain frozen and unchanged.
- No Meta write, advertising/budget change, Feishu send, commit, push, or deployment occurred.

## 2026-07-29 — Module 02 frozen; Module 03 source coverage blocker

- The user confirmed Module 02 passed and requested Module 03; Module 02 is now frozen.
- Started Module 03 BI W14–W30 trend coverage checks for five fixed Cost＋ROI charts.
- The only BI input covers current-year W22–W29 but lacks required current-year W14–W21; prior-year W14–W30 is complete.
- Future current-year W30 will remain N/A rather than zero or forecast.
- Formal Module 03 outputs were not generated. Modules 01 and 02 were not modified.
- No Meta write, advertising/budget change, Feishu send, commit, push, or deployment occurred.

## 2026-07-29 — Weekly Report Module 02 Level 1 delivery

- Started the standalone Month-to-Date module with equal-length real-date windows: 2026-07-01–07-25, 2026-06-01–06-25, and 2025-07-01–07-25.
- Confirmed that the module must show both MoM and YoY.
- After the BI input was updated, all three 25-day windows and all 150 expected date×overall-channel groups passed coverage checks.
- Added standalone `M02_Month_to_Date_Performance.html` and `M02_reconciliation.xlsx`.
- Added both MoM and YoY, aggregate-ratio recomputation, missing-data blocking, conflicting-duplicate blocking, and conservative identical-row deduplication.
- All source-to-formula reconciliation differences are zero; 14 Module 01/02 tests passed; workbook formula-error scan returned no matches.
- Status is `待验收（一级：数据正确）`; no style freeze has been declared.
- Module 01 remains frozen and unchanged. No Meta write, ad/budget change, Feishu send, commit, push, or deployment occurred.

## 2026-07-29 — Weekly Report Module 01 Level 1 delivery

- Added standalone W29 Week-to-Week HTML and reconciliation workbook.
- Added 2025 W29/W28 comparison columns and YoY while retaining the 2026 W29/W28 WoW comparison.
- Corrected week selection to use BI `event_date(week)` values instead of deriving prior-year dates by subtracting 364 days.
- Validated complete Sunday–Saturday coverage for W29 and the prior week.
- Restricted overall paid-channel aggregation to `Meta投放流量` plus `GOOGLE投放流量`; Google detail channels are not added again.
- Added conservative identical-row deduplication, missing-date/channel blocking, aggregate-ratio calculations, and boundary tests.
- Final acceptance: the user confirmed Module 01 passed and authorized freezing.
- Status is `已冻结`; no other weekly-report module was developed.
- No Meta write, advertising/budget change, Feishu send, commit, push, or deployment.

## 2026-07-29 - Weekly Report modular Roadmap V1 (documentation only)

### Added

- Added `WEEKLY_REPORT_MODULE_ROADMAP.md` with 13 business-facing modules, including a separate Meta audience module, separate display/development orders, three-level acceptance, module statuses, freeze rules, independent output requirements and Agent boundaries.
- Defined Module 01 `Week to Week表现` scope and acceptance without starting development.

### Changed

- Added the Roadmap entry and current confirmation status to `CURRENT_TASK.md`, `PROJECT_DASHBOARD.md` and `PROJECT_STATUS.md`.
- Changed the product delivery model from whole-report iteration to one-module-at-a-time acceptance and freezing.
- Fixed the display scope: BI trends use W14–W30; Google overall/channel and Meta overall include four-week and WoW views; Meta country includes platform and account views.
- Recorded user confirmation of the Roadmap and moved the single P0 to Module 01 `Week to Week表现`; development has not yet started.

### Safety

- Documentation only. No business code, tests, workflows, report output, Feishu message, Meta write, commit, push or deployment was performed.

## 2026-07-27 - W29 formal weekly-report modules (local only)

### Changed

- Added real W29 Overview, Week to Week and Month to Date sections to the leader HTML.
- Added five W14-W30 Cost and ROI comparison charts: Meta + Google, Meta, Google Overall, Google Brand and Google NonBrand. Current-year and last-year Cost/ROI series are separately identified.
- Added six fixed Google channels for W26-W29 and Google true-Purchase performance.
- Corrected W29-relative Google week labels and trend-date anchoring.

### Validation

- Generated W29 from complete BI and Google files plus the read-only Meta API: 60 spending ads, 31 unique assets, 60 image-complete ads and 38 country rows.
- Thirty-nine related tests and `git diff --check` passed.
- W29 audience breakdown remains explicitly unavailable rather than inferred from Campaign names.
- No Meta write, advertising/budget change, Feishu send, commit, push or deployment occurred.

## 2026-07-26 - W29 live Meta API dual-HTML generation

### Changed

- Connected the existing dual-HTML weekly-report generator to read W29 Meta ad hierarchy, performance and creative identifiers through the read-only Meta API instead of requiring a manually prepared W29 creative-performance worksheet.
- Added stable registry-keyword matching against the local creative library, QMDT Campaign-based prospecting/RTG grouping and Meta country breakdown output.
- Corrected input validation to read Google Excel date serials from the actual `Day` column.
- Made report headings and chart asset names use the requested week instead of retaining W28 literals.

### Validation

- Generated the real W29 outputs for 2026-07-19 through 2026-07-25: 60 spending ads, 31 aggregated asset units, 6 missing-image ad rows and 45 country rows.
- Thirty-five related tests and `git diff --check` passed.
- No Meta write, advertising/budget change, Feishu send, commit, push or deployment occurred.

## 2026-07-24 - Creative volume and commercial-efficiency classification V1 (local only)

- Added weekly creative classification for Performance accounts at creative × account × prospecting/retargeting level.
- Added Commercial Winner, High-volume Needs Optimization and High-volume Low-efficiency labels using Purchase 10, ROAS 2/3 and CPA $95 boundaries in the required decision order.
- Added source-data protections for missing Purchase/ROAS, invalid Spend/Purchase Value, incomplete natural weeks and Brand accounts.
- Added the fixed-order classification section to the existing W28 HTML home page with required metrics, reason text and category-specific sorting.
- Generated the real W28 result: one segment in each category; Purchase<10 segments remain unclassified.
- Added boundary, safety-line, missing-value, natural-week, Brand exclusion, audience-difference, order and sorting tests; 24 related tests pass.
- No Meta write, budget/ad change, Feishu send, commit, push or deployment was performed.

## 2026-07-24 - W28 creative-meeting HTML repair (local only)

- Revised the rejected first review build by reconstructing available denominators from source counts/rates, adding full video timeline strips, and documenting Hook/Body/Close structure for six high-spend videos with meaningful purchase samples.
- Added a local read-only creative-meeting HTML generator using the real W28 Meta workbook, the material registry and completed local video frames.
- Preserved the existing HTML visual language: square previews, account grouping, material cards, blue table headers and neutral report wording.
- Added fixed overall/QMDT prospecting/QMDT retargeting/Sales/review sections plus per-material aggregate, QMDT audience comparison, country placeholder, ad detail, content breakdown and neutral judgment.
- De-duplicated repeated `beyondtrends` registry rows by SHA-256 and retained both keywords.
- Resolved `Mix & match` to the real Sales ad account and recorded the registry mismatch.
- Generated 29 non-empty 1080×1080 previews; matched 63 of 66 W28 ads and kept 3 unmatched ads in manual review.
- Kept missing All Clicks, Impressions, CPM, 3-second plays, 100% plays and asset-country breakdown as explicit N/A; no ad-level rate averaging or substitute video metrics were used.
- Added eight targeted tests for classification, exact supported aggregations, missing denominators, keyword disambiguation, asset type separation, HTML structure and preview quality.
- No Meta write, advertising/budget change, Feishu send, commit, push or deployment was performed.

## 2026-07-23 - Simplified Creative Analysis user input

- Replaced two duplicate Creative Analysis input workbooks with one `素材登记表.xlsx`.
- Converted the existing W28 ad-level entries into five unique asset-level rows with stable Ad Name keywords.
- Removed user requirements to fill week, start/end dates, Account, Campaign, Ad Set, Raw Ad Name and Meta IDs.
- Changed new/existing material status from a user-entered fixed value to a system-derived value based on first spend date and the report/meeting window.
- Updated the desktop README to define fixed weekly-report dates, flexible creative-meeting timing and system-generated ad mapping.
- No application code, Meta data, advertising state, budget, commit, push or deployment was changed.

## 2026-07-23 - Use Meta account aggregate for realtime ROI

- 只读 Meta 查询确认：QMDT 有一个包含 Purchase 的小时行缺少 `action_values` 和原生 `purchase_roas`，Meta 随后回填该价值。
- Morning/Early Pulse 的当前账户日改用 Meta 账户级汇总 `action_values`，与 Ads Manager 报表读取方式一致；历史同期比较继续使用小时截止拆分。
- 真实只读验证返回 QMDT Purchase Value $2189.21 / ROAS 1.90，以及销售三部 Purchase Value $138.26 / ROAS 0.61。
- 新增当前汇总和历史小时截止测试；38 项相关测试通过。
- 最终验收：修复提交`e351fdc`已通过PR #1合并到`main`（合并提交`809e045`）；用户已真实收到修复后的Morning Report，并于2026-07-24确认验收通过。
- 本条仅补充既有修复的合并与最终验收状态，不代表一次新的代码修复。

## 2026-07-21 - Retain square previews only (local only)

- Recorded successful user acceptance of both W28 HTML reports.
- Changed the Excel creative library to retain only `square_preview.jpg` and `metadata.json`; extracted `original.*` files are no longer stored.
- Kept HTML asset references and report output unchanged.
- No Meta call, Feishu send, advertising write, commit, push or deployment was performed.

## 2026-07-21 - Weekly Report V1 Excel creative library and dual HTML (local only)

- Replaced the active DOCX delivery route with two formal HTML outputs: asset aggregation analysis and leadership weekly report.
- Added read-only extraction of W28 embedded Excel images with row anchors, inherited Account/Campaign/Ad Set hierarchy and source-row traceability.
- Added square contain-mode previews, local asset catalog, visual/name-assisted de-duplication, ad-to-asset mapping and possible-duplicate review output.
- Generated real W28 outputs from 66 Performance-ad records and 65 embedded images; Brand remains excluded.
- Recalculated aggregate ratios from reconstructed source numerators/denominators instead of averaging row-level ratios; unavailable All Clicks denominators remain review items.
- Added Feishu copy mode, static W28 spend charts, stable local assets and hierarchy Spend sorting.
- Added automated coverage for extraction, anchors, inheritance, visual de-duplication, non-merge cases, multi-ad mapping, square padding, aggregate ratio calculation, hierarchy sorting, and absence of Meta/Feishu write dependencies.
- Did not modify source Excel, call Meta, send Feishu, modify ads, commit, push or deploy.

## 2026-07-21 - Weekly Report V1 fixed-template acceptance build (local only)

- Rebuilt W27 from real BI, Google, Meta audience/country samples and read-only Meta Creative data.
- Limited Creative coverage to the two Performance accounts and retained all 63 Spend-positive ads in Account → Campaign → Ad Set → Creative Spend order.
- Added shared asset-key caching, square contain-mode output, explicit low-resolution placeholders/review reasons, fixed visible columns, hidden technical IDs and video diagnostic fields.
- Corrected the Meta three-second video metric field and isolated video-metric requests so an unsupported video field cannot remove all Creative rows.
- Replaced the manual report's Creative detail image with 12 repeated-header continuation pages while retaining the manual report structure and visual system.
- Generated local DOCX, data workbook, Creative HTML, Review workbook, 17-page review PDF/screenshots, reconciliation and acceptance matrix; P0 remains pending business review.
- No Meta write, budget action, Feishu weekly send, commit or push was performed.

## 2026-07-21 - Weekly Report development resumed during scheduler observation

- Changed the single active development P0 to Weekly Report V1 template and Creative repair.
- Reclassified scheduled-report natural-trigger checks as background production observation after deployment and successful manual delivery validation.
- Defined missed/duplicate delivery, invalid Performance ROAS or delay above 30 minutes as incidents that can interrupt Weekly Report work.
- Documentation-only priority update; no code, advertising configuration or budget was changed.

## 2026-07-21 - Scheduled reports deployed; natural-trigger acceptance pending

- Recorded the deployed Cloudflare scheduler, successful manual Feishu delivery for all three scheduled reports, and the HTTP 400/Purchase Value overwrite fixes on main commit `6d86d74`.
- Recorded verified Daily Close ROAS values and the 2026-07-22 natural-trigger observation windows.
- Kept scheduled-report reliability as the single P0 until all three natural triggers pass; Weekly Report V1 remains the next task.
- Kept the old GitHub schedule enabled for the 3-day parallel observation and retained manual dispatch.
- Documentation-only status update; no code, advertising configuration or budget was changed.

## 2026-07-20 - External scheduler, report idempotency, and ROI diagnostics (local only)

- Added a Cloudflare Worker V1 that runs every 15 minutes and only dispatches the existing Budget Alert or scheduled-report GitHub workflow for the applicable Beijing window.
- Added Cloudflare KV scheduler run keys without storing credentials in project files.
- Added scheduled-report workflow concurrency, persistent send-state restore/save, business-date/report-slot de-duplication, and delivery log artifacts.
- Added explicit Performance account Spend, Purchase, Purchase Value, calculated ROAS, data date, timezone, data status, and missing-reason output.
- Added a true seven-complete-day ROAS reference for incomplete Morning/Early Pulse data; it is not used as current ROAS.
- Daily Close now marks missing Performance ROAS as `DATA_ERROR`; Brand remains excluded from Purchase ROAS judgment.
- Kept Meta native `purchase_roas` only as diagnostics and did not fabricate Purchase Value from it.
- Local targeted tests passed. No AI call, Meta write, Budget Apply, commit, push, Cloudflare deployment, or real scheduled-report send was performed.

## 2026-07-20 - Budget Alert message simplification

- Removed Currency, Account Status, Spend Cap, and Amount Spent from the Feishu Budget Alert body.
- Retained Current Balance, seven-day average daily spend, three-day threshold, estimated remaining days, trigger reason, and recharge action.
- Added regression coverage for required and prohibited alert fields.
- No real advertising or budget operation was performed; no commit or push was made.

## 2026-07-20 - Budget Alert hourly scheduling incident fix (local only)

- Changed the local workflow definition to run a primary check hourly at minute 17 and a recovery check at minute 47.
- Added a non-cancelling concurrency group so scheduled and manual runs cannot overlap.
- Added recovery suppression after a successful primary run, state-persistence preflight, hourly success metadata, delay status, independent delay notification, workflow timing fields, per-account result fields, and Feishu HTTP/business response logging.
- Verified the real low-balance account remains protected by the existing 24-hour de-duplication state; the other two accounts did not trigger.
- All 60 tests passed. The workflow change was not committed, pushed, or deployed.

## 2026-07-17 - W27 formal delivery repair (pending acceptance)

### Added

- Added formal `投放周报｜W27.docx` generation with structured conclusions, comparison tables, trend charts, and neutral action/review sections.
- Added fixed-order Google six-channel four-week BI and platform performance data plus GG Overall, Brand, and NonBrand W14-W30 trends.
- Added local creative asset caching, original dimensions, asset type, cache status, complete metric columns, clickable contain-mode images, and explicit Creative Review reasons.

### Fixed

- Prevented 64×64 previews from being displayed as formal creative images.
- Preserved All Clicks as the only Meta funnel denominator and routes unsupported data to review instead of substituting Link Clicks or zero.
- Kept NonBrand limited to Shopping, Category, PMAX, Discovery, and YouTube without Google total or Brand duplication.

### Validation

- Generated four real W27 artifacts from 2026-07-05 through 2026-07-11; status remains pending manual acceptance.
- All 56 local tests passed. No Feishu send, Meta write operation, commit, or push was performed.

All notable project changes should be recorded here.

Format:

```text
## YYYY-MM-DD

### Added

### Changed

### Fixed
```

## 2026-07-17

### Added

- Added root `AGENTS.md` with project collaboration rules and advertising-operation safety boundaries.
- Added `CURRENT_TASK.md` as the single source for the next task: Budget Alert operational validation.
- Added `SCHEDULING_RELIABILITY_PLAN.md` with a 30-minute delivery target, delay detection, manual fallback, and missed-run recovery plan.
- Added `WEEKLY_REPORT_V1_REQUIREMENTS.md` as the frozen product, data-contract, priority, and acceptance source for Weekly Report V1.
- Added `weekly_report.py` for one-command generation of the three Weekly Report V1 files.
- Added Weekly Report tests for date parsing, Google channel mapping, true Purchase filtering, spend deduplication, All Clicks funnel rates, account-type metrics, and creative-account scope.

### Changed

- Rebuilt `PROJECT_DASHBOARD.md` as readable UTF-8 Chinese.
- Aligned `PROJECT_STATUS.md`, `CURRENT_TASK.md`, `PROJECT_DASHBOARD.md`, `PROJECT_CONTEXT.md`, and this changelog around no active P0 development and one next task.
- Changed the single active P0 to Weekly Report Automation V1 because a real weekly report must be delivered this week.
- Moved Budget Alert to conditional acceptance and production observation until a natural alert completes end-to-end validation.
- Recorded GitHub Actions scheduling latency as an unresolved product reliability risk.
- Frozen W27 real-date matching, BI channel deduplication, Google Purchase filtering, Meta audience mapping, and All Clicks funnel-rate definitions for Weekly Report V1.
- Added Google six-channel four-week reporting and W14-W30 GG Overall / Brand / NonBrand year-over-year Cost + ROI chart requirements from the updated manual weekly-report template.
- Clarified that Weekly Report V1 generates local files only and never sends Feishu messages.
- Limited Weekly Report V1 creative collection to the two specified Performance accounts; the Brand account remains excluded from the creative report.

### Fixed

- Removed stale Dashboard state that showed completed Feishu validation work as still in progress.
- This documentation-governance change does not modify code, GitHub Actions, advertising rules, account configuration, or budget execution logic.
- No real advertising operation or Budget Apply was executed.
- Weekly Report W27 real-data validation generated 3 account rows and 63 spending creatives from only the 2 approved Performance accounts; no Feishu message or Meta write operation was performed.

## 2026-07-14

### Added

- Initialized Project Documentation V1.
- Added `PROJECT_CONTEXT.md`.
- Added `AI_MEMORY.md`.
- Added root `CHANGELOG.md`.
- Added Documentation section to `README.md`.

### Changed

- Upgraded `PROJECT_STATUS.md` with Current Status, Completed, In Progress, Known Bugs, Next Milestone, and Recent Commits sections.

### Fixed

- No code fixes in this documentation-only change.

## 2026-07-16

### Added

- Added product-facing `PROJECT_DASHBOARD.md`.
- Added unified Budget Alert delivery logs.
- Added scheduled report delivery and account spend log fields.

### Changed

- Budget Alert state updates are now handled per account.
- Scheduled reports keep their planned Beijing slot when GitHub Actions runs late.
- Scheduled report Feishu summaries now label total spend by account count.

### Fixed

- Fixed Budget Alert cross-account state update risk.
- Fixed Budget Alert last-7-days empty insight handling so empty data does not become zero spend.

## 2026-09-20

### Changed

- Added `Jelenew+` (`1614799860253372`) as a Performance / Life account to the Meta reporting and creative-analysis scope.
- W37 Meta Campaign, Country, and Creative Diagnostics reports now include Jelenew+ where source data is available.
# 2026-09-04｜独立素材生命周期模块12样式版

- 用户确认按最后消耗日作为无在投素材终点，仍在投算至9月4日；三栏为>28天、8—28天、≤7天。
- 独立产物：outputs/creative_lifecycle/2026-08-31/素材生命周期_模块12版.html；不替换冻结周报。
- 6—8月66条（22/33/11），8月52条（18/25/9）；期间Purchase与Purchase Value使用项目别名优先级及统一广告组归因设置。
- 两账户花费、Purchase对账一致，Purchase Value最大舍入差0.01美元；期间视频均有本地封面。浏览器安全策略阻止自动预览，已执行静态校验。
- 未部署、未提交、未推送、未执行广告写操作。
## 2026-09-28

### Added

- Added a read-only Feishu adjustment-review test card sender for the existing Budget Alert group webhook.
- Added completed-day D0 / 3-day / 7-day platform evidence to the shadow scan output for card rendering.

### Verified

- Sent exactly one test card successfully to Feishu (`HTTP 200`, platform response `success`).
- The card contains no approve/reject action buttons and the run performed zero Meta write calls.
## 2026-10-08

### Added

- Added a read-only M12 creative-performance-library builder which merges historical M12 daily snapshots and a final read-only Meta extension.
- Added a local date-filterable creative library page through 2026-10-07.

### Verified

- Generated 180 mapped creative-performance rows and 2,627 daily facts from 2026-07-17 through 2026-10-07.
- One unmapped Jelenew+ ad was retained as review-only data; zero Meta write calls were made.
- 修复 W42 M12 回放重分类会清除用户确认首投日期的问题；用户确认的 5 条继续进入“首投不足7天且花费<$100”。同步移除页面中残留的“曝光<500”旧说明并重生成本地 M12。
