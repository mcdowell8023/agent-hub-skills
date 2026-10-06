#!/usr/bin/env bash
# cooldown-test.sh — scripts/cooldown.sh 的行为测试（隔离到临时文件，⛔ 不碰真实冷却记录）
set -uo pipefail
S="$(cd "$(dirname "$0")" && pwd)"
T="$(mktemp -d "${TMPDIR:-/tmp}/rift-cooldown-test.XXXXXX")"
export RIFT_COOLDOWN_FILE="$T/cooldown.json"
CD="$S/cooldown.sh"
pass=0; fail=0
ok()  { pass=$((pass+1)); }
bad() { fail=$((fail+1)); echo "❌ $*"; }
now_plus() { python3 -c "import datetime,sys;print((datetime.datetime.now()+datetime.timedelta(minutes=int(sys.argv[1]))).strftime('%Y-%m-%dT%H:%M'))" "$1"; }

# 1. 空文件 ⇒ get 无输出、exit 1
out=$(bash "$CD" get codebuddy-code hy3); rc=$?
[ "$rc" -eq 1 ] && [ -z "$out" ] && ok || bad "空记录 get 应 exit 1 且无输出（rc=$rc out=${out}）"

# 2. set +1h ⇒ get 返回 ≈ now+60min
bash "$CD" set codebuddy-code hy3 +1h "429 test" >/dev/null; rc=$?
[ "$rc" -eq 0 ] && ok || bad "set +1h 应 exit 0（rc=${rc}）"
out=$(bash "$CD" get codebuddy-code hy3); rc=$?
lo=$(now_plus 59); hi=$(now_plus 61)
{ [ "$rc" -eq 0 ] && [[ "$out" > "$lo" || "$out" == "$lo" ]] && [[ "$out" < "$hi" || "$out" == "$hi" ]]; } && ok \
  || bad "set +1h 后 get 应在 [$lo,$hi]（rc=$rc out=${out}）"

# 3. 🔴 更短的冷却 ⛔ 不许把更长的缩短（串行两次 set 取 max；真并发见第 12 项）
bash "$CD" set codebuddy-code hy3 +10m "shorter" >/dev/null
out2=$(bash "$CD" get codebuddy-code hy3)
[ "$out2" == "$out" ] && ok || bad "更短的 set 不应缩短冷却（原 $out 现 ${out2}）"
far=$(now_plus 300)
bash "$CD" set codebuddy-code hy3 "$far" "longer" >/dev/null
[ "$(bash "$CD" get codebuddy-code hy3)" == "$far" ] && ok || bad "更长的 set 应延长到 $far"

# 4. model id 带 `/` ⇒ 嵌套键，⛔ 不拼成单键
bash "$CD" set openrouter-free stealth/space-bunny-alpha +30m "OpenRouter 429" >/dev/null
python3 - "$RIFT_COOLDOWN_FILE" <<'PY' && ok || bad "带 / 的 model 应存成 {upstream: {model: …}} 嵌套结构"
import json, sys
d = json.load(open(sys.argv[1]))
assert 'stealth/space-bunny-alpha' in d['openrouter-free'], d
assert set(d['openrouter-free']['stealth/space-bunny-alpha']) >= {'until', 'reason', 'setAt'}
PY
[ -n "$(bash "$CD" get openrouter-free stealth/space-bunny-alpha)" ] && ok || bad "带 / 的 model get 应有值"

# 5. 过去的时间 ⇒ 视为未冷却
bash "$CD" set qoderclicn qfmodel 2020-01-01T00:00 "old" >/dev/null
bash "$CD" get qoderclicn qfmodel >/dev/null; rc=$?
[ "$rc" -eq 1 ] && ok || bad "已过期的冷却 get 应 exit 1（rc=${rc}）"

# 6. list 只列未过期
lst=$(bash "$CD" list)
{ echo "$lst" | grep -q 'codebuddy-code/hy3' && ! echo "$lst" | grep -q 'qoderclicn/qfmodel'; } && ok \
  || bad "list 应只列未过期记录：$lst"

