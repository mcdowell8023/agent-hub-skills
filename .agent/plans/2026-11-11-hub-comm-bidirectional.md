# Hub → Mac 双向 Paseo 注册与派发收口计划

## 1. 目标与边界

目标是把已经实测成功的 Hub → Mac 路由流程固化到 `hub-comm` skill，避免 Hub agent 在本地 `list_hosts` 为空时误判为“无法联系 Mac”，转而要求人工复制整段任务。

本次源码变更范围严格限定为单文件：

- `hub-comm/SKILL.md`

`rift-remote-exec` 只作为 Hub 安装包中的既有配套 skill，不修改其源码。不修改 CRM 代码、Paseo daemon 配置或其他 skill；不 commit、不 push。

## 2. 真实 RED 证据

Hub 主会话 `ff4a17ad-74b8-4074-993f-29057bc7a40e` 当时缺少 `hub-comm`，且 Hub 本地没有 Mac host 注册。其原话是：

> `list_hosts 是空的...没有 route...你把 B、C（还有 A）整段复制给 Mac 的 agent`

这是功能级 RED：网络连通并不等于 Paseo registry 已建立路由；缺少 skill 时，Hub agent 不知道需先检查/注册 Mac host，也不知道注册后可直接创建 Mac child agent。

已有人工修复证明路径可行：Hub 执行 `paseo host add` 后，`list_hosts` 看到 `macbook-pro` online，随后 Hub 主会话在 Mac workspace 创建 child agent，收到精确响应 `MAC_ROUTE_OK`，结果为 `ROUTE_E2E_PASS`。本计划要把这条人工知识变成可执行的 skill 流程。

## 3. 实施步骤

### 3.1 修订 `hub-comm/SKILL.md`

1. 在文档前部增加“当前机器先注册对端”的 fail-closed 检查顺序：
   - 先确认本机 Paseo daemon 状态。
   - 只针对明确给定的 Mac Paseo endpoint 做单点 TCP/daemon 连通性检查，不扫描网段。
   - 读取本机 registry；若 Mac `serverId` 已存在且 endpoint 一致，不重复注册。
   - 若不存在，使用 `paseo host add <mac-endpoint> --label macbook-pro`；若已存在但 serverId/endpoint 冲突，立即 STOP，不覆盖、不删除既有记录。
   - 用 `host inspect` 及会话可用的 `list_hosts` 双重复查 `enabled=true`、`status=online`、`error=null`和目标 serverId。不回显 registry key、token 或其他凭据。
2. 改正过时结论“MCP 只能操作本地 daemon、跨机器必须 CLI `--host`/SSH”：当对端已注册到当前 Paseo registry 时，应优先用 host-aware 的 `list_hosts` → `list_workspaces` → `create_agent`，并用返回的 `serverId` 验证 child 确实在 Mac 上。
3. 写清 Hub agent 的派发契约：
   - 先选中 `macbook-pro` 及 workspace `/Users/mcdowell/wb`，不自行猜测 workspace id。
   - 创建 child 后核对 child 的 `serverId` 是 Mac，再等待它返回精确验收字符串。
   - 路由未建立时不得把整段任务推回给用户人工复制；应先完成可安全自动完成的注册、检查和路由。
4. 去除文档中的明文 Dufs 认证示例，改为环境变量/受限凭据文件占位符；不在 skill 内固化真实 IP、密码、registry key 或 token。

### 3.2 静态 GREEN

实施后在工作树中运行静态验收，不连接 Hub、不修改 registry：

1. `git diff --name-only origin/main...HEAD` 与未提交变更组合检查，确认 skill 源码只改 `hub-comm/SKILL.md`（`.agent/plans/*` 是过程证据，不计入 skill 源码）。
2. 校验 YAML frontmatter 只有一个合法文档头，`name: hub-comm` 不变，且文档仍可被 skill loader 识别。
3. 静态断言必须同时出现：registry 读取、`paseo host add`、`host inspect`、`list_hosts`、`list_workspaces`、`create_agent`、child `serverId` 校验、精确回执验收及冲突 STOP。
4. 静态断言不得仍声称“MCP 只能本地、跨机器必须 CLI/SSH”，不得含真实 Dufs 密码或其他凭据。
5. 对部署用干净归档做解包前检查：只允许 `hub-comm/` 和 `rift-remote-exec/` 两棵目录；拒绝绝对路径、`..`、链接、设备项、AppleDouble `._*`、`__pycache__`、`*.pyc`、`.omx` 与 `policy.local.json`。
6. 对归档中每个正式文件生成 `RelativePath|Length|SHA256` manifest，安装后四个目标必须与各自源树 0 差异。

