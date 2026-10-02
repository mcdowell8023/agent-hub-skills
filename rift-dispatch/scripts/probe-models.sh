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
#    · openrouter-free       → **直连**（2026-09-29）：key 按 pi 配置的 `!command` 从钥匙串取，⛔ 不打印
#      ⇒ 429(额度，带 X-RateLimit-Reset) / 402(余额为负) / 404(模型下线) 分得开
#    · qoderclicn            → qcn CLI `-p -o json`（2026-09-29）；⚠️ Paseo id 与 CLI 名不同（qfmodel ⇒ Qwen3.8-Flash）
#
# ⭐ 撞额度 ⇒ 自动写冷却记录（scripts/cooldown.sh，§2 的 cooldown_until() 读它）：
#    有重置时间用重置时间（OpenRouter 头 / cb 正文「将在 HH:MM:SS 重置」），否则 +1h；402 ⇒ +24h 并提示人工核查
#    冷却中的落点默认**直接报「冷却中」、⛔ 不再探一次活**；加 --force 才强制探
#
# 用法:
#   probe-models.sh                          # 探当前阶梯的默认落点
#   probe-models.sh codebuddy-code/hy3 ...   # 显式指定 provider/model
#   probe-models.sh --all                    # 探所有已知落点
#   probe-models.sh --force …                # 忽略冷却记录，强制探
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

S="$(cd "$(dirname "$0")" && pwd)"
# 🔴 2026-09-24 同步：cb 已移出 T1 池（cb 上 T1 改落 glm）；火山 coding 09-23 已进池（此前漏写）
# ⭐ 2026-09-29 T0 免费池三条按 priority 排在最前（与 SKILL FREE_POOL 同序）
DEFAULT=(openrouter-free/stealth/space-bunny-alpha
         codebuddy-code/hy3
         qoderclicn/qfmodel
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

FORCE=0; _args=()
for a in "$@"; do [ "$a" = "--force" ] && FORCE=1 || _args+=("$a"); done   # ⭐ --force 放哪都认
set -- ${_args[@]+"${_args[@]}"}
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
    \[*|\{*) echo "OK|返回 JSON|" ;;
    '')      echo "FAIL|EMPTY（超时/静默失败）|" ;;
    *429*|*频率限制*|*使用量已超出*)                                          # 额度 ⇒ 模型级 + 冷却
             # ⚠️ 锚在「将在 … 重置」上 —— ⛔ 不抓正文里第一个 HH:MM:SS（日志前缀的时间戳会被误当成重置时刻）
             #    真实签名带日期（「将在 2026-09-17 18:43:13 UTC+8 重置」，UTC+8 = 本机时区）⇒ 日期可选地一并取出
             local reset; reset=$(printf '%s' "$out" | grep -oE '将在[[:space:]]*([0-9]{4}-[0-9]{2}-[0-9]{2}[[:space:]]+)?[0-9]{1,2}:[0-9]{2}:[0-9]{2}' \
                                  | sed -E 's/^将在[[:space:]]*//' | head -1)
             echo "FAILM|$(printf '%s' "$out" | tr -d '\n|' | head -c 170)|${reset:-+1h}" ;;
    *"service info not found"*|*"not found"*)
             echo "FAILM|$(printf '%s' "$out" | tr -d '\n|' | head -c 170)|" ;;   # 模型级：通道是通的
    *)       echo "FAIL|$(printf '%s' "$out" | tr -d '\n|' | head -c 170)|" ;;
  esac
}

