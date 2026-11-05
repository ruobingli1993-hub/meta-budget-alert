# 当前任务

## 2026-11-05｜GitHub Actions云端影子扫描联调

- 云端影子扫描首次跑通：3个账户、11个实体全部扫描成功，出1条加预算建议（FB-RTG-maxvalue-CBO-Cycling-V260731，$414→$476.10，+15%）。
- 写飞书从旧webhook方式改为直接写多维表格：新建 `tools/write_recommendations.py`，用飞书自建应用tenant token直接调bitable API写审批表。
- 修复了dataclass不能用`.get()`的AttributeError；补全了字段映射（账户、实体层级、预算层级、冷却状态、规则版本、扫描日期、数据快照等28个字段）。
- 执行器每30分钟轮询一次（cron `*/30 * * * *`）；影子扫描每天3次（cron `0 0,6,13 * * *`，北京时间早8/下午2/晚9）。
- 待完成：加飞书消息通知（写完表后自动给用户发审批提醒）；V2调价规则（ROI达标 AND 漏斗增长超10%双重条件）实现；config.json的today门槛恢复。

## 2026-10-25｜W42 M11/M12 修正

- 修复错误复用旧产物的问题：重新读取 W42 三账户 Meta 数据，M12 44 个素材对象、周花费 $10,263.52；M11 52 条有花费广告、51 个素材组。与 M11 素材级四舍五入汇总差约 $0.08。
- M11 50 个素材组已有匹配首图；43 个视频组中 42 个已替换为登记原片首帧或 GIF 第一帧，1 个 TOFU 素材原文件缺失，用户确认可暂不解析且保留数据。
- M12 视觉解析 43 完成、1 按用户确认不适用、0 待解析；“首投不足7天且花费<$100”按 Meta 广告实际上线日（created_time）计算，不用首花费日替代；曝光量没有门槛。
- 31 项相关单元测试通过。用户明确授权后已将缩略图版发布至固定 Pages 链接，并验证 HTTP 200、W42 与“查看拆解”入口；未上传原视频、未调用 Meta 写接口。
- W42 按用户确认的上线日期及广告名日期后缀重分类：5 条上线<7天且周花费<$100，另 2 条同期新素材花费$102.77 / $163.49 达到门槛、仍列“需要关注”。回放重分类不会清除确认日期；本次更新本地 M12，尚未重新部署线上版。

## 2026-10-11｜W40 周报

- 按 M01–M12 逐模块生成、核验、交付；已交付 M01–M11，正在处理 M12、本地素材复核和固定线上链接同步。
- Meta 国家数据固定从 Meta API 只读获取，不要求用户上传国家导出表；已更新工作流文档与模块 Roadmap。
- 保留 W40 原始输入；2025-10-10 Meta BI 空的销售额、订单量、支付 UV 仅在 M02 计算中按用户确认记 0。

## 2026-10-10｜M12 在投素材核对

- 已完成三账户在投广告、登记表和截至 10 月 7 日 M12 的只读核对；39 条在投中 35 条有登记映射，4 条无映射。待用户确认 Jelenew+ Pink Ribbon 对应素材，以及 pressure3 究竟是 JPG 还是需要补视频原文件；下次快照需补销售三部 supportbra 的 $0.11 截止日前花费。

## 2026-10-09｜素材表现库本地首图补齐

- 25 张缺图已从核实的 M12 本地素材封面／关键帧补齐；180 条素材图片均可用，2,627 条逐日表现记录未改。未同步线上。

## 2026-10-09｜M12 三栏分类本地验证

- 已将用户指出的 0918-3L 同账户同人群拆行合并；截至 10 月 7 日快照现为 104 行，合并前后总花费、购买、销售额不变。
- 已实现并本地重算截至 10 月 7 日快照；已通过 17 项 M12 单元测试。
- 首投日期仅有已捕获历史，近期素材无法证明从未更早投放，保守归“需要关注”并标注不可确认。后续需补足可验证历史，才可把真正未满 7 天素材放入“数据不足”。
- 本次未部署线上版；依据模块12同步硬门槛，线上交付状态仍未完成。

## 2026-10-09｜M12 素材解析流程收尾

- 用户决定跳过 05，优先实现本地最小工作流。已完成自动登记、去重、指纹复用与页面状态；截至 10 月 7 日修正快照的 105 条素材记录均已解析，待解析 0。
- 用户指出两条误判后，已找到新会员原视频，按登记表把另一条创意标题改回 `No unnecessary pressure3` 素材名，并合并同素材重复行。后续新素材按 `docs/M12_VISUAL_ANALYSIS_WORKFLOW.md` 处理；不接付费模型、不执行 Meta 写操作。

## 2026-09-28｜调整建议中控｜今日只读影子扫描已启动

- 新增 `tools/run_adjustment_shadow_v1.py`，以当前冻结的 `shadow-v0.2` 规则扫描三个 Performance 账户；只读 Meta 当前预算、D0、近3天（含D0）、账户近7天及近24小时预算变更。
- 首次手动扫描结果保存为 `outputs/adjustment_control_center_v1/current_shadow/2026-09-28/shadow_scan.json`：7个可控对象，减预算候选2条、加预算候选0条、NO_CHANGE 5条；`meta_write_calls: 0`，仅作影子观察。
- 用户指出9/28为未开始广告账户日，首次结果作废且不进入观察依据。已改为默认使用最近完整广告日：本次重算数据截至9/27，近3天为9/25–9/27；7个可控对象变为加预算候选2条、减预算候选0条、NO_CHANGE 5条，结果在 `current_shadow/2026-09-27/` 与 `latest.json`。
- 本地工作台新增“今日影子（只读）”入口，展示数据时间、D0/近3天/账户近7天ROI、当前与影子预算、健康门禁和 `$2,500` 检查；尚无同意、拒绝或执行按钮。
- 首页已改为明确指引：当前只需查看今日影子候选理由，无需审批或操作；“查看今天影子（无需操作）”直接进入今日扫描结果。
- 已修复本地工作台启动器：双击 `打开本地调价工作台.cmd` 会自动启动本地预览并打开页面；已实际校验工作台页面及 `current_shadow/latest.json` 均返回 HTTP 200。
- 下一步：将同一只读扫描接入北京时间08:00/21:00的前向影子调度并连续运行7天，再开放正式待审和人工决定账本。

## 2026-09-27｜W38模块04双订单/AOS口径冻结

- W38模块04已补入并校验 Meta、Google 两张表的“平台订单量”和“平台AOS”；平台订单量取 Purchase，平台AOS取 Purchase Value ÷ Purchase。
- 冻结为后续周报硬门槛：两张表均需保留BI订单量/AOS并并列展示平台订单量/AOS及WoW；未满足不得标记模块04或周报完成。

## 2026-09-27｜W38周报与模块12固定链接同步

- W38（2026-09-20至2026-09-26）模块01—12本地HTML已生成；模块12已按缩略图线上版打包并部署至固定链接 `https://jelenew-m12-weekly.pages.dev/`。
- 已线上核验 HTTP 200、页面包含 `W38` 与“查看拆解”入口。本地版仍保留原始视频；线上版不含原始视频。
- 冻结为硬门槛：后续每周本地M12生成后必须自动打包、部署、校验固定链接，未通过不得报完成。

## 2026-09-24｜全项目周报产能保护线（文档）

- 已在`TASK_CARD_OPERATING_PROTOCOL.md`新增周报 Token / 上下文安全边际：固定周报交付为每周日15:00（北京时间），每周五15:00起自动成为唯一P0；在周日报告交付前复杂非周报任务始终保留至少40%可用额度并必须可停止、可拆分。
- 周报生成、基础对账和可打开交付物完成前，不得让复杂开发阻塞本周交付。

