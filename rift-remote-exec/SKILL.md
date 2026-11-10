---
name: rift-remote-exec
description: 在另一台已注册的机器（hub / 跳板机 / 服务器）上执行命令，**不经 LLM、不消耗额度**：用 paseo 的 relay 通道直接开远端终端、敲命令、读输出。含连接串取法、封装脚本 rx.sh、Mac⇄远端文件下发通道、Windows COMODO 文件锁、ego 脚本三大坑与自检清单。Triggers: '远程执行', '在 hub 上跑命令', '不经模型', '不花额度', '远端终端', 'paseo terminal', 'relay 连接串', '免额度执行', '子 agent 执行'.
---

# Rift Remote Exec — 不经模型，在别的机器上直接执行命令

让**本机**当调度、让**远端**当执行器：命令在目标机的 shell 里跑，
本机只负责敲命令和读输出。**全程不经过 LLM，不消耗任何模型额度。**

⭐ 典型用途：额度耗尽时继续干活；大批量重复操作（跑 30 次同样的检查）；
远端机器上需要 GUI/浏览器配合的操作；子 agent（没有 `skill` 工具时也能用本 skill 的脚本）。

---

## 0. 什么时候用 / 什么时候别用

| 场景 | 用本 skill？ |
|---|---|
| 额度没了，但还得在 hub 上跑命令 | ✅ 这就是本 skill 存在的理由 |
| 要在远端跑 20~50 条同类命令 | ✅ 封装脚本 + 哨兵等待，零 token |
| 远端要跑复杂逻辑（几十行脚本） | ✅ 用「脚本下发模式」（§3） |
| 远端需要跑浏览器自动化（ego） | ✅ 同一个通道，见 §6 |
| 要改代码并让远端 agent 理解上下文 | ❌ 用 paseo agent（要 LLM） |
| 目标机器没注册进 paseo | ❌ 先注册（§1） |

---

## 1. 前置：目标主机必须已注册

```bash
paseo host ls
# LABEL      SERVER             ENABLED  STATUS   SOURCE
# wb-hub     srv_LAXE9kJgUPaH   true     online   owner/...
```

没有就注册不了。`paseo host add <connection>` 需要连接串（host:port / ws(s) / ssh / pairing URL）。

---

## 2. ⭐ 核心：relay 连接串 + 远端终端

### 2.1 取连接串（**必须用 connection 字段，不能用 targetDescription**）

```bash
CONN="$(grep -o '"connection":"[^"]*"' ~/.paseo/hosts.json | sed 's/.*"connection":"//; s/"$//')"
```

`~/.paseo/hosts.json` 里每条记录有两个字段：

| 字段 | 样例 | 能不能给 CLI |
|---|---|---|
| `targetDescription` | `relay://relay.paseo.sh:443/srv_XXX` | ❌ 报 `Invalid host connection` |
| `connection` | `relay://relay.paseo.sh:443/srv_XXX?key=<base64url>&ssl=true` | ✅ **带 key 和 ssl=true 才认** |

### 2.2 开终端 → 敲命令 → 读输出 → 杀终端（底层原语）

```bash
# 建（--workspace 决定 cwd；--cwd 可覆盖）
paseo terminal create --host "$CONN" --workspace wks_c6c58e33cff0d2ba \
  --cwd 'C:\Users\LienwaiverWB\wb' --name wb-direct --json
# -> {"id":"<terminal-id>","workspaceId":"...","cwd":"..."}

paseo terminal send-keys --host "$CONN" <id> 'whoami' Enter
paseo terminal capture --host "$CONN" <id>          # 当次输出
paseo terminal capture --host "$CONN" <id> -S       # 带回滚缓冲
paseo terminal kill    --host "$CONN" <id>
```

⚠️ 手写这四步容易踩一堆坑（回显污染、折行、退出码取不到、建终端超时…）。
**日常直接用 §2.3 的 `rx.sh`**，它把这些坑都封了。

### 2.3 用封装脚本（推荐，省掉一堆样板）

```bash
REPO=~/AgentWorkspace/projects/skills/agent-hub-skills
scripts/rx.sh --hosts
scripts/rx.sh --host-label wb-hub --cwd 'C:\Users\LienwaiverWB\wb' -- whoami
scripts/rx.sh --host-label wb-hub --cwd 'C:\Users\LienwaiverWB\wb' --timeout 120 -- 'dir /b C:\Users\LienwaiverWB\wb'
```

`rx.sh` 做的事：取连接串 → **取终端** → 敲 4 行 → 轮询 capture → 打印干净输出。

