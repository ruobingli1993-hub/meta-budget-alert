import os, json, base64, requests, datetime, collections
TOKEN=os.environ["META_ACCESS_TOKEN"]; V=os.environ.get("META_API_VERSION","v20.0")
B=f"https://graph.facebook.com/{V}"
GH=os.environ["GITHUB_TOKEN"]; REPO=os.environ["GITHUB_REPOSITORY"]
ACC=[("QMDT","750289240467952"),("销售三部","5600626876733411"),("Jelenew+","1614799860253372")]
def meta_get(aid, day):
    r=requests.get(f"{B}/act_{aid}/insights", params={
        "fields":"actions","breakdowns":"hourly_stats_aggregated_by_advertiser_time_zone",
        "time_range":json.dumps({"since":day,"until":day}),"level":"account","limit":"100",
        "access_token":TOKEN}, timeout=60)
    if r.status_code!=200: raise RuntimeError(f"{aid} {day} {r.status_code} {r.text[:120]}")
    out={}
    for row in r.json().get("data",[]):
        h=int(str(row["hourly_stats_aggregated_by_advertiser_time_zone"]).split(":")[0])
        a={x["action_type"]:float(x["value"]) for x in row.get("actions",[])}
        out[h]={"lclk":a.get("link_click",0),
                "atc":a.get("omni_add_to_cart",a.get("add_to_cart",0)),
                "ic":a.get("omni_initiated_checkout",a.get("initiate_checkout",0)),
                "pur":a.get("omni_purchase",a.get("purchase",0))}
    return out
now=datetime.datetime.utcnow()-datetime.timedelta(hours=7)
today=now.date()
yday=today-datetime.timedelta(days=1)
win=[today-datetime.timedelta(days=k) for k in range(7,0,-1)]
print(f"WIN|{win[0]}~{win[-1]}|today={today}|yday={yday}")
def rate(n,d): return (round(n/d,4) if d>0 else None)
def trio(c): return [rate(c["atc"],c["lclk"]), rate(c["ic"],c["atc"]), rate(c["pur"],c["ic"])]
cols=['小时']
for _,name in ACC:
    for m in ('加购率','结账率','转化率'):
        for tag in ('今天','昨天','7日均值'): cols.append(f"{name} {m} {tag}")
cache={}
for code,aid in ACC:
    t=meta_get(aid,today.isoformat()); y=meta_get(aid,yday.isoformat())
    agg=collections.defaultdict(collections.Counter)
    for k in range(7,0,-1):
        for h,c in meta_get(aid,(today-datetime.timedelta(days=k)).isoformat()).items():
            for kk,v in c.items(): agg[h][kk]+=v
    cache[code]=(t,y,{h:dict(v) for h,v in agg.items()})
Z={"lclk":0,"atc":0,"ic":0,"pur":0}
data=[]
for h in range(24):
    line=[f"{h:02d}"]
    for code,_ in ACC:
        t,y,a=cache[code]
        tt=trio(t.get(h,Z)); yy=trio(y.get(h,Z)); aa=trio(a.get(h,Z))
        for mi in range(3):
            line += [tt[mi] if h in t else None, yy[mi] if h in y else None, aa[mi]]
    data.append(line)
payload={"updated_utc":datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
         "today":str(today),"yday":str(yday),"win":[str(win[0]),str(win[-1])],
         "tz":"America/Phoenix","columns":cols,"data":data}
raw=json.dumps(payload,ensure_ascii=False)
print("ROWS|",len(data),"|COLS|",len(cols),"|BYTES|",len(raw))
url=f"https://api.github.com/repos/{REPO}/contents/hourly.json"
hdr={"Authorization":f"Bearer {GH}","Content-Type":"application/json"}
sha=requests.get(url,headers=hdr,timeout=30).json().get("sha")
body={"message":f"hourly funnel {payload['updated_utc']}","content":base64.b64encode(raw.encode()).decode(),"branch":"main"}
if sha: body["sha"]=sha
r=requests.put(url,headers=hdr,json=body,timeout=60)
print("PUBLISH|",r.status_code)
print("SAMPLE|",json.dumps(data[:2],ensure_ascii=False)[:260])
