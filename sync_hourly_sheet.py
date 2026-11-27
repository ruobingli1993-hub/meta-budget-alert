import json, urllib.request, subprocess, tempfile, os, time, shutil
SRC="https://raw.githubusercontent.com/ruobingli1993-hub/meta-budget-alert/main/hourly.json"
TOKEN_SHEET="Eu5Zsq9Avhun4ltAaWKcJ0gvneh"; SHEET="小时转化率"
LARK=shutil.which("lark-cli") or "/home/user/vm/resource-loader/bin/lark-cli"

d=json.load(urllib.request.urlopen(f"{SRC}?ts={int(time.time())}",timeout=30))
cols=d["columns"]; data=d["data"]
dtypes={"小时":"object"}; fmts={}
for c in cols[1:]: dtypes[c]="float64"; fmts[c]="0.00%"
payload={"sheets":[{"name":SHEET,"start_cell":"A2","header":False,"mode":"overwrite",
                    "columns":cols,"data":data,"dtypes":dtypes,"formats":fmts}]}
with tempfile.NamedTemporaryFile("w",suffix=".json",delete=False) as f:
    json.dump(payload,f,ensure_ascii=False); path=f.name
r=subprocess.run([LARK,"sheets","+table-put","--spreadsheet-token",TOKEN_SHEET,
                  "--sheets",f"@{path}","--format","json"],capture_output=True,text=True)
print(r.stdout[:400]); print(r.stderr[:200])
os.unlink(path)
print("SYNC|updated_utc=",d["updated_utc"],"|rows",len(data),"|cols",len(cols),
      "|excluded=",d.get("excluded",{}).get("Jelenew+"))
