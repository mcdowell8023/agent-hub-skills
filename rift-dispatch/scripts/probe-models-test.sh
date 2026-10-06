#!/usr/bin/env bash
# probe-models-test.sh — scripts/probe-models.sh 的离线测试（2026-09-29）
#   · 本地起一个假的 OpenAI 兼容端点（按 model 名返回 200 / 429 / 402 / 404）
#   · PATH 前面放假的 codebuddy / qoderclicn
#   ⛔ 不打任何真实服务、不读真实 key、不碰真实冷却记录
set -uo pipefail
S="$(cd "$(dirname "$0")" && pwd)"
T="$(mktemp -d "${TMPDIR:-/tmp}/rift-probe-test.XXXXXX")"
export RIFT_COOLDOWN_FILE="$T/cooldown.json" TMPDIR="$T"
pass=0; fail=0
ok()  { pass=$((pass+1)); }
bad() { fail=$((fail+1)); echo "❌ $*"; }

PORT=$(python3 -c 'import socket;s=socket.socket();s.bind(("127.0.0.1",0));print(s.getsockname()[1]);s.close()')
RESET_MS=$(python3 -c 'import time;print(int((time.time()+7200)*1000))')
RESET_LOCAL=$(python3 -c "
import datetime as d,sys; t=d.datetime.fromtimestamp(int(sys.argv[1])/1000)
t=t.replace(second=0,microsecond=0)+d.timedelta(minutes=1) if (t.second or t.microsecond) else t   # 向上取整到分钟
print(t.strftime('%Y-%m-%dT%H:%M'))" "$RESET_MS")
cat > "$T/server.py" <<PY
import json, http.server
class H(http.server.BaseHTTPRequestHandler):
    def log_message(self, *a): pass
    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
        if self.headers.get('Authorization') != 'Bearer testkey':
            return self._send(401, {'error': {'message': 'bad key'}})
        m = body['model']
        if m.endswith('ok-model'):        return self._send(200, {'model': m, 'usage': {'cost': 0}})
        if m.endswith('billed-model'):    return self._send(200, {'model': m, 'usage': {'cost': 0.002}})
        if m.endswith('nocost-model'):    return self._send(200, {'model': m})                       # 响应里没有 usage
        if m.endswith('strcost-model'):   return self._send(200, {'model': m, 'usage': {'cost': '0.002'}})   # 费用是字符串
        if m.endswith('quota-model'):     return self._send(429, {'error': {'message': 'rate limited'}}, {'X-RateLimit-Reset': '$RESET_MS'})
        if m.endswith('quota-noreset'):   return self._send(429, {'error': {'message': 'rate limited'}})
        if m.endswith('broke-model'):     return self._send(402, {'error': {'message': 'negative balance'}})
        return self._send(404, {'error': {'message': 'no such model'}})
    def _send(self, code, obj, hdr=None):
        b = json.dumps(obj).encode(); self.send_response(code)
        for k, v in (hdr or {}).items(): self.send_header(k, v)
        self.send_header('Content-Type', 'application/json'); self.send_header('Content-Length', str(len(b)))
        self.end_headers(); self.wfile.write(b)
http.server.HTTPServer(('127.0.0.1', $PORT), H).serve_forever()
PY
python3 "$T/server.py" & SRV=$!
trap 'kill $SRV 2>/dev/null; wait $SRV 2>/dev/null; rm -rf "$T"' EXIT
for _ in $(seq 50); do python3 -c "import socket;socket.create_connection(('127.0.0.1',$PORT),0.2)" 2>/dev/null && break; sleep 0.1; done

cat > "$T/pi.json" <<JSON
{"providers": {
  "openrouter-free":   {"baseUrl": "http://127.0.0.1:$PORT/api/v1", "apiKey": "!echo testkey", "models": []},
  "volcengine-coding": {"baseUrl": "http://127.0.0.1:$PORT/v3", "apiKey": "testkey", "models": []},
  "bailian-token-plan": {"baseUrl": "http://127.0.0.1:$PORT/v1", "apiKey": "wrongkey-SECRET", "models": []}}}
JSON
export PI_CONFIG="$T/pi.json"

mkdir -p "$T/bin"
cat > "$T/bin/codebuddy" <<'SH'
#!/usr/bin/env bash
# 假 cb：hy3 撞额度（正文带重置时刻），其余返回 JSON
for a in "$@"; do [ "$prev" = "--model" ] && model="$a"; prev="$a"; done
# ⚠️ 前缀故意带一个别的时间戳 —— 重置时刻必须锚在「将在 … 重置」上，⛔ 不许抓第一个 HH:MM:SS
#    （⚠️ 前缀⛔不能以 `[` 开头：cb 探活把 `[`/`{` 开头的输出当 JSON 成功，那是另一条判据）
if [ "$model" = "hy3" ]; then echo "10:00:00 Error: 使用量已超出频率限制，将在 18:43:13 重置"; exit 1; fi
# 🔴 真实签名带日期和时区（catalog poolQuotaState 实录：「将在 2026-09-17 18:43:13 UTC+8 重置」）—— 审查 r2
if [ "$model" = "hy3-dated" ]; then echo "您的使用量已超出频率限制，将在 2099-01-02 18:43:13 UTC+8 重置"; exit 1; fi
echo '[{"type":"result","result":"PROBE_OK"}]'
SH
cat > "$T/bin/qoderclicn" <<'SH'
#!/usr/bin/env bash
# 假 qcn：记录收到的 -m；FAKE_QCN=quota 额度错误 / hang 挂住 / billed 已计费（total_credits>0）/ nocredits 旧版无该字段
for a in "$@"; do [ "$prev" = "-m" ] && echo "$a" > "$TMPDIR/qcn-model"; prev="$a"; done
if [ "${FAKE_QCN:-}" = "hang" ]; then sleep 4242 & sleep 4243; fi
if [ "${FAKE_QCN:-}" = "quota" ]; then echo '{"is_error": true, "result": "429 Too Many Requests: 今日免费额度已用完"}'; exit 1; fi
if [ "${FAKE_QCN:-}" = "billed" ]; then echo '{"is_error": false, "result": "PROBE_OK", "total_credits": 0.1}'; exit 0; fi
if [ "${FAKE_QCN:-}" = "nocredits" ]; then echo '{"is_error": false, "result": "PROBE_OK"}'; exit 0; fi
if [ "${FAKE_QCN:-}" = "strbilled" ]; then echo '{"is_error": false, "result": "PROBE_OK", "total_credits": "0.1"}'; exit 0; fi
if [ "${FAKE_QCN:-}" = "garbage" ]; then echo '{"is_error": false, "result": "PROBE_OK", "total_credits": "n/a"}'; exit 0; fi
echo '{"is_error": false, "result": "PROBE_OK", "total_credits": 0}'
SH
cat > "$T/bin/pi" <<'SH'
#!/usr/bin/env bash
# 🔴 假 pi：⛔ 测试里任何一条路径都不许落到真 pi（它会拿真 key 打真服务 —— RED 阶段实测踩过一次）
echo "FAKE_PI_CALLED $*" >> "$TMPDIR/pi-calls"; echo "FAKE_PI_CALLED"; exit 1
SH
chmod +x "$T/bin/"*
export PATH="$T/bin:$PATH"
P="$S/probe-models.sh"
cd_get() { bash "$S/cooldown.sh" get "$1" "$2"; }

# 1. OpenRouter 200，apiKey 走 `!command`（⛔ 不打印 key）
out=$(bash "$P" openrouter-free/stealth/ok-model); rc=$?
{ [ "$rc" -eq 0 ] && echo "$out" | grep -q '✅ openrouter-free' && ! echo "$out" | grep -q testkey; } && ok \
  || bad "OpenRouter 200 应 exit 0、✅、且不泄露 key（rc=${rc}）：$out"

# 2. 429 + X-RateLimit-Reset ⇒ 模型级失败，冷却到重置时刻
out=$(bash "$P" openrouter-free/stealth/quota-model); rc=$?
echo "$out" | grep -q '〔模型级〕' && ok || bad "429 应标模型级：$out"
[ "$(cd_get openrouter-free stealth/quota-model)" = "$RESET_LOCAL" ] && ok \
  || bad "429 带 X-RateLimit-Reset 应冷却到 ${RESET_LOCAL}（实际 $(cd_get openrouter-free stealth/quota-model)）"

# 3. 429 无重置头 ⇒ 缺省 +1h
bash "$P" openrouter-free/stealth/quota-noreset >/dev/null
got=$(cd_get openrouter-free stealth/quota-noreset)
want=$(python3 -c "import datetime;print((datetime.datetime.now()+datetime.timedelta(hours=1)).strftime('%Y-%m-%dT%H:%M'))")
[ "$got" = "$want" ] && ok || bad "429 无重置头应冷却 +1h=${want}（实际 ${got}）"

# 4. 402（余额为负）⇒ 停用这一条 24h，⛔ 不是整条通道坏
out=$(bash "$P" openrouter-free/stealth/broke-model)
{ echo "$out" | grep -q '〔模型级〕' && echo "$out" | grep -q '402'; } && ok || bad "402 应标模型级并写明 402：$out"
got=$(cd_get openrouter-free stealth/broke-model)
want=$(python3 -c "import datetime;print((datetime.datetime.now()+datetime.timedelta(hours=24)).strftime('%Y-%m-%dT%H:%M'))")
[ "$got" = "$want" ] && ok || bad "402 应冷却 24h=${want}（实际 ${got}）"

# 5. 404 ⇒ 模型级失败，⛔ 不写冷却（不是额度问题）
bash "$P" openrouter-free/stealth/gone-model >/dev/null
cd_get openrouter-free stealth/gone-model >/dev/null; rc=$?
[ "$rc" -eq 1 ] && ok || bad "404 ⛔ 不该写冷却"

# 6. 火山 429 同样写冷却（冷却是落点的事实，⛔ 不只给免费档）
bash "$P" volcengine-coding/quota-noreset >/dev/null
[ -n "$(cd_get volcengine-coding quota-noreset)" ] && ok || bad "火山 429 也应写冷却"

# 7. cb 429 正文带「将在 HH:MM:SS 重置」⇒ 冷却到那个时刻
out=$(bash "$P" codebuddy-code/hy3)
echo "$out" | grep -q '〔模型级〕' && ok || bad "cb 频率限制应标模型级：$out"
got=$(cd_get codebuddy-code hy3)
[[ "$got" == *T18:44 ]] && ok || bad "cb 429 应冷却到 18:43:13 向上取整的 18:44，⛔ 不抓前缀时间戳（实际 ${got}）"

# 8. qoderclicn：qfmodel 在 CLI 里叫 Qwen3.8-Flash（Paseo id ≠ CLI 名）
out=$(bash "$P" qoderclicn/qfmodel); rc=$?
{ [ "$rc" -eq 0 ] && echo "$out" | grep -q '✅ qoderclicn'; } && ok || bad "qcn 正常应 ✅（rc=${rc}）：$out"
[ "$(cat "$T/qcn-model" 2>/dev/null)" = "Qwen3.8-Flash" ] && ok || bad "qfmodel 探活应以 -m Qwen3.8-Flash 调 CLI（实际 $(cat "$T/qcn-model" 2>/dev/null)）"

# 9. qoderclicn 额度错误 ⇒ 模型级 + 冷却 +1h
out=$(FAKE_QCN=quota bash "$P" qoderclicn/qfmodel)
echo "$out" | grep -q '〔模型级〕' && ok || bad "qcn 额度错误应标模型级：$out"
[ -n "$(cd_get qoderclicn qfmodel)" ] && ok || bad "qcn 额度错误应写冷却"

# 10. 冷却中的落点 ⇒ 默认跳过（⛔ 不再探一次活），--force 才探
out=$(bash "$P" openrouter-free/stealth/quota-model)
echo "$out" | grep -q '冷却中' && ok || bad "冷却中的落点应直接报「冷却中」而不探：$out"

# 12. --force 放在目标之后也认；冷却中的落点强制探
bash "$S/cooldown.sh" set openrouter-free stealth/ok-model +1h "manual" >/dev/null
out=$(bash "$P" openrouter-free/stealth/ok-model --force)
echo "$out" | grep -q '✅ openrouter-free' && ok || bad "--force（放在目标后）应强制探冷却中的落点：$out"

# 13. 401 ⇒ 通道级失败（key 问题），且⛔错误路径也不许把 key 打出来
out=$(bash "$P" bailian-token-plan/ok-model); rc=$?
{ echo "$out" | grep -q 'HTTP 401' && ! echo "$out" | grep -q '〔模型级〕' && ! echo "$out" | grep -q 'SECRET'; } && ok \
  || bad "401 应是通道级、且不含 key（rc=${rc}）：$out"
! grep -q SECRET "$RIFT_COOLDOWN_FILE" 2>/dev/null && ok || bad "冷却记录里出现了 key"

# 14. qcn 超时 ⇒ 报超时，且整个进程组（含它 fork 的子进程）都被杀掉
start=$(date +%s)
out=$(FAKE_QCN=hang RIFT_PROBE_QCN_TIMEOUT=2 bash "$P" --force qoderclicn/qfmodel)
el=$(( $(date +%s) - start ))
{ echo "$out" | grep -q '超时' && [ "$el" -lt 20 ]; } && ok || bad "qcn 挂住应在超时后报超时（${el}s）：$out"
sleep 1
# ⚠️ ⛔ 别用 pgrep -f / pkill -f 'sleep 424…' —— 模式串会匹配到**调用方自己的命令行**（本测试第一次写就误中了外层 shell）
#    ⇒ 按进程参数**精确**比对（argv[0]==sleep 且 argv[1]==4242/4243），只杀这个 PID 白名单
left=$(ps -axo pid=,args= | awk '$2=="sleep" && ($3=="4242" || $3=="4243") {print $1}')
if [ -n "$left" ]; then bad "超时后残留子进程 PID: $left"; kill $left 2>/dev/null; else ok; fi

# 15. cb 真实签名（带日期 + UTC+8）⇒ 冷却到那一天那一刻（向上取整），⛔ 不退回 +1h
bash "$P" codebuddy-code/hy3-dated >/dev/null
[ "$(cd_get codebuddy-code hy3-dated)" = "2099-01-02T18:44" ] && ok \
  || bad "带日期的 cb 重置时刻应冷却到 2099-01-02T18:44（实际 $(cd_get codebuddy-code hy3-dated)）"

# 16. pi 配置里没有这个 provider（SKIP）⇒ ⛔ 不许算「全部可用」、⛔ 不许 exit 0
out=$(bash "$P" openrouter-nosuch/some-model); rc=$?
{ [ "$rc" -ne 0 ] && ! echo "$out" | grep -q '全部可用'; } && ok || bad "缺配置的 provider 不该 exit 0（rc=${rc}）：$out"

# 17. 401 ⇒ 明确提示「查 key」、⛔ 不写冷却（等不好的问题）
out=$(bash "$P" bailian-token-plan/other-model)
echo "$out" | grep -q '查 key' && ok || bad "401 应提示查 key：$out"
bash "$S/cooldown.sh" get bailian-token-plan other-model >/dev/null; rc=$?
[ "$rc" -eq 1 ] && ok || bad "401 ⛔ 不该写冷却"

# 18. 🔴 freeUntil=None 的条目必须自带「已计费」探测（2026-10-02 Qoder 延期、截止未公布：免费一结束模型照样答得动、只是开始扣费）
out=$(bash "$P" --force qoderclicn/qfmodel); rc=$?
{ [ "$rc" -eq 0 ] && echo "$out" | grep -q 'credits=0'; } && ok || bad "qcn total_credits=0 应 ✅ 且回显 credits=0（rc=${rc}）：$out"
out=$(FAKE_QCN=billed bash "$P" --force qoderclicn/qfmodel); rc=$?
{ [ "$rc" -ne 0 ] && echo "$out" | grep -q '已开始计费' && echo "$out" | grep -q '〔模型级〕'; } && ok \
  || bad "qcn total_credits>0 应判已计费（模型级、非 0 退出）（rc=${rc}）：$out"
got=$(cd_get qoderclicn qfmodel)
want=$(python3 -c "import datetime;print((datetime.datetime.now()+datetime.timedelta(hours=24)).strftime('%Y-%m-%dT%H:%M'))")
[ "$got" = "$want" ] && ok || bad "已计费应冷却 24h=${want}（实际 ${got}）"
# 🔴 r4 审查：freeUntil=None 条目的**唯一**失效证据就是这个字段 ⇒ 读不到（缺失 / 字符串乱码）不能当免费（fail-closed）
#    代价：少一个免费选项（回落付费 T1，便宜）；收益：不会因 CLI 输出格式变了而静默扣费
out=$(FAKE_QCN=nocredits bash "$P" --force qoderclicn/qfmodel); rc=$?
{ [ "$rc" -ne 0 ] && echo "$out" | grep -q '无法确认' && echo "$out" | grep -q '〔模型级〕'; } && ok \
  || bad "免费条目缺 total_credits 应判「无法确认」（模型级、非 0 退出）（rc=${rc}）：$out"
out=$(FAKE_QCN=garbage bash "$P" --force qoderclicn/qfmodel); rc=$?
{ [ "$rc" -ne 0 ] && echo "$out" | grep -q '无法确认'; } && ok || bad "total_credits 是乱码字符串应判「无法确认」（rc=${rc}）：$out"
out=$(FAKE_QCN=strbilled bash "$P" --force qoderclicn/qfmodel); rc=$?
{ [ "$rc" -ne 0 ] && echo "$out" | grep -q '已开始计费'; } && ok || bad "total_credits=\"0.1\"（字符串）应判已计费（rc=${rc}）：$out"
got=$(cd_get qoderclicn qfmodel)
want=$(python3 -c "import datetime;print((datetime.datetime.now()+datetime.timedelta(hours=24)).strftime('%Y-%m-%dT%H:%M'))")
[ "$got" = "$want" ] && ok || bad "无法确认 / 已计费都应冷却 24h=${want}（实际 ${got}）"
# 非免费 qcn 型号缺字段是正常的，⛔ 不许被 fail-closed 误伤
out=$(FAKE_QCN=nocredits bash "$P" --force qoderclicn/qmodel_38max); rc=$?
{ [ "$rc" -eq 0 ] && echo "$out" | grep -q '✅ qoderclicn'; } && ok || bad "非免费 qcn 型号缺 total_credits 不该被判无法确认（rc=${rc}）：$out"
# 非免费条目：qmodel_38max 本来就按 0.5x 计费，total_credits>0 是正常的，⛔ 不许被当成「免费期结束」
out=$(FAKE_QCN=billed bash "$P" --force qoderclicn/qmodel_38max); rc=$?
{ [ "$rc" -eq 0 ] && echo "$out" | grep -q '✅ qoderclicn'; } && ok || bad "非免费 qcn 型号有 total_credits 是正常的（rc=${rc}）：$out"
# OpenRouter：响应里 usage.cost > 0 ⇒ 已计费
out=$(bash "$P" --force openrouter-free/stealth/ok-model)
echo "$out" | grep -q 'cost=0' && ok || bad "OpenRouter 200 应回显 cost=0：$out"
out=$(bash "$P" --force openrouter-free/stealth/billed-model); rc=$?
{ [ "$rc" -ne 0 ] && echo "$out" | grep -q '已开始计费' && echo "$out" | grep -q '〔模型级〕'; } && ok \
  || bad "OpenRouter usage.cost>0 应判已计费（rc=${rc}）：$out"
[ -n "$(cd_get openrouter-free stealth/billed-model)" ] && ok || bad "OpenRouter 已计费应写冷却"
out=$(bash "$P" --force openrouter-free/stealth/nocost-model); rc=$?
{ [ "$rc" -ne 0 ] && echo "$out" | grep -q '无法确认' && echo "$out" | grep -q '〔模型级〕'; } && ok \
  || bad "OpenRouter 响应缺 usage.cost 应判「无法确认」（模型级、非 0 退出）（rc=${rc}）：$out"
[ -n "$(cd_get openrouter-free stealth/nocost-model)" ] && ok || bad "OpenRouter 无法确认也应写冷却"
out=$(bash "$P" --force openrouter-free/stealth/strcost-model); rc=$?
{ [ "$rc" -ne 0 ] && echo "$out" | grep -q '已开始计费'; } && ok || bad "usage.cost=\"0.002\"（字符串）应判已计费（rc=${rc}）：$out"
# 火山没有 usage.cost 语义：⛔ 不许被 OpenRouter 的判据误伤（假端点对 ok-model 也回 cost=0，这里只确认 ✅ 不变）
out=$(bash "$P" --force volcengine-coding/ok-model); rc=$?
{ [ "$rc" -eq 0 ] && echo "$out" | grep -q '✅ volcengine-coding'; } && ok || bad "火山探活不该受影响（rc=${rc}）：$out"

# ── 19~23. codex 探针（2026-10-06 异构审 P1-1/P1-2/P2-7/P2-8：此前 codex 用例 0 条）──
cat > "$T/bin/codex" <<'SH'
#!/usr/bin/env bash
# 假 codex：记录收到的参数；FAKE_CODEX=credits(rc=1 out of credits) / tokens-noise(rc=1 但只有 tokens/耗时数字)
#   / refuse(rc=0 assistant 段拒答) / nosection(rc=0 无分段标记) / hang(挂住)；缺省 = 回显 prompt + codex 段答 PROBE_OK
echo "$*" > "$TMPDIR/codex-args"
if [ "${FAKE_CODEX:-}" = "hang" ]; then sleep 4242 & sleep 4243; fi
if [ "${FAKE_CODEX:-}" = "credits" ]; then
  printf 'OpenAI Codex v0.156.0\n--------\nuser\nreply with exactly: PROBE_OK\n'
  printf 'ERROR: Your workspace is out of credits. Ask your workspace owner to refill in order to continue.\n' >&2
  exit 1
fi
if [ "${FAKE_CODEX:-}" = "tokens-noise" ]; then
  # 🔴 旧 RX `401|429` 在这三行上全中（tokens used: 14290 / elapsed 4012ms / (4290 tokens)）—— 锚定后必须全不中
  printf 'user\nreply with exactly: PROBE_OK\nturn 1 completed (4290 tokens)\nelapsed 4012ms, retrying\ntokens used: 14290\n'
  exit 1
fi
printf 'OpenAI Codex v0.156.0\n--------\nuser\nreply with exactly: PROBE_OK\n\n'
if [ "${FAKE_CODEX:-}" = "refuse" ]; then printf 'codex\n抱歉，我无法完成该请求\n'; exit 0; fi
if [ "${FAKE_CODEX:-}" = "nosection" ]; then printf '只有回显，没有 assistant 分段标记\n'; exit 0; fi
printf 'codex\nPROBE_OK\ntokens used: 14290\n'
exit 0
SH
chmod +x "$T/bin/codex"

# 19. codex 正常：assistant 段按要求作答 ⇒ ✅；codex/codex 用 config 默认（⛔ 不传 -m），codex/<model> 走 -m
out=$(bash "$P" codex/codex); rc=$?
{ [ "$rc" -eq 0 ] && echo "$out" | grep -q '✅ codex'; } && ok || bad "codex 正常应 ✅（rc=${rc}）：$out"
grep -q -- '-m gpt-5.6-sol' "$T/codex-args" 2>/dev/null && bad "codex/codex 不该传 -m（实际 $(cat "$T/codex-args")）" || ok
out=$(bash "$P" codex/gpt-5.6-sol); rc=$?
{ [ "$rc" -eq 0 ] && grep -q -- '-m gpt-5.6-sol' "$T/codex-args"; } && ok \
  || bad "codex/<model> 应以 -m 传给 CLI 且 ✅（rc=${rc}，args=$(cat "$T/codex-args" 2>/dev/null)）"

# 20. 🔴 P1-1：rc=0 但 assistant 段没按要求答 ⇒ ⛔ 必须报失败（旧判据全文 grep PROBE_OK 被 prompt 回显击穿恒真）
out=$(FAKE_CODEX=refuse bash "$P" codex/codex); rc=$?
{ [ "$rc" -ne 0 ] && echo "$out" | grep -q '❌ codex'; } && ok || bad "assistant 拒答必须报失败（rc=${rc}）：$out"
out=$(FAKE_CODEX=nosection bash "$P" codex/codex); rc=$?
{ [ "$rc" -ne 0 ] && echo "$out" | grep -q '❌ codex'; } && ok || bad "取不到 assistant 分段必须 fail-closed（rc=${rc}）：$out"

# 21. 🔴 P1-2：rc=1 + 额度签名 ⇒ 通道级失败（⛔ 不是〔模型级〕）+ 冷却写整族键 codex/*（P2-7：model 粒度冷却换 model 即漏）
out=$(FAKE_CODEX=credits bash "$P" codex/gpt-5.6-sol); rc=$?
{ [ "$rc" -ne 0 ] && echo "$out" | grep -q '额度耗尽' && ! echo "$out" | grep -q '〔模型级〕'; } && ok \
  || bad "out of credits 应报通道级额度耗尽（rc=${rc}）：$out"
[ -n "$(cd_get codex '*')" ] && ok || bad "额度耗尽冷却应写整族键 codex/*（实际 get codex '*' 无值）"
bash "$S/cooldown.sh" get codex gpt-5.6-sol >/dev/null; [ $? -eq 1 ] && ok \
  || bad "⛔ 不该写 model 粒度冷却 codex/gpt-5.6-sol"

# 22. 🔴 P1-2 锚定：rc=1 但输出只有 tokens/耗时数字（无额度签名）⇒ 普通失败，⛔ 不许判额度耗尽、⛔ 不写冷却
bash "$S/cooldown.sh" clear codex '*' >/dev/null
out=$(FAKE_CODEX=tokens-noise bash "$P" codex/codex); rc=$?
{ [ "$rc" -ne 0 ] && echo "$out" | grep -q '❌ codex' && ! echo "$out" | grep -q '额度耗尽'; } && ok \
  || bad "裸数字噪声不许判成额度耗尽（旧 RX 裸 401|429 全中）：$out"
bash "$S/cooldown.sh" get codex '*' >/dev/null; [ $? -eq 1 ] && ok || bad "普通失败 ⛔ 不该写冷却 codex/*"

# 23. P2-8：codex 挂住 ⇒ 超时 + 整个进程组（含它 fork 的子进程）被杀（范式抄 probe_qcn）
start=$(date +%s)
out=$(FAKE_CODEX=hang RIFT_PROBE_CODEX_TIMEOUT=2 bash "$P" --force codex/codex)
el=$(( $(date +%s) - start ))
{ echo "$out" | grep -q '超时' && [ "$el" -lt 20 ]; } && ok || bad "codex 挂住应在超时后报超时（${el}s）：$out"
sleep 1
# ⚠️ 按 argv 精确比对（⛔ pgrep -f 会匹配到调用方自己的命令行，见第 14 项注释）
left=$(ps -axo pid=,args= | awk '$2=="sleep" && ($3=="4242" || $3=="4243") {print $1}')
if [ -n "$left" ]; then bad "codex 超时后残留子进程 PID: $left"; kill $left 2>/dev/null; else ok; fi

# 11. 🔴 隔离性：整场测试⛔一次都不许调到 pi（openrouter-free 必须走直连，才拿得到真实状态码）
[ ! -s "$T/pi-calls" ] && ok || bad "测试调到了 pi：$(cat "$T/pi-calls")"

echo "=== probe-models.sh 离线测试 === 通过 $pass · 失败 $fail"
[ "$fail" -eq 0 ]
