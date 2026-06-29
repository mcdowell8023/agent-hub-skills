---
name: smart-dispatch
description: "Smart task dispatch: analyze task → recommend model → create Paseo sub-session. Merges model intelligence (benchmark data) with execution (worktree + Hub + oversight). Triggers: 'dispatch', '派任务', '派个子会话', '选模型', '用 codebuddy', '用 v4-pro', '用 GLM', 'smart dispatch', 'model dispatch', '调度', 'dev sub-session'."
user-invocable: true
argument-hint: "[--model <name>] [--thinking <level>] [--hub] [--worktree <path>] <task description>"
---

# Smart Dispatch — 智能任务派发

分析任务类型 → 推荐最佳模型 → 创建 Paseo 监督式子会话。合并了模型选型智能（基准测试数据）和执行能力（worktree 隔离 + Hub 远程 + Paseo Desktop 监督）。

模型画像数据：`model-profiles.json`（同目录）。

**用户请求:** $ARGUMENTS

## Prerequisites

1. Read the **paseo** skill.
2. Read `model-profiles.json`（同目录，含基准测试数据和模型能力画像）。
3. Read `~/.paseo/orchestration-preferences.json` (unless the user explicitly named a provider).

---

## 1. 解析参数

从 `$ARGUMENTS` 中提取：

| 参数 | 解析方式 | 默认 |
|---|---|---|
| `--model <name>` | 短名或完整 model ID | 自动推荐（见 §2） |
| `--thinking <level>` | low / medium / high / max | high |
| `--hub` | 标记 | 否（本地） |
| `--worktree <path>` | 路径 | 当前目录 |
| `--provider <name>` | 强制指定 provider | 按 model 自动选 |
| 其余文本 | 任务描述 | (必填) |

### 模型短名映射

| 短名 | Provider | Model ID |
|---|---|---|
| `sonnet` | claude | claude-sonnet-4-6 |
| `opus` | claude | claude-opus-4-6 |
| `v4-pro` / `deepseek` | codebuddy-code | deepseek-v4-pro |
| `glm` | codebuddy-code | glm-5.2 |
| `kimi` | codebuddy-code | kimi-k2.7 |
| `m3` | codebuddy-code | minimax-m3 |
| `gpt` | opencode | github-copilot/gpt-5.4 |
| `qwen-max` / `qwen` | qoderclicn | qmodel_latest |
| `qwen-plus` | qoderclicn | qmodel |
| `qwen-flash` | qoderclicn | q36fmodel |
| `ds-pro` | qoderclicn | dmodel |
| `ds-flash` | qoderclicn | dfmodel |
| `glm-cn` | qoderclicn | gm51model |
| `kimi-cn` | qoderclicn | kmodel |
| `minimax` | qoderclicn | mmodel |

未匹配短名 → 视为完整 model ID，provider 从 model 名推断或要求用户 `--provider` 指定。

---

## 2. 任务类型识别与模型推荐

用户**未指定 `--model`** 时，先识别任务类型，再结合时段和配额推荐模型。

### 2.1 任务类型识别

| 类型 | 识别关键词/特征 | 代号 |
|---|---|---|
| 核心逻辑 / 快速交付 | "实现"、"开发"、"写个"、"创建服务"、架构设计、迁移 | `core` |
| 健壮性 / 容错设计 | "防御"、"容错"、"边界处理"、"校验"、数据清洗 | `robust` |
| 测试覆盖 | "写测试"、"补测试"、"异常 case"、TDD | `test` |
| API / 接口设计 | "API 设计"、"DTO"、"接口定义"、"给前端用" | `api` |
| 文档写作 / 更新 | "写文档"、"更新文档"、"技术方案"、"调研报告" | `doc` |
| 批量执行 | "批量改"、"所有文件"、"全部替换"、10+ 文件 | `batch` |
| 代码审核 | "review"、"审核"、"检查"、"交叉检查" | `review` |
| 性能优化 | "性能"、"优化"、"O(n)"、"大数据量" | `perf` |

### 2.2 按任务类型推荐（基准测试驱动）

**数据来源**：
- ConversationStats 基准（2026-06-20）
- LRU + Bug诊断 + Kafka架构 三道题盲评（2026-06-28，GPT-5.5 裁判）

**9 模型 GPT-5.5 盲评排名**（LRU Cache + 并发 Bug 诊断 + Kafka 架构设计）：

