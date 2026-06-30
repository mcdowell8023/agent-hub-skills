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


def mysql_query_rows(config, sql):
    """执行查询，返回 (columns, rows)。列名 + 数据都是字符串。"""
    conn = mysql_connect(config)
    try:
        with conn.cursor() as cur:
            cur.execute(sql)
            # SELECT 类才有 description；SHOW/DESCRIBE 也有
            if cur.description is None:
                return [], []
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


def mongo_get_collection(config, name):
    """从 URI 中提取 db 名，定位 collection。"""
    uri = config.get("uri", "")
    # 提取 mongodb://host:port/dbname?opts 中的 dbname
    db_name = None
    try:
        # 简单字符串解析：'mongodb://host:port/db?...' → 取 / 与 ? 之间
        if "/" in uri:
            after_scheme = uri.split("://", 1)[-1]
            # 跳过 host:port，找第一个 /
            path_start = after_scheme.find("/")
            if path_start >= 0:
                db_part = after_scheme[path_start + 1:]
                # 去掉 ? 后的 query string
                if "?" in db_part:
                    db_part = db_part.split("?", 1)[0]
                db_name = db_part.strip() or None
    except Exception:
        pass
    if not db_name:
        err("无法从 URI 提取 database 名")
    client = mongo_connect(config)
    return client, client[db_name][name]


def mongo_eval(config, js_code):
    """
    评估 MongoDB shell 风格代码的子集。
    支持：db.<coll>.find()、db.<coll>.findOne()、db.getCollectionNames()、
          db.<coll>.countDocuments({})、db.runCommand({...})、db.adminCommand({...})。
    返回 Python 对象（list / dict / int）。
    """
    import re

    code = js_code.strip()
    client = mongo_connect(config)

    # 简单解析；不实现完整 JS 引擎。
    # 模式 1: db.getCollectionNames()
    if re.match(r"^db\.getCollectionNames\s*\(\s*\)\s*$", code):
        # 拿 db name
        uri = config.get("uri", "")
        try:
            db_name = uri.split("://", 1)[-1].split("/", 1)[-1].split("?", 1)[0] or "test"
        except Exception:
            db_name = "test"
        return list(client[db_name].list_collection_names())

    # 模式 2: db.<coll>.find()（无 filter）
    m = re.match(r"^db\.([\w-]+)\.find\s*\(\s*\)\s*$", code)
    if m:
        coll_name = m.group(1)
        uri = config.get("uri", "")
        try:
            db_name = uri.split("://", 1)[-1].split("/", 1)[-1].split("?", 1)[0] or "test"
        except Exception:
            db_name = "test"
        docs = list(client[db_name][coll_name].find().limit(100))
        for d in docs:
            d["_id"] = str(d["_id"])
        return docs

    # 模式 3: db.<coll>.findOne()
    m = re.match(r"^db\.([\w-]+)\.findOne\s*\(\s*\)\s*$", code)
    if m:
        coll_name = m.group(1)
        uri = config.get("uri", "")
        try:
            db_name = uri.split("://", 1)[-1].split("/", 1)[-1].split("?", 1)[0] or "test"
        except Exception:
            db_name = "test"
        doc = client[db_name][coll_name].find_one()
        if doc and "_id" in doc:
            doc["_id"] = str(doc["_id"])
        return doc

    # 模式 4: db.<coll>.countDocuments({})
    m = re.match(r"^db\.([\w-]+)\.countDocuments\s*\(\s*\{\s*\}\s*\)\s*$", code)
    if m:
        coll_name = m.group(1)
        uri = config.get("uri", "")
        try:
            db_name = uri.split("://", 1)[-1].split("/", 1)[-1].split("?", 1)[0] or "test"
        except Exception:
            db_name = "test"
        return client[db_name][coll_name].count_documents({})

    # 模式 5: db.runCommand({...}) / db.adminCommand({...})
    m = re.match(r"^db\.(runCommand|adminCommand)\s*\(\s*(\{.*\})\s*\)\s*$", code, re.DOTALL)
    if m:
        kind = m.group(1)
        body = m.group(2)
        try:
            cmd = json.loads(body)
        except json.JSONDecodeError as e:
            err(f"runCommand 参数不是合法 JSON: {e}")
        target = client.admin if kind == "adminCommand" else client.get_default_database()
        return dict(target.command(cmd))

    err(f"不支持的 MongoDB 命令: {code[:80]}")


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
