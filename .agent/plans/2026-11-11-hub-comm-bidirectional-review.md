# 计划复审：Hub → Mac 双向 Paseo 注册与派发收口

## 复审结论

本版计划无阻断项，可按文档顺序实施。

## 核对结果

1. **RED 真实且可验收**：保留了 `ff4a17ad-74b8-4074-993f-29057bc7a40e` 当时“`list_hosts` 为空/没有 route/要求人工复制 A、B、C”的原始失败表现，并与后续 `ROUTE_E2E_PASS` 的人工修复证据对应。
2. **变更边界清晰**：skill 源码只允许改 `hub-comm/SKILL.md`；`rift-remote-exec` 只同步既有内容，不修改源码。
3. **路由流程闭环**：daemon/endpoint 检查 → registry 查询/缺失时注册 → `host inspect`/`list_hosts` 双重复查 → `list_workspaces` → `create_agent` → child serverId/workspace/精确回执三项验收，无人工转贴缺口。
4. **白名单完整**：只有 `.claude` 与 `.agents` 下的 `hub-comm`/`rift-remote-exec` 四个精确 Windows 目标，明确排除 `.codex`、`.minimax`、`.codebuddy` 和其他路径。
5. **安装状态机完整**：`missing/create`、`same/no-op`、`different/STOP` 都有明确语义；每个目标独立判断，different 不会被覆盖。
6. **YAML/安全/哈希校验完整**：前置 YAML 结构、skill name、干净归档路径检查、禁止项、`RelativePath|Length|SHA256` manifest 及安装后 0 差异均已列为必要门禁。
7. **回滚并发风险已闭合**：原子改名前再查目标；竞态出现 same 时 no-op、different 时 STOP；只清理本次唯一临时目录。后续失败时，仅当目标当下整树哈希仍等于安装哈希才允许删除本次创建树；若安装后发生外部改动，严禁回滚覆盖或删除。same/different 分支不获得回滚所有权。
8. **E2E 不会假绿**：要求 fresh Hub agent 实际创建 Mac child，并同时比对 Mac serverId、`/Users/mcdowell/wb` workspace 与精确响应 `MAC_ROUTE_OK_AFTER_SKILL`，不以“能看到 skill”替代路由验收。
9. **权限边界清晰**：计划禁止 commit/push，验收 child 不改文件、不执行 CRM 开发、部署、生产写入或邮件发送。

VERDICT: PASS
