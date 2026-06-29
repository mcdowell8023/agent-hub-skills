# hub-handoff

将当前或指定的 Paseo agent 工作交接到 Agent Hub 继续执行。自动处理仓库克隆、workspace 同步、环境检查，生成交接 prompt 并在 Hub 上创建新 agent。

## 触发词

- "在 Hub 继续" / "在 hub 继续" / "交接到 Hub" / "hub handoff"
- "在 Agent Hub 继续这个工作"
- "让 Hub 接手"

## Helper 脚本

`~/.claude/skills/hub-handoff/scripts/hub-handoff.sh`

## 工作流程

### Phase 0：识别源 Agent

根据用户输入自动判断：

**A. 无参数（"在 Hub 继续"）**

1. 获取当前会话的 Paseo agent ID（通过 `mcp__paseo__get_agent_status` 或从当前会话上下文推断）
2. 展示给用户确认：
   ```
   检测到当前会话：
   📋 <title>
   🤖 <provider> / <model> / thinking: <mode>
   📂 <cwd>
   确认继续这个？输入 agent ID 或名称可切换。
   ```
3. 等用户确认（"确认" / 提供其他 ID / 提供名称关键词）

**B. 带 agent ID（"在 Hub 继续 f5ac68b5"）**

直接使用该 ID，调用 `mcp__paseo__get_agent_status` 获取信息。

**C. 带名称关键词（"在 Hub 继续 tenant-app 的工作"）**

1. 调用 `mcp__paseo__list_agents` 获取最近 agent 列表
2. 按 title 模糊匹配
3. 匹配 1 个 → 展示确认
4. 匹配多个 → 列表让用户选
5. 匹配 0 → 提示找不到

### Phase 1：采集源 Agent 信息

从 `get_agent_status` 结果中提取：

```
source_cwd       ← snapshot.cwd
source_title      ← snapshot.title 或 persistence.title
source_provider   ← snapshot.provider（claude / opencode / codex）
source_model      ← snapshot.model
source_mode       ← snapshot.currentModeId
source_thinking   ← snapshot.thinkingOptionId
```

自动判断场景类型：

| cwd 路径 | 场景 | workspace 根 |
|---|---|---|
| `~/wb/projects/X` | 公司编码项目 | `~/wb` |
| `~/wb/` | 公司工作空间 | `~/wb` |
| `~/AgentWorkspace/projects/X` | 个人代码项目 | `~/AgentWorkspace` |
| `~/AgentWorkspace/` | 个人工作空间 | `~/AgentWorkspace` |
| `~/KnowledgeBase/` | 知识库操作 | `~/KnowledgeBase` |
| 其他 | 通用任务 | cwd 本身 |

### Phase 2：环境预检（⚠️ 强制，不可跳过）

**教训**：不做预检会导致 Hub agent 因路径不存在、仓库未 clone、状态过时而跑不通。

推荐用一键全检：

```bash
SCRIPT=~/.claude/skills/hub-handoff/scripts/hub-handoff.sh

# 一键全检（SSH + 路径 + Git + Memory + 状态）
$SCRIPT precheck "$source_cwd" [额外引用的路径...]
```

或分步执行：

```bash
# 1. SSH 连通
$SCRIPT check-ssh

# 2. 路径映射
hub_cwd=$($SCRIPT map-path "$source_cwd")

# 3. 目录是否存在
$SCRIPT check-dir "$hub_cwd"

# 4. Git 检查（仅编码场景）
$SCRIPT check-git "$source_cwd"
# 如果 DIRTY_FILES > 0 → 警告用户先 push

# 5. 确保 Hub 上仓库存在（仅编码场景）
$SCRIPT ensure-repo "$hub_cwd" "$remote_url" "$branch"

# 6. 同步 Memory（Claude Code project memory 路径是机器特定的！）
$SCRIPT sync-memory "<cwd-slug>" "<workspace>/memory"
# ⚠️ Mac 的 ~/.claude/projects/-Users-mcdowell-xxx/memory/ 在 Hub 上不存在
# 必须显式 sync 到 Hub 的 -home-mcdowell-xxx/memory/

# 7. 同步 workspace 配置
$SCRIPT sync-workspace "$workspace_root" "$hub_workspace_root"

# 8. 状态事实核查（在 Hub 上验证真实状态）
$SCRIPT verify-state "$hub_cwd"
# ⚠️ prompt 里的每条状态描述必须基于这个输出，不能从 Mac 复制
```

