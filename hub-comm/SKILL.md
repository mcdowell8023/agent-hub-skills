# hub-comm

Agent Hub 双向通信参考。提供 Mac ↔ Hub 的所有操作方式、推荐优先级、踩坑记录。

## 触发词

- "连接 Hub" / "操作 Hub" / "Hub 通信"
- "Hub 反向" / "Hub 回传" / "交回 Mac"
- 被 hub-handoff 等其他 skill 引用时自动加载

## 配置

通信依赖设备间网络互通（LAN 直连、VPN、Tailscale 等均可），Paseo daemon 默认端口 6767。

**启用双向通信**：确保两端 Paseo daemon 监听 `0.0.0.0:6767`（`~/.paseo/config.json` → `daemon.listen`），对端可达即可。

**当前端点**（按实际网络环境替换 IP）：

| 设备 | Paseo | SSH | 其他服务 |
|---|---|---|---|
| Hub | `<Hub-IP>:6767` | `ssh hub` | RDP `:3389`，Dufs `:8899` |
| Mac | `<Mac-IP>:6767` | — | — |

## 通信方式（按推荐优先级）

### 方式 1：Paseo CLI `--host` 直连（推荐）

v0.1.89+ 已验证，支持 ls / send / run 三种操作直连 Hub daemon。

```bash
# 列出 Hub agents
paseo agent ls --host 100.65.188.103:6767

# 给已有 agent 发消息（继续会话）
paseo send --host 100.65.188.103:6767 <agent-id> "继续工作"
# 或从文件读 prompt
paseo send --host 100.65.188.103:6767 <agent-id> --prompt-file /tmp/prompt.txt

# 创建新 agent
paseo run --host 100.65.188.103:6767 --detach \
  --provider claude/opus --mode auto \
  --title "任务标题" --cwd /home/mcdowell/wb "prompt"

# 查 agent 状态
paseo agent ls --host 100.65.188.103:6767
```

**适用**：日常 agent 管理（创建/查询/发消息）。
**注意**：Mac Paseo Desktop（Electron）会输出 GPU helper 错误日志，不影响功能，过滤即可。

### 方式 2：SSH + Hub 本地 Paseo CLI（中文 prompt / 查日志）

复杂/中文 prompt 或查 agent 日志时用 SSH 更稳。

```bash
# 复杂 prompt：scp 文件 + SSH
echo "你的任务描述..." > /tmp/prompt.txt
scp /tmp/prompt.txt hub:/tmp/prompt.txt
ssh hub 'paseo run --detach --provider claude/opus --mode auto --title "任务标题" --cwd /home/mcdowell/AgentWorkspace "$(cat /tmp/prompt.txt)"'

# 简单英文 prompt 可内联
ssh hub 'paseo run --detach --provider claude/opus --cwd /home/mcdowell/wb --title "task" "report status"'

# 查 agent 日志（--host 可能无输出，SSH 更可靠）
ssh hub 'paseo agent logs <agent-id>'

# 后续交互
ssh hub 'paseo send <agent-id> "后续指令"'
```

**适用**：中文内容、特殊字符 prompt、查看 agent 执行日志。

### 方式 3：SSH 直接执行（无 Paseo）

不经过 Paseo，直接调 agent CLI。

```bash
# Claude Code 非交互
ssh hub 'claude -p "任务描述"'

# OpenCode 非交互
ssh hub 'opencode run -m github-copilot/claude-sonnet-4.6 "任务"'

# 交互式终端
ssh -t hub 'cd ~/wb && claude'
```

**适用**：一次性命令、不需要 Paseo 管理的快速操作。

### 方式 4：MCP 工具（仅查询）

```bash
mcp__paseo__list_agents       # 只能查本地 daemon
mcp__paseo__get_agent_status  # 只能查本地 daemon
```

> ⚠️ **限制**：`mcp__paseo__create_agent` 等 MCP 工具只能操作**本地 Paseo daemon**，没有 host 参数。跨机器操作必须走 CLI `--host` 或 SSH。

## 反向通信：Hub → Mac（已验证）

Hub agent 遇到解决不了的问题时，可以把上下文交回 Mac 让用户接手。

```bash
# Hub 上执行：列出 Mac agents
paseo agent ls --host 100.101.57.43:6767

# Hub 上执行：给 Mac agent 发消息（交回问题）
paseo send --host 100.101.57.43:6767 <mac-agent-id> "Hub 端遇到问题：<描述>，需要 Mac 端处理"

# Hub 上执行：在 Mac 上创建新 agent 处理
paseo run --host 100.101.57.43:6767 --detach --provider claude/opus --title "Hub 回传任务" --cwd /Users/mcdowell/wb "问题描述"
```

**前提**：Mac Paseo daemon 监听 `0.0.0.0:6767`（`~/.paseo/config.json` 中 `daemon.listen`）。

**适用场景**：
- Hub agent 需要 Mac 本地工具（Xcode、浏览器调试等）
- Hub agent 需要用户交互确认
- Hub agent 遇到权限/网络等本地限制

## 踩坑记录（⚠️ 必读）

| # | 坑 | 正确做法 |
|---|---|---|
| 1 | `$HOME` 在 SSH 命令中被 Mac 端展开 | 硬写 `/home/mcdowell/...` 或用单引号 |
| 2 | 中文 prompt 的引号/感叹号/括号在 SSH 里炸 | scp 文件到 Hub 再 `$(cat ...)` |
| 3 | MCP create_agent 无 host 参数 | 用 CLI `--host` 或 SSH |
| 4 | `paseo agent logs --host` 可能无输出 | 查日志走 SSH |
| 5 | Electron 桌面版 GPU 错误日志刷屏 | 不影响功能，`grep -v` 过滤 |

## Dufs 文件传输

设备间传文件（APK、文档、截图等）：

```bash
# 上传
curl -u admin:hub2026 -T local-file.apk http://100.65.188.103:8899/

# 下载
curl -u admin:hub2026 -O http://100.65.188.103:8899/file.apk

# 浏览器
open http://100.65.188.103:8899
```
