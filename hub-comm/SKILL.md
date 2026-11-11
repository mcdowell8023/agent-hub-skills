---
name: hub-comm
description: Use when Mac or Agent Hub needs bidirectional Paseo communication, cross-machine agent creation or follow-up, list_hosts is empty, a reverse route is missing, or a Hub agent reports that it cannot reach or delegate work to Mac.
---

# Hub communication

## Overview

Use Paseo's registered-host fleet tools for Mac ↔ Hub agent work. A reachable daemon is not automatically a registered route.

**Registry is directional（有方向性）:** Mac 已注册 Hub ≠ Hub 已注册 Mac。`list_hosts` 只描述当前 calling daemon 的 `self` 和它已注册的 destinations；不能用 Mac 上的结果推断 Hub 上的 registry。

## When to use

- Mac 需要在 Hub 上创建 agent 或继续会话。
- Hub agent 需要在 Mac 上创建 child agent 或发送 follow-up。
- `list_hosts` 为空、对端不在列表中、reverse route 缺失，或跨机器创建失败。
- 需要确认 `{serverId, agentId}` 所属主机，避免把任务派到本机。

## Preferred fleet workflow

Paseo MCP fleet tools are the default path. Registered destinations are first-class targets; cross-machine `create_agent` and `send_agent_prompt` both support `serverId`.

1. Call `list_hosts` on the affected daemon and select the destination by its verified `serverId`, `status=online`, and expected endpoint. Labels are display names, not identity.
2. Keep `{serverId, agentId}` together for the entire conversation. Never reuse an `agentId` without its host route.
3. Call `list_workspaces({serverId})`; choose the returned `workspaceId` whose path/cwd matches the requested remote workspace. Do not guess an ID or reuse a local workspace ID.
4. Call `create_agent({serverId, workspaceId, ...})`. Verify the created child is reported on the same remote `serverId` and workspace.
5. For follow-ups, call `send_agent_prompt({serverId, agentId, prompt, ...})`. Completion notifications work across registered hosts.

Minimal shape:

```json
{
  "serverId": "<destination-server-id>",
  "workspaceId": "<workspace-id-returned-by-that-host>"
}
```

For an existing agent:

```json
{
  "serverId": "<destination-server-id>",
  "agentId": "<agent-id-returned-by-that-host>",
  "prompt": "Continue the assigned task"
}
```

## Fail-closed route repair

Run this on the daemon whose `list_hosts` is missing the destination. For Hub → Mac, the affected daemon is Hub.

1. **Resolve the current endpoint.** On the affected machine, use live Tailscale peer status to select the known Mac device and read its current address; on Mac itself, `tailscale ip -4` is also valid. Do not copy an address from this skill, guess one, scan a subnet, or probe unrelated ports.
2. **Check the local daemon.** Run `paseo daemon status --json` on the affected machine and record its `serverId`.
3. **Check one endpoint only.** Test TCP port 6767 at `<mac-tailscale-ip>` and then run:

   ```bash
   paseo --host <mac-tailscale-ip>:6767 daemon status --json
   ```

   The remote daemon must return the expected Mac `serverId`. Network reachability without a matching daemon identity is not enough.
4. **Inspect the affected registry.** Run:

   ```bash
   paseo host ls --json
   paseo host inspect <registration-id> --json
   ```

   If the expected `serverId` already maps to the same endpoint and is enabled, do not add a duplicate.
5. **Register only when absent.** If no record covers that verified `serverId` and endpoint, run on the affected daemon:

   ```bash
   paseo host add <mac-tailscale-ip>:6767 --label macbook-pro
   ```

6. **Conflict means STOP.** If a label points to another `serverId`, the same `serverId` points to another endpoint, or CLI and remote daemon identity disagree, STOP. Do not delete, overwrite, disable, or automatically replace identity. Report the conflicting registration IDs and non-sensitive metadata for human resolution.
7. **Verify twice.** Re-run `paseo host inspect <registration-id> --json`, then `list_hosts`. Require the expected `serverId`, endpoint, `enabled=true`, `status=online`, and no error before creating an agent.

Never print or copy a registry connection key, authentication token, or credential field. Redact sensitive fields even when a CLI response includes them.

## No manual-prompt fallback

**禁止人工转发:** a missing route must not be downgraded to syncing files, asking the user to copy a prompt, or claiming that cross-machine delegation is unsupported. First repair the registry/route when the checks above prove the repair is safe and automatic. If identity conflicts or the exact endpoint cannot be verified, STOP with the specific blocker; do not invent a route.

## CLI and terminal alternatives

- Paseo CLI `--host` may be used for a targeted daemon status check or when the fleet MCP surface is unavailable. It is not required once the destination is registered and visible to fleet tools.
- `rift-remote-exec` is a fallback for Mac to run commands on a registered remote machine without an LLM. It is **not** a source of credentials for a Hub agent to open a reverse terminal on Mac.
- SSH is an operational fallback only when separately configured and authorized. Do not infer SSH access from Paseo registration.

## File transfer

Agent routing and file transfer are separate. If an existing Dufs service is explicitly in scope, use placeholders or environment variables only:

```bash
curl --user "$DUFS_USER:$DUFS_PASSWORD" -T local-file http://<host>:<port>/
curl --user "$DUFS_USER:$DUFS_PASSWORD" -O http://<host>:<port>/remote-file
```

Do not place real endpoints or credentials in this skill, prompts, logs, or Paseo messages.

## Common mistakes

| Mistake | Correct response |
|---|---|
| Mac can see Hub, so Hub must see Mac | Registries are directional; inspect Hub's `list_hosts` separately. |
| TCP succeeds, therefore the route exists | Verify remote daemon `serverId`, then inspect/add the host record on the affected daemon. |
| A familiar label proves identity | Compare `serverId` and endpoint; any conflict is STOP. |
| A remote workspace path can be guessed | Use `list_workspaces(serverId)` and pass the returned `workspaceId`. |
| An `agentId` is globally unique context | Preserve and use `{serverId, agentId}` together. |
| Missing route means the user must copy the task | Repair a safe missing registration first; never fall back to manual prompt forwarding. |
