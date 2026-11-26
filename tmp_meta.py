import os, json, requests, datetime
TOKEN=os.environ["META_ACCESS_TOKEN"]; V=os.environ.get("META_API_VERSION","v20.0")
B=f"https://graph.facebook.com/{V}"
ACC=[("QMDT—20240103","750289240467952"),("销售三部—新主页账户","5600626876733411"),
     ("Jelenew+","1614799860253372"),("Jelenew-Brand & Lab","568835832834495")]
def get(path, params):
    r=requests.get(f"{B}/{path}", params={**params,"access_token":TOKEN}, timeout=60)
    if r.status_code!=200:
        print("HTTPERR|"+path+"|"+str(r.status_code)+"|"+r.text[:150]); return {}
    return r.json()
print("TS|"+datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"))
tc=tas=sc=sas=tt=0
for nm,aid in ACC:
    info=get(f"act_{aid}",{"fields":"currency,timezone_name"})
    cur=info.get("currency","?"); tz=info.get("timezone_name","?")
    camps=get(f"act_{aid}/campaigns",{"fields":"id,name,daily_budget,effective_status","limit":"200"}).get("data",[])
    ads=get(f"act_{aid}/adsets",{"fields":"id,daily_budget,effective_status,campaign_id","limit":"500"}).get("data",[])
    act_c=[c for c in camps if c.get("effective_status")=="ACTIVE"]
    act_a=[a for a in ads if a.get("effective_status")=="ACTIVE"]
    cbo=[c for c in act_c if c.get("daily_budget")]
    abo=[a for a in act_a if a.get("daily_budget")]
    # 若 campaign 是 CBO，其 adset 上的 daily_budget 不应重复计入
    cbo_ids={c["id"] for c in cbo}
    abo=[a for a in abo if a.get("campaign_id") not in cbo_ids]
    sc=sum(int(c["daily_budget"]) for c in cbo)/100
    sa=sum(int(a["daily_budget"]) for a in abo)/100
    tc+=len(act_c); tas+=len(act_a); sc_sum=sc; sas+=sa; tt+=sc+sa
    print(f"ROW|{nm}|{cur}|{tz.replace('/','_')}|{len(act_c)}|{len(act_a)}|{len(cbo)}|{sc:.2f}|{len(abo)}|{sa:.2f}|{sc+sa:.2f}")
print(f"TOTAL|{tc}|{tas}|{sas:.2f}|{tt:.2f}")