### 2.4 `rx.sh` 的四行协议（照抄即可）

```
① echo __RX_BEGIN_<唯一后缀>__   ← 锚点：定位本次输出区间
② cd /d "<目标目录>"            ← 切目录（独立成行，见下）
③ <命令>                        ← 真正要执行的命令
④ echo __RX_RC__%ERRORLEVEL%   ← 退出码探针（必须紧跟 ③）
⑤ echo __RX_OK__               ← 完成哨兵
```

⚠️ **锚点必须每次唯一**（如 `__RX_BEGIN_<pid>_<时间戳>__`）：复用终端时
capture 里留着历史运行的同名标记，固定名字会让「最后一次出现」定位到错误位置，
输出就串了。`rx.sh` 已自动加唯一后缀。

⛔ **切目录必须独立成行**，不能写成 `cd /d "..." && <命令>`：
拼起来整行过长 → 终端按宽度折行 → **回显被拆成多行**，与真实输出混在一起无法区分。
独立成行后，回显行以提示符开头（`C:\path>`）能被干净过滤。

⛔ **退出码探针必须紧跟命令、且单独一行**：
cmd 在**解析整行时**就展开 `%ERRORLEVEL%`，所以同一行里取到的是行首状态（恒为 0）；
只有跨行才取到上一行（命令）的真实退出码。实测 `cmd /c exit 7` 后另起一行
`echo %ERRORLEVEL%` 才拿到 7。

### 2.5 完成 vs 成功（两件事，别混）

| 判定 | 依据 | 结果 |
|---|---|---|
| **完成** | 哨兵 `__RX_OK__` 出现 ≥ 2 次（回显 1 次 + 输出 1 次） | 继续 |
| **成功** | 退出码 == 0 | `exit 0` |
| **失败** | 退出码 != 0 | `exit 125`（⚠️ **不静默假成功**） |
| **超时** | 等不到哨兵 | `exit 124` |

⚠️ **为什么必须区分**：cmd 的 `cd` 失败会**短路 `&&`**（后面的命令根本不跑），
但 shell 照样回到提示符。只看「提示符回来了」会把「命令没跑」判成成功。
⛔ 别用「提示符重现」当唯一的完成判据 —— 它只作兜底。

⚠️ 哨兵必须写成**纯文本**：cmd 的 `echo` **不剥引号**，
`echo __RX""_OK__` 会原样输出带引号的串。
⚠️ 比较哨兵计数前会去掉所有空白 —— 终端会按窗口宽度把哨兵折行（`__RX_` + `OK__`）。

### 2.6 取终端：先复用，再新建（重要）

实测：hub 上多个 agent 并发时，**新建终端会超时**
（`TERMINAL_CREATE_FAILED: createTerminal timed out`），
但**已存在的终端一直好用**；而 agent 通道（`paseo ls`）此时完全正常
→ 是 terminal-worker 拥塞，**不是 relay 断**。

所以 `rx.sh` 的策略是：
1. **先复用**已有终端（cwd 相同优先），发 cd 切到目标目录；
2. 复用不到才新建（重试 3 次）；
3. 新建也超时 → 降级用**父目录**建，再 cd 回去；
4. 复用的终端**不会被 kill**（可能是别人的），只有自建的才回收。

⚠️ **复用的终端可能随时被远端回收**（实测会莫名消失）→ `rx.sh` 检测到
「终端不存在」或「send-keys 失败」时会**自动重建并重试**（重建后重取基线）。

⚠️ **同一台机器上并发跑多个 rx.sh 会串台**（两条命令交错进同一个终端，
输出与退出码全乱，实测踩到）→ `rx.sh` 内置**文件锁**串行化：
锁目录 `$TMPDIR/rx-lock-<label>/lock`，里面存持锁进程 PID；
持锁进程被杀会留下**陈旧锁**，脚本按 PID 存活检查自动清理（最多试 3 次，不死循环）。
等锁最多 120 秒（`--lock-wait` 可调）；确认没别人在用时可 `--no-lock` 跳过。

⚠️ **不要用「既不传 `--cwd` 也不传 `--workspace`」建终端**：CLI 会把**本机** cwd
（`/Users/mcdowell/wb`）当默认值发给远端，远端直接报 `Directory not found`。

⚠️ `--cwd` 指定**正在被高频写入的目录**时更容易超时（Windows 实时防护 COMODO
扫描该目录会拖慢 shell 初始化）。目录本身没坏：`dir /b` 完全正常，换父目录就秒成。

⚠️ `rx.sh` 依赖目标机默认 shell 是 **cmd.exe**（Windows）或 bash（Linux/macOS），
退出码探针两种都兼容（cmd 取 `%ERRORLEVEL%`，sh 取 `$?`）。