# 7. HH:MM 早于现在 ⇒ 取明天（cb 429 正文只给「将在 18:43:13 重置」）
past_hm=$(python3 -c "import datetime;print((datetime.datetime.now()-datetime.timedelta(minutes=5)).strftime('%H:%M:%S'))")
bash "$CD" set codebuddy-code glm-5.3-flash "$past_hm" "cb 429 reset" >/dev/null
got=$(bash "$CD" get codebuddy-code glm-5.3-flash)
want=$(python3 -c "
import datetime as d; t=d.datetime.strptime('$past_hm','%H:%M:%S'); n=d.datetime.now()
t=n.replace(hour=t.hour,minute=t.minute,second=t.second,microsecond=0)+d.timedelta(days=1)
t=t.replace(second=0)+d.timedelta(minutes=1) if t.second else t      # 秒数向上取整到分钟
print(t.strftime('%Y-%m-%dT%H:%M'))")
[ "$got" == "$want" ] && ok || bad "早于现在的 HH:MM:SS 应落到明天 ${want}（实际 ${got}）"

# 8. 非法 until ⇒ exit 2 且文件不变
before=$(shasum "$RIFT_COOLDOWN_FILE")
bash "$CD" set codebuddy-code hy3 "tomorrow-ish" "bad" >/dev/null 2>&1; rc=$?
[ "$rc" -eq 2 ] && [ "$(shasum "$RIFT_COOLDOWN_FILE")" == "$before" ] && ok || bad "非法 until 应 exit 2 且不改文件（rc=${rc}）"

# 9. clear 删掉该落点
bash "$CD" clear codebuddy-code hy3 >/dev/null
bash "$CD" get codebuddy-code hy3 >/dev/null; rc=$?
[ "$rc" -eq 1 ] && ok || bad "clear 后 get 应 exit 1"

# 10. 原子写：⛔ 不留临时文件
left=$(find "$T" -name 'cooldown.json.*' ! -name 'cooldown.json.lock' | wc -l | tr -d ' ')   # .lock 是有意保留的锁文件
[ "$left" -eq 0 ] && ok || bad "目录里残留 $left 个临时文件"

# 11. 缺参数 ⇒ exit 2
bash "$CD" set codebuddy-code >/dev/null 2>&1; rc=$?
[ "$rc" -eq 2 ] && ok || bad "缺参数应 exit 2（rc=${rc}）"

# 12. 🔴 真并发：两个进程同时各写 12 个不同落点 ⇒ 24 条一条都不许丢（读-改-写必须加锁）
( for i in $(seq 1 12); do bash "$CD" set conc-a "m$i" +2h "a" >/dev/null; done ) &
( for i in $(seq 1 12); do bash "$CD" set conc-b "m$i" +2h "b" >/dev/null; done ) &
wait
n=$(bash "$CD" list | grep -c '^conc-')
[ "$n" -eq 24 ] && ok || bad "并发写丢了记录：期望 24 实际 ${n}"

# 13. 秒数向上取整到分钟（⛔ 不许比真实重置时刻早过期：18:43:13 ⇒ 18:44）
fut=$(python3 -c "import datetime;print((datetime.datetime.now()+datetime.timedelta(hours=2)).strftime('%H:%M:13'))")
bash "$CD" set codebuddy-code kimi-k3-1 "$fut" "ceil" >/dev/null
want=$(python3 -c "
import datetime as d; n=d.datetime.now(); t=d.datetime.strptime('$fut','%H:%M:%S')
t=n.replace(hour=t.hour,minute=t.minute,second=13,microsecond=0); t=t if t>n else t+d.timedelta(days=1)
print((t.replace(second=0)+d.timedelta(minutes=1)).strftime('%Y-%m-%dT%H:%M'))")
[ "$(bash "$CD" get codebuddy-code kimi-k3-1)" = "$want" ] && ok || bad "带秒的时刻应向上取整到 $want（实际 $(bash "$CD" get codebuddy-code kimi-k3-1)）"

# 14. 带日期的精确时刻（cb 真实签名）⇒ 向上取整到分钟
bash "$CD" set codebuddy-code dated "2099-01-02 18:43:13" "cb dated" >/dev/null
[ "$(bash "$CD" get codebuddy-code dated)" = "2099-01-02T18:44" ] && ok || bad "YYYY-MM-DD HH:MM:SS 应存成 2099-01-02T18:44（实际 $(bash "$CD" get codebuddy-code dated)）"

# 15. 🔴 非法 UTF-8（surrogateescape 孤代理）⇒ 仍要能写盘，且中文保持【人可读】（异构审 P2-9）
bad_reason=$(printf '坏字节\xff 触发控制')
bash "$CD" set codebuddy-code surrogate-test +1h "$bad_reason" >/dev/null; rc=$?
[ "$rc" -eq 0 ] && ok || bad "含非法 UTF-8 的 reason 应仍能写盘（rc=${rc}）"
python3 - "$RIFT_COOLDOWN_FILE" <<'PY' && ok || bad "状态文件必须中文可读 + 孤代理已清洗（⛔ 不许整体 \\uXXXX）"
import json, sys
raw = open(sys.argv[1], encoding='utf-8').read()
assert '触发控制' in raw, '中文被转义了（ensure_ascii 又被打开？）'
d = json.load(open(sys.argv[1], encoding='utf-8'))
r = d['codebuddy-code']['surrogate-test']['reason']
assert '\udcff' not in r and '坏字节' in r, repr(r)
PY

rm -rf "$T"
echo "=== cooldown.sh 行为测试 === 通过 $pass · 失败 $fail"
[ "$fail" -eq 0 ]
