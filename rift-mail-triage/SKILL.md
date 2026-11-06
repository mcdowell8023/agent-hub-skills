---
name: rift-mail-triage
description: "Use when reading mailbox tasks, creating or deduplicating email drafts, or sending an exact approved draft safely. Triggers: 'rift-mail', 'rift mail', '邮件草稿', '写邮件草稿', '存草稿', '发送邮件', '安全发送', '邮箱任务追踪', 'mail triage', 'draft email', 'send email'."
user-invocable: true
argument-hint: "<setup|selfcheck|fetch|draft|send|dedupe> [参数...]"
---

# Rift Mail Triage — IMAP 邮件拉取 + 草稿协作 + 受控发送

> 🔗 **rift 家族**：`/rift-dispatch`（派发）· `/rift-reap`（回收）· `/rift-integration-qa`（测试验收）
> · `/rift-egress-relay`（网络中继）· **`/rift-mail-triage`（邮件协作）**

用邮箱当协作媒介：默认只读邮件、写草稿；用户对当前邮件明确授权发送后，才允许通过唯一受控入口发送
精确的草稿 UID。结构化 JSON 进、MIME 邮件出，避免浏览器逐字段编辑时丢失 HTML 表格结构。

## 0. 能力边界（安全设计，不是限制）

- **默认只写草稿，不发送。** 没有用户对当前邮件的当场明确授权时，只能执行 `draft`，或执行不带
  `--apply` 的 `send` dry-run；草稿准备好不等于已获发送授权。
- **真实发送的唯一入口是 `rift-mail send --uid UID --apply`。** 禁止 agent 临时拼接 `smtplib`、SMTP、
  IMAP 或其他发送脚本，也禁止绕过 receipt 状态机直接调用底层模块。授权只覆盖用户指定的当前邮件，
  不自动扩展到下一封邮件或失败重试。
- `draft` 会把邮件以 `\Draft` 标志 APPEND 进草稿箱，并输出服务端确认的精确 IMAP UID；`send` 必须使用
  这个 UID，不能用主题、时间或会随 `EXPUNGE` 变化的消息序号猜目标。
- `send` 默认 dry-run，只打印主题、收件人、`Message-ID` 和 MIME SHA-256，零发送副作用；只有显式
  `--apply` 才尝试一次 SMTP。
- SMTP 调用前会落盘 receipt。相同 `Message-ID` 或 MIME SHA-256 的 receipt 会跨 UID 阻止重复发送：
  - `PREPARED`：发送身份已锁定，SMTP 尚未开始；只有完全相同的草稿能继续。
  - `UNKNOWN`：SMTP 已开始但结果不确定，或发生部分拒收；**禁止自动重试**，保留草稿并人工核查。
  - `ACCEPTED`：SMTP 已接受全部 envelope recipients；后续清理或 Sent 对账失败也不得再次 SMTP。
- SMTP 返回后只读轮询 Sent 中的同一 `Message-ID`。**永久禁止向 Sent 执行 `IMAP APPEND`**；Sent 暂时
  不可见只表示服务商自动归档可能延迟，不得补写 Sent、不得重发、不得把 `--apply` 再跑一次当作确认。
- `fetch_mail.py` 读邮件一律用 `BODY.PEEK[]`，不会把未读邮件静默标成已读。
- `dedupe_drafts.py` 只删「同主题里比最新那封更旧」的草稿，且默认 dry-run；删掉的草稿都能从本地
  `drafts/*.json` 用 `rift-mail draft` 重新生成，可逆。
- 凭据存 macOS 钥匙串（`security` 命令），不落盘明文；仅在子进程环境变量里短暂存在。

## 1. 首次设置

```bash
REPO=~/AgentWorkspace/projects/skills/agent-hub-skills/rift-mail-triage
cp "$REPO/scripts/config.example.json" "$REPO/scripts/config.json"
# 按需改 imap_host/smtp_host（默认网易企业邮 163/126），其余字段见文件内注释

"$REPO/scripts/rift-mail" setup you@example.com
```

`setup` 会交互式要求粘贴**客户端授权码**（不是登录密码）：

- 163/126/企业邮：登录 qiye.163.com（或对应网页版）→ 设置 → 客户端设置/IMAP → 开启 IMAP → 生成授权码
- Outlook/Gmail 等：账号安全设置里的「应用专用密码」

授权码存入 macOS 钥匙串（`security add-generic-password`，service=`rift-mail-triage`），
绑定当前 macOS 用户账号；`setup` 结束时会自动跑一次 `selfcheck` 验证登录+定位草稿箱。

## 2. 用法

在 `rift-mail-triage/` 目录下执行（或用上面的 `$REPO` 前缀）：

```bash
scripts/rift-mail selfcheck                              # 连通性自检，不改任何邮件状态
scripts/rift-mail fetch --days 7 --out state/inbox.json  # 拉近 7 天邮件到 JSON（人工看/喂给会话都行）
scripts/rift-mail draft --json drafts/reply.json         # 把一份草稿定义写进草稿箱
scripts/rift-mail send --uid 456                         # dry-run：核对精确草稿，零发送副作用
scripts/rift-mail send --uid 456 --apply                 # 仅在用户明确授权当前邮件后真实发送
scripts/rift-mail dedupe                                 # 预演：列出可清理的同主题重复草稿
scripts/rift-mail dedupe --apply                         # 真正执行清理
```

