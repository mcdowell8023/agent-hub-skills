#!/usr/bin/env bash
# db.sh — db-connect skill 核心脚本
# 支持 MySQL + MongoDB，安全权限控制，零 MCP 依赖。
# 数据库引擎通过 Python（pymysql/pymongo）实现，跨平台零差异。

set -euo pipefail

# ============ 路径 ============
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL_DIR="$(dirname "$SCRIPT_DIR")"
DB_JSON="${DATABASES_JSON:-$HOME/.claude/skills/db-connect/databases.json}"
EXPORTS_DIR="$SKILL_DIR/exports"

# Python 引擎入口（测试用可注入 mock 脚本）
DB_ENGINE="${DB_ENGINE_CMD:-python3 "$SCRIPT_DIR/db_engine.py"}"
# 标记 DB_ENGINE_CMD 是否被显式覆盖（测试场景）
DB_ENGINE_OVERRIDDEN=false
if [ -n "${DB_ENGINE_CMD+x}" ] && [ -n "$DB_ENGINE_CMD" ]; then
    DB_ENGINE_OVERRIDDEN=true
fi

# ============ 工具函数 ============
err() { echo "错误: $*" >&2; }
info() { echo "$*"; }

# python3 JSON 解析（bash 不好处理 JSON）
py_json() {
    python3 -c "import json,sys; d=json.load(open(sys.argv[1])); $1" "$DB_JSON"
}

# 获取当前活跃连接的 type/permission/字段
get_active_field() {
    local field="$1"
    py_json "print(d['connections'][d['active']].get('$field', ''))"
}

get_active_type() {
    py_json "print(d['connections'][d['active']]['type'])"
}

get_active_permission() {
    py_json "print(d['connections'][d['active']]['permission'])"
}

# 把当前活跃连接的 dict 转成 JSON 字符串，传给 Python 引擎
# 用法: get_active_config_json
get_active_config_json() {
    python3 -c "
import json
d = json.load(open('$DB_JSON'))
print(json.dumps(d['connections'][d['active']]))
"
}

# 跨平台超时执行（macOS 无 timeout 命令）
# 用法: run_with_timeout <秒数> <命令...>
# 用 mtime 真实经过时间累加，避免 sleep 累加误差
run_with_timeout() {
    local secs="$1"; shift
    local cmd=("$@")
    local tmpdir
    tmpdir=$(mktemp -d)
    local pidfile="$tmpdir/pid"
    local statfile="$tmpdir/stat"

    # 后台运行
    (
        "${cmd[@]}"
        echo $? > "$statfile"
    ) &
    local bg_pid=$!
    echo $bg_pid > "$pidfile"

    # 记录起始时间（秒，含小数）
    local start
    start=$(date +%s)

    # 轮询，最多 $secs 秒
    while :; do
        if ! kill -0 $bg_pid 2>/dev/null; then
            # 已结束
            local rc
            rc=$(cat "$statfile" 2>/dev/null || echo 1)
            rm -rf "$tmpdir"
            return $rc
        fi
        local now
        now=$(date +%s)
        local elapsed=$((now - start))
        if [ "$elapsed" -ge "$secs" ]; then
            break
        fi
        sleep 0.2
    done

    # 超时：强杀
    kill -9 $bg_pid 2>/dev/null || true
    wait $bg_pid 2>/dev/null || true
    rm -rf "$tmpdir"
    err "查询超时（${secs}s）"
    return 124  # GNU timeout 的标准超时码
}