## 2026-09-24｜低人工跟进项目推进协议（文档，试运行）

- 新增`TASK_CARD_OPERATING_PROTOCOL.md`：以任务卡、六种状态、单一负责人/资源锁、静默推进、验收包与安全边界管理00—06协作。
- 示例卡覆盖02的28天历史回放与06独立测试；示例仅等待00安排，不改变当前实现、规则、部署或广告操作。

## 2026-09-18｜定时调价系统 P0｜调度规则已确认

- 北京时间每天08:00与21:00只读扫描；生成待审调价建议/`NO_CHANGE`，不替用户审批或执行预算。
- 08:00用于美国前一投放日接近结束的高峰数据，21:00用于美国新投放日开始后的趋势/转化高峰；两者均可生成建议，但必须标注数据截至时间与覆盖范围。
- 最小调整单位仅在真实执行后进入24小时冷却；早上建议被拒绝、跳过或未执行，晚上仍可按最新数据重新评估。无实质数据变化时只更新建议版本，不重复创建待审任务。
- Alert 系统（数据/预算异常、任务漏跑、账户故障等）已拆为独立 Backlog，不与定时调价混合。

## 2026-09-17｜调整建议中控 V1｜受控线上审批骨架进行中

- 已新增 `approval_workbench/`：Cloudflare Worker 对每个 API 请求验证 Access JWT 的签名、Issuer、Audience 与有效期；不信任独立邮箱 Header。
- 已定义独立 D1 `decision_ledger`，记录建议／规则版本、证据快照、人工决定、拒绝理由、审批邮箱与时间；API 明确返回 `executed: false`，不存在 Meta 写接口。
- 已新增将已验收手机响应式界面打包为 Worker Asset 的构建脚本；本地 Worker 源码语法与构建校验通过。
- 未创建 Zero Trust 组织、未创建 D1、未部署，不会在 Access 未配置时发布真实数据。下一步需要在 Cloudflare 配置指定公司邮箱 Access 与独立 D1 后再部署，并接入飞书受控跳转。

## 2026-09-17｜调整建议中控 V1｜静态 / 影子 Dashboard 已交付，等待验收

- 已将旧三卡静态 Demo 升级为两层工作台：Overview（合计预算／$2,500、ROI、健康度、模式、目标 ROI、三窗口 KPI、四组日趋势、全指标表、两账户卡）与建议审阅（待审／已审历史／全部）。
- 待审建议按预计影响金额排序；同意或拒绝只更新页面内影子决定，审完自动切换下一条；拒绝理由强制选择，并在已审历史显示建议版本与 D+1～D+3 观察位。
- 静态文件：`outputs/adjustment_control_center_v1/调整建议中控_V1_静态Demo.html`；字段口径与验收说明：`outputs/adjustment_control_center_v1/V1_影子界面验收说明.md`。
- 未读取新广告数据、未接 Meta 写接口、未调整真实预算、未修改现有审批流程。浏览器无法读取本地 `file://` 页面，视觉实拍 QA 记录为 blocked，等待用户本地验收后接入 28 天历史回放。

## 2026-09-17｜调整建议中控 V1｜Dashboard产品设计已确认

- 已确认两层页面：Overview 先展示两 Performance 账户合计经营环境、趋势、完整指标对比、整体模式与目标；建议审阅页才逐条审 Campaign/Ad Set，并支持同意/拒绝、强制拒绝理由、审一条少一条与已审历史。
- Overview 固定包括：Spend + Meta ROAS、ATC% + Checkout%、CTR + CPC + CPM、CR + AOV 四组按天趋势图；两账户合计的今天／近7天／近14天指标表；分账户卡片后置且可覆盖整体模式。
- 广告调整工作台、广告上新仅保留“规划中”入口；本轮不实现关停、复制、素材上传或广告创建。
- 视觉方向已由用户确认，产品原型参考：`C:\Users\shzhe\.codex\generated_images\019f69cc-6a16-7111-afbd-8570b9623704\exec-c1b3c5e8-7683-4f5e-9cbf-eda0c2ddd500.png`。
- 下一步：02 在现有Dashboard实现只读静态/影子界面，先交截图和验收材料；不接Meta写接口或真实预算执行。

## 2026-09-17｜调整建议中控 P1｜手机审批与执行路线已确认

- P1 目标：在P0历史回放与7天影子验收通过后，用户可通过飞书跳转至手机适配中控页，审阅一条具体建议并进行二次“同意并执行”确认。
- 真实执行前必须重新读取建议版本、数据、实体状态、预算、冷却期及$2,500上限；任一不通过即取消并要求重新预览。
- 执行后飞书回执必须说明调了什么、前后预算、为什么、规则版本和结果；异议只进入复盘，不自动修改规则。
- P1 不是当前开发范围；当前仍只做P0只读影子界面与回放。

## 2026-09-17｜调整建议中控 V1｜影子规则已确认，等待历史回放

- 用户已确认：两个 Performance 账户；CBO 仅 Campaign、ABO 仅 Ad Set；加预算、减预算与 `NO_CHANGE` 同时覆盖；同一 Campaign 每日最多一条建议。
- 已确认口径：新客 ROAS 目标2、老客／再营销2.5；近3天（含D0）累计与D0同时达标/未达标判断加减；至少1个 Purchase 才建议加预算；Learning 可提示但标为风险。
- 已确认保护：扩量／常规／提效模式、实体目标偏差±30%的5个百分点幅度修正、最小调整$10、最低预算$80、24小时冷却、两个账户纳入范围预算合计每日上限$2,500；超上限只提醒人工决定。
- 账户整体 ROI 目标为2；近7天相对目标±50%仅用于建议投放节奏，用户手动模式／目标优先。
- 下一步：02只读完成28天逐日历史回放和验收材料；未通过用户验收前，不启动7天前向影子或任何真实预算操作。
- 禁止：Meta写操作、预算Apply、暂停广告、commit、push、部署。

## 2026-09-11｜调整建议中控 V1 盘点与静态Demo（等待01确认）

- 完成只读盘点与三条固定模拟样例：建议、数据异常 `NO_CHANGE`、已过期建议。
- 未读取新广告数据，未开发规则或影子运行，未接Meta写接口，未改变现有审批流程或Dashboard。
- 输出：`outputs/adjustment_control_center_v1/README.md` 与 `调整建议中控_V1_静态Demo.html`。
- 等待01确认账户范围、实体层级、动作类别、规则阈值与影子验收口径后再继续。

## 2026-09-11｜调整建议中控 V1 产品Roadmap（待用户确认）

- 当前产品设计任务：完成只读“调整建议中控V1”Roadmap；不启动规则实现、影子运行或任何真实预算操作。
- 入口：`ADJUSTMENT_CONTROL_CENTER_V1_ROADMAP.md`。
- 05结论已确认：借鉴局部，在现有Dashboard上建设，不接外部SaaS/Agent平台，不新建第二套中控。
- 核心边界：只读建议＋影子运行＋人工决定记录；Dashboard批准永远不直接触发Meta写入；任何数据不健康均为`NO_CHANGE`。
- 模块13保持独立周报模块，只可作为候选输入，不能直接形成或执行调整建议。
- 下一步：用户确认Roadmap后，才向02发送“盘点＋静态Demo”的最小任务书。
- 禁止：广告/预算写操作、自动暂停或扩量、commit、push、部署。

## 2026-09-06｜W35逐模块刷新

