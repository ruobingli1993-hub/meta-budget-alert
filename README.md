# Meta 广告账户预算预警

这个项目用于检查 Meta 广告账户余额。当当前余额低于过去 7 天平均日花费的 3 倍时，通过飞书群机器人发送告警。

## 监控账户

| 名称 | Ad Account ID |
| --- | --- |
| QMDT—20240103 | 750289240467952 |
| 销售三部—新主页账户 | 5600626876733411 |

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
python main.py
```

## 去重状态

`state.json` 用于记录每个账户是否已经处于告警状态。只要余额持续低于阈值，就不会重复发送告警；当余额恢复到阈值以上后，再次跌破才会重新发送。

## Linux Cron

北京时间每天 09:00 和 18:00 执行：

```cron
0 9,18 * * * cd /path/to/meta-budget-alert && /path/to/meta-budget-alert/.venv/bin/python main.py >> /path/to/meta-budget-alert/budget-alert.log 2>&1
```

如果服务器使用 UTC 时区：

```cron
0 1,10 * * * cd /path/to/meta-budget-alert && /path/to/meta-budget-alert/.venv/bin/python main.py >> /path/to/meta-budget-alert/budget-alert.log 2>&1
```
