import json, urllib.request, subprocess, tempfile, os, time, shutil, datetime
from zoneinfo import ZoneInfo
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
# 子表二：小时消耗ROI（A:M，13 列：小时 + 每账户 消耗今天/昨天 + ROI今天/昨天）
offs={"QMDT":28,"销售三部":34,"Jelenew+":40}
roi_cols=["小时"]; roi_idx=[0]
for nm,off in offs.items():
    roi_cols += [f"{nm} 消耗 今天", f"{nm} 消耗 昨天", f"{nm} ROI 今天", f"{nm} ROI 昨天"]
    roi_idx += [off, off+1, off+3, off+4]
roi_data=[[r[i] for i in roi_idx] for r in data]
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

# ---------- 子表三：BF by hour budget（分平台分小时实际消耗追踪） ----------
GSRC="https://raw.githubusercontent.com/ruobingli1993-hub/meta-budget-alert/main/google_hourly.json"
try:
    g=json.load(urllib.request.urlopen(f"{GSRC}?ts={int(time.time())}",timeout=30))
    grows={int(r["hour"]):(r.get("mai") or 0.0, r.get("nonmai") or 0.0) for r in g.get("rows",[])}
    gupd=g.get("updated_utc")
except Exception as e:
    grows={}; gupd=f"(google_hourly.json 不可用: {e})"

PHX=ZoneInfo("America/Phoenix")
now_h=datetime.datetime.now(PHX).hour

offs2={"QMDT":28,"销售三部":34,"Jelenew+":40}
bc=[]; fgh=[]; kl=[]
for h in range(24):
    row=h+3
    mv=[data[h][i] for i in offs2.values()]
    fgh.append([({"value":v} if v is not None else {"value":None}) for v in mv])
    if h<=now_h and grows:
        mai,nm=grows.get(h,(0.0,0.0))
        kl.append([{"value":mai},{"value":nm}])
    else:
        kl.append([{"value":None},{"value":None}])
    bc.append([{"formula":f'=IF(COUNT(F{row}:H{row})=0,"",SUM(F{row}:H{row}))'},
               {"formula":f'=IF(COUNT(K{row}:L{row})=0,"",SUM(K{row}:L{row}))'}])

notes=[
 "数值 = 今天各账户分小时实际消耗（随小时累加），账户时区 America/Phoenix（UTC-7），1 = 当地 00:00–01:00",
 "数据源：Meta /hourly.json（每小时 :05 更新）；Google /google_hourly.json（每小时 :10 更新，按 campaign label 拆 mai / nonmai）",
 "两个 Google 账户（jelenew-Q&M 8385977843、Jelenew Cycling-1 5188331105）均为 Phoenix 时区，与 Meta 同一小时轴，无需错位",
 "B、C 列 = 平台合计（COUNT 判空后求和）；未到的小时留空，不填 0",
]
bw=[{"sheet_name":"BF by hour budget","range":"B3:C26","cells":bc},
    {"sheet_name":"BF by hour budget","range":"F3:H26","cells":fgh},
    {"sheet_name":"BF by hour budget","range":"K3:L26","cells":kl},
    {"sheet_name":"BF by hour budget","range":"A28:A31","cells":[[{"value":n}] for n in notes]}]
with tempfile.NamedTemporaryFile("w",suffix=".json",delete=False) as f:
    json.dump(bw,f,ensure_ascii=False); p2=f.name
r2=subprocess.run([LARK,"sheets","+cells-set","--spreadsheet-token",TOKEN_SHEET,
                   "--writes",f"@{p2}","--format","json"],capture_output=True,text=True)
ok = '"succeeded": 4' in r2.stdout or '"succeeded":4' in r2.stdout
print("BF|", "ok" if ok else r2.stdout[:400])
os.unlink(p2)
print("SYNC2|meta_utc=",d["updated_utc"],"|google_utc=",gupd,"|phx_hour=",now_h)