- 用户要求自动跑完并逐模块交付；W35为2026-08-30至2026-09-05，模块01—12 HTML已生成于outputs/weekly_report/W35/modules。
- 模块03使用临时运行入口，2025趋势延伸W52；Google NonBrand W45因11月2日缺YouTube/探索渠道行保留N/A并标记复核，不修改冻结生成器。
- 模块10为37素材、57广告；花费/购买数对齐，QMDT Purchase Value差0.01美元保留原复核。模块11缺素材国家Breakdown，保留提示。
- 模块12为45对象，复用22项历史拆解、23项待视觉核对；本地链接版已打包，6个超过25MB视频未包含，未发布线上。
- 回归74项中72通过；旧M03测试缺trend_end_week参数，旧M05测试缺Google Spend Share字段。未擅改冻结模板或用例。
- 未修改广告、未发送飞书、未commit/push。下一步为数据缺口与素材拆解复核，不得声称全部内容已验收。

## 模块12｜后续周次同步规则

- 每次更新模块12，交付范围固定包含：本地 `M12_Video_Creative_Breakdown.html`、线上固定链接版，以及线上“查看拆解”详情页。
- 线上包必须使用同周 `M12_payload.json` 生成；发布前校验周次、报告起止日期和“查看拆解”入口。任一项不一致时，打包/发布中止。
- 完成汇报需同时说明本地模块、固定线上链接和查看拆解页的同步结果；只生成本地模块不得视为模块12完成。

## 2026-08-30｜模块05 W34花费占比展示冻结

- 用户确认模块05在每个细分渠道标题右侧显示“本周花费占比”，同时保留表格内逐周“花费占比”列。
- 该结构作为后续周次复用的冻结版本；更新周报时只替换数据，不擅自调整结构。
- 冻结产物：`outputs/weekly_report/W34/modules/M05_Google_Channel_Performance.html`。

## 2026-08-24｜模块03 W33长周期ROI对比版已冻结

- 用户已确认模块03当前W33版本通过并冻结。
- 保留原有BI Cost与ROI同比趋势图，并新增Meta、Google Overall的`BI ROI vs 平台 ROI`周趋势。
- 两张新增图使用当前可核实的W26–W33真实历史周；生成逻辑自动汇集历史产物、按周去重并随新报告周延伸，不写死周数。
- 冻结产物：`outputs/weekly_report/W33/modules/M03_BI_Overall_and_Channel_Trends.html`。
- 后续不得擅自修改模块03的数据口径、图表结构或历史周收集逻辑。

## 2026-08-24｜模块05 W33花费占比列版已冻结

- 用户已确认模块05当前W33版本通过并冻结。
- 六个Google细分渠道均在表格中按周展示花费占比；花费占比以同周六渠道营销花费合计为分母计算。
- 冻结产物：`outputs/weekly_report/W33/modules/M05_Google_Channel_Performance.html`。
- 后续不得擅自修改模块05口径或样式；本次继续仅处理用户明确要求的模块03 ROI趋势增强。

## 2026-08-20｜模块12 W32 已验收冻结并更新公开页面

- 用户确认模块12可以冻结；最终W32产物包含40个素材对象（25个Video、15个Pic），按本周7天/最近30天切换并使用Account×新客/老客对应Benchmark。
- 40/40素材均已附带结构化素材解析；同一Creative在同一Account×新客/老客口径内去重，图片的视频指标保持留空。
- 固定公开只读地址已更新：`https://jelenew-m12-weekly.pages.dev/`；线上核验返回HTTP 200并包含W32最新结构。
- 模块01—12均保持冻结；后续修改模块12必须先获得用户明确解冻授权。当前下一模块为模块13 `本周总结与动作`。

## 2026-08-12｜模块12 W31 视频素材拆解第一阶段（待验收）

- 已按 Creative/Asset ID 重新生成第一阶段真实产物：26个W31有花费视频Creative、37条关联广告、3个 Account×新客/老客 Benchmark。
- 两个窗口为W31报告周7天及包含报告周的最近30天；播放指标仅保留3秒播放率、50%留存率和95%完播率。
- 26/26素材已匹配本地预览；Meta读取、指标重算及对账异常为0；状态仍为`待验收`，未固化最终高/正常/低幅度。
- 当前限制：历史首次花费日尚不能从30天窗口证明；产物只显示当前窗口可验证值，并在交付说明中披露，不使用素材文件名日期代替。
- 模块01—11保持冻结；模块12未接入正式Weekly Report，未经用户确认不得标记为已冻结。

## 2026-08-11｜模块05 W31增强版已重新冻结

- 仅购物广告、品牌词、品类词和PMAX在`平台ROAS`后新增`2 Week ROAS`。
- 公式：`平台ROAS × (1.6 ÷ 1.44)`；平台ROAS缺失时保持N/A，WoW基于两周估算值计算。
- 探索广告和YouTube保持冻结版列结构，不新增该指标。
- 六个渠道均增加BI UV与Google Clicks；购物、品牌词、品类词和PMAX增加`2 Week ROAS`。
- 购物与品类词目标为1.5，品牌词目标为6，目标值在表头第二行显示；PMAX未设置目标。
- 已用W31真实数据重生成并由用户确认冻结；其他冻结模块不受影响。
- 当前下一任务：按Roadmap进入模块12 `视频素材拆解`。

## 2026-08-10｜模块11 W31跨周复用验收（已冻结）

- 用户已确认冻结整个模块11；冻结范围包含层级、指标、80×80素材预览、Active/Paused状态列和整表PNG下载。
- W31真实周期为2026-08-02至2026-08-08，覆盖两个Performance账户全部53条有花费广告。
- 重新读取用户更新后的素材登记表后，共识别26个素材，53/53条广告均有本地素材图，缺图为0、低清图为0。
- 已验证模块11通过必填周次和起止日期跨周生成，未写死W30或W31。
- 当前下一任务：按Roadmap进入模块12 `视频素材拆解`；涉及判断阈值时仍需先由03确认。

## 2026-08-09｜模块11整表下载与紧凑布局（已冻结）

- Campaign 与 Ad Set 合并单元格文字改为顶部对齐。
- 19列使用固定紧凑列宽，取消模块内横向滚动条；素材仍为80×80完整方形预览。
- 只保留一个“下载整个素材表现表（PNG）”入口，不增加账户级下载按钮。
- 已生成真实整表图片 `W30_Creative_Detail_Performance.png`（2125×6854，73条广告）。
- 用户已确认验收通过；当前状态：`已冻结`。后续模块不得修改其数据口径、层级、布局和整表下载方式。
- 下一任务：按模块Roadmap进入模块12 `视频素材拆解`，开始前需先核对03尚未确认的判断阈值。

## 2026-08-09｜模块11 W30 新产物已覆盖（历史验收前记录）

- 已按用户要求覆盖 `M11_Creative_Detail_Performance.html`，未修改旧领导周报产物。
- 73/73 条有花费广告全部保留；Campaign 与 Ad Set 相同项使用合并单元格。
- 素材类型只显示 Video 或 Picture；73 张本地素材图统一为 80×80 完整显示。
- 最后一列为生成时只读 Meta API 获取的当前状态：Active 25 条，Paused 48 条。
- 该条为冻结前记录；最终状态以本文件顶部“已冻结”为准。
- Blocker：素材级国家 Breakdown 仍未提供，不影响本次广告层级表验收。

## 2026-08-06｜模块11 W30 素材细化表现（历史首次交付记录）

