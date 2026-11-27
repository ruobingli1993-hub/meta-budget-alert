import os, json, requests
APP=os.environ["FEISHU_APP_ID"]; SEC=os.environ["FEISHU_APP_SECRET"]
TOKEN_SHEET="Eu5Zsq9Avhun4ltAaWKcJ0gvneh"
def tok():
    r=requests.post("https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal",
                    json={"app_id":APP,"app_secret":SEC},timeout=30)
    return r.json()
t=tok(); print("TOKEN|",t.get("code"),"|", (t.get("tenant_access_token") or "")[:8])
tk=t.get("tenant_access_token")
if tk:
    h={"Authorization":f"Bearer {tk}"}
    r=requests.get(f"https://open.feishu.cn/open-apis/sheets/v3/spreadsheets/{TOKEN_SHEET}/sheets/query",headers=h,timeout=30)
    print("READ|",r.status_code,"|",r.text[:200])
    r2=requests.post(f"https://open.feishu.cn/open-apis/sheets/v2/spreadsheets/{TOKEN_SHEET}/values_batch_update",
        headers=h,json={"valueRanges":[]},timeout=30)
    print("WRITEPROBE|",r2.status_code,"|",r2.text[:200])
