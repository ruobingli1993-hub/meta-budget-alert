import os, json, requests
TOKEN=os.environ["META_ACCESS_TOKEN"]; V=os.environ.get("META_API_VERSION","v20.0")
B=f"https://graph.facebook.com/{V}"
ACC=[("QMDT","750289240467952"),("销售三部","5600626876733411"),("Jelenew+","1614799860253372"),("Jelenew-Brand","568835832834495")]
def get(path, params):
    r=requests.get(f"{B}/{path}", params={**params,"access_token":TOKEN}, timeout=40)
    try:
        j=r.json()
    except Exception:
        j={"raw":r.text[:200]}
    if r.status_code!=200:
        print("HTTPERR|"+path+"|"+str(r.status_code)+"|"+json.dumps(j,ensure_ascii=False)[:200])
        return {}
    return j
for nm,aid in ACC:
    info=get(f"act_{aid}",{"fields":"id,name,currency,timezone_name,account_status"})
    print("ACC|"+nm+"|"+json.dumps({k:info.get(k) for k in ["name","currency","timezone_name","account_status"]},ensure_ascii=False))
    camps=get(f"act_{aid}/campaigns",{"fields":"id,name,objective,daily_budget,lifetime_budget,effective_status","limit":"100"}).get("data",[])
    for c in camps:
        if c.get("effective_status")=="ACTIVE":
            print(f"CAMP|{nm}|{c['name'][:70]}|{c.get('objective')}|{c.get('daily_budget') or ''}|{c.get('lifetime_budget') or ''}")
    ads=get(f"act_{aid}/adsets",{"fields":"name,daily_budget,lifetime_budget,effective_status,optimization_goal,campaign{name}","limit":"200"}).get("data",[])
    for a in ads:
        if a.get("effective_status")=="ACTIVE":
            print(f"ADSET|{nm}|{a['name'][:60]}|{a.get('daily_budget') or ''}|{a.get('lifetime_budget') or ''}|{(a.get('campaign') or {}).get('name','')[:40]}")
