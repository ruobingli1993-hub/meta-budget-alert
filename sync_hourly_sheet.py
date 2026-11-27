import json, urllib.request, subprocess, tempfile, os, time, shutil
SRC="https://raw.githubusercontent.com/ruobingli1993-hub/meta-budget-alert/main/hourly.json"
TOKEN_SHEET="Eu5Zsq9Avhun4ltAaWKcJ0gvneh"
LARK=shutil.which("lark-cli") or "/home/user/vm/resource-loader/bin/lark-cli"

d=json.load(urllib.request.urlopen(f"{SRC}?ts={int(time.time())}",timeout=30))
cols=d["columns"]; data=d["data"]
assert len(cols)==46, f"columns {len(cols)} != 46"

# 子表一：小时转化率（A:AB，28 列三率）
rate_cols=cols[:28]; rate_data=[r[:28] for r in data]
dtypes={"小时":"object"}; fmts={}
for c in rate_cols[1:]: dtypes[c]="float64"; fmts[c]="0.00%"

# 子表二：小时消耗ROI（A:S，19 列：小时 + 每账户 消耗3 / ROI3）
roi_cols=["小时"]+cols[28:46]; roi_data=[[r[0]]+r[28:46] for r in data]
rdtypes={"小时":"object"}; rfmts={}
for c in roi_cols[1:]:
    rdtypes[c]="float64"; rfmts[c]="$#,##0.00" if "消耗" in c else "0.00"

payload={"sheets":[
  {"name":"小时转化率","start_cell":"A2","header":False,"mode":"overwrite",
   "columns":rate_cols,"data":rate_data,"dtypes":dtypes,"formats":fmts},
  {"name":"小时消耗ROI","start_cell":"A2","header":False,"mode":"overwrite",
   "columns":roi_cols,"data":roi_data,"dtypes":rdtypes,"formats":rfmts},
]}
with tempfile.NamedTemporaryFile("w",suffix=".json",delete=False) as f:
    json.dump(payload,f,ensure_ascii=False); path=f.name
r=subprocess.run([LARK,"sheets","+table-put","--spreadsheet-token",TOKEN_SHEET,
                  "--sheets",f"@{path}","--format","json"],capture_output=True,text=True)
print(r.stdout[:600]); print(r.stderr[:200])
os.unlink(path)
print("SYNC|updated_utc=",d["updated_utc"],"|rows",len(data),"|cols",len(cols),
      "|excluded=",d.get("excluded",{}).get("Jelenew+"))