### Phase 2.5：Prompt 生成规则（⚠️ 强制）

生成 handoff prompt 时**必须遵守**：

1. **所有路径必须是 Hub 路径**（`/home/mcdowell/...`），不能有 `/Users/mcdowell/...`
2. **状态描述必须来自 `verify-state` 输出**，不能复制 Mac 的 git status
3. **Memory 引用必须指向 Hub 已同步的路径**，或改用仓库内文档（README/CHANGELOG）
4. **"未提交变更"等断言必须在 Hub 上 `git status` 确认**，两台机器状态可能不同

### Phase 3：检查 Hub 上是否已有相关 Agent

```bash
$SCRIPT list-hub-agents "$hub_cwd"
```

- 有同 cwd 的 idle agent → 问用户："Hub 已有 agent '<title>'，续用还是新建？"
  - 续用 → 通过 `mcp__paseo__send_agent_prompt` 发送新任务
  - 新建 → 继续 Phase 4
- 无 → 直接进 Phase 4

### Phase 4：生成交接 Prompt

组装 prompt：

```
读取以下 memory 文件恢复上下文：
- <workspace>/memory/projects/<相关文件>.md

[编码场景追加]
代码在 <hub_cwd>，当前分支 <branch>。

上次工作：<从 source agent title 提取>

继续工作。
```

### Phase 5：创建 Hub Agent

**Provider/Model 选择**：

默认沿用源 agent（provider + model + thinking + mode）。用户可覆盖：
- "用 sonnet" → 替换 model
- "用 opencode" → 替换 provider
- "新建 agent" → 强制新建

**Codex 特殊处理**：
源 agent 是 codex → 提示用户："Codex 需要交互终端，建议改用 claude 或 opencode。选哪个？"

**执行创建**：

```bash
$SCRIPT create-hub-agent "$hub_cwd" "$provider" "$model" "$mode" "$title" "$prompt"
# 内部逻辑：Paseo --host 直连优先，失败时 scp + SSH 兜底
```

> 📖 通信方式详情、踩坑记录、Dufs 文件传输参见 **hub-comm** skill。

### Phase 6：反馈

输出给用户：

```
✅ Hub Agent 已创建
📋 标题: 继续：<title>
🆔 Agent ID: <id>
📂 工作目录: <hub_cwd>
🤖 Provider: <provider>/<model>
🔀 分支: <branch>（编码场景）

查看方式：
1. Paseo Desktop → Agent-Hub → 点击 agent
2. ssh hub 'paseo agent attach <id>'
3. ssh hub 'paseo agent logs <id>'
```

## 需要问用户的场景（仅这些会中断）

| 场景 | 问什么 |
|---|---|
| Phase 0 无参数 | "确认继续当前会话？" |
| Phase 2 有未提交变更 | "有 N 个未提交文件，先 push？" |
| Phase 2 凭据缺失 | "需要 git token" |
| Phase 3 Hub 已有 agent | "续用现有 agent 还是新建？" |
| 源是 Codex | "改用 claude 还是 opencode？" |

## 不问用户的（全自动）

SSH 检查、路径映射、git clone/fetch、memory 同步、目录创建、provider/model 继承。

## 示例

### 示例 1：当前会话直接交接
```
用户：在 Hub 继续
Agent：检测到当前会话：
  📋 tenant-app MoveOut/MoveIn 测试
  🤖 claude / claude-opus-4-8 / thinking: max
  📂 ~/wb/projects/tenant-app
  确认？
用户：确认
Agent：[执行 Phase 1-6]
  ✅ Hub Agent 已创建 (ID: 28f2588d)
```

### 示例 2：指定 agent ID
```
用户：在 Hub 继续 f5ac68b5
Agent：[直接获取 agent 信息，执行 Phase 1-6]
```

### 示例 3：按名称匹配
```
用户：在 Hub 继续 agent-gates 的工作
Agent：匹配到 "agent-gates v1.1.0 发布与基建验证"，确认？
```

