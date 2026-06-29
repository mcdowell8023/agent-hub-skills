#!/usr/bin/env bash
# test-db.sh — db.sh TDD 测试套件
# 用法：bash test-db.sh
# 通过 DB_ENGINE_CMD mock 掉 db_engine.py，零真实数据库依赖。

set -u

# ============ 路径 ============
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL_DIR="$(dirname "$(dirname "$SCRIPT_DIR")")"
DB_SH="$SKILL_DIR/scripts/db.sh"
DB_ENGINE="$SKILL_DIR/scripts/db_engine.py"
MOCK_DIR="$SCRIPT_DIR/mock"
TEST_DB_JSON="$MOCK_DIR/databases.json"
DB_ENGINE_MOCK="$MOCK_DIR/db_engine.py"

# ============ 颜色 ============
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

# ============ 计数器 ============
PASS=0
FAIL=0
FAILED_TESTS=()

# ============ 辅助函数 ============
setup() {
    rm -rf "$MOCK_DIR"
    mkdir -p "$MOCK_DIR"

    # mock databases.json：test-mysql (readonly), test-mysql-full (full), test-mongo (readonly), test-mongo-full (full)
    cat > "$TEST_DB_JSON" <<'JSON'
{
  "connections": {
    "test-mysql": {
      "type": "mysql",
      "host": "127.0.0.1", "port": 3306,
      "user": "root", "pass": "pw", "db": "wb_project",
      "permission": "readonly",
      "ssl": false,
      "label": "测试 MySQL 只读"
    },
    "test-mysql-full": {
      "type": "mysql",
      "host": "127.0.0.1", "port": 3306,
      "user": "root", "pass": "pw", "db": "wb_project",
      "permission": "full",
      "ssl": false,
      "label": "测试 MySQL 读写"
    },
    "test-mongo": {
      "type": "mongodb",
      "uri": "mongodb://127.0.0.1:27017/crm_bridge",
      "permission": "readonly",
      "label": "测试 MongoDB 只读"
    },
    "test-mongo-full": {
      "type": "mongodb",
      "uri": "mongodb://127.0.0.1:27017/crm_bridge",
      "permission": "full",
      "label": "测试 MongoDB 读写"
    },
    "bad-mysql": {
      "type": "mysql",
      "host": "127.0.0.1", "port": 3306,
      "user": "root", "pass": "wrong", "db": "wb_project",
      "permission": "readonly",
      "ssl": false,
      "label": "测试连接失败"
    }
  },
  "active": "test-mysql"
}
JSON

    # mock db_engine.py：统一 mock 入口
    # 接受 action 和 config_json 作为参数
    # stderr 记录到 $MOCK_DIR/engine.log 用于断言
    cat > "$DB_ENGINE_MOCK" <<'MOCK'
#!/usr/bin/env bash
echo "ENGINE_ARGS: $*" >> "${MOCK_DIR:-.}/engine.log"
action="$1"; shift
config="$1"; shift
# 模拟连接失败：config 含 "wrong" 时
if echo "$config" | grep -q '"pass": "wrong"'; then
    echo "ERROR 1045 (28000): Access denied" >&2
    exit 1
fi
# 模拟 export：把 CSV 写到 csv.out
if [ "$action" = "export" ]; then
    echo "mock csv data,field1,field2" >> "${MOCK_DIR:-.}/csv.out"
    exit 0
fi
# 默认输出：tab 分隔的伪结果（模拟 mysql CLI -e 输出格式）
echo -e "col1\tcol2"
echo -e "v1\tv2"
exit 0
MOCK
    chmod +x "$DB_ENGINE_MOCK"

    # 清空 log
    : > "$MOCK_DIR/engine.log"
    : > "$MOCK_DIR/csv.out"
}

# db 命令封装：传入子命令和参数
db() {
    DATABASES_JSON="$TEST_DB_JSON" \
    DB_ENGINE_CMD="$DB_ENGINE_MOCK" \
    MOCK_DIR="$MOCK_DIR" \
    "$DB_SH" "$@"
}