### 2.7 ⛔ 命令别太长（折行会让输出失真）

终端按窗口宽度（约 80 列）折行。命令一长，**回显就被拆成多行**，
回显与真实输出无法可靠分离 —— 表现为「输出整段丢失」或「混进回显碎片」。

- 命令 **≤ 60 字符**：直接敲，正常。
- 命令 **> 60 字符**：改用 §3 的**脚本下发模式**（Mac 写文件 → hub `curl` 拉 → 执行），
  终端里只敲一条短命令。

`rx.sh` 在命令超过 60 字符时会打印警告，但仍会继续执行。

---

## 3. 复杂逻辑：脚本下发模式（远端跑脚本，Mac 出逻辑）

远端不能直接写文件（Mac→hub 入站端口全关），所以**让远端来拉**：

1. Mac 侧起一个最小 HTTP 接收器（一次性，用完即杀）：
   ```python
   # ~/wb/tmp-scratch/inbound/receiver.py
   from http.server import BaseHTTPRequestHandler, HTTPServer
   class H(BaseHTTPRequestHandler):
       def do_GET(self):
           name = self.path.strip("/").split("?")[0]
           data = open("/abs/dir/" + name, "rb").read()
           self.send_response(200); self.send_header("Content-Length", str(len(data))); self.end_headers()
           self.wfile.write(data)
       def do_POST(self):
           n = int(self.headers.get("Content-Length", 0))
           open("/abs/dir/" + self.path.strip("/"), "wb").write(self.rfile.read(n))
           self.send_response(200); self.end_headers()
       def log_message(self, *a): pass
   HTTPServer(("0.0.0.0", 18080), H).serve_forever()
   ```
2. 远端拉脚本并执行（通过 §2 的通道发这条命令）：
   ```powershell
   curl.exe -s -m 60 -o "$env:TEMP\job.ps1" "http://<mac-ip>:18080/job.ps1"
   powershell -NoProfile -ExecutionPolicy Bypass -File "$env:TEMP\job.ps1"
   ```
3. 脚本内把结果 POST 回 Mac：`curl.exe -sS -X POST --data-binary "@$out" "http://<mac-ip>:18080/result.txt"`。
4. Mac 侧读 `result.txt` 验收。

⚠️ Mac 的 Tailscale IP **会变**，用 `tailscale status` 的实时输出，别写死历史值。
⚠️ 传输可能**中途截断**（大文件偶发）：远端下完必须校验**字节数 + SHA256**，不一致就重试。

---

## 4. 已知坑（都实测过，别重走）

| 现象 | 原因 | 解法 |
|---|---|---|
| `Invalid host connection` | 只给了 `targetDescription` | 用 `connection` 字段（带 `key=` + `ssl=true`） |
| `paseo terminal ls --host <br>` 返回空但没报错 | 连接成功，只是这台没有终端 | 正常现象，先 `terminal create` |
| MCP 侧 `create_terminal` 在**本机**建了个字面量目录 | MCP 的 terminal/script 是**本地作用域**，没有 `serverId` | 走 CLI（带 `--host`） |
| `list_workspace_scripts` 报 `Workspace not found` | 同上，远端 workspace id 不认 | 同上 |
| `respond_to_permission` / `set_agent_mode` → `Unknown agent` | 只认本机 agent | 远端 agent 用 `send_agent_prompt` 的 `sessionMode: bypassPermissions` |
| 完成通知报 `code: -32603`（Session already has an active Turn） | 通知投递撞上本轮 Turn | 只丢通知不丢结果；`notifyOnFinish: false` + 主动轮询 |
| 远端 `Move-Item -Force` 覆盖不生效 | PowerShell 5.1 的坑 + 文件被占 | 用 `[System.IO.File]::Copy($src,$dst,$true)` |
| 远端文件「被其他进程占用」删不掉 | **COMODO 实时防护**（`cmdagent.exe` / 服务 `CmdAgent`）长期独占句柄 | ⛔ 不杀毒软件；改路径重装（新文件新句柄）；或经用户同意重启服务 |
| 带 `--cwd` 建终端整体超时（`createTerminal timed out`） | COMODO 扫该目录把 shell 初始化拖慢（目录本身没坏，换父目录就秒成） | 重试；仍失败则改用父目录建 + 独立 `cd`（`rx.sh` 已内置） |
| 多 agent 并发时**新建终端**超时，但 `paseo ls` 正常 | terminal-worker 拥塞，**不是 relay 断** | 先**复用**已有终端（`rx.sh` 默认行为） |
| 建终端报 `Directory not found: /Users/mcdowell/wb` | 既没传 `--cwd` 也没传 `--workspace` → CLI 把**本机** cwd 发给了远端 | 至少传 `--workspace` 或 `--cwd` |
| 同一行里 `cmd & echo %ERRORLEVEL%` 取到的是 0 | cmd 解析整行时就展开了 `%ERRORLEVEL%` | 退出码探针**单独一行**、紧跟命令 |
| `cd` 失败后命令没跑，脚本却报成功 | `cd` 失败会短路 `&&`，但 shell 照样回提示符 | 看**退出码**，别只看提示符（`rx.sh` 用退出码，失败 exit 125） |
| 输出里混入命令回显 / 提示符 | 终端回显输入、且长命令会折行 | `cd` 独立成行；靠提示符前缀过滤回显行 |
| 锚点定位到历史运行的位置，输出串台 | 复用终端时 capture 里留着旧标记 | 锚点带**唯一后缀**（PID + 时间戳） |
| 两条命令交错执行，输出与退出码全乱 | 同一台机器**并发**跑多个 rx.sh，踩同一个终端 | 内置文件锁串行化（PID 存活检查自动清陈旧锁） |
| curl 下的文件字节数不对 | 传输中途截断 | 校验字节数 + SHA256，不一致重试 |