- 已生成可复用的模块11独立HTML，生成入口强制传入报告周、开始日期和结束日期，周期必须连续7天；未写死W30。
- W30覆盖两个Performance账户全部73条有花费广告，按Account → Campaign → Ad Set → Creative展示，每层按Spend降序。
- 同一素材图片允许复用，但73条关联广告记录全部保留；当前形成69个Ad Set内素材位置。
- 69/69个素材位置均有本地图片且无断链；素材缩略图统一为80×80px完整展示。
- 素材级国家Breakdown当前未提供，报告明确标记待补，没有使用账户级国家数据冒充。
- 当前状态：`待验收（一级：数据正确）`；模块01–10保持冻结。
- 下一步：用户先核对W30层级、广告覆盖、排序和指标；国家下钻作为明确未完成项单独补齐。

## 2026-08-06｜模块10 W30 素材总体表现（已冻结｜已知素材归因差异待复核）

- 已补齐销售三部两份本地视频的1秒方形封面，当前31个素材图片覆盖率为100%。
- 已通过Meta只读接口读取W29（60条广告）与W30（73条广告），31个W30素材全部匹配到统一的账户×素材对比键。
- 表内全部指标均显示W30数值及W30对W29变化；变化保留两位小数，涨跌分别用绿/红表示，绝对变化达到30%时重点标记；上周为0或缺失时保持N/A。
- 素材类型已统一为两类：22个Video、9个Picture；不再展示Meta投放形式Flexible或Unknown。
- 素材缩略图显示规则已按用户要求更新为80×80px方形完整展示，不拉伸、不裁主体；表格字体和留白同步缩小，后续周次自动复用。

- 用户已确认先冻结模块10；模块01–10现均已冻结，模块10保留已知素材归因差异说明。
- 真实产物：`outputs/weekly_report/W30/modules/M10_Creative_Overview.html` 与 `M10_reconciliation.xlsx`。
- 范围：两个Performance账户、73条有花费广告、35个账户×素材聚合行；Brand账户已排除。
- 素材图片：29个聚合素材有本地方形预览，6个缺图素材保留占位并进入复核；没有因缺图删除表现记录。
- 聚合口径：同一账户内相同素材合并；ROAS、CR、CPC、CPM、ATC率、Checkout率、AOV、CPA、CTR均由聚合分子/分母重算。
- 对账结果：销售三部Purchase与模块06一致；其余5项存在差异。QMDT差异为Spend +$0.35、Purchase -2、Purchase Value -$657.28；销售三部差异为Spend +$0.10、Purchase Value -$0.01。
- 当前状态：`已冻结｜已知素材归因差异待复核`。已知差异不再阻塞进入下一模块，但仍保留在对账记录中。
- 下一步：模块11 `素材细化表现`，优先完成高花费素材的账户、Campaign、Ad Set、国家和关联广告下钻。

## 2026-08-05｜模块01–09跨周复用参数化（已完成）

- 已清除模块01–09生成入口中的W29/W30、固定日期及固定年份默认值。
- 模块01必须传入`week/since/until`；模块02–09必须传入`report-week/report-end`，避免漏参时误用旧周数据。
- 模块03的趋势终点、当年/去年年份、标题、图例与覆盖说明均跟随报告参数动态生成。
- 模块09的国家趋势标题、比较窗口与BI年份跟随报告参数动态生成。
- 47项模块01–09测试通过；九个模块语法检查通过；固定周次与日期扫描无残留。
- 真实跨周验证：模块01–03均已用W29与W30参数成功生成到临时目录，未覆盖正式产物。
- 模块04–05真实复现被当前Google主表缺少可识别日期覆盖拦截；这是数据输入阻塞，程序未静默生成错误报告。
- 模块01–09的冻结业务口径、结构和样式未改变。
- 当前下一任务：模块10 `素材总体表现`。

## 2026-08-05｜模块09 W30 国家表现（已冻结）

- 用户已明确确认冻结模块09 `Meta国家表现`。
- W30周期：2026-07-26至2026-08-01；对比W29及W26–W29前4周均值。
- 两个Performance账户合并展示，不拆账户；W30共37个国家，按Spend降序。
- W26–W30的Spend、Purchase、Purchase Value、Clicks、Impressions共25项对账全部PASS。
- W30合计：Spend $12,133.39、Purchase 88、Purchase Value $21,717.77；Review Required为空。
- 表格已新增上周ROAS值和前4周平均ROAS值，不再只显示变化百分比。
- 已新增W30 Spend Top 5国家（US、GB、CA、DE、CH）的W27–W30组合图：BI花费柱状、BI ROI蓝线、Meta ROI绿线。
- BI数据来自`BI_Weekly_日期范围.xlsx`的`数据模板-国家`工作表，只取`Meta投放流量`。
- 当前状态：`已冻结`；后续模块不得修改其数据口径、结构或样式。
- 生成逻辑按传入的报告周与周结束日期计算本周、上周、前4周和BI年份；未写死W30日期。
- 当前下一任务：模块10 `素材总体表现`。

## 2026-08-03｜W30素材周对周下降分析（待用户验收）

- 目标：识别W30对W29花费下降最大的素材，按`素材 × Performance账户`聚合并按花费下降金额排序。
- 周期：W29为2026-07-19至2026-07-25；W30为2026-07-26至2026-08-01。
- CR口径：Purchase ÷ All Clicks；同一素材关联多个广告时先汇总分子和分母再计算。
- 真实数据：W29共60条有花费广告，W30共73条；22个素材×账户组合花费下降。
- 图片：22条均使用本地素材截图；不存在断开的图片引用。
- 产物：`outputs/weekly_report/W30/Creative_WoW_Decline.html`与`Creative_WoW_reconciliation.json`。
- 指标：已补充ROI、CPC、Frequency、Add to Cart Rate、Checkout Rate的W29→W30对比及变化值。
- 状态：待用户验收；不自动输出暂停、预算或换素材动作。

## 2026-08-02｜模块05 W30版本已冻结

- 用户已确认冻结W30模块05 `Google分渠道表现`。
- 六个Google细分渠道继续按固定顺序展示最近4周及WoW；其他五个渠道沿用既有冻结结构。
- YouTube固定为Upper Funnel，前置列为Spend、Page View Conversion、Page View Conversion Rate、Cost per Page View、Impressions、Clicks、CPC，Purchase指标后置。
- 六个渠道的`Google Purchase ROAS`展示名称统一为`平台ROAS`，底层计算口径不变。
- Page View仅使用`Google Shopping App Page View (2)`的Conversion；Page View Conversion Rate＝Page View Conversion ÷ Impressions；Purchase继续仅使用`Google Shopping App Purchase (2)`，两套口径不得混算。
- 冻结产物：`outputs/weekly_report/W30/modules/M05_Google_Channel_Performance.html`。
- 当前下一任务仍为模块09 Meta国家表现验收，不得自行修改已冻结模块05。

## 2026-07-29｜模块04 Google整体表现（待验收：一级数据正确）

- 当前唯一 P0：模块04 `Meta与Google整体表现（过去4周＋周对周）`。
- 报告周期：W26–W29；本周W29为2026-07-19至2026-07-25，上周W28为2026-07-12至2026-07-18。
- Google主表和转化操作明细均已确认覆盖2026-06-14至2026-07-25，共42个自然日，支持过去4周。
- 购买口径只使用`Google Shopping App Purchase (2)`；Page View等非购买操作不得计入Purchase或Purchase Value。
- 输出边界：Meta与Google分别展示W26–W29；BI指标在前、平台ROI/CTR/CPC/CVR在后；每个渠道最后一行展示W29对W28并用颜色标记变化；不开发模块05六渠道拆分。
- 真实产物：`outputs/weekly_report/W29/modules/M04_Google_Overall_Performance.html`与`M04_reconciliation.xlsx`。
- 对账结果：W26–W29四周完整；BI严格只读取`Meta投放流量`和`GOOGLE投放流量`，完全重复记录先去重；Google W28 BI Spend由错误的$25,248.66修正为$12,624.33。
- 当前阶段：待用户进行一级数据正确验收。
- 模块01、02、03均保持冻结，不得修改。
- 禁止 Meta/Google 写操作、广告/预算修改、飞书发送、commit、push 和部署。

