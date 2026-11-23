---
name: rift-session
description: "通用登录态能力层：给任意「账号密码 + 可选二次验证」的网站做登录态固化、定时保活、会话丢失后自动用密码重登、备份/恢复 cookie 和失效演练。跨 Linux（Agent Hub）与 macOS；站点配置与引擎分离，密码/验证码只走 stdin。Triggers: '登录态', '会话保持', '保活', '验证码', '记住设备', '重登', 'session', 'keepalive', 'rift-session', '会话丢了', '登录过期'."
user-invocable: true
argument-hint: "<list|status|login|keepalive|relogin|backup|restore|drill|schedule> [site] [--code 123456]"
---

# rift-session · 登录态固化 + 保活 + 自动重登 + 演练

> 🔗 rift 家族：`/rift-browser`（Hub 浏览器租约）· `/rift-mfa`（TOTP 动态码）· **`/rift-session`（登录态）**

引擎是一个 Python3 标准库单文件 `scripts/rift-session`（兼容 Python 3.8+，Linux / macOS）。
每个站点一份 JSON 配置放在**用户目录**（不进 git）；引擎只管：访问保活地址刷新空闲计时 → 判断是否仍登录 →
丢了就用本机私密文件里的账号密码重登一次（限频）→ 落到二次验证页就停手交给人。

## 0. 与相邻能力的关系

| 能力 | 关系 |
| --- | --- |
| `rift-browser`（Hub 浏览器租约） | 本 skill 的 `rift` 后端经它的 `cdp-helper.py` 命令行调用，**不改它、不 import 它**；它读不到 HttpOnly cookie，所以 `rift` 后端没有 backup / restore / drill |
| `rift-mfa` | 站点配 `two_factor.type = "totp:<条目名>"` 时调用它取码；不用 TOTP 的站点完全不需要 |
| `wb-archery` 等业务 skill | 它们各自处理业务页面；本 skill 只负责「让登录态活着」，**不点任何业务功能** |
| ego-browser（Mac） | `ego` / `ego_over_ssh` 后端的浏览器，复用任务空间里的登录态 |

## 1. 命令与退出码

```bash
S=~/AgentWorkspace/projects/skills/agent-hub-skills/rift-session/scripts/rift-session   # 或装到 PATH 的 rift-session
python3 $S list                       # 所有站点：上次状态、选中的后端、cookie / 记住设备令牌剩余时间（来自缓存，非实时）
python3 $S status <site>              # 实时：访问保活地址，报告是否已登录 + cookie 剩余寿命 + 实际后端及探测原因
python3 $S login <site>               # 首次登录 / 令牌过期后；走到验证码页输出 NEED_CODE 并停在原页
python3 $S login <site> --code 123456 # 在同一页继续提交验证码（`--code -` 从 stdin 读，避免进 argv）
python3 $S keepalive <site>           # 访问保活地址一次；丢了且 auto_relogin 开着就 relogin
python3 $S relogin <site>             # 仅密码重登，限频，永不请求验证码
python3 $S backup <site> | restore <site>      # cookie 备份 / 恢复（只打印名称，值不打印）
python3 $S drill <site> [--dry-run]            # A/B/C 失效演练，失败自动还原
python3 $S schedule install|remove|status <site> [--script PATH]
```

每个命令输出两行：`RIFT_SESSION cmd=… site=… state=… rc=… [k=v …]` + 一行人话。

| 退出码 | 含义 |
| --- | --- |
| 0 | 成功（LOGGED_IN / BACKUP_OK / SCHEDULED / DRILL_PASS …） |
| 2 | 需要人：`NEED_CODE`（到了二次验证页） |
| 3 | 会话丢失且无法自动恢复（含 UNKNOWN、限频跳过、登录失败、演练失败） |
| 4 | 配置 / 后端 / 参数错误（配置校验失败、后端不可用、host 被拦、站点不存在） |

状态词：`LOGGED_IN` `SESSION_LOST` `NEED_CODE` `UNKNOWN` `RELOGIN_SKIPPED` `LOGIN_FAILED` `DRILL_PASS` `DRILL_FAIL` `HOST_BLOCKED` `BACKEND_ERROR` …

## 2. 站点配置（`~/.config/rift-session/sites/<site>.json`，目录 0700、文件 0600）

样例：`scripts/examples/example-site.json`（占位域名）。配置校验失败会逐条报错；权限过宽直接拒绝。

