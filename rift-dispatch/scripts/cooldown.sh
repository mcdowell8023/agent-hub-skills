#!/usr/bin/env bash
# cooldown.sh — 落点撞额度后的冷却记录（rift-dispatch §2 `cooldown_until()` 的数据源，2026-09-29）
#
# 🔴 为什么需要它：免费落点撞额度（cb「使用量已超出频率限制」/ OpenRouter 429）之后，
#    不记下来，下一次派发还会先去探它、再排一次队 —— 用户 09-29 定：撞额度 ⇒ 换下一个免费落点，并加冷却。
#
# 用法:
#   cooldown.sh set   <upstream> <model> <until> <reason>
#       until = YYYY-MM-DDTHH:MM        绝对时间（本地）
#             | YYYY-MM-DD HH:MM:SS     绝对时间到秒（cb 真实签名：「将在 2026-09-17 18:43:13 UTC+8 重置」）
#             | HH:MM[:SS]              下一次出现的这个时刻（早于现在 ⇒ 明天；cb 429 正文只给「将在 18:43:13 重置」）
#             | +<N>m | +<N>h           相对现在；⭐ 不知道重置时间时按用户定的缺省 +1h
#   cooldown.sh get   <upstream> <model>    未过期 ⇒ 打印 until、exit 0；否则无输出、exit 1
#   cooldown.sh list                        列出所有未过期记录
#   cooldown.sh clear <upstream> <model>
#
# 文件: ${RIFT_COOLDOWN_FILE:-~/.cache/rift-dispatch/cooldown.json}
#   {"<upstream>": {"<model>": {"until": "YYYY-MM-DDTHH:MM", "reason": "...", "setAt": "..."}}}
#   ⚠️ 嵌套键：model id 可能带 `/`（stealth/space-bunny-alpha），⛔ 不拼成 "u/m" 单键
#   ⚠️ 时间一律本地（Asia/Shanghai）、不带时区 —— 与 §2 伪代码的 now() 同口径
#   ⚠️ 故意⛔不放 ~/AgentWorkspace 或 ~/.claude 下：那两处是 syncthing 双向同步的，
#      额度是按账号 / key 算的，两台机器互相覆盖冷却记录只会添乱
# 并发: 读-改-写全程持有 `<文件>.lock` 的 flock（⛔ 只靠 mv 原子替换防不住丢更新 —— 审查 09-29 实测两进程各写 12 条丢了 3 条）；
#       写临时文件后 mv（原子替换，读方永远读到完整 JSON）；同一落点重复 set 取 until 较大者（⛔ 不许把更长的冷却缩短）
# 取整: 给了精确到秒的重置时刻（HH:MM:SS）⇒ **向上**取整到分钟（⛔ 不许比真实重置时刻早过期）
# 退出码: 0 成功 / 已冷却 · 1 get 时未冷却 · 2 参数错误或记录文件损坏（⇒ 调用方按「未冷却」处理，fail-open）
set -uo pipefail
F="${RIFT_COOLDOWN_FILE:-$HOME/.cache/rift-dispatch/cooldown.json}"

usage() { sed -n '8,16p' "$0" >&2; exit 2; }
cmd="${1:-}"
case "$cmd" in
  set)   [ $# -eq 5 ] || usage ;;
  get|clear) [ $# -eq 3 ] || usage ;;
  list)  [ $# -eq 1 ] || usage ;;
  *)     usage ;;
esac
mkdir -p "$(dirname "$F")"

python3 - "$F" "$@" <<'PY'
import fcntl, json, os, re, sys, tempfile, datetime as dt
F, cmd, args = sys.argv[1], sys.argv[2], sys.argv[3:]
FMT = '%Y-%m-%dT%H:%M'
now = dt.datetime.now()

def load():
    try:
        with open(F) as fh: return json.load(fh)
    except FileNotFoundError: return {}
    except json.JSONDecodeError:
        print(f'⛔ {F} 不是合法 JSON ⇒ 不读也不覆盖，先人工看一眼（调用方按「未冷却」处理：最坏多探一次活）', file=sys.stderr); sys.exit(2)

def save(d):
    fd, tmp = tempfile.mkstemp(prefix=os.path.basename(F) + '.', dir=os.path.dirname(F))
    try:
        with os.fdopen(fd, 'w') as fh: json.dump(d, fh, ensure_ascii=False, indent=2)
        os.replace(tmp, F)                   # 原子替换
    except BaseException:
        os.unlink(tmp); raise

def parse_until(s):
    if re.fullmatch(r'\+\d+[mh]', s):
        n = int(s[1:-1]); return now + (dt.timedelta(minutes=n) if s[-1] == 'm' else dt.timedelta(hours=n))
    if re.fullmatch(r'\d{4}-\d{2}-\d{2}T\d{2}:\d{2}', s):
        return dt.datetime.strptime(s, FMT)
    m = re.fullmatch(r'(\d{4}-\d{2}-\d{2})[ T](\d{2}):(\d{2}):(\d{2})', s)      # cb 真实签名带日期（审查 r2）
    if m:
        t = dt.datetime.strptime(f'{m[1]} {m[2]}:{m[3]}:{m[4]}', '%Y-%m-%d %H:%M:%S')
        return t.replace(second=0) + dt.timedelta(minutes=1) if t.second else t   # 向上取整到分钟
    m = re.fullmatch(r'(\d{1,2}):(\d{2})(?::(\d{2}))?', s)
    if m:
        t = now.replace(hour=int(m[1]), minute=int(m[2]), second=int(m[3] or 0), microsecond=0)
        t = t if t > now else t + dt.timedelta(days=1)
        return t.replace(second=0) + dt.timedelta(minutes=1) if t.second else t   # 向上取整到分钟
    return None

def live(rec):
    try: return dt.datetime.strptime(rec['until'], FMT) > now
    except Exception: return False

lock = None
if cmd in ('set', 'clear'):                  # 🔴 写操作：读-改-写整段加排他锁（读操作不加：mv 保证读到的总是完整文件）
    lock = open(F + '.lock', 'w'); fcntl.flock(lock, fcntl.LOCK_EX)
d = load()
if cmd == 'set':
    up, model, until_s, reason = args
    u = parse_until(until_s)
    if u is None:
        print(f'⛔ 看不懂的 until：{until_s!r}（要 YYYY-MM-DDTHH:MM / HH:MM[:SS] / +Nm / +Nh）', file=sys.stderr); sys.exit(2)
    old = d.get(up, {}).get(model)
    if old and live(old) and dt.datetime.strptime(old['until'], FMT) >= u:
        print(f'保持 {up}/{model} 冷却到 {old["until"]}（新值 {u.strftime(FMT)} 更短，⛔ 不缩短）'); sys.exit(0)
    d.setdefault(up, {})[model] = {'until': u.strftime(FMT), 'reason': reason, 'setAt': now.strftime(FMT)}
    save(d); print(f'{up}/{model} 冷却到 {u.strftime(FMT)}（{reason}）')
elif cmd == 'get':
    rec = d.get(args[0], {}).get(args[1])
    if rec and live(rec): print(rec['until']); sys.exit(0)
    sys.exit(1)
elif cmd == 'list':
    for up, ms in sorted(d.items()):
        for model, rec in sorted(ms.items()):
            if live(rec): print(f'{up}/{model}\t{rec["until"]}\t{rec.get("reason", "")}')
elif cmd == 'clear':
    if d.get(args[0], {}).pop(args[1], None) is not None:
        if not d[args[0]]: d.pop(args[0])
        save(d)
PY
