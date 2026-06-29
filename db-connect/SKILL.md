---
name: db-connect
description: 统一连接 MySQL + MongoDB 的 CLI 工具，替代 MCP mysql server，支持权限控制（readonly/full）、DDL 拦截、自动 LIMIT、CSV 导出。
type: cli
---

# db-connect

零 MCP 依赖的数据库 CLI：MySQL + MongoDB 统一入口，权限沙箱，跨平台（macOS/Linux）。

## 触发词

`db query`、`查数据库`、`切换数据库`、`用测试库`、`用生产库`、`db`、`数据库查询`

## 配置文件

`~/.claude/skills/db-connect/databases.json`（明文密码，本地不进 git）：

```bash
cp ~/.claude/skills/db-connect/databases.json.example \
   ~/.claude/skills/db-connect/databases.json
# 编辑填入真实密码
```

格式：

```json
{
  "connections": {
    "test-mysql": {
      "type": "mysql",
      "host": "...", "port": 3306,
      "user": "...", "pass": "...", "db": "...",
      "permission": "full" | "readonly",
      "ssl": false,
      "label": "..."
    },
    "test-mongo": {
      "type": "mongodb",
      "uri": "mongodb://host:port/db",
      "permission": "full" | "readonly",
      "label": "..."
    }
  },
  "active": "test-mysql"
}
```

## 子命令

| 命令 | 说明 |
|---|---|
| `db ls` | 列出所有连接（标注 `*` 活跃） |
| `db use <name>` | 切换活跃连接 |
| `db test` | 测试当前连接 |
| `db query "SQL or mongo shell cmd"` | 执行查询 |
| `db tables` | 列出表/集合 |
| `db desc <table\|collection>` | 表结构 / 样本文档 |
| `db count <table\|collection>` | 计数 |
| `db export <table> [--where "..."]` | 导出 CSV 到 `exports/` |
| `db help` | 帮助 |

## 安全模型

| 模式 | 允许 | 拒绝 |
|---|---|---|
| `readonly` | SELECT / SHOW / DESCRIBE / EXPLAIN / find / count / aggregate | INSERT / UPDATE / DELETE / DDL / 高危 |
| `full` | 上述 + INSERT / UPDATE / DELETE / insertOne / updateMany / deleteMany | DDL + 高危 |
| 任何模式 | — | DROP / ALTER / CREATE / TRUNCATE / RENAME / CALL / LOAD DATA / INTO OUTFILE / SET GLOBAL / 多语句 |

其他保护：
- MySQL 无 LIMIT 的 SELECT 自动追加 `LIMIT 100`
- 单次查询 30 秒超时
- 多语句（`;` 后还有内容）拒绝
- DELETE 写操作不自动确认（信任用户已切到 full 模式）

## 跨平台

- MySQL CLI：`mysql`（Mac: `brew install mysql-client`，Hub: `mariadb-client`）
- MongoDB CLI：`mongosh`（Mac: `brew install mongosh`）
- 自实现超时（macOS 无 GNU `timeout`）

环境变量可 mock：`MYSQL_CMD`、`MONGOSH_CMD`、`DATABASES_JSON`。

## 依赖

- `python3`（解析 JSON）
- `mysql` CLI / `mongosh`
- `bash 4+`

## 测试

```bash
bash ~/.claude/skills/db-connect/scripts/tests/test-db.sh
```

23 个用例覆盖：参数解析、连接列表、切换、权限拒绝、DDL/高危拦截、自动 LIMIT、连接失败检测。无需真实数据库（mock CLI）。

## JumpServer 中转（jms_exec transport）

内网数据库从外网不可达时，通过 JumpServer WebSocket 中转执行查询。

### 什么时候需要

- 数据库 IP 为 `172.31.x.x`（AWS 内网），外网无法直连
- 已有 JumpServer 堡垒机账号且有目标服务器 SSH 权限
- 目标服务器上已安装 `python3` + `pymysql`

### databases.json 配置示例

```json
"test-wb-ucs": {
  "type": "mysql",
  "host": "172.31.5.87", "port": 3306,
  "user": "root", "pass": "Doh+SaNyUdsVxg", "db": "wb_ucs",
  "permission": "full",
  "ssl": false,
  "label": "测试 wb_ucs (内网, JumpServer 中转)",
  "transport": "jms_exec",
  "jms": {
    "url": "https://jump.lvshiwanyang.com",
    "username": "mengxianchao",
    "asset_id": "a4cd3fa9-47d3-4059-9e48-d969748766d7",
    "account_id": "e9b49234-1f40-4173-ac61-655336dc8912"
  }
}
```

- `transport: "jms_exec"` — 启用 JumpServer 中转模式
- 不填或 `"transport": "direct"` — 走现有直连逻辑
- `jms.asset_id` / `jms.account_id` — JumpServer 资产和账号 UUID（从 `wb-jumpserver-log-query` SKILL.md 获取）

### JMS 密码配置

JumpServer 登录密码**不存 databases.json**（安全原因）。按优先级：

1. 环境变量 `JMS_PASSWORD`
2. `~/.ai/rules/credentials.md` 或 `~/wb/.ai/rules/credentials.md` 的 §1.5 节

### 依赖

- `pip3 install websockets`（本地）
- 远程服务器需要 `python3` + `pymysql`

### 限制

- 每次查询建一次 WebSocket 连接，比直连慢 3-5 秒
- 不支持验证码自动处理（首次登录如触发验证码需手动处理）
- 仅支持 MySQL（MongoDB 不支持 jms_exec）
- SQL 安全检查（DDL 拦截、权限控制）与 direct 模式一致

## TUN 代理兼容（v2rayN / sing-box）

sing-box gvisor TUN 会破坏 MySQL 协议握手，导致所有数据库连接失败。

### 修复方法

在 v2rayN 路由规则中添加数据库直连规则：

1. 打开 v2rayN → 路由规则
2. 新建或编辑一条规则：
   - **别名**: WB直连IP
   - **规则类型**: ALL（同时对 Routing 和 DNS 生效）
   - **outboundTag**: direct
   - **Domain**:
     ```
     wbsmysql.cravyof0csdw.us-east-1.rds.amazonaws.com,
     worldesusde.cf6km0y04l41.us-east-1.rds.amazonaws.com
     ```
   - **IP**（当前解析，RDS IP 会变需定期更新）:
     ```
     100.31.205.43,
     100.31.205.99,
     3.211.153.99,
     172.31.5.87,
     3.220.48.20,
     34.236.250.114
     ```
   - **Port**: `3306,24686,27017`
3. 保存并重启 v2rayN

### 注意

- 规则类型必须选 **ALL**，不能只选 Routing（MySQL 不走 SNI，域名匹配需要 DNS 层配合）
- RDS IP 会变（AWS 弹性 IP），如果突然连不上先 `dig +short <rds-domain>` 查新 IP 并更新规则
- Hub 上的 v2rayN 也需要同样配置（配置存在 guiNDB.db SQLite 数据库里）
- 不使用 TUN 时无需此配置