# ============ 依赖检查 ============
# 启动时检查 Python 引擎依赖（pymysql + pymongo）
# 仅在执行需要引擎的子命令时检查；help/ls 不依赖引擎
check_python_deps() {
    local missing=()
    if ! python3 -c "import pymysql" 2>/dev/null; then
        missing+=("pymysql")
    fi
    if ! python3 -c "import pymongo" 2>/dev/null; then
        missing+=("pymongo")
    fi
    if [ ${#missing[@]} -gt 0 ]; then
        err "缺少 Python 依赖: ${missing[*]}"
        err "运行: pip3 install ${missing[*]}"
        return 1
    fi
}

# ============ 权限检查 ============
# 检查 SQL 是否包含危险关键词
# 返回 0 = 通过（拒绝），返回 1 = 安全（允许）
# 注意：返回码语义反直觉，因为 set -e 下需要特殊处理

# MySQL 语句检查
# 总是拒绝的 DDL/高危语句
MYSQL_DENY_REGEX='^\s*(DROP|ALTER|CREATE|TRUNCATE|RENAME)\b'
MYSQL_DENY_REGEX+='|^\s*CALL\b'
MYSQL_DENY_REGEX+='|\bLOAD\s+DATA\b'
MYSQL_DENY_REGEX+='|\bINTO\s+OUTFILE\b'
MYSQL_DENY_REGEX+='|\bSET\s+GLOBAL\b'
MYSQL_DENY_REGEX+='|;.*;'  # 禁止多语句

check_mysql_permission() {
    local sql="$1"
    local permission="$2"

    # 0. 拒绝任何包含分号的输入：mysql -e 虽是单语句，但允许多语句是
    #    已知攻击面（SELECT 1; DELETE FROM users）。安全优先，一律拒绝。
    if echo "$sql" | grep -q ';'; then
        err "禁止 SQL 含分号（拒绝多语句，请去掉末尾分号）"
        return 1
    fi

    # 1. 总是拒绝 DDL/高危
    if echo "$sql" | grep -iqE "$MYSQL_DENY_REGEX"; then
        err "禁止执行 DDL/高危语句（DROP/ALTER/CREATE/TRUNCATE/CALL/LOAD DATA/INTO OUTFILE/SET GLOBAL）"
        return 1
    fi

    # 2. readonly 额外限制：拒绝 INSERT/UPDATE/DELETE/REPLACE
    if [ "$permission" = "readonly" ]; then
        if echo "$sql" | grep -iqE '^\s*(INSERT|UPDATE|DELETE|REPLACE)\b'; then
            err "readonly 模式禁止写操作（INSERT/UPDATE/DELETE/REPLACE）"
            return 1
        fi
    fi

    # 3. full 模式下 DELETE 需要确认（不在这里做，简化处理）
    return 0
}

# MongoDB 语句检查
check_mongo_permission() {
    local cmd="$1"
    local permission="$2"

    # 0. 总是拒绝 runCommand/adminCommand 中的 DDL/危险动作。
    #    拦截模式名（.drop/.createCollection 等）不够，runCommand({drop:...}) 会绕过。
    #    显式列出必须拒绝的命令关键字。
    if echo "$cmd" | grep -iqE '\.(runCommand|adminCommand)\s*\(\s*\{[^}]*\b(drop|create|rename|dropDatabase|shutdown|fsync|replSetGetStatus)\b'; then
        err "禁止 runCommand/adminCommand 中执行 DDL/危险操作（drop/create/rename/shutdown/fsync）"
        return 1
    fi

    # 总是拒绝的方法
    if echo "$cmd" | grep -iqE '\.(drop|dropDatabase|createCollection|renameCollection)\b'; then
        err "禁止 DDL 操作（drop/createCollection/renameCollection）"
        return 1
    fi

    # readonly 模式：直接拒绝 runCommand/adminCommand（防 admin 写命令绕过方法名检查）
    if [ "$permission" = "readonly" ]; then
        if echo "$cmd" | grep -iqE '\.(runCommand|adminCommand)\b'; then
            err "readonly 模式禁止 runCommand/adminCommand"
            return 1
        fi
        if echo "$cmd" | grep -iqE '\.(insert|insertOne|insertMany|update|updateOne|updateMany|delete|deleteOne|deleteMany|replaceOne|save|findOneAndUpdate|findOneAndReplace|findOneAndDelete)\b'; then
            err "readonly 模式禁止写操作"
            return 1
        fi
    fi

    return 0
}

# ============ 子命令 ============
cmd_ls() {
    if [ ! -f "$DB_JSON" ]; then
        err "配置文件不存在: $DB_JSON"
        return 1
    fi
    python3 -c "
import json, sys
d = json.load(open('$DB_JSON'))
active = d.get('active', '')
for name, c in d.get('connections', {}).items():
    marker = '*' if name == active else ' '
    print(f\"{marker} {name:20s} {c.get('type','?'):8s} {c.get('permission','?'):10s} {c.get('label','')}\")
"
}

cmd_use() {
    local target="${1:-}"
    if [ -z "$target" ]; then
        err "用法: db use <connection-name>"
        return 1
    fi
    if ! py_json "exit(0 if '$target' in d['connections'] else 1)" 2>/dev/null; then
        err "连接不存在: $target"
        return 1
    fi
    # 改写 JSON 中的 active
    local tmp="${DB_JSON}.tmp"
    python3 -c "
import json
d = json.load(open('$DB_JSON'))
d['active'] = '$target'
json.dump(d, open('$tmp','w'), indent=2, ensure_ascii=False)
"
    mv "$tmp" "$DB_JSON"
    info "已切换到: $target"
}

cmd_test() {
    local type
    type=$(get_active_type)
    local config_json
    config_json=$(get_active_config_json)
    local stderr_tmp
    stderr_tmp=$(mktemp)
    if run_with_timeout 30 $DB_ENGINE connect "$config_json" > /dev/null 2>"$stderr_tmp"; then
        rm -f "$stderr_tmp"
        info "连接成功: $(get_active_field label)"
        return 0
    else
        err "连接失败: $(get_active_field label) — $(tail -1 "$stderr_tmp" 2>/dev/null)"
        rm -f "$stderr_tmp"
        return 1
    fi
}

cmd_query() {
    local query="${1:-}"
    if [ -z "$query" ]; then
        err "用法: db query \"SQL or mongo shell cmd\""
        return 1
    fi

    local type permission
    type=$(get_active_type)
    permission=$(get_active_permission)

    case "$type" in
        mysql)
            if ! check_mysql_permission "$query" "$permission"; then
                return 1
            fi

            # MySQL: 无 LIMIT 的 SELECT 自动加 LIMIT 100
            local final_query="$query"
            if echo "$query" | grep -iqE '^\s*SELECT\b' && ! echo "$query" | grep -iqE '\bLIMIT\b'; then
                final_query="${query} LIMIT 100"
            fi

            local config_json
            config_json=$(get_active_config_json)
            run_with_timeout 30 $DB_ENGINE query "$config_json" "$final_query"
            ;;

        mongodb)
            if ! check_mongo_permission "$query" "$permission"; then
                return 1
            fi

            local config_json
            config_json=$(get_active_config_json)
            run_with_timeout 30 $DB_ENGINE query "$config_json" "$query"
            ;;

        *)
            err "未知数据库类型: $type"
            return 1
            ;;
    esac
}