| Tier | 模型 | 总分/120 | 强项 |
|---|---|---|---|
| S | MiniMax-M3 | 114 | Bug 诊断(38)、架构设计(39)、双方案洞察 |
| A | GLM-5.2 | 101 | 架构深度(Outbox+SKIP LOCKED+CAP) |
| B | Kimi-K2.7-Code | 94 | Outbox+手写 AsyncLock |
| B | Hy3 preview | 92 | 均衡无短板 |
| B | Qwen3.7-Max | 90 | Bug 诊断强(35) |
| B | DeepSeek-V4-Pro | 86 | 全面均衡 |
| B | Kimi-K2.6 | 82 | 合格 |
| C | Sonnet 4.6 | 77 | LRU 代码质量最高(35)，但术语错+缺 Outbox |
| C | Qwen3.7-Plus | 76 | 无泛型、去 async 方案弱 |

```
任务到达
  │
  ├─ 用户显式指定模型？ → 用指定的，跳到 §3
  │
  ├─ 独立审查 / 交叉检查？ → GPT-5.4/5.5 (opencode --pure，不走 Paseo)
  │
  ├─ batch / 批量？（区分调度层 vs 执行层）
  │    ├─ 调度编排（多 agent 并发分发）→ Sonnet 4.6 (Agent tool 原生并发)
  │    └─ 实际执行 worker
  │         ├─ 质量优先 → M3
  │         ├─ 架构类批量 → GLM-5.2
  │         ├─ Bug/并发类批量 → Kimi-K2.7 / Qwen3.7-Max
  │         └─ 轻量批量 → Qwen3.7-Plus
  │
  ├─ 架构 / 系统设计？
  │    ├─ 深度架构（分布式、Kafka、微服务、Outbox）→ M3 (S) / GLM-5.2 (A)
  │    ├─ 实用容错设计 → M3
  │    └─ 类型安全 / 防御性编码 → GLM-5.2
  │
  ├─ bug 诊断 / 并发分析 / 调试？
  │    ├─ 高风险 / 并发 / 竞态 → M3 (S)
  │    ├─ 一般 bug 诊断 → Qwen3.7-Max / Kimi-K2.7
  │    └─ 根因分析 → Qwen3.7-Max
  │
  ├─ 算法 / 数据结构 / 精细编码？
  │    ├─ 生产级实现 → M3
  │    └─ 简单算法题（LRU 类）→ Sonnet 4.6 可接受
  │
  ├─ core / 快速交付 / 跨文件重构？ → Opus 4.6
  │
  ├─ KB 整理 / 知识库 / 文档分类标签？
  │    ├─ 7/1 前 + 轻量（摘要/标签/分类）→ xfyun/xopqwen36v35b（免费，/free-fleet）
  │    ├─ 批量扫描 → xfyun（免费）或 Qwen3.7-Plus（qoderclicn 免费）
  │    ├─ 深度整理（需要高质量归类建议）→ GLM-5.2 或 Qwen3.7-Plus
  │    └─ 7/1 后 → Qwen3.7-Plus（qoderclicn 免费到 7/30）
  │
  ├─ doc / 文档？
  │    ├─ 重文档（>500 行，多章节重写）→ Opus 4.6
  │    ├─ 结构性文档（中文技术方案、方案对比）→ GLM-5.2
  │    └─ 状态更新、踩坑记录（需要全面不遗漏）→ v4-pro
  │
  ├─ test / 测试？
  │    ├─ 生产级测试策略 → M3
  │    ├─ 根因导向测试 → Qwen3.7-Max
  │    └─ 实现级测试 → Kimi-K2.7
  │
  ├─ api / 接口设计？
  │    ├─ 架构级 API → GLM-5.2
  │    └─ 实现级接口 → Kimi-K2.7
  │
  ├─ perf / 性能？ → M3
  │
  ├─ 轻量 / 低风险？
  │    ├─ 日间 → Qwen3.7-Plus / v4-pro
  │    └─ 夜间 → Qwen3.7-Max（优惠）
  │
  └─ 不确定？ → 进入默认决策树（§2.3）
```

### 2.3 默认决策（无明确任务类型时）

> **配额策略**：CLI/Paseo 均无法主动查询剩余配额，只能在报错时感知。
> qoderclicn 有限时免费套餐（截止 2026-07-30），闲置时段多用它消耗免费额度。

