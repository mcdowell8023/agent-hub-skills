#!/usr/bin/env python3
"""
db_engine.py — 跨平台数据库引擎（pymysql + pymongo）

设计目标：替换 db.sh 中的 mysql CLI / mongosh 调用，统一跨平台行为。

调用方式：
  python3 db_engine.py <action> <config_json> [args...]

Actions:
  connect <config_json>                       测试连接
  query   <config_json> <sql_or_js>           执行查询
  tables  <config_json>                       列出表/集合
  desc    <config_json> <table>               表结构
  count   <config_json> <table>               行数
  export  <config_json> <table> [where]       导出 CSV（仅 MySQL，stdout 输出）

config_json 是单个连接的 JSON 字符串（由 db.sh 从 databases.json 提取后传入）。
Python 不读 databases.json，路径单一来源在 bash 层。

输出约定：
  MySQL  query/tables/desc/count → tab 分隔（与 mysql CLI -e 一致）
  MySQL  export                  → CSV（stdout）
  MongoDB query/tables/desc/count → JSON Lines（每行一个 JSON 对象，便于解析）
  连接失败/错误                  → stderr，exit 非 0

安全说明：
  db.sh 在调用本引擎前已完成安全检查（SQL 注入拦截、DDL 禁止、分号禁止、权限模型）。
  本脚本不重复做安全检查；只负责执行。
"""

import json
import sys
import csv
import io
import os
import re
import time
import asyncio


# ============ 帮助 ============

def usage():
    sys.stderr.write(
        "用法: python3 db_engine.py <action> <config_json> [args...]\n"
        "  action: connect | query | tables | desc | count | export\n"
    )
    sys.exit(1)


# ============ 工具函数 ============

def load_config(argv):
    """解析 argv：[action, config_json, ...args]"""
    if len(argv) < 3:
        usage()
    action = argv[1]
    try:
        config = json.loads(argv[2])
    except json.JSONDecodeError as e:
        sys.stderr.write(f"错误: config_json 解析失败: {e}\n")
        sys.exit(1)
    return action, config, argv[3:]


def err(msg):
    sys.stderr.write(f"错误: {msg}\n")
    sys.exit(1)


# ============ MySQL 引擎 ============

def mysql_connect(config):
    """建立 pymysql 连接；connect_timeout=10，read_timeout 默认"""
    try:
        import pymysql
    except ImportError:
        err("缺少 pymysql，运行: pip3 install pymysql")

    # ssl 字段：true/True 启用；false/False/缺省 → ssl_disabled=True（统一不强制）
    ssl_flag = config.get("ssl", False)
    ssl_enabled = str(ssl_flag).lower() in ("true", "1", "yes")

    kwargs = dict(
        host=config["host"],
        port=int(config.get("port", 3306)),
        user=config["user"],
        password=config.get("pass", ""),
        database=config.get("db"),
        connect_timeout=10,
        read_timeout=30,
        write_timeout=30,
        charset="utf8mb4",
        cursorclass=pymysql.cursors.Cursor,  # 默认 cursor，输出 tab 分隔
    )
    if ssl_enabled:
        # pymysql 默认不强制 SSL；显式传 ssl_disabled=False 开启握手
        kwargs["ssl_disabled"] = False
    else:
        # 统一处理：不强制 SSL（Hub MariaDB 等老实例兼容）
        kwargs["ssl_disabled"] = True

    try:
        return pymysql.connect(**kwargs)
    except Exception as e:
        err(f"MySQL 连接失败: {type(e).__name__}: {e}")


# ⛔ 无 WHERE 的 UPDATE/DELETE 一律拒绝（用户 2026-08-13 拍板）。
#
# 与 db.sh 的守卫分工：db.sh 管**权限**（readonly 禁 DML :174 · DDL 永远禁 :149），
# 这条管**影响面** —— 全表覆盖在任何环境都不该由 agent 随手执行，
# 与连接是 full 还是 readonly 无关。守在引擎里是因为这层才真正 commit，离后果最近。
#
# ⚠️ 这道门在「写会静默回滚」的年代形同虚设（写了也不落）。commit 修好后才有牙。
def _strip_sql_comments(sql):
    """去掉注释，避免 `DELETE FROM t -- WHERE x` 用注释里的 WHERE 骗过检查。"""
    sql = re.sub(r"/\*.*?\*/", " ", sql, flags=re.S)   # 块注释
    sql = re.sub(r"--[^\n]*", " ", sql)                 # -- 行注释
    sql = re.sub(r"#[^\n]*", " ", sql)                  # # 行注释
    return sql


