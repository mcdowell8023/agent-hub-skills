#!/usr/bin/env bash
# probe-models.sh — 跨 provider 的模型探活（rift-dispatch 的 `probe_ok()` 可执行实现）
#
# 🔴 为什么需要它：**Paseo 不透传 HTTP 状态码。**
#    模型被 429 限流时，Paseo 侧只表现为「新会话零产出（updateCount==1）」或
#    「turn 到头唤不醒（activeTurn:null）」—— 形态与 provider 稳定性故障**一模一样**，
#    而两者处置**方向相反**：稳定性问题换 provider，配额问题换模型或等重置。
#
# ⭐ 分流（不同 provider 能拿到的证据强度不同，⛔ 别一套办法打天下）：
#    · codebuddy-code        → cb CLI，判 stdout 是不是 JSON（CLI 也不给状态码，只能看正文）
#    · volcengine-* / bailian-* → **直连端点**，拿【真实 HTTP 状态码】
#      ⇒ 429(额度) / 403(无权限) / 404(不存在) **三态分得开**，且 429 正文带重置时间
#    · github-copilot        → 走 pi（没有可直连的 key）
#
# 用法:
#   probe-models.sh                          # 探当前阶梯的默认落点
#   probe-models.sh codebuddy-code/hy3 ...   # 显式指定 provider/model
#   probe-models.sh --all                    # 探所有已知落点
#
# 退出码（⭐ 三档，⛔ 不是二值）：
#   0 = 全部可用
#   1 = **部分**不可用 ⇒ ⚠️ 这是**正常状态**，换个模型/换个池即可，⛔ 别据此怀疑通道
#   2 = **通道级**失败 ≥2 且无一可用 ⇒ 才该怀疑通道 / 凭据 / 网络
#       🔴 HTTP 400/403/404/429（及 cb 的限流/不存在正文）是【模型级】失败 —— 通道能规范地返回错误
#          就说明它是通的 ⇒ ⛔ 不计入通道判据（2026-09-24：同一模型两种写法×两套餐全 404，旧逻辑误报「怀疑通道」）
#   ⭐ 这个区分就是为了防「某个模型失败 ⇒ 判定整条通道坏了」这类误诊。

set -uo pipefail
PI_CFG="${PI_CONFIG:-$HOME/.pi/agent/models.json}"
PROBE_DIR="${TMPDIR:-/tmp}/rift-probe"; mkdir -p "$PROBE_DIR"

# 🔴 2026-09-24 同步：cb 已移出 T1 池（cb 上 T1 改落 glm）；火山 coding 09-23 已进池（此前漏写）
DEFAULT=(codebuddy-code/hy3
         volcengine-coding/deepseek-v4.1-flash
         volcengine-agent-plan/deepseek-v4.1-flash
         bailian-token-plan/deepseek-v4.1-flash
         codebuddy-code/glm-5.3-flash)
ALL=("${DEFAULT[@]}"
     codebuddy-code/deepseek-v4.1-flash
     volcengine-coding/glm-5.3-flash
     volcengine-coding/deepseek-v4-flash
     volcengine-agent-plan/deepseek-v4-flash
     bailian-token-plan/qwen3.8-max
     codebuddy-code/kimi-k3-1)   # ⚠️ cb/glm 已在 DEFAULT 里，别重复

case "${1:-}" in
  --all) TARGETS=("${ALL[@]}") ;;
  "")    TARGETS=("${DEFAULT[@]}") ;;
  *)     TARGETS=("$@") ;;
esac

probe_cb() {   # $1=model ；cb CLI 不给状态码 ⇒ 只能判正文
  local out
  out=$(cd "$PROBE_DIR" && codebuddy -p --model "$1" --output-format json \
          --tools "" 'reply with exactly: PROBE_OK' 2>&1 | head -c 400)
  case "$out" in
    \[*|\{*) echo "OK|返回 JSON" ;;
    '')      echo "FAIL|EMPTY（超时/静默失败）" ;;
    *429*|*频率限制*|*使用量已超出*|*"service info not found"*|*"not found"*)
             echo "FAILM|$(printf '%s' "$out" | tr -d '\n' | head -c 170)" ;;   # 模型级：通道是通的
    *)       echo "FAIL|$(printf '%s' "$out" | tr -d '\n' | head -c 170)" ;;
  esac
}

probe_http() { # $1=provider $2=model ；直连端点 ⇒ 真实状态码
  python3 - "$1" "$2" "$PI_CFG" <<'PY'
import json, sys, urllib.request, urllib.error
prov, mid, cfg = sys.argv[1], sys.argv[2], sys.argv[3]
try:
    p = json.load(open(cfg))['providers'][prov]          # ⛔ key 只在内存里用，不打印
except Exception as e:
    print(f"SKIP|pi 配置里没有 provider {prov}（{type(e).__name__}）"); sys.exit()
body = {"model": mid, "messages": [{"role": "user", "content": "reply with exactly: PROBE_OK"}],
        "max_tokens": 16}
req = urllib.request.Request(p['baseUrl'].rstrip('/') + '/chat/completions',
        data=json.dumps(body).encode(), method='POST',
        headers={'Authorization': 'Bearer ' + p['apiKey'], 'Content-Type': 'application/json'})
try:
    with urllib.request.urlopen(req, timeout=60) as r:
        print("OK|HTTP 200 回显 " + str(json.loads(r.read()).get('model')))
except urllib.error.HTTPError as e:
    try:    m = str((json.loads(e.read().decode(errors='replace')).get('error') or {}).get('message', ''))[:150]
    except Exception: m = ''
    kind = {429: '额度耗尽', 403: '无权限', 404: '模型不存在', 400: '请求被拒（多为配置/参数问题，如缺 compat.supportsDeveloperRole —— 查配置，⛔ 不是额度）'}.get(e.code, '')
    tag = 'FAILM' if e.code in (400, 403, 404, 429) else 'FAIL'    # 模型级 vs 通道级
    print(f"{tag}|HTTP {e.code} {kind} {m}".rstrip())
except Exception as e:
    print(f"FAIL|{type(e).__name__}")
PY
}

