---
name: rift-reap
description: "Rift Reap: archive your OWN finished Paseo sub-agents. Strict ownership boundary — only children whose paseo.parent-agent-id equals this session. Triggers: 'rift-reap', 'rift reap', '清理子会话', '归档子会话', '收割子会话', '清理我的子agent', 'reap children', 'archive subagents', '清理派发的会话'."
user-invocable: true
argument-hint: "[--yes] [--include-idle] [--include-error] [--dry-run]"
---

# Rift Reap — 归档自己派出去的子会话

> 🔗 **rift 家族**：`/rift-dispatch`（派发）· **`/rift-reap`（回收）** · `/rift-integration-qa`（测试验收）

`rift-dispatch` 把任务派出去，`rift-reap` 把跑完的收回来。

**用户请求:** $ARGUMENTS

---

## 0. ⛔ 唯一的硬边界：只归档自己的子会话

**归档不可逆** —— Paseo 只有 `archive`（软删）和 `delete`（硬删），**没有 unarchive**。
过滤条件就是唯一防线。

| | |
|---|---|
| ✅ **可以归档** | `labels["paseo.parent-agent-id"] == 当前会话的 agentId` |
| ⛔ **一律不碰** | 顶层会话（`labels` 为空或无该字段）—— 那是用户自己开的 |
| ⛔ **一律不碰** | 别的 agent 的子会话（parent 指向别人） |
| ⛔ **一律不碰** | 孙辈（子会话的子会话）—— 它们的 parent 是我的子会话，不是我 |

🔴 **`status` 不是归属判据。** 曾经有人用 `status in ("closed","error")` 清理，
误删了用户自己开的顶层会话 —— 状态只说明会话结束了，**不说明它是谁的**。

---

## 1. 拿到自己的 agentId

```bash
echo "$PASEO_AGENT_ID"
```

Paseo 拉起的会话都有这个环境变量。**这是唯一可靠来源。**

⛔ **拿不到就停手**，不要用别的方式猜自己是谁：

```bash
if [ -z "$PASEO_AGENT_ID" ]; then
  echo "❌ 不在 Paseo 会话中（无 PASEO_AGENT_ID），无法确定归属边界 → 中止"
  exit 1
fi
```

**自检**（可选但推荐）：确认它在 agent 列表里、`labels` 为空（说明自己是顶层会话）、
`cwd` 与 `$PASEO_AGENT_CWD` 一致。

---

## 2. 列出候选 —— 🔴 必须用 MCP，CLI 拿不到归属

```
mcp__paseo__list_agents(statuses=["closed"], limit=200)
# sinceHours 可传可不传 —— 实测无效，见 §2.1
```

| 数据源 | `labels["paseo.parent-agent-id"]` |
|---|---|
| ✅ MCP `list_agents` | **有** |
| ❌ CLI `paseo agent ls --json` | **没有**（`labels` 恒为 `{}`，2026-09-09 实测 0/200） |

⛔ **不要用 CLI 的输出做过滤** —— 从那个源根本过滤不出归属。

### 2.1 🔴 `sinceHours` 被后端静默忽略 —— 不要依赖它

**2026-09-09 实测**：`sinceHours=1` + `statuses=["closed"]` 返回 155 条，
其中 **149 条的 `updatedAt` 早于 1 小时前**，最早的是 **28 天前**。

⇒ 这个参数**不生效**，返回的是全量（只受 `limit` 约束）。

| | |
|---|---|
| 好消息 | 不用担心「窗口没覆盖到老子会话」 |
| 坏消息 | **`limit` 是唯一的真实约束**，覆盖面风险全在截断上 |

⚠️ 这是「传了不支持的参数 → 后端不报错、直接返回全量」的典型形态。
传 `sinceHours` 无害（当文档注释用），但**⛔ 不能拿它当覆盖面的保证**。

### 2.2 🔴 `limit=200` 是硬上限，撞上就是截断

实测：不带 `statuses` 查询返回正好 200 条 = 上限，其中 `closed` 只有 155 条，
而单独查 `closed` 有 163 条 —— **8 条被吃掉了**。

⇒ **按 `statuses` 分开查**，每次检查返回条数：

```
len(agents) >= 200  ⇒ 🔴 截断了，候选集不完整，⛔ 不能据此归档
len(agents) <  200  ⇒ ✅ 该状态的全集
```

**撞上限怎么办**：`sinceHours` 既然无效，就没法用时间分段。可行的只有
① 按 `statuses` 拆得更细（本 skill 默认只查 `closed`，通常远低于 200）；
② 按 `cwd` 过滤（MCP 支持 `cwd` 参数）缩小范围。
⛔ **不要靠调 `sinceHours` 分段** —— 它不起作用。

## 3. 三个筛选条件

用户的口径是「归档**已收割完毕、没有报错、没有在运行**的」。对应字段：

| 口径 | 判据 | 默认 |
|---|---|---|
| **没有在运行** | `status == "closed"` | ✅ 只收 closed |
| **没有报错** | `attentionReason != "error"` | ✅ 排除 error |
| **已收割完毕** | 🔴 **没有可靠的客观字段** | ⚠️ 默认 dry-run 让人确认 |

