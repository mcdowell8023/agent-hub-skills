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

**9 模型盲评排名 + 性价比**（GPT-5.5 裁判，2026-06-28）：

| Tier | 模型 | 得分/120 | cb Credit | qcn Credit | 性价比(得分/credit) | 强项 |
|---|---|---|---|---|---|---|
| S | MiniMax-M3 | 114 | **0.25x** | — | **456** | Bug+架构全面最强 |
| A | GLM-5.2 | 101 | 0.79x | 0.60x | 128(cb)/168(qcn) | 架构深度强 |
| B | Kimi-K2.7-Code | 94 | 0.59x | — | 159 | AsyncLock+Outbox |
| B | Hy3 preview | 92 | **0.18x** | — | **511** 🏆 | 均衡+性价比第一 |
| B | Qwen3.7-Max | 90 | — | 0.25x(日)/0.10x(夜) | 360(日)/**900(夜)** | Bug 诊断强，夜间超值 |
| B | DeepSeek-V4-Pro | 86 | **0.25x** | 0.50x | 344(cb) | 全面均衡 |
| B | Kimi-K2.6 | 82 | 0.52x | 0.30x | 158(cb)/273(qcn) | qcn 便宜 42% |
| C | Sonnet 4.6 | 77 | — | — | (订阅制) | LRU 最高但架构弱 |
| C | Qwen3.7-Plus | 76 | — | 0.10x(日)/0.04x(夜) | 760(日)/**1900(夜)** | 夜间性价比之王 |

> **费率数据来源**：Paseo `list_models` API 实时查询（2026-06-30）。费率会变，派发前可重新查询。

**性价比排名**（得分÷credit，越高越好）：
1. Qwen3.7-Plus: 760（轻量任务首选）
2. **Hy3 preview: 511**（0.18x 降价后逆袭，B tier 但性价比超 M3）
3. MiniMax-M3: 456（S tier，质量+性价比双优）
4. Qwen3.7-Max: 360
5. V4-Pro: 344
6. Kimi-K2.6 qcn: 273
7. GLM-5.2 qcn: 168
8. Kimi-K2.7: 159
9. GLM-5.2 cb: 128

**性价比决策规则**：
- 质量要求高 → M3（0.25x，S tier）
- 质量够用 + 省钱 → Hy3（0.18x，B tier 92 分，性价比第一）
- 轻量/批量 → Qwen3.7-Plus（0.10x）
- GLM-5.2 必须走 qoderclicn（0.60x），cb 上 0.79x 贵 32%
- V4-Pro 必须走 codebuddy（0.25x），qcn 上 0.50x 贵一倍
- K2.6 走 qoderclicn（0.30x），cb 上 0.52x 贵 73%

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
  │         ├─ 质量优先 → M3（0.25x）
  │         ├─ 省钱优先 → Hy3（0.18x，性价比 511）
  │         ├─ 轻量批量 → Qwen3.7-Plus（0.10x qcn）
  │         └─ 需中文结构化 → GLM-5.2 via qcn（0.60x）
  │
  ├─ 架构 / 系统设计？
  │    ├─ 默认 → M3（0.25x，S tier，性价比最优选择）
  │    ├─ M3 不擅长的中文结构性设计文档 → GLM-5.2 via qoderclicn（0.60x）
  │    └─ 类型安全 / 防御性编码 → GLM-5.2 via qoderclicn（0.60x）
  │
  ├─ bug 诊断 / 并发分析 / 调试？
  │    ├─ 高风险 / 并发 / 竞态 → M3（0.25x，Bug=38 最高分）
  │    ├─ 一般 bug → Qwen3.7-Max（0.10x qcn）或 V4-Pro（0.25x cb）
  │    └─ 根因分析 → Qwen3.7-Max（0.10x）
  │
  ├─ 算法 / 数据结构 / 精细编码？ → M3（0.25x，LRU=37）
  │
  ├─ core / 快速交付 / 跨文件重构？ → Opus 4.6（订阅制，不消耗 credit）
  │
  ├─ KB 整理 / 知识库 / 文档分类标签？
  │    ├─ 批量扫描 → Qwen3.7-Plus（0.04x，最省）
  │    ├─ 深度整理 → Qwen3.7-Plus（0.04x，KB 实测质量够用）
  │    └─ 高质量归类 → GLM-5.2 via qoderclicn（0.60x）
  │
  ├─ doc / 文档？
  │    ├─ 重文档（>500 行，多章节重写）→ Opus 4.6（订阅制）
  │    ├─ 结构性文档 → GLM-5.2 via qoderclicn（0.60x，比 cb 1.06x 省 43%）
  │    └─ 踩坑记录 → V4-Pro via codebuddy（0.25x，比 qcn 0.50x 省 50%）
  │
  ├─ test / 测试？
  │    ├─ 生产级测试策略 → M3（0.25x）
  │    ├─ 根因导向测试 → Qwen3.7-Max（0.25x qcn）
  │    └─ 实现级测试 → Hy3（0.18x，性价比最高）或 V4-Pro（0.25x cb）
  │
  ├─ api / 接口设计？
  │    ├─ 默认 → M3（0.25x，比 K2.7 的 0.76x 省 67% 且 S tier）
  │    └─ 需要具体实现细节 → V4-Pro（0.25x）
  │
  ├─ perf / 性能？ → M3（0.25x）
  │
  ├─ 轻量 / 低风险？
  │    ├─ 日间最省 → Qwen3.7-Plus（0.10x qcn）
  │    ├─ 日间常规 → Hy3（0.18x cb）或 V4-Pro（0.25x cb）
  │    └─ 夜间(22-08) → Qwen3.7-Plus（**0.04x**）/ Qwen3.7-Max（**0.10x**）
  │
  └─ 不确定？
       ├─ 质量优先 → M3（0.25x，S tier）
       └─ 省钱优先 → Hy3（0.18x，B tier 92 分，性价比 511 最高）
```

### 2.3 默认决策（无明确任务类型时）

> **配额策略**：CLI/Paseo 均无法主动查询剩余配额，只能在报错时感知。
> qoderclicn 有限时免费套餐（截止 2026-07-30），闲置时段多用它消耗免费额度。

```
Provider 选择 = 任务类型决策树（§2.2）选出模型后，按场景选 provider：

  第一层：时段判断
  ├─ 夜间闲时（22:00-08:00 北京时间）
  │    └─ 优先 qoderclicn 消耗免费额度（截止 2026-07-30）
  │         ├─ Qwen3.7-Max（0.10x → 夜间 0.02x）
  │         ├─ Qwen3.7-Plus（0.10x → 夜间 0.04x）
  │         └─ 报错 → 降级到 codebuddy 同类模型
  │
  └─ 日间 / 非夜间闲时（08:00-22:00）
       └─ 优先 codebuddy-code（质量更可控，thinking 可调）
            ├─ 质量优先 → M3（0.25x，S tier，codebuddy 独占）
            ├─ 均衡性价比 → Hy3（0.18x，性价比第一，codebuddy 独占）
            ├─ 常规开发 → V4-Pro（0.25x cb，比 qcn 0.50x 便宜一半）
            ├─ 中文结构文档 → GLM-5.2（cb 0.79x / qcn 0.60x，按实时费率选更便宜的）
            └─ 轻量 → Kimi-K2.6（0.30x qcn）或 Qwen3.7-Plus（0.10x qcn）

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
> - 2026-06-30 v4：用 Paseo list_models 实时费率替换旧数据；加入性价比排名；
>   Hy3 降价 51%(0.37→0.18x) 成性价比第一；GLM-5.2 降价 25%(1.06→0.79x)；
>   Qwen 夜间费率独立标注（Max 0.25→0.10x，Plus 0.10→0.04x）；
>   每个分支标注 credit 费率，同模型跨 provider 选最便宜的

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

| 模型 | 日间 Credit | 夜间 Credit (22:00-08:00 北京) | 折扣 |
|---|---|---|---|
| Qwen3.7-Max | 0.25x | **0.10x** | 降 60% |
| Qwen3.7-Plus | 0.10x | **0.04x** | 降 60% |

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