probe_pi() {   # $1=provider $2=model
  local out
  # 🔴 必须 < /dev/null：继承的管道 stdin 会让 pi -p 永久阻塞（2026-09-24 A/B 实证）
  out=$(pi -p --provider "$1" --model "$2" -nt -ns -nc 'reply with exactly: PROBE_OK' < /dev/null 2>&1 | head -c 300)
  case "$out" in
    *PROBE_OK*) echo "OK|pi 返回正常" ;;
    '')         echo "FAIL|EMPTY（pi 无输出）" ;;
    *)          echo "FAIL|$(printf '%s' "$out" | tr -d '\n' | head -c 170)" ;;
  esac
}

# ⚠️ 下面凡是中文紧跟变量的地方**必须写 ${VAR}** —— 全角字符会被当成变量名的一部分，
#    在 `set -u` 下直接炸「unbound variable」。2026-09-17 实测踩到（memory 里记着这条，又犯了）。
ok=0; bad=0; bad_model=0
printf '%-26s %-24s %s\n' PROVIDER MODEL 结果
for t in "${TARGETS[@]}"; do
  prov="${t%%/*}"; model="${t#*/}"
  case "$prov" in
    codebuddy-code)            r=$(probe_cb "$model") ;;
    volcengine-*|bailian-*)    r=$(probe_http "$prov" "$model") ;;
    *)                         r=$(probe_pi "$prov" "$model") ;;
  esac
  status="${r%%|*}"; detail="${r#*|}"
  case "$status" in
    OK)   printf '✅ %-24s %-24s %s\n' "$prov" "$model" "$detail"; ok=$((ok+1))
          # 🔴 火山两套餐是【账号级 5 小时滚动额度】：16 token 的探活能 200，长上下文会话照样 429
          #    （09-15 记过、09-28 又踩：探活 200 后唤醒 X14 立刻 429）⇒ 结构性提示，⛔ 靠记性
          case "$prov" in volcengine-*)
            echo "   ⚠️ 仅证明【小请求】可过；账号级 5 小时额度下长会话仍可能 429 ⇒ 若今天该账号报过 429 且未过重置时刻，按不可用处理" ;;
          esac ;;
    SKIP) printf '⚠️  %-24s %-24s %s\n' "$prov" "$model" "$detail" ;;
    FAILM) printf '❌ %-24s %-24s %s  〔模型级〕\n' "$prov" "$model" "$detail"; bad=$((bad+1)); bad_model=$((bad_model+1)) ;;
    *)    printf '❌ %-24s %-24s %s\n' "$prov" "$model" "$detail"; bad=$((bad+1)) ;;
  esac
done

ok_plus_bad=$((ok + bad))
echo "----"
if   [ "$bad" -eq 0 ]; then echo "全部可用（${ok}）"; exit 0
elif [ "$ok" -gt 0 ];  then
  echo "部分不可用：可用 ${ok} / 不可用 ${bad}"
  echo "⚠️ 这是**正常状态** —— 换个模型或换个池即可，⛔ 别据此判定通道坏了。"
  exit 1
elif [ "$((bad - bad_model))" -lt 2 ]; then
  # 🔴 **通道级失败不足 2 个 ⛔ 推不出通道有问题**：
  #    · n=1 时「全部失败」就是「这一个失败」（断言「X 类不可用」前必须测过该类里多个实例）
  #    · 模型级失败（4xx 规范错误）说明通道**正常应答** —— 数再多也⛔不是通道问题
  if [ "$bad_model" -eq "$bad" ]; then
    echo "全部失败，但都是【模型级】（${bad_model} 个 HTTP 400/403/404/429 或 cb 限流/不存在）"
    echo "⭐ 通道能规范返回错误 ⇒ **通道是通的**，⛔ 别怀疑通道 —— 查模型 id / 套餐是否包含 / 额度；全是 400 则多为请求参数或 compat 配置问题。"
  else
    echo "通道级失败只有 $((bad - bad_model)) 个（另有模型级 ${bad_model} 个）"
    echo "⚠️ ⛔ **不足以判断通道**。要怀疑通道请再探同 provider 的其它模型。"
  fi
  exit 1
else
  echo "🔴 通道级失败 $((bad - bad_model)) 个、无一可用（样本 ≥2）—— 这才该怀疑通道 / 凭据 / 网络。"
  exit 2
fi
