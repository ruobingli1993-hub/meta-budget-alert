import os, json, requests
TOKEN=os.environ["META_ACCESS_TOKEN"]; V=os.environ.get("META_API_VERSION","v20.0")
B=f"https://graph.facebook.com/{V}"
AID="1614799860253372"
for label, since, until in [("7DAY","2026-11-20","2026-11-26"),("YDAY","2026-11-26","2026-11-26"),("TODAY","2026-11-27","2026-11-27")]:
    r=requests.get(f"{B}/act_{AID}/insights", params={
        "fields":"campaign_name,spend,clicks,actions","level":"campaign",
        "time_range":json.dumps({"since":since,"until":until}),
        "limit":"50","access_token":TOKEN}, timeout=120)
    if r.status_code!=200:
        print(f"FAIL|{label}|{r.status_code}|{r.text[:160]}"); continue
    for row in r.json().get("data",[]):
        a={x["action_type"]:float(x["value"]) for x in row.get("actions",[])}
        atc=a.get("omni_add_to_cart",a.get("add_to_cart",0))
        ic=a.get("omni_initiated_checkout",a.get("initiate_checkout",0))
        pur=a.get("omni_purchase",a.get("purchase",0))
        print(f"P|{label}|{row.get('campaign_name')}|spend={float(row.get('spend',0)):.2f}|clk={float(row.get('clicks',0)):.0f}|atc={atc:.0f}|ic={ic:.0f}|pur={pur:.0f}")