## 2026-07-29｜模块03 BI整体与渠道趋势（已冻结）

- 当前唯一 P0：模块03 `BI整体与渠道趋势图（W14–W30）`。
- 固定输出：Meta＋Google、Meta、Google Overall、Google Brand、Google NonBrand五张Cost柱形＋ROI折线同比图；Sales＋CR暂不展示。
- 数据覆盖：更新后的BI已覆盖2026 W14–W29与2025 W14–W30；2026 W30为未来周，显示N/A且不连线、不预测。
- 真实产物：`outputs/weekly_report/W29/modules/M03_BI_Overall_and_Channel_Trends.html`、`M03_reconciliation.xlsx`及`assets/M03/`五张正式SVG图。
- NonBrand只汇总Shopping、Category、PMAX、Discovery、YouTube，不包含Google Overall和Brand。
- 图表样式：2026 Cost橙色、2025 Cost黄色；2026 ROI实线逐点标注数值、2025 ROI虚线。
- 内部检查：170条图表周序列已生成；20项模块01–03测试通过；工作簿公式错误扫描为0。
- 模块01、02均保持冻结，不得修改。
- 禁止 Meta 写操作、广告/预算修改、飞书发送、commit、push 和部署。

## 2026-07-29｜模块02 Month to Date 表现（已冻结）

- 已完成并验收 `M02_Month_to_Date_Performance.html` 与 `M02_reconciliation.xlsx`。
- 固定比较窗口：本月至今 `2026-07-01` 至 `2026-07-25`；上月同期 `2026-06-01` 至 `2026-06-25`；去年同期 `2025-07-01` 至 `2025-07-25`。
- 固定对比：本月至今对上月同期显示 MoM；本月至今对去年同期显示 YoY。
- 数据覆盖：用户更新后的 BI 输入已补齐 `2026-06-16`；三个窗口各覆盖25个自然日、50个日期×渠道组，无冲突记录。
- 真实产物：`outputs/weekly_report/W29/modules/M02_Month_to_Date_Performance.html`、`outputs/weekly_report/W29/modules/M02_reconciliation.xlsx`。
- 对账结果：本月、上月同期和去年同期的源值与工作簿公式计算值差异均为0；同时展示 MoM 和 YoY；50条完全相同重复记录按模块01冻结规则去重。
- 已冻结模块01不得修改；本任务不涉及其他周报模块。
- 禁止 Meta 写操作、广告/预算修改、飞书发送、commit、push 和部署。

## 2026-07-29｜模块01 Week to Week 表现（已冻结）

- 当前唯一开发任务：独立生成并验收 `M01_Week_to_Week_Performance.html` 与 `M01_reconciliation.xlsx`。
- 数据周期：W29（2026-07-19至2026-07-25）对比上一完整自然周（2026-07-12至2026-07-18）。
- 当前阶段：用户已确认模块通过并允许冻结；模块01正式状态为“已冻结”。
- 真实产物：`outputs/weekly_report/W29/modules/M01_Week_to_Week_Performance.html`、`outputs/weekly_report/W29/modules/M01_reconciliation.xlsx`。
- 核对结果：四周均按BI字段`event_date(week)`筛选（`2026-29`、`2026-28`、`2025-29`、`2025-28`）并覆盖完整Sunday–Saturday 7天；模块同时展示WoW与YoY；仅纳入`Meta投放流量`和`GOOGLE投放流量`；Google细分渠道未重复加总；源数据14条完全重复记录已按保守规则去重。
- 不涉及 Month to Date、趋势图、Google/Meta细分、国家、人群、素材、总结与动作或完整周报。
- 禁止 Meta 写操作、广告/预算修改、飞书发送、commit、push 和部署。

## 2026-07-29 Weekly Report 模块化 Roadmap V1（已确认）

- 当前唯一 P0：模块02 `Month to Date表现`。
- 产品决定：Weekly Report V1 改为按最终报告中的13个业务模块逐个开发、逐个三级验收、逐个冻结，不再整份同时修改；Meta人群表现保留为独立模块。
- 展示范围校正：BI趋势固定W14–W30；Google整体和分渠道、Meta整体均展示过去4周及WoW；Meta国家同时展示平台整体和账户层级。
- 当前状态：Roadmap已由用户确认；模块01为“已冻结”；模块02为“待验收（一级：数据正确）”；其余模块为“未开始”。
- 两份最终输出：`02_领导周报.html` 组合整体/渠道/账户/国家/素材摘要/总结模块；`01_素材聚合分析.html` 组合素材总体/素材细化/视频拆解/素材复核摘要。
- 用户已确认模块02通过；状态改为“已冻结”，后续模块不得修改。
- 入口：`WEEKLY_REPORT_MODULE_ROADMAP.md`。
- 本轮边界：只更新产品与项目管理文档；不修改业务代码、测试、工作流，不生成周报，不发送飞书，不进行Meta写操作，不commit、不push、不部署。

## 2026-07-27 Weekly Report V1｜W29 正式模块生成（待业务验收）

- 负责人：Codex / Tech Lead。
- 状态：真实 W29 数据生成与技术验收完成，等待用户打开两份 HTML 进行业务验收。
- 周期：W29，2026-07-19 至 2026-07-25，Sunday–Saturday。
- 已生成：整体表现、Week to Week、Month to Date、Meta＋Google/Meta/GG Overall/GG Brand/GG NonBrand 五张 W14–W30 Cost＋ROI 图、Google 六个细分渠道近4周表现、Google 真实 Purchase、Meta 层级与素材模块。
- 真实结果：60 条有花费 Performance 广告、31 个去重素材、60/60 广告有本地图片、38 行国家数据；素材聚合合并 29 条重复广告表现。
- 数据完整性：BI 覆盖至 2026-07-25；Google Performance 与 Conversion Actions 覆盖至 2026-07-25，W29 无缺失日期。
- 测试：39 项相关测试通过，`git diff --check` 通过。
- 当前唯一下一步：用户打开 W29 两份 HTML，验收整体表现、周/月对比、五张趋势图、Google 明细和素材内容。
- 已知限制：真实 Meta audience breakdown 输入尚未覆盖 W29，因此人群模块保留明确缺失说明，不使用 Campaign 名称猜测。
- 禁止：广告写操作、预算调整、飞书发送、未经授权的 commit/push/deploy。

## 2026-07-26 Weekly Report V1｜W29实时Meta API双HTML（待业务验收）

- 负责人：Codex / Tech Lead。
- 状态：程序接线修复、真实W29只读生成和技术验收完成；等待用户打开两份HTML进行业务验收。
- 周期：W29，2026-07-19至2026-07-25，Sunday–Saturday。
- 数据链路：BI和Google读取桌面Excel；Meta广告层级、表现、素材标识和国家Breakdown直接读取Meta API；QMDT人群按Campaign名称是否包含`RTG`拆分；素材使用登记表稳定Ad Name关键词和本地素材库匹配。
- 真实结果：60条Performance有花费广告，层级完整60条；聚合为31个素材单元，其中27个有本地图片、4个缺图单元；广告级54条有图、6条缺图；国家Breakdown 45行。
- 产物：`outputs/weekly_report/W29/01_素材聚合分析.html`、`02_领导周报.html`、`Review_Required.xlsx`及`assets/`。
- 验证：35项相关测试通过；两份HTML无W28文本残留，47个图片/图表引用全部存在；Review中6条缺图广告均保留Raw Ad Name、账户、Campaign、Ad Set、Spend和原因。
- 下一步：用户打开两份W29 HTML进行业务验收；确认后再决定是否整理为独立提交和PR。
- 禁止：预算调整、广告写操作、飞书发送、未经授权的commit/push/deploy。

