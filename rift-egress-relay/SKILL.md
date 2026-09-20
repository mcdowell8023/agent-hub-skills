---
name: rift-egress-relay
description: 本机到某个特定端点的网络被拦截时，借道另一台联网机器做 egress 中继，让原有工具链不改代码继续工作。含诊断隔离方法、SSH SOCKS 隧道、HTTP CONNECT 垫片、新中继机上线步骤与踩坑清单。
---

# Rift Egress Relay — 借道其他机器打通被封的网络出口

本机到**某个特定端点**的连接被网络层拦截时，用一台能到达该端点的机器做 TCP 中继，
让原有工具链（远程执行脚本、`aws` CLI 等）**不改代码**继续工作。

⭐ **凭据与私钥全程不离开本机**——中继机只转发 TCP 字节流，不持有任何密钥、不需要装业务工具。

## 1. 先隔离：确认真的是端点级拦截

🔴 **必须用【认证过的真实 API 调用】做对照，⛔ 不要用 curl 打裸 root path。**

实测教训：`curl https://<endpoint>/` 打未认证根路径时，**正常端点和异常端点都返回 5s 超时**，
信号被完全糊掉，差点据此误判成「整片服务都不通」。未认证根路径的行为和真实 API 调用不是一回事。

✅ 三端点对照（以 AWS 为例，其他云换成等价调用）：

| 调用 | 正常表现 | 作用 |
|---|---|---|
| `aws sts get-caller-identity` | ~1s 返回身份 | 凭据 + 基础连通性基线 |
| `aws ssm describe-instance-information` | ~1s 正常返回 | 同区域另一端点对照 |
| `aws ec2-instance-connect send-ssh-public-key` | 挂起十几秒后 `Connection was closed` | ← 被封的那个 |

**判据**：前两个正常、第三个在 TLS 层失败 ⇒ 端点级拦截，适用本 skill。
三个都失败 ⇒ 不是端点问题，⛔ 别往下走。

典型报错形态——TCP 连得上，TLS 在 Client Hello 之后被重置：
`SSL: UNEXPECTED_EOF_WHILE_READING` / `SSL_ERROR_SYSCALL` /
`Connection was closed before we received a valid response`。

⚠️ 具体是哪一层拦的（企业防火墙 / 运营商 / 目标侧），客户端侧看不出来，⛔ 不要下断言。
⛔ 也别误判成凭据过期或权限不足——那两类报错形态完全不同（`MFA_EXPIRED` / `AccessDenied` + ARN）。

## 2. 中继机的必要条件（很低）

| 条件 | 说明 |
|---|---|
| ✅ sshd 可密钥登录 | 仅此而已 |
| ✅ `AllowTcpForwarding` | **OpenSSH 默认即 yes**，通常不需要改任何配置 |
| ✅ 它自己能到达目标端点 | 上线前必须先验证，见 §4 |
| ⛔ **不需要**装云 CLI / python / 任何业务工具 | 中继只转发字节流；垫片跑在本机 |

⇒ 任何一台能 SSH 进去、且出口网络正常的机器都能当中继。

⚠️ **节点地址不要写进本 skill 或脚本**——记到你自己的基础设施清单里（本仓不收录私有拓扑），
脚本一律用 `RELAY_HOST` 环境变量注入。

⚠️ 家用机通常**不常开**：用前先确认在线，离线就请机主开机，
⛔ 不要假设它在线，也 ⛔ 不要因为它当前离线就断言中继方案不可行。

## 3. 建立通道

### 🔴 为什么需要两层

`ssh -D` 提供的是 **SOCKS5**，而 🔴 **AWS CLI v2 不支持 socks5**：
填 `HTTPS_PROXY=socks5h://127.0.0.1:1080` 会被 botocore 拼成
`http://socks5h://127.0.0.1:1080`，报 `Failed to connect to proxy URL`。
botocore 只认 **HTTP CONNECT** 代理。

⇒ 中间加一层 CONNECT→SOCKS 垫片（跑在**本机**，不在中继机上）：

```
本机工具 --HTTPS_PROXY--> CONNECT代理:18888 --> SOCKS:1080 --ssh--> 中继机 --> 目标端点
```

### 启动 / 关闭（幂等，可反复开关）

