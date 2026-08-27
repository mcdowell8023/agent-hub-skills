# rift-free — 免费模型通道

利用 OpenCode 中配置的免费模型执行任务。通过 `opencode run --pure` 调用，绕过 OMO 编排。

## 可用模型

### Tier 1: OpenRouter（需 VPN，能力强）

| 短名 | Model ID | 适合场景 |
|---|---|---|
| `coder` | qwen/qwen3-coder:free | 代码审查/生成/重构（1M 上下文） |
| `llama70` | meta-llama/llama-3.3-70b-instruct:free | 通用任务/摘要/分析 |
| `nemotron` | nvidia/nemotron-3-ultra-550b-a55b:free | 复杂推理/深度分析（550B） |
| `gemma` | google/gemma-4-31b-it:free | 通用/多语言 |

限速：20 RPM / 200 RPD。

### Tier 2: 智谱（国内直连，永久免费）

| 短名 | Model ID | 适合场景 |
|---|---|---|
| `flash` | glm-4-flash | 中文摘要/分类/标签/格式化 |

### Tier 3: 讯飞（国内直连，能力有限）

| 短名 | Model ID | 适合场景 |
|---|---|---|
| `hunyuan` | xophunyuan7bmt | 简单摘要/标签提取 |

## 快速使用

```
/rift-free 总结一下这篇文档
/rift-free --model coder 审查这段代码
/rift-free --task kb-organize --file ~/KnowledgeBase/Wiki/04_Knowledge/某笔记.md
/rift-free --task tag --file ~/KnowledgeBase/Wiki/04_Knowledge/某笔记.md
/rift-free --task batch --file ~/KnowledgeBase/Wiki/04_Knowledge/
```

## 不适合的任务（用 rift-dispatch 替代）

- 架构设计 → M3 / GLM-5.2
- 安全审计 → M3 / Claude
- 生产级代码生成 → rift-dispatch
