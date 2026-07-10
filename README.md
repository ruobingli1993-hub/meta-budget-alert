# Meta 广告账户预算预警

这个项目用于检查 Meta 广告账户余额。当当前余额低于过去 7 天平均日花费的 3 倍时，通过飞书群机器人发送告警。

## 账户配置

账户统一维护在 `config.py` 的 `ACCOUNT_CONFIGS` 中：

| 名称 | 类型 | Ad Account ID |
| --- | --- | --- |
| QMDT—20240103 | performance | 750289240467952 |
| 销售三部—新主页账户 | performance | 5600626876733411 |
| Jelenew-Brand & Lab | brand | 568835832834495 |

预算预警 `--check-budget` 只监控 `performance` 账户。Morning Report V1 会遍历全部三个账户。

## 安装

```bash
cd meta-budget-alert
python3.11 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Windows PowerShell:

```powershell
cd meta-budget-alert
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

## 配置

复制示例文件：

```bash
cp .env.example .env
```

填写环境变量：

```env
META_ACCESS_TOKEN=your_meta_marketing_api_access_token
FEISHU_WEBHOOK_URL=https://open.feishu.cn/open-apis/bot/v2/hook/your-webhook-token
```

`META_ACCESS_TOKEN` 需要具备读取广告账户与 Insights 数据的权限，例如 `ads_read`。

## Dry Run 测试

dry-run 模式不会调用 Meta API，也不会发送飞书消息，只使用本地模拟数据验证程序流程：

```bash
python main.py --dry-run
```

也可以通过环境变量启用：

```bash
DRY_RUN=true python main.py
```

Windows PowerShell:

```powershell
$env:DRY_RUN="true"
python main.py
```

## 真实运行

确认 `.env` 中配置了真实的 `META_ACCESS_TOKEN` 和 `FEISHU_WEBHOOK_URL` 后运行：

```bash
python main.py --check-budget
```

## Morning Report V1

Morning Report V1 是独立报告命令，不会修改 `state.json`，也不会影响预算预警命令：

```bash
python main.py --morning-report
```

报告顺序固定为：

1. Overall Total Summary
2. Account Performance Summary
3. Campaign Ranking

报告会自动遍历 `config.py` 中配置的三个账户。

Morning Report 的 Balance 使用账户花费限额剩余额度：

```text
account_spend_limit - amount_spent
```

如果 Meta API 没有返回账户花费限额，报告会显示：

```text
Balance source unavailable
```

Campaign Ranking 暂时只输出每个账户的 Top 1 Campaign 和 Bottom 1 Campaign，不输出 Pause、Scale、Increase Budget 或其他强动作建议。

## 去重状态

`state.json` 用于记录每个账户是否已经处于告警状态。只要余额持续低于阈值，就不会重复发送告警；当余额恢复到阈值以上后，再次跌破才会重新发送。

## Budget Manager Skill V1

Budget Manager 是高风险预算管理流程，默认必须 `NO_CHANGE`。它不会自动运行，也没有接入 GitHub Actions。

先只运行预览：

```bash
python main.py --budget-manager-preview
```

Preview 会：

- 真实读取两个 Performance Account
- 不修改预算
- 不修改 `state.json`
- 发送飞书预览
- 同时在终端输出
- 保存快照到 `logs/budget_previews/<RUN_ID>.json`

不要在确认 preview 前运行 apply。

执行命令需要指定 RUN_ID，并且必须手动输入精确的 `APPLY`：

```bash
python main.py --budget-manager-apply RUN_ID
```

回滚命令需要指定 RUN_ID，并且必须手动输入精确的 `ROLLBACK`：

```bash
python main.py --budget-manager-rollback RUN_ID
```

Budget Manager 规则统一维护在：

```text
skills/budget_manager/config.json
```

运行日志和快照保存在 `logs/` 下，本地不会提交。

## Meta Automation Dashboard V1

Dashboard is a local Streamlit workspace for reviewing Budget Manager Preview suggestions.

Start it from Windows CMD:

```cmd
streamlit run dashboard/app.py
```

Local address:

```text
http://localhost:8501
```

Dashboard V1 only reads local files and does not call Meta API:

- `logs/budget_previews/<RUN_ID>.json`
- `data/approvals/<RUN_ID>.json`
- `data/rule_feedback/*.json`

Approval records are saved to:

```text
data/approvals/<RUN_ID>.json
```

The dashboard supports Overall Summary, Account Status, Budget Review Queue, Approve / Reject / Skip records, Batch Reject, Batch Skip, Rule Feedback summary, and rejection summary export.

Approve only means "review approved" in Dashboard V1. It does not execute Meta API writes or change any real budget.

Feishu Budget Manager Preview messages are now concise summaries with a View More line. Set the optional environment variable:

```env
DASHBOARD_URL=http://localhost:8501
```

If `DASHBOARD_URL` is not configured, Feishu shows:

```text
Dashboard URL not configured
```

Close the dashboard with `Ctrl+C` in the terminal where Streamlit is running.

## Scheduled Meta Reports

Three concise Feishu reports share the same command, Meta Data Provider, health logic, Feishu sender, and Dashboard URL handling:

```bash
python main.py --scheduled-report morning
python main.py --scheduled-report daily-close
python main.py --scheduled-report early-pulse
```

Report slots use Beijing time, while Meta data boundaries use each ad account's timezone:

| Mode | Beijing Time | Purpose |
| --- | --- | --- |
| `morning` | 09:00 | Realtime same-time-window report |
| `daily-close` | 15:30 | Previous complete ad-account day close |
| `early-pulse` | 18:00 | New ad day early startup pulse |

Feishu only receives a concise summary and a View More line. Configure:

```env
DASHBOARD_URL=http://localhost:8501
```

If not configured, the report shows:

```text
Dashboard URL not configured
```

Scheduled report logs are written to:

```text
logs/scheduled_reports.log
```

GitHub Actions workflow:

```text
.github/workflows/scheduled_reports.yml
```

## GitHub Actions

仓库已包含 GitHub Actions workflow：

```text
.github/workflows/check_budget.yml
```

它会在北京时间每天 09:00 自动运行一次。GitHub Actions 使用 UTC 时间，因此对应 cron 为：

```yaml
0 1 * * *
```

运行命令：

```bash
python main.py --check-budget
```

需要在 GitHub 仓库的 Secrets 中配置：

| Secret | 说明 |
| --- | --- |
| `META_ACCESS_TOKEN` | Meta Marketing API Access Token |
| `FEISHU_WEBHOOK_URL` | 飞书群机器人 Webhook |

## Linux Cron

北京时间每天 09:00 执行：

```cron
0 9 * * * cd /path/to/meta-budget-alert && /path/to/meta-budget-alert/.venv/bin/python main.py --check-budget >> /path/to/meta-budget-alert/budget-alert.log 2>&1
```

如果服务器使用 UTC 时区：

```cron
0 1 * * * cd /path/to/meta-budget-alert && /path/to/meta-budget-alert/.venv/bin/python main.py --check-budget >> /path/to/meta-budget-alert/budget-alert.log 2>&1
```