```
Provider 选择 = 任务类型决策树（§2.2）选出模型后，按场景选 provider：

  关键任务 / 工作时间？
  ├─ 是 → 按任务质量选最佳模型，provider 跟着模型走
  │       （M3 只在 codebuddy → 用 codebuddy）
  │       （两边都有的模型 → 哪边质量更好用哪边）
  └─ 否（闲置时段 / 非关键 / 夜间）
       └─ 优先用 qoderclicn 消耗免费额度
            ├─ 夜间 22:00-08:00 → Qwen3.7-Max（优惠 80%）
            ├─ 闲时一般任务 → qoderclicn 版 GLM-5.2 / V4-Pro / K2.6
            └─ 轻量任务 → Qwen3.7-Plus / Qwen-Flash

  任何 provider 报错(quota/rate limit)？ → 切另一个 provider 的同模型
  两边都报错？ → 报告用户

特殊路径（不走上述逻辑）：
├─ 需要 Claude 原生工具链（Agent tool 并发）→ Sonnet / Opus
├─ 需要独立审查视角 → GPT-5.4/5.5 (opencode --pure)
└─ 用户明确指定 provider → 用指定的
```

**qoderclicn ↔ codebuddy 模型对照表**（同模型不同 provider）：

| 模型 | qoderclicn ID | codebuddy ID | 优先用 |
|---|---|---|---|
| Qwen3.7-Max | qmodel_latest | — | qoderclicn 独占 |
| Qwen3.7-Plus | qmodel | — | qoderclicn 独占 |
| Qwen3.6-Flash | q36fmodel | — | qoderclicn 独占 |
| DeepSeek-V4-Pro | dmodel | deepseek-v4-pro | qoderclicn 先 |
| DeepSeek-V4-Flash | dfmodel | deepseek-v4-flash | qoderclicn 先 |
| GLM-5.2 | gm51model | glm-5.2 | qoderclicn 先 |
| Kimi-K2.6 | kmodel | kimi-k2.6 | qoderclicn 先 |
| MiniMax-M3 | — | minimax-m3 | codebuddy 独占 |
| Kimi-K2.7-Code | — | kimi-k2.7 | codebuddy 独占 |
| Hy3 preview | — | hy3-preview | codebuddy 独占 |
| MiniMax-M2.7 | mmodel | minimax-m2.7 | qoderclicn 先 |

> **决策树变更记录**：
> - 2026-06-28 v1：GPT-5.5 审查后优化（batch 拆调度/执行、test 三级、新增 algorithm 分支）
> - 2026-06-28 v2：删除臆想的"配额优先"分支，改为错误触发降级
> - 2026-06-28 v3：qoderclicn 限时免费优先策略——默认先用 qoderclicn，报错再切 codebuddy

### 2.4 思考强度建议

| 任务复杂度 | thinking | 适用场景 |
|---|---|---|
| `low` | 单行修改、typo、配置 | 不建议开 agent，直接做 |
| `medium` | 简单功能、常规 bug fix | 简单功能 |
| `high` | 多文件功能、服务设计、文档更新 | **默认** |
| `max` | 架构决策、跨模块迁移、安全关键 | 重大决策 |

### 2.5 模型能力速查（基准测试数据）

| 模型 | 代码 | 设计 | 测试 | 健壮 | 速度 | 文档 | 适合 |
|---|---|---|---|---|---|---|---|
| Opus 4.6 | ★5 | ★4 | ★4 | ★4 | ★5 | ★5 | 核心逻辑/重文档 |
| GLM-5.2 | ★5 | ★5 | ★4 | ★5 | ★3 | ★4 | 容错/中文技术文档 |
| M3 | ★4 | ★5 | ★4 | ★5 | ★4 | ★3 | 容错/性能/算法 |
| v4-pro | ★4 | ★4 | ★5 | ★4 | ★5 | ★4 | 测试/状态更新文档 |
| Kimi-K2.7 | ★4 | ★3 | ★3 | ★4 | ★3 | ★3 | API 设计 |
| Sonnet 4.6 | ★4 | ★3 | ★3 | ★3 | ★5 | ★3 | 批量/前端 |
| GPT-5.4 | — | — | — | — | — | ★4 | 审核/交叉检查 |

---

## 3. Provider 降级与限额处理

### Permission mode 映射

| Provider | Mode |
|---|---|
| claude | auto |
| codebuddy-code | bypassPermissions |
| qoderclicn | bypassPermissions |
| opencode | build |
| codex | auto |

### Provider 降级链

