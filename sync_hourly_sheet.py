import json, urllib.request, subprocess, tempfile, os, time, shutil, datetime
from zoneinfo import ZoneInfo
SRC="https://raw.githubusercontent.com/ruobingli1993-hub/meta-budget-alert/main/hourly.json"
TOKEN_SHEET="Eu5Zsq9Avhun4ltAaWKcJ0gvneh"
LARK=shutil.which("lark-cli") or "/home/user/vm/resource-loader/bin/lark-cli"

# ---------- 上游保鲜：GitHub schedule 在本仓库不触发，改为本机按需 dispatch ----------
RAW="https://raw.githubusercontent.com/ruobingli1993-hub/meta-budget-alert/main/"
WFS={"hourly.json":"hourly-funnel.yml","google_hourly.json":"google-hourly.yml","bf_budget.json":"bf-budget.yml"}
TOKF=os.path.expanduser("~/.cache/gbud/.ghtok")
TOK=open(TOKF).read().strip() if os.path.exists(TOKF) else ""
def _dt(s): return datetime.datetime.strptime(s,"%Y-%m-%dT%H:%M:%SZ")
def _peek(n):
    try: return _dt(json.load(urllib.request.urlopen(f"{RAW}{n}?ts={int(time.time())}",timeout=20))["updated_utc"])
    except Exception: return None
try:
    if TOK:
        now=datetime.datetime.utcnow(); need=[n for n in WFS if (lambda u:(u is None or (now-u).total_seconds()>2700))(_peek(n))]
        if need:
            for n in need:
                req=urllib.request.Request(
                    f"https://api.github.com/repos/ruobingli1993-hub/meta-budget-alert/actions/workflows/{WFS[n]}/dispatches",
                    data=json.dumps({"ref":"main"}).encode(), method="POST",
                    headers={"Authorization":f"Bearer {TOK}","Accept":"application/vnd.github+json","Content-Type":"application/json"})
                urllib.request.urlopen(req,timeout=20).read()
            print("PREFETCH| dispatched", need)
            for _ in range(12):
                time.sleep(15)
                if all((lambda u: u is not None and (datetime.datetime.utcnow()-u).total_seconds()<300)(_peek(n)) for n in need): break
except Exception as e:
    print("PREFETCH| skip", type(e).__name__, e)

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

# ---------- 子表三：BF by hour budget（分小时实时日预算巡航，逐小时留痕） ----------
BSRC="https://raw.githubusercontent.com/ruobingli1993-hub/meta-budget-alert/main/bf_budget.json"
def _get(u):
    return json.load(urllib.request.urlopen(f"{u}?ts={int(time.time())}",timeout=30))

try:
    b=_get(BSRC); bud_utc=b.get("updated_utc")
except Exception as e:
    b=None; bud_utc=f"(bf_budget.json 不可用: {e})"

PHX=ZoneInfo("America/Phoenix")
cur_h=datetime.datetime.now(PHX).hour
bh=cur_h+1  # BF 表标签 1..24 = 当地第 1..24 个小时，当前正在进行的是第 bh 个小时