def assert_write_is_bounded(sql):
    """UPDATE / DELETE 必须带 WHERE，否则拒绝执行。⛔ 在 execute 之前调用。"""
    body = _strip_sql_comments(sql)
    if not re.match(r"^\s*(UPDATE|DELETE)\b", body, flags=re.I):
        return  # INSERT / REPLACE / SELECT 等不受此门约束
    if re.search(r"\bWHERE\b", body, flags=re.I):
        return
    verb = re.match(r"^\s*(\w+)", body).group(1).upper()
    err(
        f"拒绝执行：{verb} 没有 WHERE 条件，会影响全表。\n"
        f"   这道门与连接权限无关 —— 全表覆盖不该由 agent 随手执行。\n"
        f"   确实要全表操作：加显式条件（如 WHERE 1=1），或输出脚本交人工执行。"
    )


def mysql_query_rows(config, sql):
    """执行语句，返回 (columns, rows)。列名 + 数据都是字符串。

    ⚠️ 写语句（无 description）必须 commit —— pymysql 默认 autocommit=False，
    只 close 不 commit 会让事务在关连接时静默回滚，而调用方拿到空结果 + exit 0，
    误以为写成功了。这个坑 2026-08-13 被 ACS 线在执行迁移 SQL 时踩到。
    ⛔ 不要把 commit 去掉「简化」，回归测试见 tests/test-engine-commit.py。

    安全边界不在本层，且**不因本函数会提交而放宽**：
      - DDL 永远禁止 —— db.sh:149 MYSQL_DENY_REGEX
      - readonly 禁 INSERT/UPDATE/DELETE/REPLACE —— db.sh:174-176
    进得到这里的写语句，都是 permission=full 的连接被明确放行的。
    """
    assert_write_is_bounded(sql)          # ⛔ 必须在建连接/执行之前
    conn = mysql_connect(config)
    try:
        with conn.cursor() as cur:
            cur.execute(sql)
            # SELECT / SHOW / DESCRIBE 有 description；写语句没有
            if cur.description is None:
                conn.commit()
                affected = cur.rowcount if cur.rowcount is not None else 0
                # 把影响行数回给调用方 —— 只回空结果的话，
                # 「写成功 0 行」与「压根没写」在输出上不可区分。
                return ["affected_rows"], [[str(affected)]]
            columns = [d[0] for d in cur.description]
            rows = cur.fetchall()
            # 转 str（处理 Decimal/date/datetime 等）
            rows = [[str(v) if v is not None else "" for v in row] for row in rows]
            return columns, rows
    finally:
        conn.close()


def mysql_print_table(columns, rows):
    """tab 分隔输出（与 mysql CLI -e 默认格式一致）"""
    if columns:
        sys.stdout.write("\t".join(columns) + "\n")
    for row in rows:
        sys.stdout.write("\t".join(row) + "\n")


def mysql_export(config, table, where):
    """导出 CSV 到 stdout（db.sh 会重定向到文件）"""
    sql = f"SELECT * FROM {table}"
    if where:
        sql += f" WHERE {where}"
    sql += " LIMIT 10000"

    conn = mysql_connect(config)
    try:
        with conn.cursor() as cur:
            cur.execute(sql)
            if cur.description is None:
                return
            columns = [d[0] for d in cur.description]
            writer = csv.writer(sys.stdout, quoting=csv.QUOTE_MINIMAL)
            writer.writerow(columns)
            for row in cur.fetchall():
                # None → ""（与 mysql --batch 的 \N 略有差异，但 CSV 兼容；db.sh 解析 CSV 不依赖 \N）
                writer.writerow(["" if v is None else v for v in row])
    finally:
        conn.close()


# ============ MongoDB 引擎 ============

def mongo_connect(config):
    """建立 pymongo 客户端；serverSelectionTimeoutMS=10s"""
    try:
        from pymongo import MongoClient
    except ImportError:
        err("缺少 pymongo，运行: pip3 install pymongo")

    uri = config.get("uri")
    if not uri:
        err("MongoDB 连接缺少 uri 字段")

    try:
        client = MongoClient(uri, serverSelectionTimeoutMS=10000)
        # 强制一次 server selection，失败立即抛
        client.admin.command("ping")
        return client
    except Exception as e:
        err(f"MongoDB 连接失败: {type(e).__name__}: {e}")


def _mongo_db_name(config):
    """Extract database name from MongoDB URI."""
    uri = config.get("uri", "")
    try:
        after_scheme = uri.split("://", 1)[-1]
        path_start = after_scheme.find("/")
        if path_start >= 0:
            db_part = after_scheme[path_start + 1:]
            if "?" in db_part:
                db_part = db_part.split("?", 1)[0]
            return db_part.strip() or "test"
    except Exception:
        pass
    return "test"


def _mongo_client(config):
    """Get pymongo client and database."""
    client = mongo_connect(config)
    db_name = _mongo_db_name(config)
    return client, client[db_name]