## 2026-07-24 素材爆量与商业效率分类 V1（待业务验收）

- 负责人：Codex / Tech Lead。
- 状态：规则实现、真实W28生成和自动测试完成；等待用户打开HTML进行业务视觉与内容验收。
- 时间与层级：完整自然周2026-07-12至2026-07-18；素材 × Performance账户 × 新客/老客，Brand不参与。
- 规则：Purchase≥10后依次判断ROAS最低安全线2、ROAS商业目标3和CPA目标$95；CPA达标不能覆盖ROAS<2。
- 真实W28结果：商业爆款1个分群、高量待优化1个分群、高量低效1个分群；其余32个分群因Purchase<10不进入爆量分类。
- 展示：报告首页按商业爆款、高量待优化、高量低效固定顺序展示素材、账户、分群、Spend、Purchase、ROAS、CPA、标签和触发原因。
- 验证：24项相关测试通过，包含全部边界案例、缺失值、完整7天、Brand排除、新客/老客不同标签、固定顺序及排序。
- 产物：`outputs/weekly_report/W28/01_素材聚合分析.html`。
- 下一步：用户刷新本地HTML验收分类内容；通过后继续W28素材拆解分析第二版的账户/同类素材基准与视频分秒结构。
- 禁止：预算调整、暂停广告、Meta写操作、飞书发送、未经授权的commit/push/deploy。

## 2026-07-24 Weekly Report V1：W28素材拆解分析第二版（当前唯一开发P0）

- 复审修复：第一版因大量N/A且未拆解高表现视频结构未通过；第二版已用源表计数与比率反推分母后重新聚合，并增加6个高花费且购买样本较充分视频的0–3秒Hook、Body、Close和结构模式拆解。
- 负责人：Codex / Tech Lead。
- 状态：第一轮真实W28 HTML已生成并完成业务复审；第二版仍需补齐账户/同类素材基准对比、视频指标和分秒结构拆解，验收通过前不宣告P0完成。
- 真实产物：`outputs/weekly_report/W28/01_素材聚合分析.html`。
- 数据结果：66条W28 Performance广告；29个登记去重素材；29个素材均有1080×1080本地方形预览；63条广告已匹配，3条进入人工复核。
- 分类结果：QMDT中Campaign名称包含`RTG`的1个Campaign归入老客/再营销，其余4个归入新客；销售三部唯一Campaign不拆分。
- 已修复：图片与视频指标分离；同素材多广告聚合；`Mix & match`按真实广告账户归入销售三部；重复`beyondtrends`按文件SHA-256合并；所有支持的ROAS/AOV/CPA由聚合分子分母重算。
- 数据边界：源表缺少原始All Clicks、Impressions、CPM、3秒播放、100%播放和素材×国家Breakdown；对应聚合指标显示`N/A`并注明原因，图片视频指标显示“不适用”。
- 验证：8项自动测试通过；29张预览均为非空1080×1080图片；未调用Meta写接口、未发飞书、未修改广告或预算。
- 下一步：完成W28素材拆解分析第二版，补齐账户/同类素材基准对比、视频指标和分秒结构拆解；业务验收通过后，再整理为独立提交和PR。
- 禁止：Meta写操作、预算Apply、飞书发送、未经授权的commit/push/deploy。

## 2026-07-23 生产事故：Morning ROAS 缺失（已完成并关闭）

- 负责人：Codex / Tech Lead。
- 状态：已完成。修复分支`fix/realtime-meta-roi`的提交`e351fdc`已通过PR #1合并到`main`，合并提交为`809e045`。
- 目标：保持 Morning 固定截止时间，同时处理 Meta 单个小时行遗漏 Purchase Value 的情况。
- 修复：Morning/Early Pulse 的当前账户日改用 Meta 账户级汇总 `action_values`，与 Ads Manager 报表读取方式一致；历史同期比较仍使用小时截止拆分。
- 验证：38项定时报表和Meta Provider测试通过；用户已真实收到修复后的Morning Report，并于2026-07-24确认验收通过。
- 结论：不存在待合并、待部署或待真实Morning Report验收事项，本任务已关闭。
- 禁止：Meta 写操作、Budget Apply、伪造 Purchase Value、未经授权 commit/push。

## 2026-07-21 Weekly Report Automation V1｜Excel素材库与双HTML（当前唯一开发P0）

- Creative登记输入已简化：桌面 `04_Creative_Analysis_Input` 只保留一份 `素材登记表.xlsx`；用户每个素材填写一行和稳定Ad Name关键词，不再逐广告填写Account、Campaign、Ad Set或Raw Ad Name。
- `新素材/已有素材`不是用户固定字段：周报按首次花费是否发生在本周自动判断，素材会按最近7天判断；无法取得首次花费日期时显示`待确认`。
- 日期规则：不要求用户填写周次、报告开始日期和报告结束日期；周报自动使用固定Sunday-Saturday，素材会按当前在投或最近7天有花费素材生成。
- 当前5个真实素材已从旧W28映射表去重迁移到唯一登记表；后续开发接入关键词候选搜索、Meta只读自动映射和异常复核。
- 最新方向：正式交付物改为 `01_素材聚合分析.html` 与 `02_领导周报.html`；Word/DOCX路线停止。
- 正式素材源：`Weekly_Report_V1_Input/01_Raw_Data/Meta/周报-素材表现.xlsx` 的真实W28工作表；优先提取Excel嵌入图片，不批量访问Meta。
- 当前实现：W28已识别66条Performance广告记录、65张嵌入图，全部层级映射成功；生成31个自动归并后的唯一素材、23组疑似重复复核项和1条缺图项。
- 当前产物：`outputs/weekly_report/W28/01_素材聚合分析.html`、`02_领导周报.html`、`Review_Required.xlsx`；素材目录为`creative_library/assets/`。
- 当前状态：本地生成和18项周报相关测试通过，等待业务打开两份HTML验收；P0尚未由用户确认完成。
- HTML业务验收：用户确认本次两份HTML报告效果完美；素材库按最新要求只保留`square_preview.jpg`，不保留`original.*`。
- 下一步：人工核对素材视觉去重、65张低清Excel图的可接受性，以及缺图广告是否需要单独从Meta补图。
- 禁止：Word重构、自动写入飞书、Meta批量截图、广告写操作、未经授权commit/push/deploy。

## 历史任务：Weekly Report V1 模板固化与素材模块修复

- 决策：定时报表已经部署并完成人工真实验收，后续自然触发属于后台生产观察，不阻塞周报开发。
- 目标：严格按照最新人工周报完成固定模板和Creative模块修复，优先解决素材完整性、方形高清缩略图、缓存复用和固定层级排序。
- 需求与验收单一来源：`WEEKLY_REPORT_V1_FIXED_TEMPLATE_ACCEPTANCE.md`。
- 开发顺序：先提交页码/模块/数据源/差距对应表；确认后优先修Creative，再完成整份周报逐页一致性。
- 视频诊断范围：展示Hook Rate、50%/75%/95%/ThruPlay留存及人工版本映射；不自动判胜、拼接视频或输出投放动作。
- 禁止：重新设计周报、增加自动预算调整、广告写操作、未经授权commit/push。
- 定时报表处理方式：继续后台观察；只有出现漏发、重复、ROAS异常或延迟超过30分钟时，才作为生产事故打断周报开发。
- 当前状态：W27真实产物已重新生成，开发侧9项代码测试与15项交付检查通过；等待业务打开DOCX、Creative HTML、Review和逐页材料验收，尚未宣告P0完成。
- 数据核对：两个Performance账户共63条Spend大于0广告（QMDT 56、销售三部7），42个去重素材键；34条仅有低清源图并显示统一占位进入Review，29条复用可用方形素材。
- 当前交付目录：`outputs/weekly_report/W27-fixed-template`。