### 示例 4：换 provider
```
用户：在 Hub 继续，用 sonnet
Agent：[用 claude-sonnet-4-6 创建]
```

### 示例 5：Hub 已有 agent
```
用户：在 Hub 继续
Agent：Hub 上已有 agent "Hub wb 测试" (28f2588d)，续用还是新建？
用户：续用
Agent：[发送新 prompt 到现有 agent]
```

## Pull from Hub（从 Hub 拉取进度）

### 触发词

- "拉取 Hub 成果" / "Hub 上做到哪了" / "hub harvest"
- "从 Hub 拉取" / "看看 Hub 进度"

### 流程

```
用户："Hub 上 tenant-app 做到哪了"
  ↓
Phase 1：hub-harvest.sh 采集 Hub 上下文
  $SCRIPT_DIR/hub-harvest.sh hub /home/mcdowell/wb/projects/tenant-app [--agent-id <id>]
  → 输出 Markdown 报告（Agent 状态/Memory/Git/文档/阻塞）
  ↓
Phase 2（可选）：用户看报告后决定
  "了解了" → 结束
  "本地继续" → Phase 3
  ↓
Phase 3：hub-return.sh 在本地创建续接 agent
  $SCRIPT_DIR/hub-return.sh hub /home/mcdowell/wb/projects/tenant-app [--provider claude --model opus]
  → 本地创建 agent，注入 Hub 上下文
```

### 示例

```
用户：Hub 上 CRM bridge 做到哪了
Agent：[执行 hub-harvest.sh hub /home/mcdowell/wb/projects/wb-mcs-check]
  📋 Hub Harvest Report
  Agent: bf6f262 | idle | GLM-5.2
  Branch: feat-crm-bridge (3 new commits)
  Memory: crm-bridge.md updated 2h ago
  Blockers: none
  
  要在本地继续吗？
用户：继续，用 opus
Agent：[执行 hub-return.sh hub /home/mcdowell/wb/projects/wb-mcs-check --provider claude --model opus]
  ✅ 本地 agent 已创建 (ID: xxxx)
```

## Pull from Mac（Hub 从 Mac 拉取）

### 触发词

- "从 Mac 拉取" / "Mac 上做到哪了" / "mac harvest"
- Hub agent 说 "拉取 Mac 进度"

### 流程

与 Pull from Hub 对称，方向反转：

```
Hub agent："从 Mac 拉取 tenant-app 进度"
  ↓
hub-harvest.sh <mac-host> /Users/mcdowell/wb/projects/tenant-app
  → 采集 Mac 上的 agent 状态/git/memory
  ↓
hub-return.sh <mac-host> /Users/mcdowell/wb/projects/tenant-app
  → 在 Hub 本地创建续接 agent
```

前提：Mac Paseo daemon 监听 `0.0.0.0:6767`，Hub 能 SSH 到 Mac（或通过 Tailscale）。

### 注意

- 路径自动映射：`/Users/mcdowell` ↔ `/home/mcdowell`
- 不指定 provider/model 时继承远端 agent 的设置
- 如果本地已有同 cwd 的 agent，会提示续用还是新建

## Push to Local（主动推送到本地设备）

### 触发词

- "交回 Mac" / "推给 Mac" / "hub push"
- "交回本地" / "本地继续这个"

### 流程

Hub agent："这个任务需要 Mac 本地工具，交回 Mac"
  ↓
hub-push.sh <mac-host> <hub-cwd> [--provider claude --model opus]
  → 采集 Hub 本地上下文
  → 在 Mac 上创建续接 agent

### 示例

Hub agent：Mac 端需要调试，交回去
Agent：[执行 hub-push.sh 100.101.57.43 /home/mcdowell/wb/projects/tenant-app]
  ✅ Mac agent 已创建 (ID: xxxx)

### 注意

- 路径自动映射：`/Users/mcdowell` ↔ `/home/mcdowell`
- target-host 可以是 IP（自动拼 `:6767`）或 `host:port` 形式
- 所有 paseo 调用通过 `PASEO_CMD` 注入，支持测试 mock
- 如果远端已有同 cwd 的 agent，paseo 本身会处理（detach 模式自动新建）
