---
name: rift-mfa
description: "通用 TOTP 动态码能力层：从本地种子文件算 RFC 6238 六位码，供任何需要 MFA 的场景（JumpServer / Jenkins / CRM / AWS / 任意 2FA）取码。种子只在本地、不进 git、不绑定任何具体站点。Triggers: 'mfa', 'MFA', '动态码', '6位码', '验证码', 'TOTP', 'totp', 'rift-mfa', 'OTP', '二步验证'."
user-invocable: true
argument-hint: "<list|<条目名|关键字>> [--ahead N]"
---

# rift-mfa · 通用 TOTP 动态码能力层

> 🔗 rift 家族协议能力层：`/rift-dispatch`（派发）· `/rift-browser`（浏览器）· `/rift-mail-triage`（邮件）· **`/rift-mfa`（动态码）**

任何 agent 需要 MFA 六位码就调它——JumpServer、Jenkins、CRM、AWS 或任何 2FA 场景，传条目名或关键字即可。
本 skill 只做一件事：读本地种子文件 → 按 RFC 6238 算当前六位码 → stdout 只输出码。
不绑定具体站点、不含任何站点登录逻辑、不打印种子内容。

## 0. 硬性铁律（违反即泄露凭据）

1. **种子文件绝不进 git、绝不跨机同步**。种子放 `~/.local/share/rift-mfa/seeds.json`（文件 `0600`，目录 `0700`）。源仓 `.gitignore` 已显式排除；换机自行导入，不通过 Syncthing/git 传。
2. **读种子前必须检查权限 `0600`**。不是 `0600` 一律拒绝（退出码 `4`），不降级读取、不自动放宽或收紧权限。
3. **全程不打印种子 / otpauth URI 内容**。`list` 只列条目名（key），不显 value；诊断信息一律走 stderr；stdout 只有六位码或条目名。
4. **不内嵌任何站点逻辑**。取码是通用能力；登录 JumpServer/Jenkins 等是调用方的事，不要在本 skill 里拼登录脚本。
5. **不要把码回显到公开日志/报告**。六位码是短时有效凭据，用完即弃，不写进提交、issue、共享文档。

## 1. 用法

脚本：`rift-mfa/scripts/rift-mfa`（纯 Python 标准库 `hmac`/`hashlib`/`base64`/`time`/`urllib`，无需装任何库）。

```bash
S=~/AgentWorkspace/projects/skills/agent-hub-skills/rift-mfa/scripts/rift-mfa

# 列出所有条目名（只列 key，绝不显种子）
python3 "$S" list

# 取某个条目的当前六位码（stdout 只有 6 位数字）
python3 "$S" <条目名或唯一关键字>

# 窗口剩 ≤N 秒时提前进入下一个 30s 窗口（防提交时刚好翻窗）
python3 "$S" <条目名> --ahead 5
```

- 精确条目名优先；否则按子串匹配，唯一命中才返回，多个命中报「不唯一」（退出码 `5`）。
- 标准参数：30s 步长、SHA1、6 位（RFC 6238 默认）；一般无需改动。

## 2. 退出码

| 码 | 含义 | 处理 |
|---|---|---|
| 0 | 成功（stdout 为 6 位码或条目列表） | 直接用 |
| 2 | 参数错误 | 查用法 |
| 3 | 无此条目 | `list` 看有哪些 key |
| 4 | 种子文件缺失或权限不安全（非 0600） | 就地配种子并 `chmod 600`（见 §3） |
| 5 | 关键字不唯一 | 用更长的关键字或精确条目名 |
| 6 | 其他失败（种子内容非法 / 计算失败） | 检查种子格式 |

## 3. 换机导入种子（种子只在本地，不跨机同步）

1. 建目录并设权限：`mkdir -p ~/.local/share/rift-mfa && chmod 700 ~/.local/share/rift-mfa`
2. 写种子文件 `~/.local/share/rift-mfa/seeds.json`，格式（value 可为裸 base32 或 `otpauth://` URI）：
   ```json
   { "jumphost": "<BASE32 或 otpauth://...>", "jenkins": "<BASE32 或 otpauth://...>" }
   ```
3. 设权限：`chmod 600 ~/.local/share/rift-mfa/seeds.json`（非 0600 会被拒绝）。
4. 验证：`python3 "$S" list`（只列 jumphost/jenkins 等 key）、`python3 "$S" jumphost`（返回 6 位码）。
5. 换机时**手动**重复以上步骤；不要把 seeds.json 放进仓库或同步目录。

测试/隔离：环境变量 `RIFT_MFA_SEEDS` 指向临时假种子、`RIFT_MFA_NOW` 固定时间（Unix 秒），用于 TDD 与端到端验证，不碰真实种子。

## 4. 算法与验证

RFC 6238：counter = floor(now/30)，HMAC-SHA1(key=base32decode(secret), msg=counter 的 8 字节大端)，取 digest 末字节低 4 位作偏移，截取 4 字节 & 0x7fffffff，取模 10^6 补足 6 位。`--ahead N` 仅在窗口剩余 ≤N 秒时 counter+1。
测试用 RFC 6238 Appendix B 官方向量（seed=`12345678901234567890`）逐点校验，见 `scripts/tests/test_rift_mfa.py`。