probe_http() { # $1=provider $2=model ；直连端点 ⇒ 真实状态码
  python3 - "$1" "$2" "$PI_CFG" "$S" <<'PY'
import json, sys, urllib.request, urllib.error
sys.path.insert(0, sys.argv[4])
from billing import classify                      # 免费条目「已计费」判定的唯一口径（三态、fail-closed）
prov, mid, cfg = sys.argv[1], sys.argv[2], sys.argv[3]
import subprocess, datetime
try:
    p = json.load(open(cfg))['providers'][prov]          # ⛔ key 只在内存里用，不打印
except Exception as e:
    print(f"SKIP|pi 配置里没有 provider {prov}（{type(e).__name__}）|"); sys.exit()
key = p.get('apiKey', '')
if key.startswith('!'):                                  # pi 的 `!command` 写法（如从钥匙串取）⇒ 照样执行
    try:    key = subprocess.run(key[1:], shell=True, capture_output=True, text=True, timeout=20).stdout.strip()
    except Exception: key = ''
    if not key:
        print(f"FAIL|取 key 的命令没返回值（钥匙串里没有？）|"); sys.exit()
body = {"model": mid, "messages": [{"role": "user", "content": "reply with exactly: PROBE_OK"}],
        "max_tokens": 16}
req = urllib.request.Request(p['baseUrl'].rstrip('/') + '/chat/completions',
        data=json.dumps(body).encode(), method='POST',
        headers={'Authorization': 'Bearer ' + key, 'Content-Type': 'application/json'})
try:
    with urllib.request.urlopen(req, timeout=60) as r:
        ok = json.loads(r.read())
        if prov.startswith('openrouter'):
            # 🔴 免费条目 freeUntil=None（截止未公布）的失效条件：免费一结束，模型照样 200、只是开始扣费 ⇒ 光看 200 会一直当免费用。
            #    证据 = 响应自带的实扣费用 usage.cost（credits）。⭐ 三态 + fail-closed：读不到也不能当免费（r4 审查）
            kind, cost = classify((ok.get('usage') or {}).get('cost'))
            if kind == 'billed':
                print(f"FAILM|已开始计费：usage.cost={cost:g}（免费期应已结束 ⇒ 核对 OpenRouter 模型页，更新 FREE_POOL / catalog 该条目）|+24h")
            elif kind == 'unknown':
                print("FAILM|无法确认免费状态：响应里 usage.cost 缺失 / 非数字（OpenRouter 响应格式变了？）⇒ 免费条目读不到计费证据，按「免费结束」处理|+24h")
            else:
                print("OK|HTTP 200 回显 " + str(ok.get('model')) + " · cost=0|")
        else:
            print("OK|HTTP 200 回显 " + str(ok.get('model')) + "|")      # 火山 / 百炼没有 usage.cost 语义（包月套餐）⇒ 不判
except urllib.error.HTTPError as e:
    try:    m = str((json.loads(e.read().decode(errors='replace')).get('error') or {}).get('message', ''))[:150]
    except Exception: m = ''
    kind = {401: 'key 无效或缺失 ⇒ 查 key（OpenRouter 在钥匙串 `openrouter` 条目）；⛔ 不写冷却 —— 等不好',
            429: '额度耗尽', 402: '余额为负（OpenRouter）⇒ 停用这一条 24h，请人工核查账户', 403: '无权限', 404: '模型不存在 / 已下线',
            400: '请求被拒（多为配置/参数问题，如缺 compat.supportsDeveloperRole —— 查配置，⛔ 不是额度）'}.get(e.code, '')
    tag = 'FAILM' if e.code in (400, 402, 403, 404, 429) else 'FAIL'    # 模型级 vs 通道级
    cool = ''
    if e.code == 429:
        rs = e.headers.get('X-RateLimit-Reset') or ''
        try:
            v = float(rs); v = v / 1000 if v > 1e11 else v            # OpenRouter 给的是毫秒时间戳
            t = datetime.datetime.fromtimestamp(v)
            if t.second or t.microsecond:                              # 向上取整到分钟（⛔ 不许比重置时刻早过期）
                t = t.replace(second=0, microsecond=0) + datetime.timedelta(minutes=1)
            cool = t.strftime('%Y-%m-%dT%H:%M')
        except ValueError:
            cool = '+1h'                                              # ⭐ 不知道重置时间 ⇒ 用户定的缺省 1 小时
    elif e.code == 402:
        cool = '+24h'
    msg = f"HTTP {e.code} {kind} {m}".rstrip().replace('|', '/')      # ⚠️ 只替换正文里的 `|`，⛔ 别连 tag 分隔符一起换
    print(f"{tag}|{msg}|{cool}")
except Exception as e:
    print(f"FAIL|{type(e).__name__}|")
PY
}

probe_qcn() {  # $1=model ；qcn CLI `-p -o json`，判 is_error + 正文。⚠️ 带超时并杀进程组（MEMORY：只杀子进程=没超时）
  python3 - "$1" "$PROBE_DIR" "${RIFT_PROBE_QCN_TIMEOUT:-120}" "$S" <<'PY'
import json, os, re, signal, subprocess, sys
mid, cwd, limit = sys.argv[1], sys.argv[2], int(sys.argv[3])
sys.path.insert(0, sys.argv[4])
from billing import classify                      # 免费条目「已计费」判定的唯一口径（三态、fail-closed）
# 🔴 Paseo 的 model id → (CLI 的 -m 名, 是否免费池条目)。
#    · 名字：Paseo id ≠ CLI 名（09-24 bench 实测 -m Qwen3.8-Flash）
#    · 免费标记：只有免费条目才把 total_credits>0 当成「免费期结束」—— qmodel_38max 本来就按 0.5x 计费，⛔ 不能被误判
#    ⚠️ 与 SKILL FREE_POOL 的 qoderclicn 条目必须一致（consistency-check §3o ⑬ 比对）
QCN = {'qfmodel': ('Qwen3.8-Flash', True)}
cli_name, expect_free = QCN.get(mid, (mid, False))
p = subprocess.Popen(['qoderclicn', '-p', '-m', cli_name, '--tools', '', '-o', 'json',
                      'reply with exactly: PROBE_OK'], cwd=cwd, stdin=subprocess.DEVNULL,
                     stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, start_new_session=True)
try:
    out, _ = p.communicate(timeout=limit)
except subprocess.TimeoutExpired:
    os.killpg(p.pid, signal.SIGKILL); p.wait(); print(f"FAIL|超时 {limit}s（已杀进程组）|"); sys.exit()
try:
    d = json.loads(out)
except Exception:
    print("FAIL|" + out.replace('\n', ' ').replace('|', '/')[:170] + "|"); sys.exit()
res = str(d.get('result') or '')
kind, tcv = classify(d.get('total_credits'))
if not d.get('is_error') and res:
    # 🔴 免费条目 freeUntil=None（Qoder CN 10-01 公告：结束时间只在公告页提前通知）的失效条件：
    #    免费一结束模型照样答得动、只是开始扣 Credits ⇒ 光看「答得动」会一直当免费用。total_credits 是 CLI 直接给的实扣值。
    #    ⭐ 三态 + fail-closed：读不到（缺失 / 乱码）也不能当免费（r4 审查：原先只认 number，缺字段就放行）
    if expect_free and kind == 'billed':
        print(f"FAILM|已开始计费：total_credits={tcv:g}（免费期应已结束 ⇒ 核对 Qoder CN 事件页，更新 FREE_POOL / catalog 的 qfmodel）|+24h"); sys.exit()
    if expect_free and kind == 'unknown':
        print("FAILM|无法确认免费状态：total_credits 缺失 / 非数字（CLI 输出格式变了？）⇒ 免费条目读不到计费证据，按「免费结束」处理|+24h"); sys.exit()
    print("OK|返回 JSON · " + res[:40].replace('|', '/') + (f" · credits={tcv:g}" if kind != 'unknown' else "") + "|"); sys.exit()
brief = res.replace('\n', ' ').replace('|', '/')[:170]
if re.search(r'429|额度|quota|rate.?limit|频率|too many', res, re.I):
    print(f"FAILM|{brief}|+1h")                   # 额度 ⇒ 模型级 + 冷却（⚠️ qcn 的额度报错原文未在真实环境见过，关键词是推测）
elif re.search(r'not found|invalid model|不存在|不支持', res, re.I):
    print(f"FAILM|{brief}|")
else:
    print(f"FAIL|{brief or 'is_error 且无正文'}|")
PY
}

