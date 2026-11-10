---
name: pingcode-api
description: 直接调 PingCode Open API，**不登录、不换 token**：用个人访问令牌（PAT，pcpat_ 开头）在任意脚本里查工作项、需求、迭代、工时。附 pc.sh（curl 封装）与 pc.py（Python 封装，令牌自动解析 + 自动分页）。Triggers: 'pingcode api', '查 pingcode 工作项', 'pingcode 令牌', 'pcpat', 'pingcode open api', '免登录访问 pingcode', 'pingcode 工时查询'.
---

# PingCode Open API — 免登录访问

**核心**：PingCode Open API 用 `Authorization: Bearer <PAT>` 直接调，**不需要浏览器登录、
不需要 client_credentials 换 token、不需要 cookie**。所有 agent 只要能读到这个 skill
就能直接查 PingCode。

---

## 0. 令牌在哪（不写明文，只写位置）

| 优先级 | 位置 | 说明 |
|---|---|---|
| 1 | 环境变量 `PINGCODE_API_TOKEN` | CI / 临时覆盖用 |
| 2 | `~/wb/secrets/pingcode-token` | **本机主位置**（权限 600，不入 git） |
| 3 | `~/wb/projects/pingcode-tracker/.env` 的 `PINGCODE_API_TOKEN` | tracker 项目配置 |
| 4 | macOS 钥匙串 `pingcode-token` | 备用 |
| 5 | `client_credentials` 换 token | **兜底**：需要 `PINGCODE_CLIENT_ID` + `PINGCODE_CLIENT_SECRET` |

`pc.sh` / `pc.py` 会按上表自动解析，**调用方不需要关心令牌在哪**。

⚠️ 令牌是**长期有效**的个人访问凭据（当前有效期到 2027-11-10），
**不要写进代码、文档、git 仓、聊天记录**。

---

## 1. 最快：pc.sh（curl 封装，零依赖）

```bash
SKILL_DIR=~/.claude/skills/pingcode-api

# 查工作项（默认 IT研发部 RD-IT 项目）
bash "$SKILL_DIR/scripts/pc.sh" work_items --identifier RD-IT-4033
bash "$SKILL_DIR/scripts/pc.sh" work_items --keywords 审批 --page-size 20

# 任意端点：pc.sh get <path> [k=v ...]
bash "$SKILL_DIR/scripts/pc.sh" get /v1/project/work_items project_id=69cfa488ff85507e68564f20 page_size=5
bash "$SKILL_DIR/scripts/pc.sh" get /v1/project/workloads page_size=10
```

输出是格式化后的 JSON（已过滤空字段，便于阅读）。
加 `--raw` 输出原始 JSON。

---

## 2. 稳一点：pc.py（Python 封装，自动分页 + 结构化输出）

```bash
SKILL_DIR=~/.claude/skills/pingcode-api

# 查单个工作项
python3 "$SKILL_DIR/scripts/pc.py" item RD-IT-4033

# 查我的未结束工作项（推荐口径：排除 已完成/已挂起/已关闭/已驳回）
python3 "$SKILL_DIR/scripts/pc.py" mine --open --all

# 按关键词过滤
python3 "$SKILL_DIR/scripts/pc.py" mine --open --all --keyword 审批

# 自动翻页拉全量并统计
python3 "$SKILL_DIR/scripts/pc.py" list --all

# 任意 GET
python3 "$SKILL_DIR/scripts/pc.py" get /v1/project/work_items project_id=... page_size=5
```

⚠️ `pc.py` **只用 Python 标准库**（urllib），不需要 venv / httpx —— `python3` 直接跑即可。

**`mine` 的状态口径**（与 `pingcode-item.py` 对齐）：

| 状态 | `mine` 默认 | `mine --open` | 提交时能否用 |
|---|---|---|---|
| 待计划 / 开发中 / 联调中 / 需求梳理中 / 打开 … | ✅ 列出 | ✅ 列出 | ✅ 可用（`VERDICT=OK`） |
| 已完成 / 已挂起 | ✅ 列出 | ❌ 排除 | ⚠️ 先问用户（`VERDICT=ASK`） |
| 已关闭 / 已驳回 | ❌ 排除 | ❌ 排除 | ⛔ 不可用（`VERDICT=STOP`） |

`pc.py` 会：
- 自动解析令牌（见 §0），找不到就报明确错误而不是静默 401
- 令牌失效（401）时**自动换一次** client_credentials 再重试一次
- `--all` 自动翻页（PingCode 用 `page_index`，**从 0 开始**，不是 `page`）

---

## 3. 常用端点（Open API v1，base = `https://open.pingcode.com`）

| 端点 | 用途 | 关键参数 |
|---|---|---|
| `/v1/project/work_items` | 工作项（需求/任务/缺陷） | `project_id`（必填）、`identifier`、`keywords`、`assignee_ids`、`page_size`、`page_index` |
| `/v1/project/workloads` | 工时 | `project_id`；⚠️ `report_by` 会被服务端静默忽略，要客户端过滤 |
| `/v1/pjm/workitems/{id}` | 单个工作项详情 | 路径里的 workitem id |
| `/v1/project/iterations` | 迭代 | `project_id` |

⚠️ `project_id` 用**内部 id**（如 `69cfa488ff85507e68564f20` = IT研发部 / RD-IT），
不是 `identifier` 前缀。

---

## 4. 已封装好的现成脚本（别重写）

| 脚本 | 用途 |
|---|---|
| `~/wb/.ai/scripts/pingcode-item.py` | 提交前的编号核对：`check <ID>` / `mine [--keyword]` |
| `~/wb/projects/pingcode-tracker/` | PingCode tracker 服务（工时、钉钉通知等） |

`pingcode-item.py` 的退出码约定（提交规范依赖它）：
`0` OK / `1` NOT_FOUND / `2` ASK（已完成或已挂起→先问用户）/ `3` STOP（已关闭或已驳回，不可��用）/ `5` 工单类编号。

---

## 5. 令牌失效 / 报错怎么办

| 现象 | 原因 | 处理 |
|---|---|---|
| 401 | 令牌过期或被撤销 | 到 `https://wanbridge.pingcode.com/account/access-token` 点「重新生成」；旧令牌立即失效 |
| 403 | 权限不足 | 令牌权限 = 账号权限，确认账号有目标项目权限 |
| 404 | 端点路径错 | 查 open.pingcode.com 文档；注意 `/v1/user`、`/v1/users` **不存在** |
| `project_id` 报空 | 用了 identifier 前缀 | 必须传内部 id（`69cfa488ff85507e68564f20`） |
| 页码重复同一批数据 | 用了 `page` 参数 | 用 `page_index`，**从 0 开始** |

⛔ **不要为了拿数据去浏览器登录**。能用 PAT 就用 PAT；
只有 PAT 彻底不可用（且确实需要 web 界面操作）才用 ego lite 复用登录态。

---

## 6. 自检

```bash
bash ~/.claude/skills/pingcode-api/scripts/pc.sh health
# 应输出 {"ok": true, ...}；401 则说明令牌失效
```
