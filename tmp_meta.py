import os, json, requests
TOKEN=os.environ["META_ACCESS_TOKEN"]; V=os.environ.get("META_API_VERSION","v20.0")
B=f"https://graph.facebook.com/{V}"
ACC=[("QMDT","750289240467952"),("SALES3","5600626876733411"),("JELENEWPLUS","1614799860253372")]
DAYS=["2026-11-20","2026-11-21","2026-11-22","2026-11-23","2026-11-24","2026-11-25","2026-11-26","2026-11-27"]
for tag, aid in ACC:
    for day in DAYS:
        r=requests.get(f"{B}/act_{aid}/insights", params={
            "fields":"spend,impressions,clicks,actions",
            "breakdowns":"hourly_stats_aggregated_by_advertiser_time_zone",
            "time_range":json.dumps({"since":day,"until":day}),
            "level":"account","limit":"100","access_token":TOKEN}, timeout=120)
        if r.status_code!=200:
            print(f"FAIL|{tag}|{day}|{r.text[:160]}"); continue
        d=r.json().get("data",[])
        print(f"CNT|{tag}|{day}|{len(d)}")
        for row in d:
            acts={a["action_type"]:float(a["value"]) for a in row.get("actions",[])}
            h=str(row.get("hourly_stats_aggregated_by_advertiser_time_zone","?")).split(":")[0]
            print(f"H|{tag}|{day}|{h}|{float(row.get('spend',0)):.2f}|{row.get('impressions',0)}|{row.get('clicks',0)}|"
                  f"{acts.get('add_to_cart',0):.0f}|{acts.get('omni_add_to_cart',0):.0f}|"
                  f"{acts.get('initiate_checkout',0):.0f}|{acts.get('omni_initiated_checkout',0):.0f}|"
                  f"{acts.get('purchase',0):.0f}|{acts.get('omni_purchase',0):.0f}|"
                  f"{acts.get('link_click',0):.0f}|{acts.get('landing_page_view',0):.0f}")
