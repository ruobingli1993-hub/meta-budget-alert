import os, requests
TOKEN = os.environ["META_ACCESS_TOKEN"]; V = os.environ.get("META_API_VERSION","v20.0")
B = f"https://graph.facebook.com/{V}"
ACC = [("QMDT—20240103","750289240467952"),("销售三部—新主页账户","5600626876733411"),
       ("Jelenew+","1614799860253372"),("Jelenew-Brand & Lab","568835832834495")]
def get(path, fields, extra=None, limit=500):
    out=[]; params={"fields":fields,"limit":limit,"access_token":TOKEN}
    if extra: params.update(extra)
    url=f"{B}/{path}"
    while True:
        r=requests.get(url, params=params, timeout=40)
        if r.status_code!=200:
            return out, r.text[:300]
        j=r.json(); out += j.get("data",[])
        nxt=j.get("paging",{}).get("next")
        if not nxt: break
        url=nxt; params={}
    return out, None
CAMP_F="id,name,effective_status,status,objective,daily_budget,lifetime_budget,bid_strategy"
ADSET_F="id,name,campaign_id,campaign{name},effective_status,status,daily_budget,lifetime_budget,optimization_goal"
print("META|账户|币种|时区|ACTIVE_campaign(含CBO)|ACTIVE_adset(含日预算)|日预算合计")
tot=0.0
for name, aid in ACC:
    ac,_ = get(f"act_{aid}","id,name,currency,account_status,timezone_name",extra={"limit":"1"})
    info=ac[0] if ac else {}; cur=info.get("currency","?"); tz=info.get("timezone_name","?")
    camps,e1 = get(f"act_{aid}/campaigns",CAMP_F,extra={"effective_status":'["ACTIVE"]',"limit":"500"})
    ads,e2 = get(f"act_{aid}/adsets",ADSET_F,extra={"effective_status":'["ACTIVE"]',"limit":"500"})
    cbo=[c for c in camps if c.get("daily_budget")]; ab=[a for a in ads if a.get("daily_budget")]
    s_cbo=sum(int(c["daily_budget"]) for c in cbo)/100; s_ab=sum(int(a["daily_budget"]) for a in ab)/100
    ov=[a for a in ab if any(c["id"]==a["campaign_id"] for c in cbo)]; s_ov=sum(int(a["daily_budget"]) for a in ov)/100
    ded=s_cbo+s_ab-s_ov; tot+=ded
    print(f"META|{name}|{cur}|{tz}|{len(camps)}|{len(ads)}|{ded:.2f}|campaign日预算{s_cbo:.2f}+adset日预算{s_ab:.2f}-重叠{s_ov:.2f}")
    print(f"   {name} 月预算条数: campaign {len([c for c in camps if c.get('lifetime_budget')])} / adset {len([a for a in ads if a.get('lifetime_budget')])}")
    print("   样例campaign: " + " || ".join([c['name'][:45]+f"[{c.get('objective','')[:14]}]"+("(CBO)" if c.get('daily_budget') else "") for c in camps[:4]]))
    print("   样例adset: " + " || ".join([a['name'][:40] for a in ab[:4]]))
    if e1 or e2: print("   ERR",(e1 or "")[:150],(e2 or "")[:150])
print(f"META|4账户合计|||||{tot:.2f}")
