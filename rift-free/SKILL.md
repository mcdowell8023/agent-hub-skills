---
name: rift-free
description: "Rift Free Channel: dispatch tasks to free-tier models (OpenRouter, Zhipu, iFlytek) via OpenCode --pure. Triggers: 'rift-free', 'rift free', '免费模型', '白嫖模型', 'dispatch free', '派免费的', '用免费额度', 'openrouter', 'xfyun'."
user-invocable: true
argument-hint: "[--task <type>] [--model <short>] [--file <path>] <task description>"
---

# Rift Free — 免费模型通道

将任务派发给 OpenCode 中配置的免费模型，通过 `opencode run --pure` 调用，绕过 OMO 编排。

**用户请求:** $ARGUMENTS

## 0. 可用模型

### Tier 1: OpenRouter（推荐，能力强）

| 短名 | Model ID | 参数 | 上下文 | 适合 |
|---|---|---|---|---|
| `coder` | openrouter/qwen/qwen3-coder:free | — | 1M | 代码审查/生成/重构 |
| `llama70` | openrouter/meta-llama/llama-3.3-70b-instruct:free | 70B | 131K | 通用任务/摘要/分析 |
| `nemotron` | openrouter/nvidia/nemotron-3-ultra-550b-a55b:free | 550B | 1M | 复杂推理/深度分析 |
| `gemma` | openrouter/google/gemma-4-31b-it:free | 31B | 262K | 通用/多语言 |

限速：20 RPM / 200 RPD，需 VPN 或代理。

### Tier 2: 智谱（国内直连，永久免费）

| 短名 | Model ID | 适合 |
|---|---|---|
| `flash` | zhipu/glm-4-flash | 中文摘要/分类/标签/格式化 |

### Tier 3: 讯飞（国内直连，能力有限）

| 短名 | Model ID | 适合 |
|---|---|---|
| `hunyuan` | xfyun/xophunyuan7bmt | 简单摘要/标签提取 |

### 模型选择策略

| 任务 | 首选 | 降级 |
|---|---|---|
| 代码审查/生成 | `coder` | `llama70` |
| 复杂推理/深度分析 | `nemotron` | `llama70` |
| KB 整理/中文摘要 | `flash` | `llama70` |
| 标签提取/简单分类 | `flash` | `hunyuan` |
| 批量轻量任务 | `flash` | `hunyuan` |
| 需要 VPN 不可用时 | `flash` | `hunyuan` |

默认模型：`flash`（国内直连、质量够用）。用户指定 `--model` 时按指定走。涉及代码时自动选 `coder`。

## 1. 解析参数

| 参数 | 说明 | 默认 |
|---|---|---|
| `--task <type>` | summarize / tag / kb-organize / review / batch | 自动推断 |
| `--model <short>` | 模型短名（见上表） | 按任务自动选 |
| `--file <path>` | 目标文件/目录 | 无 |
| 其余文本 | 任务描述 | (必填) |

### 任务类型自动推断

| 关键词 | 推断类型 | 默认模型 |
|---|---|---|
| 摘要/总结/提取/summary | summarize | flash |
| 标签/tag/分类标注 | tag | flash |
| 整理/分类/归类/知识库/KB | kb-organize | flash |
| 审查/review/代码 | review | coder |
| 批量/batch/遍历 | batch | flash |

## 2. 构建派发命令

```bash
opencode run --pure -m "{model_id}" "{prompt}" 2>&1
```

带文件上下文：

```bash
file_content=$(head -300 "{file_path}")
opencode run --pure -m "{model_id}" "以下是文件内容:\n\n${file_content}\n\n任务: {prompt}" 2>&1
```

## 3. 任务模板

### 3.1 知识库整理 (kb-organize)

```
你是一个知识库管理助手。分析以下笔记内容，给出整理建议。

笔记路径: {file_path}
笔记内容:
{content}

请输出 JSON 格式:
{
  "suggested_folder": "建议的目录路径",
  "suggested_tags": ["tag1", "tag2"],
  "summary": "一句话摘要",
  "related_topics": ["可能关联的主题"],
  "quality": "complete|stub|draft|outdated",
  "action": "keep|move|merge|archive",
  "action_detail": "具体操作建议"
}
```

### 3.2 内容摘要 (summarize)

```
为以下内容生成结构化摘要:
- 一句话概述（30字内）
- 3-5 个要点
- 关键术语列表

{content}
```

### 3.3 标签提取 (tag)

```
为以下内容建议 Obsidian 标签（#tag 格式），要求:
- 3-7 个标签
- 按 领域/技术/状态 三个维度

{content}
```

### 3.4 代码审查 (review)

```
Review the following code. Focus on:
- Correctness bugs
- Security issues
- Performance concerns
- Simplification opportunities

Be concise. Only report real issues, not style nits.

{content}
```

### 3.5 批量扫描 (batch)

```bash
for file in {target_dir}/*.md; do
  opencode run --pure -m "{model_id}" \
    "分析这个文件并输出 JSON: {summary, tags, quality}. 文件内容: $(head -200 "$file")" 2>&1
done
```

## 4. 知识库整理工作流

### 4.1 单文件分析

```
/rift-free --task kb-organize --file ~/KnowledgeBase/Wiki/04_Knowledge/某篇笔记.md
```

流程：
1. 用 `obsidian-cli read` 读取文件内容
2. 发送给模型分析
3. 输出 JSON 格式的整理建议
4. **不自动执行**，由主会话用 obsidian-cli 执行

### 4.2 目录扫描

```
/rift-free --task kb-organize --file ~/KnowledgeBase/Wiki/04_Knowledge/
```

流程：
1. 用 `obsidian-cli files` 列出文件
2. 逐个生成摘要+标签
3. 汇总输出整理报告
4. 主会话确认后批量执行

### 4.3 知识库健康检查

```
/rift-free --task kb-organize 知识库健康检查
```

检查项：
- `obsidian-cli orphans` → 孤儿笔记 → 模型建议链接
- `obsidian-cli deadends` → 死胡同笔记 → 模型建议出链
- 按目录统计文件数，找出过大/过空的目录

## 5. 额度感知

调用后检查输出是否包含错误：

| 错误关键词 | 含义 | 处理 |
|---|---|---|
| `quota`/`limit`/`exceeded` | 额度用完 | 切换到其他免费模型 |
| `rate limit`/`429` | 频率限制 | OpenRouter: 等 60 秒重试；其他: 等 30 秒 |
| `unauthorized`/`401`/`403` | 认证失败 | 报告用户 |

OpenRouter 限速时降级到 `flash`（国内直连不受影响）。全部不可用时引导 `rift-dispatch`。

## 6. 与其他 Skill 的协作

- **rift-dispatch**: rift-free 能力不足时，引导用户用 rift-dispatch 选更强的付费模型
- **obsidian-cli**: 知识库整理时，rift-free 负责分析，obsidian-cli 负责执行写入
- **kb-maintenance**: 未来 KB 整理 skill 可复用 rift-free 的批量扫描能力
