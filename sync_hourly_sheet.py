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

# ---------- 子表三：BF by hour budget（日预算拆到小时，每小时刷新） ----------
BSRC="https://raw.githubusercontent.com/ruobingli1993-hub/meta-budget-alert/main/bf_budget.json"
GSRC="https://raw.githubusercontent.com/ruobingli1993-hub/meta-budget-alert/main/google_hourly.json"
def _get(u):
    return json.load(urllib.request.urlopen(f"{u}?ts={int(time.time())}",timeout=30))
def alloc(total, series):
    s=sum(series) or 1.0
    vals=[round(total*(v/s),2) for v in series]
    d=round(total-sum(vals),2)
    if d: 
        j=max(range(len(vals)),key=lambda i: vals[i]); vals[j]=round(vals[j]+d,2)
    return vals

try:
    b=_get(BSRC); bud_utc=b.get("updated_utc")
except Exception as e:
    b=None; bud_utc=f"(bf_budget.json 不可用: {e})"
try:
    g=_get(GSRC); g_yd={int(r["hour"]):(r.get("mai") or 0.0,r.get("nonmai") or 0.0) for r in g.get("rows_yday",[])}
except Exception as e:
    g_yd={}

if b:
    mo={"QMDT":29,"销售三部":35,"Jelenew+":41}
    q_vals=[]
    mv={}
    for nm,ci in mo.items():
        ys=[(data[h][ci] or 0.0) for h in range(24)]
        tot=float(b["meta"][nm]["budget"])
        mv[nm]=alloc(tot,ys)
    mai_s=[g_yd.get(h,(0.0,0.0))[0] for h in range(24)] or [1.0]*24
    nm_s=[g_yd.get(h,(0.0,0.0))[1] for h in range(24)] or [1.0]*24
    mk=alloc(float(b["google"]["mai"]),mai_s)
    nk=alloc(float(b["google"]["nonmai"]),nm_s)
    bcw=[[{"formula":f'=SUM(F{3+h}:H{3+h})'},{"formula":f'=SUM(K{3+h}:L{3+h})'}] for h in range(24)]
    fgh=[[{"value":mv["QMDT"][h]},{"value":mv["销售三部"][h]},{"value":mv["Jelenew+"][h]}] for h in range(24)]
    kl=[[{"value":mk[h]},{"value":nk[h]}] for h in range(24)]
    notes=[
     "每小时预算 = 当日 daily budget 按昨天同小时实际消耗占比拆到 24 小时；账户时区 America/Phoenix（UTC-7），1 = 当地 00:00–01:00",
     f"预算总额每小时从平台读取（bf_budget.json，更新于 {bud_utc}）：Meta 账户 campaign+adset 日预算合计，Google campaign_budget 去重后按 mai / 非mai 汇总",
     "昨天小时占比：Meta 取 hourly.json 的昨天各账户分小时消耗；Google 取 google_hourly.json 的昨天分小时消耗（mai、非mai 各自一条曲线）",
     "B、C 列 = 平台合计，公式 =SUM(F:H) / =SUM(K:L)；金额 USD",
    ]
    bw=[{"sheet_name":"BF by hour budget","range":"B3:C26","cells":bcw},
        {"sheet_name":"BF by hour budget","range":"F3:H26","cells":fgh},
        {"sheet_name":"BF by hour budget","range":"K3:L26","cells":kl},
        {"sheet_name":"BF by hour budget","range":"A28:A31","cells":[[{"value":n}] for n in notes]}]
    with tempfile.NamedTemporaryFile("w",suffix=".json",delete=False) as f:
        json.dump(bw,f,ensure_ascii=False); p2=f.name
    r2=subprocess.run([LARK,"sheets","+cells-set","--spreadsheet-token",TOKEN_SHEET,
                       "--writes",f"@{p2}","--format","json"],capture_output=True,text=True)
    ok = '"succeeded": 4' in r2.stdout
    print("BF|", "ok" if ok else r2.stdout[:300])
    os.unlink(p2)
    print("BFSUM|meta", round(sum(sum(mv[k]) for k in mv),2), "google", round(sum(mk)+sum(nk),2), "|budget_utc", bud_utc)
else:
    print("BF| skipped (no bf_budget.json)")