# 断言函数
assert_exit() {
    local expected="$1"; shift
    local desc="$1"; shift
    db "$@"
    local actual=$?
    if [ "$actual" -eq "$expected" ]; then
        echo -e "${GREEN}PASS${NC} $desc (exit=$actual)"
        PASS=$((PASS+1))
    else
        echo -e "${RED}FAIL${NC} $desc (expected exit=$expected, got $actual)"
        FAIL=$((FAIL+1))
        FAILED_TESTS+=("$desc")
    fi
}

assert_contains() {
    local needle="$1"; shift
    local desc="$1"; shift
    local output
    output=$(db "$@" 2>&1)
    if echo "$output" | grep -qF "$needle"; then
        echo -e "${GREEN}PASS${NC} $desc"
        PASS=$((PASS+1))
    else
        echo -e "${RED}FAIL${NC} $desc"
        echo "  expected to contain: $needle"
        echo "  actual output: $output"
        FAIL=$((FAIL+1))
        FAILED_TESTS+=("$desc")
    fi
}

assert_not_contains() {
    local needle="$1"; shift
    local desc="$1"; shift
    local output
    output=$(db "$@" 2>&1)
    if echo "$output" | grep -qF "$needle"; then
        echo -e "${RED}FAIL${NC} $desc"
        echo "  expected NOT to contain: $needle"
        echo "  actual output: $output"
        FAIL=$((FAIL+1))
        FAILED_TESTS+=("$desc")
    else
        echo -e "${GREEN}PASS${NC} $desc"
        PASS=$((PASS+1))
    fi
}

# ============ 测试用例 ============
echo -e "${YELLOW}=== TDD: db.sh 测试套件 ===${NC}"
setup

echo "--- T1: 无参数 → usage + exit 1 ---"
assert_exit 1 "T1: 无参数退出码=1" "" 2>/dev/null || true
# 单独验证 usage 输出
T1_OUT=$(db 2>&1 || true)
if echo "$T1_OUT" | grep -qiE "(usage|用法|用法:)"; then
    echo -e "${GREEN}PASS${NC} T1: 无参数输出 usage"
    PASS=$((PASS+1))
else
    echo -e "${RED}FAIL${NC} T1: 无参数未输出 usage"
    FAIL=$((FAIL+1))
    FAILED_TESTS+=("T1 usage")
fi

echo "--- T2: db ls 输出连接列表 ---"
assert_contains "test-mysql" "T2: ls 列出 test-mysql" ls
assert_contains "test-mongo" "T2: ls 列出 test-mongo" ls
assert_contains "readonly" "T2: ls 显示 permission" ls

echo "--- T3: db use test-mysql 切换成功 ---"
assert_exit 0 "T3: use 切换退出码=0" use test-mysql
assert_contains "test-mysql" "T3: use 后输出当前连接" use test-mysql

echo "--- T4: readonly 模式拒绝 INSERT ---"
assert_exit 1 "T4: readonly 拒绝 INSERT" query "INSERT INTO users VALUES (1)"
assert_not_contains "mock mysql" "T4: INSERT 未实际执行" query "INSERT INTO users VALUES (1)"

echo "--- T5: readonly 模式允许 SELECT ---"
assert_exit 0 "T5: readonly 允许 SELECT" query "SELECT * FROM users"

echo "--- T6: DDL 任何模式都拒绝 ---"
# 切到 full 模式
db use test-mysql-full > /dev/null 2>&1
assert_exit 1 "T6a: full 拒绝 DROP" query "DROP TABLE users"
assert_exit 1 "T6b: full 拒绝 ALTER" query "ALTER TABLE users ADD COLUMN x INT"
assert_exit 1 "T6c: full 拒绝 CREATE" query "CREATE TABLE t (id INT)"
assert_exit 1 "T6d: full 拒绝 TRUNCATE" query "TRUNCATE users"
# 切回 readonly
db use test-mysql > /dev/null 2>&1
assert_exit 1 "T6e: readonly 拒绝 DROP" query "DROP TABLE users"