probe_pi() {   # $1=provider $2=model
  local out
  # 🔴 必须 < /dev/null：继承的管道 stdin 会让 pi -p 永久阻塞（2026-09-24 A/B 实证）
  out=$(pi -p --provider "$1" --model "$2" -nt -ns -nc 'reply with exactly: PROBE_OK' < /dev/null 2>&1 | head -c 300)
  case "$out" in
    *PROBE_OK*) echo "OK|pi 返回正常|" ;;
    '')         echo "FAIL|EMPTY（pi 无输出）|" ;;
    *)          echo "FAIL|$(printf '%s' "$out" | tr -d '\n|' | head -c 170)|" ;;
  esac
}

# ⚠️ 下面凡是中文紧跟变量的地方**必须写 ${VAR}** —— 全角字符会被当成变量名的一部分，
#    在 `set -u` 下直接炸「unbound variable」。2026-09-17 实测踩到（memory 里记着这条，又犯了）。
ok=0; bad=0; bad_model=0
printf '%-26s %-24s %s\n' PROVIDER MODEL 结果
for t in "${TARGETS[@]}"; do
  prov="${t%%/*}"; model="${t#*/}"
  # ⭐ 冷却中 ⇒ 直接报，⛔ 不再探一次活（那正是冷却要省掉的排队 / 429）
  if [ "$FORCE" -eq 0 ] && until_=$(bash "$S/cooldown.sh" get "$prov" "$model"); then
    printf '⏸  %-24s %-24s 冷却中至 %s（--force 强制探）  〔模型级〕\n' "$prov" "$model" "$until_"
    bad=$((bad+1)); bad_model=$((bad_model+1)); continue
  fi
  case "$prov" in
    codebuddy-code)                         r=$(probe_cb "$model") ;;
    volcengine-*|bailian-*|openrouter-*)    r=$(probe_http "$prov" "$model") ;;
    qoderclicn)                             r=$(probe_qcn "$model") ;;
    *)                                      r=$(probe_pi "$prov" "$model") ;;
  esac
  status="${r%%|*}"; rest="${r#*|}"; detail="${rest%|*}"; cool="${rest##*|}"
  if [ -n "$cool" ]; then
    bash "$S/cooldown.sh" set "$prov" "$model" "$cool" "probe: ${detail:0:80}" >/dev/null \
      && detail="${detail} ⇒ 已写冷却（${cool}）"
  fi
  case "$status" in
    OK)   printf '✅ %-24s %-24s %s\n' "$prov" "$model" "$detail"; ok=$((ok+1))
          # 🔴 火山两套餐是【账号级 5 小时滚动额度】：16 token 的探活能 200，长上下文会话照样 429
          #    （09-15 记过、09-28 又踩：探活 200 后唤醒 X14 立刻 429）⇒ 结构性提示，⛔ 靠记性
          case "$prov" in volcengine-*)
            echo "   ⚠️ 仅证明【小请求】可过；账号级 5 小时额度下长会话仍可能 429 ⇒ 若今天该账号报过 429 且未过重置时刻，按不可用处理" ;;
          esac ;;
    SKIP) printf '⚠️  %-24s %-24s %s\n' "$prov" "$model" "$detail"; bad=$((bad+1)) ;;   # ⛔ 探不了 ≠ 可用（审查 r2：原先不计数，单目标会 exit 0）
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
