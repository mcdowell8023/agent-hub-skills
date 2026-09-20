# 在 Windows 中继机上以【管理员身份】运行
#   powershell -ExecutionPolicy Bypass -File setup-relay-windows.ps1 -PublicKey "ssh-ed25519 AAAA... you@host"
#
# 作用：开启 OpenSSH Server + 放行 22 + 写入公钥（只认公钥，不设密码、不碰开机密码）
# 建议只在私有网络（如 Tailscale/WireGuard 网段）内可达，不要暴露到公网。

param(
    [Parameter(Mandatory = $true)]
    [string]$PublicKey
)

$ErrorActionPreference = "Stop"
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

# 1) 安装 OpenSSH Server 组件
$cap = Get-WindowsCapability -Online -Name OpenSSH.Server~~~~0.0.1.0
if ($cap.State -ne "Installed") {
    Write-Host "安装 OpenSSH Server..."
    Add-WindowsCapability -Online -Name OpenSSH.Server~~~~0.0.1.0 | Out-Null
    $cap = Get-WindowsCapability -Online -Name OpenSSH.Server~~~~0.0.1.0
    # 🔴 关键：此处可能是 InstallPending，即使返回 RestartNeeded:False 也必须重启
    if ($cap.State -ne "Installed") {
        Write-Warning "当前状态: $($cap.State) —— 必须【重启】后本脚本才能继续，重启后请重跑一次。"
        exit 1
    }
} else {
    Write-Host "OpenSSH Server 已安装"
}

# 2) 启动服务并设为开机自启
Start-Service sshd
Set-Service -Name sshd -StartupType Automatic
Write-Host "sshd 服务状态: $((Get-Service sshd).Status)"

# 3) 确认防火墙放行 22
if (-not (Get-NetFirewallRule -Name "OpenSSH-Server-In-TCP" -ErrorAction SilentlyContinue)) {
    New-NetFirewallRule -Name "OpenSSH-Server-In-TCP" -DisplayName "OpenSSH Server (sshd)" `
        -Enabled True -Direction Inbound -Protocol TCP -Action Allow -LocalPort 22 | Out-Null
    Write-Host "已创建防火墙规则放行 22"
} else {
    Write-Host "防火墙规则已存在"
}

# 4) 写入公钥
$isAdmin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole(
    [Security.Principal.WindowsBuiltInRole]::Administrator)

if ($isAdmin) {
    # ⚠️ 管理员账号必须用这个特殊路径，且权限要收紧，否则 sshd 静默拒绝该文件
    $authFile = "C:\ProgramData\ssh\administrators_authorized_keys"
    Add-Content -Force -Path $authFile -Value $PublicKey
    icacls $authFile /inheritance:r | Out-Null
    icacls $authFile /grant "Administrators:F" | Out-Null
    icacls $authFile /grant "SYSTEM:F" | Out-Null
    Write-Host "已写入 $authFile（管理员账号路径）"
} else {
    $sshDir = "$HOME\.ssh"
    if (-not (Test-Path $sshDir)) { New-Item -ItemType Directory -Path $sshDir | Out-Null }
    Add-Content -Force -Path "$sshDir\authorized_keys" -Value $PublicKey
    Write-Host "已写入 $sshDir\authorized_keys（普通账号路径）"
}

Write-Host ""
Write-Host "=== 完成 ==="
Write-Host "当前账号: $env:USERNAME  (管理员: $isAdmin)"
Write-Host "现在可以从对端: ssh $env:USERNAME@<本机私有网络地址>"