if b:
    import csv, io
    q=float(b["meta"]["QMDT"]["budget"]); s3=float(b["meta"]["销售三部"]["budget"]); jl=float(b["meta"]["Jelenew+"]["budget"])
    mai=float(b["google"]["mai"]); nm=float(b["google"]["nonmai"])
    # 读现有格子，保留已跑过的历史值
    rr=subprocess.run([LARK,"sheets","+csv-get","--spreadsheet-token",TOKEN_SHEET,"--sheet-name",
                       "BF by hour budget","--range","F3:L26","--format","json"],capture_output=True,text=True)
    old=[[""]*7 for _ in range(24)]
    try:
        rows=list(csv.reader(io.StringIO(json.loads(rr.stdout)["data"]["csv"])))
        rows=rows+[[""]*7]*(24-len(rows))
        for i,r in enumerate(rows[:24]):
            old[i]=(list(r)+[""]*7)[:7]
    except Exception:
        pass
    def filled(r,idx):
        return any((r[i] or "").strip() not in ("","0","0.00","0.0") for i in idx)
    fgh=[]; kl=[]
    for h in range(24):
        cur=[q,s3,jl]; gv=[mai,nm]
        if h==bh:
            fgh.append([{"value":cur[0]},{"value":cur[1]},{"value":cur[2]}])
            kl.append([{"value":gv[0]},{"value":gv[1]}])
        elif h>bh:
            fgh.append([{}]*3); kl.append([{}]*2)
        else:  # 已过小时：有值就保留，空着才补当前预算
            fgh.append([{}]*3 if filled(old[h],[0,1,2]) else
                       [{"value":cur[0]},{"value":cur[1]},{"value":cur[2]}])
            kl.append([{}]*2 if filled(old[h],[5,6]) else [{"value":gv[0]},{"value":gv[1]}])
    bcw=[[{"formula":f'=IF(COUNT(F{3+h}:H{3+h})=0,"",SUM(F{3+h}:H{3+h}))'},
          {"formula":f'=IF(COUNT(K{3+h}:L{3+h})=0,"",SUM(K{3+h}:L{3+h}))'}] for h in range(24)]
    notes=[
     "每格 = 该小时在平台上的实时日预算（同一份日预算，未改动则各小时相同；一旦改预算，改动后读到的那小时起写入新值，已跑过的小时保持原值留痕）",
     f"账户时区 America/Phoenix（UTC-7）；本表第 N 行 = 当地第 N 个小时（N=1 即 00:00–01:00），与小时转化率/小时消耗ROI 的 \"00–23\" 行错一位（本表第 N 行 = 那两表的 (N-1) 行）；本次写入第 {bh} 行（当地 {cur_h:02d}:00–{bh:02d}:00，正在进行中），之后的格子留空待到点",
     f"数据源：bf_budget.json（更新于 {bud_utc}）——Meta 为 campaign+adset 日预算合计（Jelenew+ 已剔除 tofu），Google 为 campaign_budget 去重后按 label 拆 mai / 非mai",
     "B、C 列 = 平台合计，公式 =IF(COUNT(...)=0,\"\",SUM(...))；金额 USD",
    ]
    bw=[{"sheet_name":"BF by hour budget","range":"B3:C26","cells":bcw},
        {"sheet_name":"BF by hour budget","range":"F3:H26","cells":fgh},
        {"sheet_name":"BF by hour budget","range":"K3:L26","cells":kl},
        {"sheet_name":"BF by hour budget","range":"A28:A31","cells":[[{"value":n}] for n in notes]}]
    with tempfile.NamedTemporaryFile("w",suffix=".json",delete=False) as f:
        json.dump(bw,f,ensure_ascii=False); p2=f.name
    r2=subprocess.run([LARK,"sheets","+cells-set","--spreadsheet-token",TOKEN_SHEET,
                       "--writes",f"@{p2}","--format","json"],capture_output=True,text=True)
    ok='"succeeded": 4' in r2.stdout
    print("BF|","ok" if ok else r2.stdout[:300])
    if bh < 24:  # 未到的小时一律清空（null/"" 写不掉旧值，改用 cells-clear）
        for rng in (f"F{bh+3}:H26", f"K{bh+3}:L26"):
            subprocess.run([LARK,"sheets","+cells-clear","--spreadsheet-token",TOKEN_SHEET,
                            "--sheet-name","BF by hour budget","--range",rng,"--yes"],
                           capture_output=True,text=True)
    os.unlink(p2)
    print(f"BFNOW|phx_h={cur_h} |row={bh+2} |QMDT {q} 销售 {s3} Jelenew {jl} |mai {mai} nonmai {nm} |budget_utc {bud_utc}")
else:
    print("BF| skipped (no bf_budget.json)")
