import os, json, base64, requests, datetime, collections
TOKEN=os.environ["META_ACCESS_TOKEN"]; V=os.environ.get("META_API_VERSION","v20.0")
B=f"https://graph.facebook.com/{V}"
GH=os.environ["GITHUB_TOKEN"]; REPO=os.environ["GITHUB_REPOSITORY"]

# 账户元组: (展示名, act_id, 需要剔除的 campaign 名称关键词列表, 大小写不敏感)
ACC=[
    ("QMDT","750289240467952",[]),
    ("销售三部","5600626876733411",[]),
    ("Jelenew+","1614799860253372",["tofu"]),
]
Z={"lclk":0,"atc":0,"ic":0,"pur":0,"spend":0,"pv":0}
FIELDS="campaign_name,actions,action_values,spend"
KEYS=("lclk","atc","ic","pur","spend","pv")

def meta_get(aid, day):
    """按 campaign 粒度取某天分小时数据，返回 {campaign_name: {hour: counters}}，带分页。"""
    out=collections.defaultdict(lambda: collections.defaultdict(lambda: dict.fromkeys(KEYS,0.0)))
    url=f"{B}/act_{aid}/insights"
    params={
        "fields":FIELDS,
        "breakdowns":"hourly_stats_aggregated_by_advertiser_time_zone",
        "time_range":json.dumps({"since":day,"until":day}),
        "level":"campaign","limit":"200",
        "access_token":TOKEN,
    }
    for _ in range(20):
        r=requests.get(url, params=params, timeout=60)
        if r.status_code!=200: raise RuntimeError(f"{aid} {day} {r.status_code} {r.text[:160]}")
        j=r.json()
        for row in j.get("data",[]):
            name=(row.get("campaign_name") or "(未命名)").strip()
            h=int(str(row["hourly_stats_aggregated_by_advertiser_time_zone"]).split(":")[0])
            a={x["action_type"]:float(x["value"]) for x in row.get("actions",[])}
            av={x["action_type"]:float(x["value"]) for x in row.get("action_values",[]) or []}
            cell=out[name][h]
            cell["lclk"]+=a.get("link_click",0)
            cell["atc"]+=a.get("omni_add_to_cart",a.get("add_to_cart",0))
            cell["ic"]+=a.get("omni_initiated_checkout",a.get("initiate_checkout",0))
            cell["pur"]+=a.get("omni_purchase",a.get("purchase",0))
            cell["spend"]+=float(row.get("spend",0) or 0)
            cell["pv"]+=av.get("omni_purchase",av.get("purchase",0))
        nxt=(j.get("paging") or {}).get("next")
        if not nxt: break
        url, params = nxt, {}
    return out

def keep(name, keywords):
    low=name.lower()
    return not any(k.lower() in low for k in keywords)

now=datetime.datetime.utcnow()-datetime.timedelta(hours=7)
today=now.date()
yday=today-datetime.timedelta(days=1)
win=[today-datetime.timedelta(days=k) for k in range(7,0,-1)]
print(f"WIN|{win[0]}~{win[-1]}|today={today}|yday={yday}")

def rate(n,d): return (round(n/d,4) if d>0 else None)
def trio(c): return [rate(c["atc"],c["lclk"]), rate(c["ic"],c["atc"]), rate(c["pur"],c["ic"])]

cols=['小时']
for _,name,_ in ACC:
    for m in ('加购率','结账率','转化率'):
        for tag in ('今天','昨天','7日均值'): cols.append(f"{name} {m} {tag}")
for _,name,_ in ACC:
    for m in ('消耗','ROI'):
        for tag in ('今天','昨天','7日均值'): cols.append(f"{name} {m} {tag}")

def fold(aid, day, kw):
    """当天 campaign 行按小时合并，剔除命中关键词的 campaign。返回 (小时字典, 当日全部campaign名, 命中名)"""
    by_camp=meta_get(aid, day)
    kept=collections.defaultdict(lambda: dict.fromkeys(KEYS,0.0))
    hit=[]
    for name, hrs in by_camp.items():
        if not keep(name,kw):
            hit.append(name); continue
        for h,c in hrs.items():
            for kk in KEYS: kept[h][kk]+=c[kk]
    return {h:dict(v) for h,v in kept.items()}, sorted(by_camp.keys()), sorted(hit)

cache={}; inventory={}; dropped={}
for code,aid,kw in ACC:
    t,tnames,thit=fold(aid, today.isoformat(), kw)
    y,ynames,yhit=fold(aid, yday.isoformat(), kw)
    agg=collections.defaultdict(lambda: dict.fromkeys(KEYS,0.0))
    hits=set(thit)|set(yhit); names=set(tnames)|set(ynames)
    for k in range(7,0,-1):
        w,wnames,whit=fold(aid, (today-datetime.timedelta(days=k)).isoformat(), kw)
        hits|=set(whit); names|=set(wnames)
        for h,c in w.items():
            for kk in KEYS: agg[h][kk]+=c[kk]
    cache[code]=(t,y,{h:dict(v) for h,v in agg.items()})
    inventory[code]=sorted(names)
    dropped[code]=sorted(hits)
    print(f"CAMP|{code}|total={len(names)}|dropped={sorted(hits)}")

data=[]
for h in range(24):
    line=[f"{h:02d}"]
    for code,_,_ in ACC:
        t,y,a=cache[code]
        tt=trio(t.get(h,Z)); yy=trio(y.get(h,Z)); aa=trio(a.get(h,Z))
        for mi in range(3):
            line += [tt[mi] if h in t else None, yy[mi] if h in y else None, aa[mi]]
    for code,_,_ in ACC:
        t,y,a=cache[code]
        st=t[h] if h in t else None; sy=y[h] if h in y else None; sa=a.get(h)
        line += [round(st["spend"],2) if st else None,
                 round(sy["spend"],2) if sy else None,
                 round(sa["spend"]/7,2) if sa else 0.0,
                 rate(st["pv"],st["spend"]) if st else None,
                 rate(sy["pv"],sy["spend"]) if sy else None,
                 rate(sa["pv"],sa["spend"]) if sa else None]
    data.append(line)

payload={"updated_utc":datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
         "today":str(today),"yday":str(yday),"win":[str(win[0]),str(win[-1])],
         "tz":"America/Phoenix","columns":cols,"data":data,
         "campaigns":inventory,"excluded":dropped}
raw=json.dumps(payload,ensure_ascii=False)
print("ROWS|",len(data),"|COLS|",len(cols),"|BYTES|",len(raw))
url=f"https://api.github.com/repos/{REPO}/contents/hourly.json"
hdr={"Authorization":f"Bearer {GH}","Content-Type":"application/json"}
r=None
for attempt in range(5):
    sha=requests.get(url,headers=hdr,timeout=30).json().get("sha")
    body={"message":f"hourly funnel {payload['updated_utc']}","content":base64.b64encode(raw.encode()).decode(),"branch":"main"}
    if sha: body["sha"]=sha
    r=requests.put(url,headers=hdr,json=body,timeout=60)
    print("PUBLISH|",r.status_code,"|try",attempt+1)
    if r.status_code in (200,201):
        break
    import time as _t; _t.sleep(3)
if r is not None and r.status_code not in (200,201):
    raise SystemExit(f"publish failed: {r.status_code} {r.text[:200]}")
print("SAMPLE|",json.dumps(data[:2],ensure_ascii=False)[:300])
