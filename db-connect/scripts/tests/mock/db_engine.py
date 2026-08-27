#!/usr/bin/env bash
echo "ENGINE_ARGS: $*" >> "${MOCK_DIR:-.}/engine.log"
action="$1"; shift
config="$1"; shift

# JMS transport mode
if echo "$config" | grep -q '"transport": "jms_exec"\|"transport":"jms_exec"'; then
    # Check JMS password: env var first, then credentials.md
    if [ -z "${JMS_PASSWORD:-}" ]; then
        CRED_FOUND=false
        for CRED_FILE in "$HOME/.ai/rules/credentials.md" "$HOME/wb/.ai/rules/credentials.md"; do
            if [ -f "$CRED_FILE" ] && grep -q "1.5.*JumpServer\|JumpServer.*堡垒机" "$CRED_FILE" 2>/dev/null; then
                CRED_FOUND=true
                break
            fi
        done
        if [ "$CRED_FOUND" != "true" ]; then
            echo "错误: JMS 密码未配置。设置环境变量 JMS_PASSWORD 或在 credentials.md §1.5 配置" >&2
            exit 1
        fi
    fi
    if [ "$action" = "connect" ]; then
        exit 0
    fi
    if [ "$action" = "export" ]; then
        echo "id,name"
        echo "1,test"
        exit 0
    fi
    # Default: tab-separated mock result (simulates parsed WS JSON output)
    echo -e "col1\tcol2"
    echo -e "v1\tv2"
    exit 0
fi

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