## 后台观察：三个定时报表调度可靠性

- 已完成：Cloudflare Worker、15分钟Cron、`SCHEDULER_STATE` KV和`GITHUB_TOKEN` Secret首次部署；三个报告人工触发并真实送达飞书。
- 已修复：Cloudflare dispatch HTTP 400；实时小时数据中空Purchase Value覆盖有效值造成Performance ROAS为N/A。
- 已部署：main commit `6d86d74`，36项相关测试通过。
- 已验证：Daily Close中QMDT ROAS 3.65、销售三部ROAS 8.94、Performance汇总ROAS 4.48、三账户Overall ROI 4.27。
- 实时ROI事项已完成：修复后的Morning Report已真实送达并由用户验收通过；不再列入待发布或待验收。
- 剩余观察仅限独立的调度可靠性记录：Morning、Daily Close、Early Pulse的自然触发时效和重复消息情况。
- 2026-07-22观察时段：09:00-09:14、15:30-15:44、18:00-18:14；记录Cloudflare触发、GitHub开始、飞书送达、ROAS和重复消息。
- 观察完成条件：三个报告自然触发全部成功、Performance ROAS正确或有明确原因、无重复发送；随后继续完成3个自然日并行观察。
- 旧GitHub `schedule`在3日观察通过前不得关闭；人工`workflow_dispatch`继续保留。
- 观察期间不继续添加调度功能；不执行预算调整或广告写操作。

## Weekly Report V1 既定需求

- 角色：产品定义与验收；本阶段只定义规则，不修改程序。
- 目标：以最新人工周报 `投放周报｜week 27.docx` 为唯一视觉和结构标准，冻结模块顺序、页码映射、数据来源、列顺序、排序、数字格式、颜色、人工判断边界和逐页验收规则。
- 素材重点：两个Performance账户分别完整展示；Account → Campaign → Ad Set → Creative；各层按Spend降序；统一方形完整画面；建立高清缓存复用；低清、缺图、Flexible和权限不足进入明确复核流程。
- 视频诊断新增：Creative Report展示3秒Hook Rate、50%/75%/95%/ThruPlay留存，并支持人工填写Creative Family、Hook Variant和Body Variant；当前只做客观比较与“值得继续验证”标记，不自动判胜或拼接视频，样本门槛待03确认。
- 明确不包含：预算调整、放量/暂停/更换素材策略、Google API、BI API、新Dashboard或新周报视觉设计。
- 需求与验收单一来源：`WEEKLY_REPORT_V1_FIXED_TEMPLATE_ACCEPTANCE.md`。
- 下一步：先由用户确认本文规则，再交给02按页实现和提交视觉验收材料。
- 原Budget Alert/Cloudflare调度进入已记录的独立上线观察，不得打断本任务；旧schedule仍须按3天并行规则后再关闭。

## 历史任务：2026-07-20 Budget Alert P0

- 真实告警已于 2026-07-20 13:45:55 送达销售三部账户，第二次正式运行已验证 24 小时去重生效。
- 告警正文已精简为账户、账户 ID、当前余额、近 7 个完整日的日均花费、3 天阈值、预计剩余天数、触发原因和充值动作。
- 每小时第 17 分钟主检查、第 47 分钟漏跑恢复、单实例并发锁、状态预检、延迟告警和执行日志已在本地实现并通过测试。
- 当前唯一下一步：在不违反“不得 commit、不得 push”的限制下等待部署授权；部署后验证 GitHub Actions 主检查、恢复检查和状态缓存。
- P1 定时报表和 W28 周报继续暂停。

### 调度切换保护规则（用户无需操作）

- Cloudflare 上线后，暂时保留 GitHub 原有定时调度，新旧调度进入并行观察期。
- 并行期间使用同一业务日期/时段的去重规则，避免同一条告警或报告重复发送。
- 至少完成四类任务真实验收，并连续观察 3 个自然日；确认无漏发、无重复、90% 在计划时间后 30 分钟内送达，才允许关闭 GitHub 原有 `schedule`。
- 关闭动作由 02 执行并回报，不要求用户修改工作流；关闭后仍保留人工补跑入口。

## 2026-07-17 W27 正式交付修复状态

- 当前唯一 P0：周报自动化 V1 的 W27 正式交付人工验收。
- 开发状态：输出层修复和真实只读生成已完成；P0 **尚未完成**，等待人工打开四个产物验收。
- 真实产物目录：`outputs/weekly_report/W27-delivery`。
- 已生成：`投放周报｜W27.docx`、`Weekly_Report.xlsx`、`Creative_Report.html`、`Review_Required.xlsx`。
- 真实数据范围：2026-07-05 至 2026-07-11；素材仅包含两个指定 Performance 账户，共 63 个有消耗广告。
- 当前 Blocker：Meta Token 可读取 Ad Creative 和 `asset_feed_spec`，但对 Video 对象的 `picture` / `thumbnails` / `source` 返回权限错误 `(#10)`。因此 34 个长边不足 600 像素的素材已进入 Creative Review；其中 6 个 64×64 预览禁止在正式 HTML 中展示。此限制不能伪装为高清识别成功。
- 下一步：人工验收四个 W27 产物，并补充可读取 Video 高清首帧的 Meta 权限后复验低清素材。
- 禁止事项：不执行 Budget Apply，不调整预算，不暂停、创建或修改广告，不发送飞书周报。

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
6. 正式周报增加 Google 六个细分渠道近 4 周表现，以及 GG Overall、GG Brand、GG NonBrand 三张 W14-W30 同比 Cost + ROI 图。NonBrand 仅汇总购物、品类词、PMAX、探索和 YouTube，禁止与 Google 总计或品牌词重复。
7. 输出整体花费与账户级核心指标。
8. Performance 账户展示 Purchase、Revenue、ROAS、CPA、CTR。
9. Brand 账户展示 Spend、Reach、Impressions、Frequency、CTR；不使用 Purchase ROAS 判断其健康状态。
10. Meta 人群映射固定为：`prospecting` / `engaged` = 新客，`existing` = 老客/再营销，`uncategorized` / `unknown` = 未识别。
11. Meta Purchase CVR、Add to Cart Rate 和 Checkout Rate 均使用 All Clicks 作为分母；分母为零或缺失时显示不可用。
12. Creative Analysis 只覆盖 QMDT—20240103 / `750289240467952` 和销售三部—新主页账户 / `5600626876733411` 两个 Performance 账户中报告期内所有有消耗广告；Brand 账户不进入素材报告。输出层级、缩略图、素材标识、指标、匹配方式和复核状态。
13. 生成 `Weekly_Report.xlsx`、`Creative_Report.html` 和 `Review_Required.xlsx`。
14. 支持人工立即生成，定时触发不是本次交付的前置条件。

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
# Current Task Update — 2026-07-20