cmd_tables() {
    local type
    type=$(get_active_type)
    case "$type" in
        mysql)
            cmd_query "SHOW TABLES"
            ;;
        mongodb)
            cmd_query "db.getCollectionNames()"
            ;;
    esac
}

cmd_desc() {
    local target="${1:-}"
    if [ -z "$target" ]; then
        err "用法: db desc <table|collection>"
        return 1
    fi
    local type
    type=$(get_active_type)
    case "$type" in
        mysql)
            cmd_query "DESCRIBE $target"
            ;;
        mongodb)
            cmd_query "db.$target.findOne()"
            ;;
    esac
}

cmd_count() {
    local target="${1:-}"
    if [ -z "$target" ]; then
        err "用法: db count <table|collection>"
        return 1
    fi
    local type
    type=$(get_active_type)
    case "$type" in
        mysql)
            cmd_query "SELECT COUNT(*) FROM $target"
            ;;
        mongodb)
            cmd_query "db.$target.countDocuments({})"
            ;;
    esac
}

cmd_export() {
    local target="${1:-}"
    local where=""
    shift || true
    while [ $# -gt 0 ]; do
        case "$1" in
            --where) where="$2"; shift 2 ;;
            *) err "未知参数: $1"; return 1 ;;
        esac
    done
    if [ -z "$target" ]; then
        err "用法: db export <table> [--where \"...\"]"
        return 1
    fi
    local type
    type=$(get_active_type)
    if [ "$type" != "mysql" ]; then
        err "export 当前仅支持 MySQL"
        return 1
    fi

    # 权限检查：拼好的最终 SQL 也必须走安全校验
    # 防止 --where 注入 INTO OUTFILE / UNION 等绕过 readonly
    local permission
    permission=$(get_active_permission)
    local final_export_sql="SELECT * FROM $target"
    if [ -n "$where" ]; then
        final_export_sql="$final_export_sql WHERE $where"
    fi
    final_export_sql="$final_export_sql LIMIT 10000"
    if ! check_mysql_permission "$final_export_sql" "$permission"; then
        return 1
    fi

    mkdir -p "$EXPORTS_DIR"
    # 路径穿越防护：basename 去掉 ../、/、绝对路径前缀等
    target=$(basename "$target")
    local ts=$(date +%Y%m%d_%H%M%S)
    local outfile="$EXPORTS_DIR/${target}_${ts}.csv"

    local config_json
    config_json=$(get_active_config_json)

    if [ -n "$where" ]; then
        run_with_timeout 30 $DB_ENGINE export "$config_json" "$target" "$where" > "$outfile"
    else
        run_with_timeout 30 $DB_ENGINE export "$config_json" "$target" > "$outfile"
    fi

    info "已导出: $outfile"
}