| 字段 | 说明 |
| --- | --- |
| `base_url` / `login_url` | 站点首页 / 登录页（主机必须在 `allowed_hosts` 内） |
| `logged_in_check` | `title_regex` / `selector` / `text`，任一命中即已登录 |
| `login_page_check` | `title_regex` / `selector`，用来区分「登录页」与「无法识别」 |
| `login_form` | `username` `password` `submit` 选择器；`next` 可选（两步式：用户名页→下一步→密码页）；`after_next_wait_ms` `after_submit_wait_ms`。选择器支持 CSS，外加 `:has-text("文字")` |
| `secret_refs` | 账号密码**从哪取**：`file` + `format`（`json`/`env`：`user_key` `password_key`；`md_row`：`row_match`，取该行前两个反引号值）。只写路径与键名，不写值 |
| `session_cookie_names` / `device_token_cookie_names` | 会话 cookie / 「记住设备」令牌 cookie 名 |
| `two_factor` | `none`（默认）；或对象：`type`=`manual_code` / `totp:<rift-mfa 条目名>`，`page_title_regex` / `page_url_regex`（识别验证码页）、`code_input`、`submit`、`remember`（「记住设备」勾选，配了就必勾） |
| `keepalive` | `url`、`interval_minutes`（1..59，默认 10）、`auto_relogin`（默认 true） |
| `relogin_policy` | `max_per_hour`（默认 1） |
| `allowed_hosts` | 站点白名单，支持 `*.example.com`；引擎绝不访问 / 填写 / 点击白名单外的主机 |
| `backend` | `auto`（默认）/ `ego` / `ego_over_ssh` / `rift` / `chrome`；非 auto 时只用这一个 |
| `backend_order` | `backend=auto` 时的探测顺序，默认见 §3 |
| `backend_host` | ssh 目标（别名或 user@host，**写在用户配置里，不进仓库**）；非空表示可经 ssh 去另一台机器上跑 ego |
| `task_space` | ego 任务空间名（默认 `rift-session-<site>`）；要复用已有登录态就写已有任务空间名 |
| `chrome_bin` / `chrome_headless` / `chrome_port` | chrome 后端：可执行文件、`true`/`false`/`"auto"`、调试端口（默认自动挑空闲端口并记入状态文件） |
| `backup_file` | cookie 备份文件（默认 `~/.config/agent-secrets/rift-session-<site>.json`，0600） |
| `drill_allowed` | 必须显式 `true` 才允许 `drill` |

## 3. 后端与跨平台

接口统一（open / goto / fill / click / check / exists / get_cookies / set_cookies / delete_cookie / …）：

| 后端 | 说明 | cookie 读写 |
| --- | --- | --- |
| `ego` | macOS 本机 `ego-browser nodejs`（脚本走 stdin），任务空间在多次调用间保持页面与登录态 | ✅ |
| `ego_over_ssh` | Linux（或任意机器）经 `ssh -o BatchMode=yes <backend_host> 'zsh -lic "ego-browser nodejs"'` 在装有 ego 的 Mac 上执行 | ✅ |
| `rift` | Agent Hub：`rift-browser/bin/cdp-helper.py`（`RIFT_BROWSER_HELPER` 可指定路径）；`acquire --help` 含 `--ttl-ms` 就申请持久租约，否则退化为普通租约（靠每 <15 分钟保活续命） | ❌（读不到 HttpOnly） |
| `chrome` | **兜底**：用专用持久 profile 启动 Google Chrome（`<state>/chrome-profile/<site>`，0700），`--remote-debugging-port` 只绑 127.0.0.1，自带最小 WebSocket 客户端，不依赖任何其它组件。已在跑就复用；Linux 无显示环境自动 `--headless=new`，否则有头（便于人工过验证码）。profile 落盘即 cookie 落盘：Chrome 重启后「记住设备」等**持久** cookie 仍在（会话 cookie 不会，需 relogin） | ✅ |

默认探测顺序（逐个探测，第一个可用的就用；`status` / `list` 显示选中的后端与原因）：
macOS → `["ego","chrome"]`；Linux → `["ego_over_ssh"（仅配了 backend_host）,"rift","chrome"]`。

跨平台要点：路径一律 `expanduser`，不硬写 `/home` / `/Users`；不依赖 GNU 专有命令；日志统一写 `~/.local/state/rift-session/<site>.log`（macOS 也是这里）；
定时保活 Linux 写用户 crontab（先备份、只加不删、去重，行尾标记 `# rift-session:<site>`），macOS 写 `~/Library/LaunchAgents/com.rift-session.<site>.plist` 并打印 `launchctl bootstrap` 命令（**不自动加载**）。
日志行 `ISO时间 <site> <状态> <简述>`，超过 1 MB 轮转为 `.log.1`。`--script` 用来把定时任务指向不随 worktree 变化的稳定路径（如 `~/.local/bin/rift-session` 软链）。

## 4. 二次验证与重登规则