```
首选 provider 限额/不可用?
├─ qoderclicn 限额或刷新超时 → 先重试 1 次，再降级到 codebuddy-code 同类模型
│   ├─ qwen-max → v4-pro
│   ├─ qwen-plus → glm-4.7
│   └─ ds-pro → deepseek-v4-pro
├─ codebuddy-code 限额 → 降级到 qoderclicn 同类模型
│   ├─ v4-pro → qwen-max
│   ├─ glm-5.2 → glm-cn
│   └─ kimi-k2.7 → kimi-cn
└─ 两者都限额 → 降级到 claude/sonnet 或提示用户
```

qoderclicn 的 `Timed out refreshing Qoder CLI CN after 60000ms` 属于 **provider refresh timeout**，不是 Qwen 模型推理超时。处理方式：

1. 等 5-10 秒，用相同 `provider/model` 重试 `create_agent` 1 次。
2. 第二次仍失败才走降级链。
3. 向用户报告原始错误时写“Qoder CLI CN provider refresh 超时”，禁止写“Qwen 超时”。

降级时 title 前缀加 `[降级]`，向用户报告。

### 夜间优惠（北京时间 22:00 - 08:00）

| 模型 | 日间 Credit | 夜间 Credit | 折扣 |
|---|---|---|---|
| Qwen3.7-Max | 0.10x | ~0.02x | 降 80% |
| Qwen3.7-Plus | 0.04x | ~0.016x | 降 60% |

---

## 4. 前置检查

### 4.1 Provider 可用性

创建前确认目标 provider 可用（Hub 上可能没装某些 provider）。不可用时查降级映射。

### 4.2 Agent-gates

```bash
ls {target_cwd}/.agent-gates/ 2>/dev/null && echo "gates: yes" || echo "gates: no"
```

未 init → 警告但不阻断。

### 4.3 工作目录

- 用户指定了 `--worktree` → 用指定路径
- 当前在 worktree 中 → 用当前 worktree
- 当前在主仓中 → 提醒建议在 worktree 中开发，不阻断

---

## 5. 打包上下文 + 创建子会话

### Dispatch Prompt 模板

```
## 任务
{task_description}

## 项目上下文
- 工作目录: {cwd}
- 分支: {branch}
- 技术栈: {tech_stack}
- 关键文件:
  - `{file}` — {说明}

## 验收标准
- [ ] {来自任务描述的可验证条件}

## 约束
- 在当前目录开发，遵守项目 CLAUDE.md / AGENTS.md 规则
- 遇到不确定的设计决策 → 停下来描述选项，不自行决定
- 不做任务范围外的修改
```

**总 prompt ≤ 2000 字。** 超过时提示拆分任务。

### 本地创建

```
create_agent({
  title: "[Dev] {task_short_title}",
  provider: "{provider/model}",
  relationship: { kind: "subagent" },
  workspace: { kind: "current" },
  initialPrompt: "{dispatch_prompt}",
  notifyOnFinish: true,
  settings: {
    modeId: "{permission_mode}",
    thinkingOptionId: "{thinking}"
  },
  labels: { "smart-dispatch": "true" }
})
```

### Hub 远程创建（--hub）

```bash
scp /tmp/prompt.txt hub:/tmp/
ssh hub "paseo run --detach \
  --provider {provider} --model {model} \
  --thinking {thinking} --mode '{permission_mode}' \
  --title '[Dev] {title}' \
  --cwd /home/mcdowell/{project_path} \
  \"\$(cat /tmp/prompt.txt)\""
```

Hub `--cwd` 必须是 `/home/mcdowell/...`。

---

## 6. 输出

```
子会话已创建
  Agent:  {short_id} — {title}
  Model:  {provider}/{model} · thinking: {thinking}
  任务类型: {task_type}（{推荐理由}）
  CWD:    {cwd}
  Gates:  agent-gates ✓ / ⚠ 未安装

管理:
  进度: paseo agent logs {short_id}
  反馈: paseo send {short_id} "消息"
  中止: paseo agent archive {short_id}
```

完成后立即写 memory（防上下文压缩丢失子会话 ID）。

---

## 7. 审查集成

子会话完成后，按 `agent-review-protocol` 的规则做交叉审查：

- 代码变更 → opencode --pure GPT-5.4 审查
- 文档变更 → 同样用不同模型审查（GPT-5.4 或 Gemini）
- 审查发现按 ❌/⚠️/💡 分级，❌ 必须修复