echo "--- T7: 高危语句拒绝 ---"
db use test-mysql-full > /dev/null 2>&1
assert_exit 1 "T7a: full 拒绝 CALL" query "CALL some_proc()"
assert_exit 1 "T7b: full 拒绝 LOAD DATA" query "LOAD DATA INFILE '/tmp/x' INTO TABLE users"
assert_exit 1 "T7c: full 拒绝 INTO OUTFILE" query "SELECT * FROM users INTO OUTFILE '/tmp/x'"
assert_exit 1 "T7d: full 拒绝 SET GLOBAL" query "SET GLOBAL max_connections=1000"
db use test-mysql > /dev/null 2>&1

echo "--- T8: MySQL 无 LIMIT 自动加 LIMIT 100 ---"
db query "SELECT * FROM users" > /dev/null 2>&1
if grep -qE "LIMIT 100" "$MOCK_DIR/engine.log"; then
    echo -e "${GREEN}PASS${NC} T8: 无 LIMIT 自动加 LIMIT 100"
    PASS=$((PASS+1))
else
    echo -e "${RED}FAIL${NC} T8: 未自动加 LIMIT 100"
    echo "  log: $(cat $MOCK_DIR/engine.log)"
    FAIL=$((FAIL+1))
    FAILED_TESTS+=("T8 LIMIT")
fi

echo "--- T9: MongoDB readonly 拒绝 insertOne ---"
db use test-mongo > /dev/null 2>&1
assert_exit 1 "T9: Mongo readonly 拒绝 insertOne" query "db.users.insertOne({name:'x'})"
assert_not_contains "col1" "T9: insertOne 未实际执行" query "db.users.insertOne({name:'x'})"

echo "--- T10: db test 连接失败报错 ---"
# engine mock 已经处理 config 中 pass=wrong 的情况
# 切换到 bad-mysql 然后测连接，整体应 exit=1
T10_OUT=$(db use bad-mysql && db test 2>&1)
T10_EXIT=$?
if [ $T10_EXIT -eq 1 ]; then
    echo -e "${GREEN}PASS${NC} T10: 连接失败退出码=1"
    PASS=$((PASS+1))
else
    echo -e "${RED}FAIL${NC} T10: 连接失败退出码 (expected=1, got=$T10_EXIT)"
    echo "  output: $T10_OUT"
    FAIL=$((FAIL+1))
    FAILED_TESTS+=("T10")
fi

# ============ 安全修复新增测试 ============
# T_semi*: 分号多语句绕过防护
# T_mongo_cmd*: MongoDB runCommand/adminCommand 绕过防护
# T_path1: export 路径穿越防护
# T_empty: 真正的无参数测试

echo "--- T_semi1: readonly 拒绝 SELECT 1; DELETE ---"
db use test-mysql > /dev/null 2>&1
: > "$MOCK_DIR/engine.log"
assert_exit 1 "T_semi1: readonly 拒绝 SELECT 1; DELETE" query "SELECT 1; DELETE FROM users"
# 验证 engine mock 未被调用（说明 SQL 在权限层被拦）
if [ ! -s "$MOCK_DIR/engine.log" ]; then
    echo -e "${GREEN}PASS${NC} T_semi1: SELECT 1; DELETE 未实际执行（mock log 为空）"
    PASS=$((PASS+1))
else
    echo -e "${RED}FAIL${NC} T_semi1: mock 被调用了，SQL 未被拦截"
    echo "  log: $(cat $MOCK_DIR/engine.log)"
    FAIL=$((FAIL+1))
    FAILED_TESTS+=("T_semi1 mock-untouched")
fi

