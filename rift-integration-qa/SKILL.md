---
name: rift-integration-qa
description: Unified QA routing hub — detects testing scenario and dispatches to the right skill/workflow. Covers TDD, contract verification, fake-green detection, multi-layer consistency, real-device regression, deploy verification, and code review.
argument-hint: "[tdd|verify|contract|regression|deploy-check|fake-green|review|auto] [--scope <area>]"
level: 3
---

# rift-integration-qa — QA Hub · 统一质量保障路由

> 🔗 **rift 家族**：`/rift-dispatch`（派发）· `/rift-free`（免费通道）· **`/rift-integration-qa`（测试验收）**

> 触发词：`qa`、`测试`、`验证`、`集成验证`、`三层验证`、`契约验证`、`假绿`、`真机回归`、`deploy check`、`code review`、`质量检查`
>
> 这是所有 QA 活动的**统一入口**。根据场景自动路由到对应的 skill 或内置流程。

---

## 0. 场景路由表

收到 QA 相关请求时，先判断场景，再路由：

| 场景 | 关键词 | 路由到 | 说明 |
|------|--------|--------|------|
| 写新功能/修 bug | `实现`、`修复`、`feature`、`bugfix` | **§1 TDD** → `test-driven-development` skill | 先写失败测试再实现 |
| 单测/构建/lint 不过 | `测试不过`、`build 失败`、`修到过` | **§2 自动修复** → `ultraqa` skill | 循环：跑测试→分析→修→重跑 |
| 验证 DB↔API↔FE 一致 | `三层验证`、`字段映射`、`数据对不上` | **§3 三层一一对应** | 本 skill 内置 |
| API 契约检查 | `契约`、`contract`、`类型不匹配` | **§4 契约验证** | 本 skill 内置 |
| 怀疑单测假绿 | `假绿`、`mock 不对`、`测试过了但功能不对` | **§5 假绿检测** | 本 skill 内置 |
| 真机测试 | `真机`、`regression`、`APK 装上试试` | **§6 真机回归** | 本 skill 内置 |
| 线上产物验证 | `deploy`、`线上版本`、`CDN`、`下载下来不对` | **§7 部署后验证** | 本 skill 内置 |
| 代码审查 | `review`、`审查`、`交叉检查` | **§8 代码审查** → `agent-review-protocol` skill | 三 agent 审查流水线 |
| 截图视觉对比 | `截图`、`UI 不一样`、`视觉验证` | **§9 视觉验证** → `visual-verdict` skill | 截图 vs 参考图 |
| 发布打包 | `发布`、`打包`、`release`、`上线` | **§10 发布** → 项目级 `release-and-deploy` skill | 构建+签名+上传+CDN |
| 不确定 / 全面检查 | `auto`、`全面验证`、`上线前检查` | **§11 全量流程** | 按顺序串联多个模式 |

### 路由规则

1. **明确场景** → 直接跳到对应章节
2. **混合场景** → 按表中从上到下的顺序依次执行
3. **`auto` 模式** → 执行 §11 全量流程
4. **有项目级 skill** → 优先用项目级（如 `release-and-deploy`），本 skill 提供通用方法论兜底

---

## 1. TDD（路由到 `test-driven-development` skill）

**何时用：** 写新功能、修 bug、重构——任何要改生产代码的时候。

**加载方式：** 通知 agent 加载 `test-driven-development` skill，执行 RED→GREEN→REFACTOR。

**核心规则：**
- 没有失败测试就不写生产代码
- Mock 数据必须来自真实 API 响应（防 §5 假绿）
- 枚举值必须对齐后端，不能自造

---

## 2. 自动修复循环（路由到 `ultraqa` skill）

**何时用：** 测试/构建/lint/类型检查不过，需要自动循环修复。

**加载方式：** `/ultraqa --tests` 或 `/ultraqa --build` 或 `/ultraqa --typecheck`

最多 5 轮：跑 QA → 分析失败 → 修复 → 重跑。

---

## 3. 三层一一对应验证

**何时用：** 确认前端展示的数据与数据库一致，排查"页面显示不对"类问题。

### 链路

```
数据库列 → API 响应字段 → 前端渲染
```

### 步骤

1. **查 DB schema** — `information_schema.COLUMNS` 确认列存在
2. **查 DB 数据** — `SELECT`（只读）看实际值
3. **调 API** — curl + token，看响应字段和值
4. **对照前端** — DTO 类型定义 + 组件渲染逻辑
5. **输出映射表**

### 输出格式

```markdown
| DB 列 | 表 | API 字段 | FE 类型 | 组件 | 一致性 |
|-------|---|---------|--------|------|--------|
| ws_payment_url | workorderset | portalUrl | Step1DTO.portalUrl | Page1:35 | ✅ |
```

### 常见陷阱

- **同名表跨库** — 同一张表可能在多个 DB 中存在，后端读的不一定是你查的那个
- **同表多字段** — 如 `WT_LeaseFromDate` vs `Original_Lease_From_Date`，后端可能读任意一个，必须通过 API 实测确认
- **后端预格式化** — 金额带 `$` 前缀，前端再加 `$` 会变 `$$`
- **JSON payload** — 如 `onboard_steps.payload`，需查实际数据才知结构
- **时间戳精度** — 毫秒 vs 秒 vs 日期字符串

---

## 4. 契约验证

**何时用：** 怀疑前后端类型不一致，或刚对接新接口。

### 方法

| 工具 | 说明 |
|------|------|
| curl 实测 | 调真实 API 看响应结构 |
| 静态对照 | Swagger ↔ FE 类型文件逐字段比对 |
| Schemathesis | 基于 spec 自动 fuzz（⛔ 仅安全 GET） |
| openapi-typescript | 从 spec 生成 TS 类型 |