`draft` 成功后会输出 `[draft] uid=456` 和下一条 dry-run 命令。先运行 dry-run，把主题、收件人、
`Message-ID`、MIME SHA-256 与用户授权内容逐项核对；确认一致后，才可在同一授权范围内增加 `--apply`。
若 `--apply` 返回非零或 receipt 为 `UNKNOWN`，停止并人工核查，不能重试。

`draft` 的 JSON 结构（字段说明见 `scripts/save_draft.py` 顶部 docstring）：

```json
{
  "to": "a@x.com, b@y.com",
  "cc": "c@z.com",
  "subject": "Re: ...",
  "body": "纯文本正文（实际发送内容）",
  "body_html": "<html><table>...</table></html>",
  "in_reply_to": "<原邮件 Message-ID>",
  "references": "<...> <...>"
}
```

给了 `body_html` 就发 `multipart/alternative`（纯文本兜底 + HTML 富文本，**表格结构完整保留**——
这是相对"用浏览器编辑器手工拼 HTML 容易在换行处丢掉 `<table>` 结构"这个真实踩过的坑而设计的）。
英文正文务必配 `body_zh`（+ 可选 `context_zh`/`incoming_zh`），会在 JSON 同目录自动导出
`<文件名>_中文版.md` 供本地阅读核对，不参与实际发送。

## 3. 已知坑（协议层面，照抄即可，不要自己重新踩一遍）

- **部分 IMAP 服务商(典型如网易 163/126/企业邮) Unsafe Login**：LOGIN 成功后如果不额外发送 `ID`
  命令，任何 `SELECT` 都会返回 `Unsafe Login. Please contact ...`（这条报错本身具有误导性——
  LOGIN 明明成功了）。`mail_lib.py` 已手工把 `ID` 注册进 `imaplib.Commands` 并在登录后发送；
  换服务商时若没这限制，留着这段逻辑也无害（失败会被忽略）。
- **草稿箱等特殊文件夹名可能是 modified UTF-7 编码的中文**：网易系"草稿箱" = `&g0l6P3ux-`。
  `find_folder()` 已按 `\Drafts` 特殊标志优先、按名字模式退回两层兜底。
- **服务端 `SEARCH SUBJECT/FROM/TEXT` 子串匹配在部分服务商上完全不可用**（恒返回空）：
  想按主题/发件人找邮件，只能 `SEARCH SINCE <日期>` 拉回一批再本地按字符串过滤，
  ⛔ 不要指望服务端搜索。
- **`BODY.PEEK[]` 而非 `RFC822`**：后者会隐式给邮件打上 `\Seen`，导致邮箱打开后发现一堆
  邮件莫名其妙变成已读。
- **IMAP 删除必须用 UID 命令**：`search`/`store` 如果用序号，`expunge` 后序号整体重排，
  一次删多封容易保留的被删、作废的留下。全程用 `M.uid("SEARCH"/"FETCH"/"STORE", ...)`，
  且删除前一律先 dry-run（`dedupe_drafts.py` 默认即 dry-run）。
- **草稿回复必须带 `In-Reply-To`/`References`**，否则草稿发出去会另起一个新会话，收件人看不到
  和原邮件的关联。
- **SMTP 成功后补写 Sent 是错误模式**：没有受控发送原语时，agent 容易建议“SMTP 2xx 后 IMAP
  APPEND Sent；立即查不到就重试 APPEND”。服务商可能自行延迟归档，这会制造重复 Sent 记录。
  `send` 已负责只读轮询；任何 Sent `APPEND`、补写或发送重试都属于绕过安全边界。
- **Sent 可见性不是投递判据**：receipt 为 `ACCEPTED` 而 `sent_seen_at` 暂为空时，保留现状并报告对账
  延迟；receipt 为 `UNKNOWN` 时，停止自动化并人工核查。两种情况都不得再次执行真实发送。

## 4. 与原始版本的差异（macOS 移植说明）

本 skill 由一份 Windows 版工具包移植而来。`mail_lib.py`/`fetch_mail.py`/`save_draft.py`/
`dedupe_drafts.py`/`send_draft.py`/`selfcheck.py` 是纯 Python（stdlib only）。凭据存储方面：
原版用 Windows DPAPI（`ConvertFrom-SecureString`，绑定当前 Windows 用户+本机）经 PowerShell 脚本注入
环境变量；本版换成 **macOS 钥匙串**（`security` 命令，同样绑定当前系统用户账号），经 `rift-mail`
这个 bash 入口统一取出后注入环境变量，两者安全属性等价（文件/钥匙串项泄露 ≠ 密码泄露）。受控发送
另使用本地 receipt 记录幂等状态，默认目录为 `~/.local/state/rift-mail-triage/send-receipts/`。

原版另有一层"每日自动巡检"（Windows 计划任务 + headless Claude Code + 团队自定义的
分类/去重/bug 推进 SOP skill）**未纳入本次移植**——那一层强依赖具体团队的业务规则，
不是通用工具。如果需要，可以后续单独加一版 `rift-mail-triage-daily`，复用这里的
`fetch`/`draft`/`send`/`dedupe` 四个原语。

## 5. 依赖

纯 Python 3 标准库（`imaplib`/`smtplib`/`email`/`json`/`argparse`），零第三方包。
凭据存取依赖 macOS 自带的 `security` CLI（钥匙串），无需额外安装。