echo "--- T_semi2: full 拒绝 DESCRIBE t; DROP ---"
db use test-mysql-full > /dev/null 2>&1
: > "$MOCK_DIR/engine.log"
assert_exit 1 "T_semi2: full 拒绝 DESCRIBE t; DROP" query "DESCRIBE t; DROP TABLE x"
if [ ! -s "$MOCK_DIR/engine.log" ]; then
    echo -e "${GREEN}PASS${NC} T_semi2: DESCRIBE t; DROP 未实际执行（mock log 为空）"
    PASS=$((PASS+1))
else
    echo -e "${RED}FAIL${NC} T_semi2: mock 被调用了，SQL 未被拦截"
    echo "  log: $(cat $MOCK_DIR/engine.log)"
    FAIL=$((FAIL+1))
    FAILED_TESTS+=("T_semi2 mock-untouched")
fi

echo "--- T_semi3: 合法单语句不含分号 → 通过 ---"
db use test-mysql > /dev/null 2>&1
: > "$MOCK_DIR/engine.log"
assert_exit 0 "T_semi3: 合法无分号 SELECT 通过" query "SELECT * FROM users WHERE name='test'"
# 验证 mock 真的被调用了（说明正常路径没误拦）
if [ -s "$MOCK_DIR/engine.log" ]; then
    echo -e "${GREEN}PASS${NC} T_semi3: 合法 SELECT 正常执行（mock 被调用）"
    PASS=$((PASS+1))
else
    echo -e "${RED}FAIL${NC} T_semi3: 合法 SELECT 被误拦（mock log 为空）"
    FAIL=$((FAIL+1))
    FAILED_TESTS+=("T_semi3 mock-called")
fi

echo "--- T_mongo_cmd1: readonly 拒绝 db.runCommand({delete:...}) ---"
db use test-mongo > /dev/null 2>&1
: > "$MOCK_DIR/engine.log"
assert_exit 1 "T_mongo_cmd1: readonly 拒绝 runCommand delete" query "db.runCommand({delete:'users',deletes:[{q:{},limit:0}]})"
if [ ! -s "$MOCK_DIR/engine.log" ]; then
    echo -e "${GREEN}PASS${NC} T_mongo_cmd1: runCommand delete 未实际执行（mock log 为空）"
    PASS=$((PASS+1))
else
    echo -e "${RED}FAIL${NC} T_mongo_cmd1: mock 被调用了，runCommand 未被拦截"
    FAIL=$((FAIL+1))
    FAILED_TESTS+=("T_mongo_cmd1 mock-untouched")
fi

echo "--- T_mongo_cmd2: readonly 拒绝 db.adminCommand({shutdown:1}) ---"
db use test-mongo > /dev/null 2>&1
: > "$MOCK_DIR/engine.log"
assert_exit 1 "T_mongo_cmd2: readonly 拒绝 adminCommand shutdown" query "db.adminCommand({shutdown:1})"
if [ ! -s "$MOCK_DIR/engine.log" ]; then
    echo -e "${GREEN}PASS${NC} T_mongo_cmd2: adminCommand shutdown 未实际执行（mock log 为空）"
    PASS=$((PASS+1))
else
    echo -e "${RED}FAIL${NC} T_mongo_cmd2: mock 被调用了，adminCommand 未被拦截"
    FAIL=$((FAIL+1))
    FAILED_TESTS+=("T_mongo_cmd2 mock-untouched")
fi

echo "--- T_mongo_cmd3: full 拒绝 db.runCommand({dropDatabase:1}) ---"
db use test-mongo-full > /dev/null 2>&1
: > "$MOCK_DIR/engine.log"
assert_exit 1 "T_mongo_cmd3: full 拒绝 runCommand dropDatabase" query "db.runCommand({dropDatabase:1})"
if [ ! -s "$MOCK_DIR/engine.log" ]; then
    echo -e "${GREEN}PASS${NC} T_mongo_cmd3: runCommand dropDatabase 未实际执行（mock log 为空）"
    PASS=$((PASS+1))
