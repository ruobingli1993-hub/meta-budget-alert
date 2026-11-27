import os, json, requests
TOKEN=os.environ["META_ACCESS_TOKEN"]; V=os.environ.get("META_API_VERSION","v20.0")
B=f"https://graph.facebook.com/{V}"
def get(path, params):
    r=requests.get(f"{B}/{path}", params={**params,"access_token":TOKEN}, timeout=90)
    if r.status_code!=200:
        print("HTTPERR|"+path+"|"+str(r.status_code)+"|"+r.text[:300]); return {}
    return r.json()
# 1) 小时粒度是否可用
for tr in ['{"since":"2026-11-27","until":"2026-11-27"}','{"since":"2026-11-26","until":"2026-11-26"}']:
    d=get("act_750289240467952/insights",{"fields":"spend,impressions,clicks,actions",
        "breakdowns":"hour","time_range":tr,"level":"account","limit":"100"})
    rows=d.get("data",[])
    print(f"HOURLY|{tr}|rows={len(rows)}|sample={json.dumps(rows[:3],ensure_ascii=False)[:400]}")
# 2) 账户当前时间（用于判断"今天"落在哪一天）
for aid in ["750289240467952","5600626876733411","1614799860253372"]:
    i=get(f"act_{aid}",{"fields":"name,timezone_name,account_status"})
    print("ACC|"+json.dumps(i,ensure_ascii=False))