```bash
export RELAY_HOST='<user>@<relay-host>'      # ⛔ 不写死在脚本里

bash scripts/relay-up.sh      # 起：SOCKS 隧道（自动重连）+ CONNECT 垫片
bash scripts/relay-down.sh    # 关：按正确顺序停掉，并验证端口确实释放
```

`relay-up.sh` **幂等**：已经起着时不重复启动，只打印现有 pid——所以怀疑掉线时直接重跑即可。
两个进程用 `nohup` 脱离当前 shell，调用结束后继续存活；pid 文件与日志在
`${TMPDIR}/rift-egress-relay/`（可用 `RIFT_RELAY_RUN_DIR` 覆盖）。

### 使用

```bash
export HTTPS_PROXY=http://127.0.0.1:18888
aws sts get-caller-identity --profile <profile> --region <region>   # 自检：返回身份即全链路通
```

⭐ 关键收益：**既有远程执行脚本一行代码都不用改**，导出这一个环境变量即恢复工作。

### ⭐ 更精准：只代理真正被封的那一个调用

被封的常常只是**一个** API 端点，其余链路本机直连就是通的。
以 AWS SSM + EC2 Instance Connect 为例：SSH-over-SSM 隧道本机直连正常
（未注入公钥时返回 `Permission denied (publickey)` 就是证据——已经打到 sshd，只差认证），
只有 EIC 公钥注入被封。那就只给那一条命令加前缀：

```bash
HTTPS_PROXY=http://127.0.0.1:18888 aws ec2-instance-connect send-ssh-public-key \
      --instance-id "$IID" --instance-os-user "$OSUSER" \
      --ssh-public-key "file://$SSH_KEY.pub" --profile "$PROFILE" --region "$REGION" \
  && ssh -i "$SSH_KEY" "$OSUSER@$IID" '<命令>'
```

🔴 EIC 注入的公钥**只有 60 秒有效**，注入与 ssh 必须用 `&&` 串在同一条命令里。
⭐ 这样凭据和 SSH 私钥完全不经过中继机，且非代理链路保持原有速度。

## 4. 给一台新机器开通中继

### 第一步：先验证它能不能到达目标（⛔ 别先配 SSH）

```bash
ssh <user>@<newhost> 'curl -sS -o /dev/null -w "%{http_code}\n" --max-time 12 https://<目标端点>/'
```

拿到**任意** HTTP 状态码（403/404 都算）即说明 TLS 握手正常。⛔ 别要求必须 200。

⚠️ **换中继机之前必须做这一步**：同一 tailnet 里的另一台机器完全可能和本机撞同一堵墙。
实测遇到过——备用服务器对目标端点报**与本机一模一样**的 TLS 错误，白配一遍 SSH。

### 🔴 第二步：先想清楚 sshd 挂了你怎么进去

SSH 往往是中继机的**唯一**入口，sshd 一停就是鸡生蛋问题——**agent 没有任何办法自己修**。
⇒ 开通中继机时必须同时确认**一条不依赖 SSH 的带外通道**，且它要**独立于主传输层**
（带外通道如果也走同一个 VPN / 隧道，那就不算独立）。

常见带外通道：第三方远程控制软件（走厂商自有中继）、IPMI / iDRAC、云厂商串口控制台。
⚠️ 别指望这两个兜底：**WinRM 默认不开放**；**Tailscale SSH 的服务端不支持 Windows**。

⚠️ 带外通道**自身**也要能在无人登录时可用：确认它是**系统服务**（开机自启、session 0），
而不是登录后才拉起的用户态程序——否则无人值守重启后它自己也不在。

**连不上时先分诊，⛔ 不要盲目重试：**

| 判据 | 结论 | 谁能处理 |
|---|---|---|
| 中继机在网络层就看不见 | 关机 / 休眠 | 需要人去开机 |
| 在线但 22 端口不通 | 机器活着，**sshd 没跑** | ⛔ agent 无解，必须走带外通道 |
| 22 通但认证失败 | 公钥问题 | agent 可自查，见下方 Windows 部分 |

⛔ 把带外通道的**确切操作步骤**写进你自己的基础设施清单（⛔ 不要写进本仓），
让 agent 在失败时直接告诉用户点哪里、敲哪条命令，而不是自己试一通。