else
    echo -e "${RED}FAIL${NC} T_mongo_cmd3: mock 被调用了，dropDatabase 未被拦截"
    FAIL=$((FAIL+1))
    FAILED_TESTS+=("T_mongo_cmd3 mock-untouched")
fi

echo "--- T_path1: export 路径穿越防护 ---"
db use test-mysql > /dev/null 2>&1
EXPORT_DIR="$HOME/.claude/skills/db-connect/exports"
# 清理旧的 evil_ 文件
rm -f "$EXPORT_DIR"/evil_*.csv 2>/dev/null
T_PATH_OUT=$(db export "../evil" 2>&1)
T_PATH_EXIT=$?
# 找新建的 evil_ 文件并校验（关闭 nounset 避免空变量报错）
set +u
EVIL_FILE=$(ls "$EXPORT_DIR"/evil_*.csv 2>/dev/null | head -1)
EVIL_BASENAME=$(basename "$EVIL_FILE" 2>/dev/null)
if [ -n "$EVIL_BASENAME" ] && ! echo "$EVIL_BASENAME" | grep -qE '\.\.'; then
    echo -e "${GREEN}PASS${NC} T_path1: export 路径穿越被拦（文件名: $EVIL_BASENAME）"
    PASS=$((PASS+1))
else
    echo -e "${RED}FAIL${NC} T_path1: export 路径穿越未被拦（exit=$T_PATH_EXIT, file=$EVIL_FILE, basename=$EVIL_BASENAME）"
    echo "  output: $T_PATH_OUT"
    FAIL=$((FAIL+1))
    FAILED_TESTS+=("T_path1")
fi
set -u

echo "--- T_export_perm: readonly 模式 export --where 注入 INTO OUTFILE 应被拒 ---"
db use test-mysql > /dev/null 2>&1
: > "$MOCK_DIR/engine.log"
T_EXPORT_OUT=$(db export users --where "1 UNION SELECT password INTO OUTFILE '/tmp/x' FROM users" 2>&1)
T_EXPORT_EXIT=$?
if [ "$T_EXPORT_EXIT" -eq 1 ] && [ ! -s "$MOCK_DIR/engine.log" ]; then
    echo -e "${GREEN}PASS${NC} T_export_perm: readonly export --where 含 INTO OUTFILE 被拒"
    PASS=$((PASS+1))
else
    echo -e "${RED}FAIL${NC} T_export_perm: readonly export --where 绕过权限 (exit=$T_EXPORT_EXIT)"
    echo "  output: $T_EXPORT_OUT"
    echo "  engine log: $(cat $MOCK_DIR/engine.log)"
    FAIL=$((FAIL+1))
    FAILED_TESTS+=("T_export_perm")
fi

echo "--- T_empty: 真正无参数调用 ---"
T_EMPTY_OUT=$(db 2>&1)
T_EMPTY_EXIT=$?
if [ "$T_EMPTY_EXIT" = "1" ] && echo "$T_EMPTY_OUT" | grep -qiE "(用法|usage)"; then
    echo -e "${GREEN}PASS${NC} T_empty: 无参数输出 usage 且 exit=1"
    PASS=$((PASS+1))
else
    echo -e "${RED}FAIL${NC} T_empty: 无参数行为不对（exit=$T_EMPTY_EXIT）"
    echo "  output: $T_EMPTY_OUT"
    FAIL=$((FAIL+1))
    FAILED_TESTS+=("T_empty")
fi

# ============ 总结 ============
echo ""
echo "================================"
echo -e "PASS: ${GREEN}$PASS${NC}  FAIL: ${RED}$FAIL${NC}"
echo "================================"
if [ $FAIL -gt 0 ]; then
    echo -e "${RED}FAILED TESTS:${NC}"
    for t in "${FAILED_TESTS[@]}"; do
        echo "  - $t"
    done
    exit 1
fi
exit 0
