import os, json, requests
TOKEN=os.environ["META_ACCESS_TOKEN"]; V=os.environ.get("META_API_VERSION","v20.0")
B=f"https://graph.facebook.com/{V}"
ACC=[("QMDT","750289240467952"),("SALES3","5600626876733411"),("JELENEWPLUS","1614799860253372")]
TR='{"since":"2026-11-20","until":"2026-11-27"}'
F=["add_to_cart","omni_add_to_cart","initiate_checkout","omni_initiated_checkout",
   "purchase","omni_purchase","link_click","landing_page_view"]
for tag, aid in ACC:
    r=requests.get(f"{B}/act_{aid}/insights", params={
        "fields":"spend,impressions,clicks,actions,date_start,date_stop",
        "breakdowns":"hourly_stats_aggregated_by_advertiser_time_zone",
        "time_range":TR,"level":"account","limit":"500","access_token":TOKEN}, timeout=120)
    if r.status_code!=200:
        print(f"FAIL|{tag}|{r.text[:200]}"); continue
    d=r.json().get("data",[])
    print(f"CNT|{tag}|{len(d)}")
    for row in d:
        acts={a["action_type"]:float(a["value"]) for a in row.get("actions",[])}
        h=row.get("hourly_stats_aggregated_by_advertiser_time_zone","?")
        line=f"H|{tag}|{row['date_start']}|{h}|{row.get('spend','0')}|{row.get('impressions','0')}|{row.get('clicks','0')}"
        for k in F: line+=f"|{acts.get(k,0):.0f}"
        print(line)
