import os, json, requests
TOKEN=os.environ["META_ACCESS_TOKEN"]; V=os.environ.get("META_API_VERSION","v20.0")
B=f"https://graph.facebook.com/{V}"
TR='{"since":"2026-11-26","until":"2026-11-26"}'
def try_q(tag, params):
    r=requests.get(f"{B}/act_750289240467952/insights", params={**params,"access_token":TOKEN}, timeout=90)
    if r.status_code!=200:
        print(f"FAIL|{tag}|{r.text[:220].replace(chr(10),' ')}"); return
    d=r.json().get("data",[])
    print(f"OK|{tag}|rows={len(d)}|{json.dumps(d[:2],ensure_ascii=False)[:350]}")
try_q("hourly_breakdown_enum", {"fields":"spend,actions","breakdowns":"hourly_stats_aggregated_by_advertiser_time_zone","time_range":TR,"level":"account"})
try_q("hour_level_ad", {"fields":"spend,actions","breakdowns":"hour","time_range":TR,"level":"ad","time_increment":"1","limit":"50"})
try_q("hour_level_campaign", {"fields":"spend,actions","breakdowns":"hour","time_range":TR,"level":"campaign","limit":"50"})
try_q("daily_baseline", {"fields":"spend,actions,clicks,impressions","time_range":TR,"level":"account","time_increment":"1"})
