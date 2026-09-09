# rift-reap CHANGELOG

## v1.0.0 — 2026-09-09

首个版本。从一次真实清理（13 个子会话）中固化出来。

### 核心

- 唯一归属判据：`labels["paseo.parent-agent-id"] == $PASEO_AGENT_ID`
- 默认只归档 `status=closed` 且 `attentionReason != error`
- 默认 dry-run，`--yes` 才执行（archive 不可逆）

### 固化的四条实战判据

1. **CLI 拿不到归属** —— `paseo agent ls --json` 的 `labels` 恒为 `{}`
   （2026-09-09 实测 0/200），必须用 MCP `list_agents`。
2. **`limit=200` 会静默截断** —— 全状态查询返回正好 200，其中 closed 只有 155；
   单独查 closed 有 163，**8 条被吃掉**。⇒ 按 statuses 分开查并检测是否撞上限。
3. 🔴 **`sinceHours` 被后端静默忽略** —— `sinceHours=1` 实测返回 155 条 closed，
   其中 **149 条 `updatedAt` 早于 1 小时前**，最早 28 天前。
   ⇒ ⛔ 不能拿它当覆盖面的保证，也不能靠它分段；**覆盖面只取决于 `limit`**。
4. **验证用 id 集合比对，不看数量差** —— 实测归档 13 个而总数只掉 11，
   差额是并发（期间别的会话又结束了 2 个）。数量差会误判成漏归档。

### 「已收割」为什么不做成自动判据

`requiresAttention` / `attentionReason` 反映的是 **Paseo UI 未读标记**，
不是「产出被人用过没有」：agent 通过 MCP 收割**不会**清掉 `finished` 标记。
实测一次清理中 13 个待归档全是 `finished`，而它们的结论早已落进文档。
⇒ 这个维度只有派发方自己知道，所以默认 dry-run 交人确认。

### 异构审查抓到的（首版即修）

- P1：原文档写「父会话超 30 天 → 改 sinceHours 分段查」—— 事实错误。
  顺着这条查下去才发现更根本的问题：**`sinceHours` 压根不生效**（见上）。
- P2：`--include-error` 语义不完整 —— 查询固定 `statuses=["closed"]` 时，
  `status=="error"` 的会话根本查不到。已明确该参数**要同时改查询与过滤两处**。

### 脚本

`scripts/reap-verify.py`，两个子命令：

- `preflight` —— 查截断、查窗口覆盖、列候选状态分布
- `verify` —— 三条判据：残留 0 / 误伤 0 / 遗漏 0

自测：正向 1 例通过；负向 3 例（误伤 / 遗漏 / 残留）各自命中不同判据并以退出码 1 报警。