cmd_help() {
    cat <<'EOF'
db.sh — db-connect skill CLI
用法: db <子命令> [参数]

通用:
  db ls                                 列出所有连接
  db use <name>                         切换活跃连接
  db test                               测试当前连接
  db query "SQL or mongo shell cmd"     执行查询
  db tables                             列出表/集合
  db desc <table|collection>            表结构/样本
  db count <table|collection>           计数
  db help                               显示此帮助

MySQL 专用:
  db export <table> [--where "..."]     导出 CSV

环境变量:
  DATABASES_JSON  配置文件路径（默认 ~/.claude/skills/db-connect/databases.json）
  DB_ENGINE_CMD   Python 引擎入口（默认 python3 <skill>/scripts/db_engine.py）
EOF
}

# ============ 入口 ============
main() {
    if [ $# -eq 0 ]; then
        cmd_help
        return 1
    fi
    local subcmd="$1"
    shift

    # 配置文件存在性检查（除 help 外）
    if [ "$subcmd" != "help" ] && [ ! -f "$DB_JSON" ]; then
        err "配置文件不存在: $DB_JSON"
        err "请参考 databases.json.example 创建"
        return 1
    fi

    # 需要 Python 引擎的子命令：提前检查依赖
    # 但如果 DB_ENGINE_CMD 被显式覆盖（测试场景），跳过依赖检查
    case "$subcmd" in
        test|query|tables|desc|count|export)
            if [ "$DB_ENGINE_OVERRIDDEN" != "true" ]; then
                if ! check_python_deps; then
                    return 1
                fi
            fi
            ;;
    esac

    case "$subcmd" in
        ls) cmd_ls "$@" ;;
        use) cmd_use "$@" ;;
        test) cmd_test "$@" ;;
        query) cmd_query "$@" ;;
        tables) cmd_tables "$@" ;;
        desc) cmd_desc "$@" ;;
        count) cmd_count "$@" ;;
        export) cmd_export "$@" ;;
        help|--help|-h) cmd_help ;;
        *)
            err "未知子命令: $subcmd"
            cmd_help
            return 1
            ;;
    esac
}

main "$@"