---

## 5. 在远端跑 ego 浏览器脚本（Windows）

ego 的 `nodejs` **只认 `-e <代码>`**，不认脚本文件路径。正确姿势是 **PowerShell + 调用运算符 `&`**：

```powershell
$ego = 'C:\Users\LienwaiverWB\.local\share\ego\active_version_dir\ego-browser.exe'
$dst = 'C:\Users\LienwaiverWB\wb\tmp-scratch\job.mjs'
$u = 'file:///' + ($dst -replace '\\','/')
$js = "const f=async()=>{await import('$u').then(m=>m.default())};f().catch(e=>console.error('ERR '+String(e)))"
& $ego nodejs -e $js 2>&1
```

三个连环坑：

1. `Start-Process -ArgumentList` 传**带空格**的参数会被拆开 → node 只收到半截代码，
   报 `SyntaxError: Unexpected end of input`。改用 `& $ego nodejs -e $js`。
2. **cmd.exe 把 `=>` 里的 `>` 当重定向符**，代码被截断。优先在 PowerShell 里跑；
   必须走 cmd 时改用 `function(m){return m.default()}` 这类无 `>` 的写法。
3. `"$i:"` 在 PowerShell 里是**驱动器引用**，报 `Variable reference is not valid` → 写 `"${i}:"`。

ego 脚本要点：
- 脚本用 `export default async function`，外层 `.then(m => m.default())` 才拿得到。
- `console.log` 才回显；`return` 的值不打印。
- **必须用 ego 原生 `page.hover()` + `page.click()`**；手工拼 `Input.dispatchMouseEvent`
  点不动（同一元素手动点 6 次菜单都不弹，原生点击一次就开）。
- `page.evaluate` 里的 `el.click()` 是合成手势，很多页面直接免疫。
- 脚本内把中文结果 POST 回 Mac（终端 capture 是 GBK 乱码，POST 回来才是 UTF-8）。

---

## 6. 自检清单（动手前过一遍）

- [ ] `paseo host ls` 里目标主机 `status=online`
- [ ] 连接串取的是 `connection` 字段（带 `key=` / `ssl=true`）
- [ ] 优先用 `rx.sh`（自带复用终端 / 降级 / 退出码判定），别手写裸命令
- [ ] 手写时：切目录**独立成行**，退出码探针**单独一行且紧跟命令**
- [ ] 用完**杀了自建的终端**（`paseo terminal kill`），别在远端留一堆壳（复用的别杀）
- [ ] 长逻辑走「脚本下发模式」，不要在终端里手打几百行
- [ ] 下载的文件校验**字节数 + SHA256**
- [ ] 脚本输出 POST 回 Mac 验收，**别信「脚本跑完了」**
- [ ] 没有把凭据写进 `docs/`、git 仓或 skill 正文

---

## 7. 边界

- 本 skill 只做**命令执行**通道，不做「让远端 agent 理解需求」——那需要 paseo agent（吃额度）。
- 不要用它绕过权限：远端能执行什么，仍受目标机自身的权限与安全策略约束
  （例如 COMODO 这类安全软件**不应被停用**）。
- 连接串里的 `key` 等于**远端主机访问凭据**：不要提交进 git、不要贴进聊天记录。