### 3.1 为什么「已收割」判不出来

Paseo 的 `requiresAttention` / `attentionReason` 反映的是 **UI 未读标记**，
不是「它的产出被人用过没有」：

| 取值 | 含义 | 能当「已收割」吗 |
|---|---|---|
| `false` / `null` | 在 Paseo UI 里被点开过 | ❌ 点开 ≠ 结论被采纳 |
| `true` / `finished` | 跑完了，UI 上还有未读标记 | ❌ **agent 通过 MCP 收割不会清掉这个标记** |
| `true` / `error` | 出错了 | 这个倒是可靠 → 默认排除 |

⇒ 实测：一次典型清理里 13 个待归档全部是 `finished`，但它们的结论早就写进文档了。
**「收割没收割」只有派发方自己知道。**

⇒ 所以：**默认 dry-run 打印清单**，由调用方确认后再执行。
`--yes` 跳过确认（仅当调用方明确知道这批已经收割完）。

### 3.2 可选放宽（都要显式声明）

| 参数 | 效果 | ⚠️ 风险 |
|---|---|---|
| `--include-idle` | 把 `idle` 也纳入 | idle 会话**还活着**，可能还要继续对话；archive 会中断它 |
| `--include-error` | 查询扩成 `statuses=["closed","error"]`，且不再排除 `attentionReason=error` | 错误可能还没诊断，归档后不好查 |

⚠️ **`--include-error` 要同时改两处**，只放宽一处不起作用：
① 查询阶段的 `statuses`（否则 `status=="error"` 的根本查不到）
② 过滤阶段的 `attentionReason != "error"` 条件（否则 `closed` 里带 error 标记的仍被排除）

---

## 4. 执行

```
对清单里每一个 id：mcp__paseo__archive_agent(agentId=<id>)
```

独立调用，可并行。逐个确认返回 `{"success":true}`。

**归档前把清单落盘**（archive 不可逆，留追溯记录）：

```bash
# 存 id + title + provider + 时间，放在会话产物目录下
~/AgentWorkspace/tmp/rift-reap/reaped-$(date +%Y%m%d-%H%M).json
```

---

## 5. 🔴 验证：用 id 集合比对，不看数量差

归档后重新查一次同样的 `statuses`，然后：

```bash
python3 scripts/reap-verify.py \
  --before <归档前的 MCP 快照 json> \
  --after  <归档后的 MCP 快照 json> \
  --reaped <落盘的清单 json> \
  --me "$PASEO_AGENT_ID"
```

判据（三条都要过）：

| # | 判据 | 期望 |
|---|---|---|
| ① | 我的子会话残留数 | **0** |
| ② | 消失的 id ⊄ 我的清单（误伤） | **0** |
| ③ | 我的清单 ⊄ 消失的 id（遗漏） | **0** |

### ⚠️ 为什么不能看数量差

实测一次清理：归档 13 个，但 `closed` 总数只从 163 掉到 152（**差 11**）。
差额是**并发** —— 期间别的会话又结束了 2 个 agent 进入 closed。

`163 - 13 + 2 = 152` ✅

⇒ 只看数量差会误判成「漏了 2 个」。**集合比对不受并发影响。**

---

## 6. 边界情况

| 情况 | 处理 |
|---|---|
| `PASEO_AGENT_ID` 为空 | ⛔ 中止，不猜 |
| 我自己就是别人的子会话 | 不影响 —— 判据是「谁的 parent 是我」，与我的 parent 无关 |
| 父会话活了很久（>30 天） | 不成问题 —— `sinceHours` 本就不生效（§2.1），老子会话照样返回。**真正要盯的是 `limit` 截断** |
| 候选为 0 | 正常，说明没派过或已清完。报告后结束 |
| 某个 archive 返回失败 | 记下来单独报告，⛔ 不重试到底（可能是已被别人归档） |
| 孙辈子会话 | ⛔ 不递归。孙辈的 parent 是我的子会话，归档我的子会话**不会**级联归档孙辈 —— 要清得由那个子会话自己跑 `/rift-reap` |

---

## 7. 输出格式

```
🔍 归属边界: <my-agent-id-前8位>  (title: <我的标题>)
📊 覆盖面:   closed 返回 <n> 条 < 200 ✓ 未截断
             (sinceHours 无效，覆盖面只看截断 —— §2.1)

📋 候选 <N> 个（全部 closed / 无 error）:
   <id前8>  <provider>/<model>  <title 截断 44 字>
   ...

⚠️  归档不可逆。确认后执行（或用 --yes 跳过本确认）

✅ 已归档 <N>/<N>
🔬 验证: 残留 0 · 误伤 0 · 遗漏 0
📄 清单: ~/AgentWorkspace/tmp/rift-reap/reaped-<时间戳>.json
```

---

## 8. 相关

- `/rift-dispatch` —— 派发（本 skill 的反向）
- `/paseo` —— Paseo 完整参考（workspaces / schedules / plugins）
- Paseo MCP：`list_agents` · `archive_agent` · `get_agent_status`