### Windows 中继机

`scripts/setup-relay-windows.ps1`（**管理员身份**运行）：
装 OpenSSH Server → 起服务并设自启 → 放行 22 → 写入公钥（只认公钥，不碰开机密码）。

🔴 **`Add-WindowsCapability` 会假成功**：返回 `RestartNeeded: False`，但真实状态是
`InstallPending`，sshd 服务根本不存在。**必须重启**后 `State` 才变 `Installed`。

⚠️ **管理员账号的公钥路径不一样**：不在 `~/.ssh/authorized_keys`，而在
`C:\ProgramData\ssh\administrators_authorized_keys`（由 sshd_config 的
`Match Group administrators` 指定），且权限必须收紧到仅 `SYSTEM` + `Administrators`，
否则 sshd 会**静默拒绝**该文件。

### Linux / macOS 中继机

装好 sshd、放公钥即可，`AllowTcpForwarding` 默认 yes，不用动配置。

## 5. 踩坑清单

| 坑 | 表现 | 处理 |
|---|---|---|
| 🔴 AWS CLI v2 不支持 socks5 | `Failed to connect to proxy URL: "http://socks5h://..."` | 必须加 CONNECT 垫片，⛔ 别再试 socks 写法 |
| 🔴 中继链路空闲即断 | `Timeout, server ... not responding`，ssh 退出 255 | 用 `keep_socks.sh` 重启循环；⛔ 别用 `ssh -f` 后台化（与 ProxyCommand 有交互问题） |
| ⚠️ 中继机休眠/关机 | 隧道断且重连一直失败 | 先确认它在线，离线请机主开机 |
| ⚠️ Windows 防火墙默认拦入站 | 在中继机上开监听端口连不上 | ⇒ 走 SSH 隧道复用已放行的 22，⛔ 不要为此新开端口 |
| ⚠️ Windows 控制台 GBK | PowerShell 中文输出乱码 | 脚本首行 `[Console]::OutputEncoding=[Text.Encoding]::UTF8`；用 `powershell -EncodedCommand <base64(UTF-16LE)>` 规避引号地狱 |
| ⚠️ `cmd` 不认 `;` 分隔符 | `hostname; whoami` 报 hostname 参数错误 | 用 `powershell -Command` 或 `-EncodedCommand` |
| ⛔ `nc -z` 验隧道必假阳性 | 本地 listener 无条件 accept，远端不通也显示成功 | 用协议级探针或真实 API 调用验通 |

## 6. 关闭（⚠️ 网络恢复后必须做）

```bash
bash scripts/relay-down.sh
unset HTTPS_PROXY          # ⚠️ 脚本管不到你当前 shell 里的变量
```

### 🔴 为什么不能随手 kill

- **顺序**：必须**先杀守护循环，再杀 ssh 隧道**。反过来做，守护会在 2 秒后把隧道重新拉起来，
  表现成「怎么都关不掉」。
- **定位方式**：⛔ 不要用 `pkill -f` 这类全局模式——它按命令行匹配，可能误杀无关进程。
  `relay-down.sh` 优先用 pid 文件，退化时才按脚本名定位，且**每个 PID 在发信号前都会打印出来**。
- **判据**：以「两个端口都已释放」作为成功判据并据此设退出码。
  端口没释放 ⇒ 下次 `relay-up.sh` 会因 `EADDRINUSE` 起不来。

### 关掉之后还能再起来吗

能，且已实测：`relay-down` → 两端口释放 → `relay-up` → 端到端调用恢复，来回两轮均通过。

- `relay-up.sh` **不依赖上次的残留状态**：靠「端口是否在监听」判断死活，不信任可能过期的 pid 文件
- `relay-down.sh` 退出前清掉 pid 文件，不留污染
- ⚠️ 唯一的外部前提是**中继机得开着**。它关机/休眠时 `relay-up.sh` 会等待后超时退出、
  提示去看 `socks.log`，⛔ 不会静默假装成功

## 相关

- `rift-dispatch` —— 任务派发；网络受限时常与本 skill 组合使用
- 节点地址、目标端点等私有拓扑请记在你自己的基础设施清单中，⛔ 不要提交到本仓
