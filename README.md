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