def _parse_json_arg(s):
    """Parse a JSON-like argument, tolerating single quotes and unquoted keys."""
    s = s.strip()
    if not s:
        return {}
    try:
        return json.loads(s)
    except json.JSONDecodeError:
        pass
    # Try replacing single quotes with double quotes
    normalized = s.replace("'", '"')
    try:
        return json.loads(normalized)
    except json.JSONDecodeError as e:
        err(f"无法解析 JSON 参数: {e}\n  输入: {s[:120]}")


def _serialize_doc(doc):
    """Convert ObjectId and other BSON types to strings for JSON output."""
    if doc is None:
        return None
    if isinstance(doc, dict):
        return {k: _serialize_doc(v) for k, v in doc.items()}
    if isinstance(doc, list):
        return [_serialize_doc(v) for v in doc]
    if hasattr(doc, '__str__') and type(doc).__module__ == 'bson':
        return str(doc)
    return doc


def mongo_eval(config, js_code):
    """
    评估 MongoDB shell 风格代码。
    支持：
      db.getCollectionNames()
      db.<coll>.find()  /  db.<coll>.find({filter})
      db.<coll>.find({filter}).sort({field:dir}).limit(n).skip(n)
      db.<coll>.findOne()  /  db.<coll>.findOne({filter})
      db.<coll>.countDocuments({})  /  db.<coll>.countDocuments({filter})
      db.<coll>.aggregate([{...}, ...])
      db.<coll>.distinct("field")  /  db.<coll>.distinct("field", {filter})
      db.runCommand({...})  /  db.adminCommand({...})
    """
    import re

    code = js_code.strip()

    # db.getCollectionNames()
    if re.match(r"^db\.getCollectionNames\s*\(\s*\)\s*$", code):
        _, db = _mongo_client(config)
        return list(db.list_collection_names())

    # db.runCommand({...}) / db.adminCommand({...})
    m = re.match(r"^db\.(runCommand|adminCommand)\s*\(\s*(\{.*\})\s*\)\s*$", code, re.DOTALL)
    if m:
        kind = m.group(1)
        cmd = _parse_json_arg(m.group(2))
        client = mongo_connect(config)
        target = client.admin if kind == "adminCommand" else client.get_default_database()
        return _serialize_doc(dict(target.command(cmd)))

    # db.<coll>.aggregate([...])
    m = re.match(r"^db\.([\w-]+)\.aggregate\s*\(\s*(\[.*\])\s*\)\s*$", code, re.DOTALL)
    if m:
        coll_name = m.group(1)
        pipeline = _parse_json_arg(m.group(2))
        _, db = _mongo_client(config)
        docs = list(db[coll_name].aggregate(pipeline))
        return _serialize_doc(docs)

    # db.<coll>.distinct("field") or db.<coll>.distinct("field", {filter})
    m = re.match(r'^db\.([\w-]+)\.distinct\s*\(\s*["\'](\w+)["\']\s*(?:,\s*(\{.*?\}))?\s*\)\s*$', code, re.DOTALL)
    if m:
        coll_name = m.group(1)
        field = m.group(2)
        filt = _parse_json_arg(m.group(3)) if m.group(3) else {}
        _, db = _mongo_client(config)
        return db[coll_name].distinct(field, filt)

    # db.<coll>.find(...) with optional .sort().limit().skip() chain
    m = re.match(r"^db\.([\w-]+)\.find\s*\((.*)\)\s*$", code, re.DOTALL)
    if m:
        coll_name = m.group(1)
        rest = m.group(2).strip()
        _, db = _mongo_client(config)

        # Parse chained modifiers: .sort({...}).limit(n).skip(n)
        sort_spec = None
        limit_val = 100
        skip_val = 0
        chain = rest

        # Extract .sort()
        sm = re.search(r'\.sort\s*\(\s*(\{[^)]*\})\s*\)', chain)
        if sm:
            sort_spec = _parse_json_arg(sm.group(1))
            chain = chain[:sm.start()] + chain[sm.end():]

        # Extract .limit()
        lm = re.search(r'\.limit\s*\(\s*(\d+)\s*\)', chain)
        if lm:
            limit_val = int(lm.group(1))
            chain = chain[:lm.start()] + chain[lm.end():]

        # Extract .skip()
        skm = re.search(r'\.skip\s*\(\s*(\d+)\s*\)', chain)
        if skm:
            skip_val = int(skm.group(1))
            chain = chain[:skm.start()] + chain[skm.end():]

        # Remaining should be the filter argument(s)
        chain = chain.strip().rstrip(')')
        if chain.startswith('('):
            chain = chain[1:]
        chain = chain.strip()

        filt = {}
        if chain and chain not in ('', '{}'):
            # Take only the first JSON object (filter), ignore projection for now
            filt = _parse_json_arg(chain.split(',')[0].strip())

        cursor = db[coll_name].find(filt)
        if sort_spec:
            cursor = cursor.sort(list(sort_spec.items()))
        if skip_val:
            cursor = cursor.skip(skip_val)
        cursor = cursor.limit(limit_val)
        docs = list(cursor)
        return _serialize_doc(docs)

    # db.<coll>.findOne() or db.<coll>.findOne({filter})
    m = re.match(r"^db\.([\w-]+)\.findOne\s*\(\s*(\{.*?\})?\s*\)\s*$", code, re.DOTALL)
    if m:
        coll_name = m.group(1)
        filt = _parse_json_arg(m.group(2)) if m.group(2) else {}
        _, db = _mongo_client(config)
        doc = db[coll_name].find_one(filt)
        return _serialize_doc(doc)

    # db.<coll>.countDocuments({}) or db.<coll>.countDocuments({filter})
    m = re.match(r"^db\.([\w-]+)\.countDocuments\s*\(\s*(\{.*?\})?\s*\)\s*$", code, re.DOTALL)
    if m:
        coll_name = m.group(1)
        filt = _parse_json_arg(m.group(2)) if m.group(2) else {}
        _, db = _mongo_client(config)
        return db[coll_name].count_documents(filt)

    err(f"不支持的 MongoDB 命令: {code[:120]}")