- `login`：走到验证码页 → `manual_code` 输出 `NEED_CODE` 并**停在原页**；拿到码后用 `login <site> --code <码>` 在同一页继续（不要重新 `login`，会再发一封验证码）；配了 `remember` 必勾。`totp:<name>` 会等到 TOTP 窗口剩余 ≥16 秒再取码并自动提交。
- `relogin` / keepalive 自动重登：**永不请求验证码**，落到验证码页输出 `NEED_CODE`（退出码 2）并停手；1 小时最多 `max_per_hour` 次，失败不重试。
- `drill`（须 `drill_allowed: true`，且当前已登录、需要能读写 cookie 的后端）：A 删会话 cookie→应回登录页；B 用备份恢复→应回已登录；C 再删会话 cookie 后只用账号密码重登→看是否还要验证码（有记住设备令牌时不要）；任一步失败自动从备份还原；全部通过后刷新备份。先 `--dry-run` 看计划。

## 5. 安全红线

1. 密码与验证码只经 stdin / CDP 消息体交给后端，**不进 argv、不进环境变量、不落盘、不进日志 / stdout**；所有输出与日志都过一遍脱敏。
2. cookie 备份只写 0600 文件，命令只打印 cookie 名称，值从不出现。
3. 只访问 / 填写 / 点击 `allowed_hosts` 内的页面；页面跳到白名单外立即 `HOST_BLOCKED` 中止。
4. 写操作只限登录页表单提交（用户名、密码、验证码、记住设备）；业务页面一律不点。
5. 登录失败不自动重试；`drill` 只对 `drill_allowed: true` 的站点。
6. 仓库里不放任何真实域名 / 账号 / 密码 / cookie / 邮箱 / IP；站点配置只在用户目录。
7. `--code` 写在命令行会出现在 `ps`，优先用 `--code -` 从 stdin 读。

## 6. 新站点接入清单

1. 复制 `scripts/examples/example-site.json` → `~/.config/rift-session/sites/<site>.json`，`chmod 600`；填 URL、选择器、`secret_refs`、cookie 名、`allowed_hosts`。
2. 把账号密码放进 `secret_refs` 指向的本机私密文件（权限 0600，不进 git）。
3. `status <site>` 确认后端、识别结果；首次需要时人工 `login <site>`（→ `--code`）。
4. `backup <site>`，再 `drill <site> --dry-run` → `drill <site>`（站点允许演练时）。
5. `schedule install <site> [--script 稳定路径]`；Mac 另需 `launchctl bootstrap …`。

## 7. 已知限制

- **不能绕过验证码**；「记住设备」令牌到期后需要一次人工验证码（令牌寿命由站点决定，`status` 会显示剩余小时数）。
- 服务端有最大会话寿命时，保活救不了，会走自动重登。
- `rift` 后端读不到 HttpOnly cookie → 无 backup / restore / drill；未启用持久租约时，租约过期会丢失登录态。
- `chrome` 后端的持久 cookie 约 30 秒后才落盘；会话 cookie（无过期时间）Chrome 重启即失效。
- macOS 的 ego-browser 不能退出 / 休眠，否则 `ego` / `ego_over_ssh` 保活会失败。
- `ego_over_ssh` 探测会做一次 `ssh … true`（8 秒超时）。

## 8. Mac 安装与使用

前置：`python3`（3.8+，系统自带即可）；ego 后端需要 ego-browser（`ego-browser nodejs` 可用）；chrome 后端需要 Google Chrome（默认路径 `/Applications/Google Chrome.app`）。两者装一个即可。

```bash
# 1) 取得 skill（自包含，只需 rift-session/ 目录）；2) 软链到各 runtime 的 skills 目录，例如：
ln -sfn <repo>/rift-session ~/.claude/skills/rift-session      # 另有 ~/.agents ~/.codex ~/.codebuddy 等
# 3) 命令行入口（可选，便于定时任务指向稳定路径）
mkdir -p ~/.local/bin && ln -sfn <repo>/rift-session/scripts/rift-session ~/.local/bin/rift-session
# 4) 写站点配置（见 §6），然后
rift-session list          # 无站点时：RIFT_SESSION cmd=list state=OK rc=0 sites=0 + 一行说明
rift-session status <site>
rift-session schedule install <site> --script ~/.local/bin/rift-session   # 只写 plist，不自动加载
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.rift-session.<site>.plist
```

## 9. 测试

```bash
cd rift-session/scripts && python3 -m unittest discover -s tests   # 全部离线：假后端 / 假 CDP 服务端 / 假 rift-mfa
```
含 Python 3.8 语法兼容检查（`ast.parse(feature_version=(3,8))` + 禁用构造扫描）。