## 4. Hub 安装：四个严格白名单目标

仅允许安装到以下四个精确路径：

1. `C:\Users\LienwaiverWB\.claude\skills\hub-comm`
2. `C:\Users\LienwaiverWB\.claude\skills\rift-remote-exec`
3. `C:\Users\LienwaiverWB\.agents\skills\hub-comm`
4. `C:\Users\LienwaiverWB\.agents\skills\rift-remote-exec`

本轮明确不安装 `.codex`、`.minimax`、`.codebuddy` 或其他路径，不运行全量链接安装脚本。

对每一个白名单目标独立执行如下状态机：

- **missing → create**：把源树复制到目标同父目录下的唯一临时目录，校验 manifest 为 0 差异后，立即重查正式目标仍 missing，再原子改名为正式目标。
- **same → no-op**：现有目标的完整树 manifest 与源树相同时不写入、不改名、不刷新 mtime，只记录 no-op。
- **different → STOP**：任何路径、长度或 SHA256 不同均立即停止该目标及后续目标的安装，不覆盖、不备份、不删除。

### 4.1 防竞态与回滚约束

1. 安装前、临时树校验后/原子改名前、改名后分别重查目标。
2. 如果 missing 分支在改名前发现目标被其他进程创建：
   - 新目标与源树相同：转为 no-op，仅清理本次唯一临时目录。
   - 新目标与源树不同：STOP，不碰新目标，仅清理本次唯一临时目录。
3. 每个已创建目标记录“安装树哈希”。如果后续验证失败，只有在回滚当下重算的整树哈希仍与该安装哈希完全一致时，才可删除本次创建的目标。
4. 如果目标在安装后被其他进程改动，整树哈希将不一致；此时禁止回滚覆盖/删除，只报告并 STOP。
5. same/no-op 和 different/STOP 分支从未获得目标所有权，不得将它们纳入回滚清单。

## 5. Fresh Hub agent 端到端 GREEN

四个目标安装与 manifest 复核通过后，新建 Hub agent（不复用旧会话的 skill 快照），且仅给它以下验收任务：

1. 确认新会话的 skill 清单能发现 `hub-comm` 和 `rift-remote-exec`。
2. 按 `hub-comm` 新流程使用 `list_hosts` 定位 online 的 `macbook-pro`，记录 Mac serverId。
3. 使用 `list_workspaces` 选中 `/Users/mcdowell/wb`。
4. 由 Hub 新会话实际创建一个 Mac child agent，要求 child 仅返回精确一行 `MAC_ROUTE_OK_AFTER_SKILL`，不改文件、不创建更多 agent。
5. 复查 child 的实际 serverId 等于步骤 2 的 Mac serverId，workspace/cwd 等于 `/Users/mcdowell/wb`，且响应精确为 `MAC_ROUTE_OK_AFTER_SKILL`。三项缺一即 E2E FAIL。

该验收只验证路由，不执行 CRM 开发、部署、push、生产写入或邮件发送。

## 6. 完成条件

- skill 源码只修改 `hub-comm/SKILL.md`。
- 静态 GREEN 全部通过，计划审查哈希与当前计划一致。
- Hub 仅上述四个白名单目标进入 create 或 no-op，每个目标与对应源树 0 manifest 差异。
- Fresh Hub agent 实际在 Mac 创建 child，child 返回 `MAC_ROUTE_OK_AFTER_SKILL`，serverId 和 workspace 同时验证通过。
- 实施、安装和验收过程均不 commit、不 push。

<!-- PLAN_REVIEW: L1 -->
<!-- PLAN_REVIEW_TOOL: external -->
<!-- PLAN_REVIEW_MODEL: codex/gpt-6-luna -->
<!-- PLAN_REVIEW_VERDICT: PASS -->
<!-- PLAN_REVIEW_SHA256: a93e1582353600f27113cd212111bf5ae0aab7d2a6f84fa815a823adba2eb448 -->
<!-- PLAN_REVIEW_AT: 2026-11-10T23:23:08Z -->
<!-- PLAN_REVIEW_RAW: VERDICT: PASS -->
<!-- PLAN_REVIEW_BRANCH: fix/hub-comm-bidirectional -->