def mongo_print(obj):
    """JSON Lines 输出；非 list 自动包成单元素 list"""
    if isinstance(obj, list):
        for item in obj:
            sys.stdout.write(json.dumps(item, default=str, ensure_ascii=False) + "\n")
    else:
        sys.stdout.write(json.dumps(obj, default=str, ensure_ascii=False) + "\n")



# ============ External transport (plugin) ============

def external_exec(config, action, args=None):
    """Execute via external transport script."""
    script = os.path.expanduser(config.get("transport_script", ""))
    if not script or not os.path.isfile(script):
        err(f"transport_script not found: {script}")
    import subprocess
    cmd = [sys.executable, script, action, json.dumps(config)]
    if args:
        cmd.extend(args)
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    if result.returncode != 0:
        err(result.stderr.strip() or f"transport script failed: exit {result.returncode}")
    print(result.stdout, end="")


# ============ Dispatcher ============

def main():
    if len(sys.argv) < 2:
        usage()
    action, config, args = load_config(sys.argv)
    transport = config.get("transport", "direct")
    db_type = config.get("type", "").lower()

    if transport not in ("direct", ""):
        external_exec(config, action, args)
        return

    if db_type == "mysql":
        if action == "connect":
            conn = mysql_connect(config)
            conn.close()
            return
        if action == "query":
            if not args:
                err("query 需要 SQL 参数")
            cols, rows = mysql_query_rows(config, " ".join(args))
            mysql_print_table(cols, rows)
            return
        if action == "tables":
            cols, rows = mysql_query_rows(config, "SHOW TABLES")
            mysql_print_table(cols, rows)
            return
        if action == "desc":
            if not args:
                err("desc 需要表名")
            cols, rows = mysql_query_rows(config, f"DESCRIBE {args[0]}")
            mysql_print_table(cols, rows)
            return
        if action == "count":
            if not args:
                err("count 需要表名")
            cols, rows = mysql_query_rows(config, f"SELECT COUNT(*) AS cnt FROM {args[0]}")
            mysql_print_table(cols, rows)
            return
        if action == "export":
            if not args:
                err("export 需要表名")
            table = args[0]
            # where 条件：拼接剩余 args（与 db.sh 已有行为一致：where 在 export 时单独传 SQL 片段）
            where = " ".join(args[1:]) if len(args) > 1 else ""
            mysql_export(config, table, where)
            return
        err(f"未知 action: {action}")

    elif db_type == "mongodb":
        if action == "connect":
            mongo_connect(config)
            return
        if action == "query":
            if not args:
                err("query 需要 MongoDB 命令")
            result = mongo_eval(config, " ".join(args))
            mongo_print(result)
            return
        if action == "tables":
            result = mongo_eval(config, "db.getCollectionNames()")
            mongo_print(result)
            return
        if action == "desc":
            if not args:
                err("desc 需要集合名")
            result = mongo_eval(config, f"db.{args[0]}.findOne()")
            mongo_print(result)
            return
        if action == "count":
            if not args:
                err("count 需要集合名")
            result = mongo_eval(config, f"db.{args[0]}.countDocuments({{}})")
            mongo_print(result)
            return
        if action == "export":
            err("export 当前仅支持 MySQL")
        err(f"未知 action: {action}")

    else:
        err(f"未知数据库类型: {db_type}")


if __name__ == "__main__":
    main()
