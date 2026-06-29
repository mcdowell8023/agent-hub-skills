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