- Owner: Codex / Tech Lead
- Priority: P0
- Status: Local implementation complete; deployment blocked pending Cloudflare KV/secret setup and explicit deployment authorization.
- Goal: Restore Budget Alert delivery, make Performance ROAS traceable, add report idempotency/timing logs, and use a free Cloudflare Cron Worker only to dispatch GitHub Actions.
- Completed: Real Budget Alert delivery and immediate de-duplication validation; local ROI/missing-reason fix; report run-key de-duplication; workflow concurrency/state cache; Cloudflare 15-minute dispatcher implementation.
- Next action: Create/bind Cloudflare KV `SCHEDULER_STATE`, store the fine-grained GitHub token as Cloudflare secret `GITHUB_TOKEN`, then authorize deployment and the four workflow-dispatch acceptance tests.
- Prohibited: Budget Apply, Meta writes, AI calls, credential logging, committing or pushing without explicit authorization.
# 2026-07-29｜模块05 Google分渠道表现（待验收）

- 当前唯一开发 P0：模块05 `Google分渠道表现（过去4周＋周对周）`。
- 模块04已由用户确认通过并冻结；模块01–04均不得在本任务中修改。
- 固定六渠道顺序：购物广告、品牌词、品类词、PMAX、探索广告、YouTube。
- 数据周期：W26–W29；每个渠道最后一行展示W29对W28变化。
- BI指标在前、Google平台指标在后；Purchase与Purchase Value只使用`Google Shopping App Purchase (2)`。
- Google Overall仅用于与模块04对账，不加入六渠道明细。
- 真实产物：`outputs/weekly_report/W29/modules/M05_Google_Channel_Performance.html`与`M05_reconciliation.xlsx`。
- 当前阶段：待用户进行一级数据正确验收。
- 禁止广告/预算写操作、飞书发送、commit、push和部署。
# 2026-07-30｜模块06 Meta整体表现（待验收）

- 模块05已由用户确认通过并冻结；当前唯一开发P0为模块06。
- 输出Meta整体W26–W29、W29对W28，以及三个账户同期贡献。

# 2026-07-30｜模块07 Meta Campaign表现（已冻结）

- 模块06已由用户确认通过并冻结。
- 用户已确认模块07通过并冻结；产物为 `M07_Meta_Campaign_Performance.html` 与 `M07_reconciliation.xlsx`。
- 日期：W29 `2026-07-19`–`2026-07-25`，对比W28 `2026-07-12`–`2026-07-18`。
- 主页面将两个Performance账户合并为一个Campaign花费排名，展示Campaign Name、Spend、Performance合计Spend Share和ROI，不展示账户标题或Account字段。
- 销售三部Campaign标记为`Life线`；QMDT Campaign名称包含`RTG`时标记为重点投老客/再营销；Brand账户不进入模块07。

# 2026-07-30｜模块08 Meta人群表现（已冻结）

- 模块07已经用户验收通过并冻结，后续模块不得修改。
- 输入：`Meta_AI_受众新老客分析_上周样例.xlsx`，现已覆盖W28与W29两个完整自然周。
- 两个Performance账户合并汇总；明细展示Prospecting、Engaged、Existing，低量Unknown与Uncategorized仅保留在底层对账。
- `existing`归老客；`prospecting`、`engaged`、`unknown`、`uncategorized`归新客。
- 输出：`M08_Meta_Audience_Performance.html`与`M08_reconciliation.xlsx`。
- 用户已确认模块08通过并冻结。
- 真实结果：W29五类人群合计Spend为 `$12,464.22`，与模块06两个Performance账户合计完全一致；Review Required为空。
- 页面已增加新客/老客图表概览，展示W29花费占比、可归属ROI及对比W25–W28前4周均值。
- 数据边界：Meta Breakdown将“点击量（全部）”集中归入uncategorized；unknown部分Purchase Value为空。页面保留源值，不改用Link Clicks，并用ROI覆盖率标识可归属口径。
- 禁止事项：不修改已冻结模块，不执行Meta写操作，不调整广告或预算，不发送飞书，不commit、不push。

# 2026-09-20｜Jelenew+ Meta账户纳入范围

- 新增账户：`Jelenew+` / `1614799860253372`，类型为 Performance、非 Brand、Life 线。
- 已纳入 Meta 花费、Purchase Value、ROAS、Campaign、国家、素材和后续调价范围；统一受 `$2,500` 总日预算上限约束。
- 人群规则沿用既有口径：Campaign 名称含 `RTG` 归老客/再营销，其余归新客。
- W37 已重跑 M07、M09、M12；M08 当前源导出未包含 Jelenew+，待补新账户的受众导出后重跑。
- 未执行 Meta 写操作、预算调整、部署、提交或推送。

# 2026-07-30｜模块09 Meta国家表现（历史开发记录，现已冻结）

- 模块08已由用户确认通过并冻结。
- 输入：Meta API只读国家Breakdown，覆盖W25–W29两个Performance账户。
- 展示口径：两个Performance账户合并，只展示国家综合表现，不拆账户。
- 输出：`M09_Country_Performance.html`与`M09_reconciliation.xlsx`。
- 该条为历史验收前记录；模块09最终状态为已冻结。
- 真实结果：W29共36个国家；Spend合计`$12,464.22`，与模块06两个Performance账户合计完全一致；API与对账Review均为0。
- 禁止事项：不修改已冻结模块，不执行Meta写操作，不调整广告或预算，不发送飞书，不commit、不push。
# 2026-09-04｜独立素材生命周期模块12样式版

- 用户确认按最后消耗日作为无在投素材终点，仍在投算至9月4日；三栏为>28天、8—28天、≤7天。
- 独立产物：outputs/creative_lifecycle/2026-08-31/素材生命周期_模块12版.html；不替换冻结周报。
- 6—8月66条（22/33/11），8月52条（18/25/9）；期间Purchase与Purchase Value使用项目别名优先级及统一广告组归因设置。
- 两账户花费、Purchase对账一致，Purchase Value最大舍入差0.01美元；期间视频均有本地封面。浏览器安全策略阻止自动预览，已执行静态校验。
- 未部署、未提交、未推送、未执行广告写操作。
# 2026-09-28｜飞书调价审批卡 V1 阶段 A

- 已向当前 Budget Alert 飞书群发送 1 张 `调价建议｜测试卡｜只读影子验证`，平台返回 HTTP 200 / success。
- 卡片只展示影子建议：使用美国账户最近完整投放日 2026-09-27，以及近 3 / 近 7 个完整投放日；不包含尚未结束的 9 月 28 日。
- 展示对象为 ABO Ad Set：`facebook-life-abo-int-new creative test`，影子建议 `$120 → $144`（+20%）。
- 卡片无“同意 / 拒绝”可执行按钮，明确写明不会调整 Meta 预算与 `不可执行：测试 / 只读影子验证`。
- 本轮 Meta 写调用为 0；未修改预算、广告或状态；未部署、未提交、未推送。
- 下一阶段仅盘点飞书自建应用机器人、加群和卡片回调所需权限；未经用户后续授权，不创建应用、不配置密钥、不部署回调。
# 2026-10-08｜M12 素材表现库 V1（本地只读）

- 已生成首版可按日期、账户、新客/老客及素材名称筛选的素材表现库，日期覆盖 `2026-07-17` 至 `2026-10-07`。
- 历史来自 W31–W38 的 M12 快照；重叠日期按最新快照去重。已用 Meta 只读广告级接口补齐 `2026-09-27` 至 `2026-10-07`。
- 数据结果：180 个“素材 × 账户 × 新老客”表现行、2,627 条日事实；Meta 写调用为 0。
- 1 个 Jelenew+ 广告在 7 个日记录中未匹配素材登记表，明确保留为待映射，未错误并入其他素材。
- 输出：`outputs/creative_performance_library/2026-10-07/素材表现库_截至2026-10-07.html` 与 `creative_daily_facts.json`。