### ⛔ Schemathesis 安全规则

- 绝不全量扫描
- 绝不扫 sync/trigger/webhook 类接口
- 逐条确认端点无副作用
- **GET ≠ 安全**（某些 GET 会触发邮件/同步等副作用）

### 输出格式

```markdown
| API 字段 | Swagger 类型 | 实际响应 | FE 类型 | 一致 |
|---------|-------------|--------|--------|------|
| stepStatus | 未定义(!) | string | CardState enum | ⚠️ |
```

---

## 5. 假绿检测

**何时用：** 单测全过但功能不对，或怀疑 mock 数据偏离真实数据。

### 步骤

1. 列出测试文件中的 mock/fixture 数据
2. 对每个 mock，调真实 API 获取对应响应
3. 逐字段比对 mock vs 真实响应
4. 标记偏离项（枚举值、字段名、结构、格式）
5. 修正 mock 后重跑测试——**测试失败了 = 之前是假绿**

### 高危模式

| 模式 | 特征 | 检测 |
|------|------|------|
| 枚举自造 | mock `DONE/TODO`，后端 `Done/To do` | grep mock 枚举对照 API |
| 结构偏离 | mock 是 string，后端返回 object | 对比类型 |
| 缺失字段 | mock 省略关键字段 | 对比字段数 |
| 预格式化忽略 | mock 用裸值 `5500`，后端 `$5,500.00` | 检查格式 |

### 大规模排查（状态矩阵深扫）

多 agent 并行：
1. 提取后端状态机枚举
2. 查 DB 实际状态值分布
3. 提取前端 mock 枚举值
4. 对照 PRD/AC 验收条件
5. 交叉比对，输出矩阵

---

## 6. 真机回归

**何时用：** 发版前或修完 bug 后，在真机上验证。

### 环境

```bash
# Android
adb connect <ip>:<port>    # WiFi
adb install -r <apk>

# iOS
xcrun devicectl list devices
xcrun devicectl device install app --device <UDID> <app-path>
```

### 通用回归清单

```markdown
- [ ] 核心 happy path 完整走通
- [ ] 表单必填校验 + 提交数据正确
- [ ] 文件上传（拍照/相册/文件类型）
- [ ] 网络异常（断网/超时/401）
- [ ] 权限控制（不同角色的差异）
- [ ] 跨步骤状态保持
- [ ] 杀进程恢复
- [ ] 深链/外部跳转
```

每项记录 PASS/FAIL + 截图/日志。FAIL 项记 bug：严重性、复现步骤、期望 vs 实际。

---

## 7. 部署后验证

**何时用：** 发布上线后，确认线上产物与预期一致。

### Android

```bash
curl -s -o /tmp/deployed.apk '<url>'
aapt dump badging /tmp/deployed.apk | grep -E 'versionCode|versionName|application-label:'
keytool -printcert -jarfile /tmp/deployed.apk | head -10
# 解压检查内部 JS
unzip -o -q /tmp/deployed.apk -d /tmp/check
grep -r '<test-env-url>' /tmp/check/assets/ && echo "⛔ 测试环境残留"
```

### iOS

```bash
/usr/libexec/PlistBuddy -c "Print CFBundleDisplayName" <Info.plist>
/usr/libexec/PlistBuddy -c "Print CFBundleShortVersionString" <Info.plist>
```

### CDN 缓存

```bash
curl -sI '<url>' | grep -iE 'cf-cache-status|content-length|etag'
# HIT = 缓存命中（可能旧文件）→ 换 ?v= 参数
# MISS = 回源（新文件）→ 对比 content-length 确认
```

---

## 8. 代码审查（路由到 `agent-review-protocol` skill）

**何时用：** 完成实现后，交叉检查代码质量。

**加载方式：** 加载 `agent-review-protocol` 或 `/code-review`

**三角色流水线：** Implementer → Spec Reviewer → Quality Reviewer

---

## 9. 视觉验证（路由到 `visual-verdict` skill）

**何时用：** UI 改动后，需要截图对比验证视觉正确性。

**加载方式：** 加载 `visual-verdict` skill

---

## 10. 发布打包（路由到项目级 skill）

**何时用：** 需要构建、签名、上传、部署。

**加载方式：** 加载项目级 `release-and-deploy` skill（如有），否则按通用流程：

```
npm run build → cap sync → 平台构建 → 签名 → 上传 → 部署后验证(§7)
```

---

## 11. 全量流程（auto 模式）

上线前全面检查，按顺序执行：

```
1. 假绿检测(§5) — 确认单测可信
2. 单测/类型检查 — npx vitest run && npx vue-tsc -b
3. 契约验证(§4) — API spec ↔ FE 类型 ↔ 实际响应
4. 三层验证(§3) — 核心字段 DB→API→FE 链路
5. 构建验证 — npm run build + grep 环境地址残留
6. 真机回归(§6) — 核心路径 + 回归清单
7. 代码审查(§8) — 跨模型 review
8. 发布(§10) — 构建+签名+上传
9. 部署后验证(§7) — 线上产物一致性
```

任何步骤失败则**停止**，修复后从失败步骤重新开始。

---

## 12. 验证报告模板

```markdown
## QA Report — <日期>

**范围**: <描述>
**模式**: tdd / verify / contract / regression / deploy-check / fake-green / auto

### 结果
- ✅ 通过: N 项
- ⚠️ 待确认: N 项
- ❌ 失败: N 项

### 发现
| # | 类型 | 描述 | 严重性 | 状态 |
|---|------|------|--------|------|

### 下一步
1. ...
```
