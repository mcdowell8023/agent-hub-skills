#!/usr/bin/env python3
"""local-policy.py 的离线测试（2026-10-10）—— 临时 HOME，⛔ 不读真实 ~/.config/rift-dispatch/。"""
import json, os, pathlib, subprocess, sys, tempfile

S = pathlib.Path(__file__).resolve().parent
fails = []

def run(home, cwd, policy_file=None):
    env = dict(os.environ, HOME=str(home))
    args = [sys.executable, '-B', str(S / 'local-policy.py'), '--cwd', str(cwd)]
    if policy_file: args += ['--file', str(policy_file)]
    p = subprocess.run(args, env=env, capture_output=True, text=True)
    try: out = json.loads(p.stdout)
    except json.JSONDecodeError: out = None
    return p.returncode, out, p.stdout + p.stderr

def check(cond, msg):
    if not cond: fails.append(msg)

with tempfile.TemporaryDirectory() as t:
    home = pathlib.Path(t, 'home'); (home / 'company/projects/app').mkdir(parents=True); (home / 'company2/x').mkdir(parents=True)
    cfg = home / '.config/rift-dispatch'; cfg.mkdir(parents=True)
    pol = cfg / 'policy.local.json'
    rule = {'id': 'company-no-personal-spend', 'when': {'workspaceUnder': ['~/company']},
            'allow': {'upstreams': ['claude'], 'freePool': True},
            'fallback': {'upstream': 'claude', 'model': 'claude-sonnet-5', 'thinking': 'max'}}

    # 1. 没有策略文件 ⇒ 不命中、rc=0（与原行为一致）
    rc, out, raw = run(home, home / 'company/projects/app')
    check(rc == 0 and out and out['rule'] is None and out['file'] is None, f'无文件应 rule=None rc=0：{raw}')

    pol.write_text(json.dumps({'rules': [rule]}))
    # 2. 子目录命中（默认路径 ~/.config/rift-dispatch/policy.local.json）
    rc, out, raw = run(home, home / 'company/projects/app')
    check(rc == 0 and out['rule'] == 'company-no-personal-spend' and out['allow']['freePool'] is True, f'company 子目录应命中：{raw}')
    # 3. 根目录本身命中；~/company2 不命中
    rc, out, raw = run(home, home / 'company'); check(out and out['rule'] == 'company-no-personal-spend', f'company 根应命中：{raw}')
    rc, out, raw = run(home, home / 'company2/x'); check(rc == 0 and out['rule'] is None, f'~/company2 不应命中：{raw}')
    # 4. 软链进 company ⇒ 按物理路径命中
    link = pathlib.Path(t, 'link-to-app'); link.symlink_to(home / 'company/projects/app')
    rc, out, raw = run(home, link); check(out and out['rule'] == 'company-no-personal-spend', f'软链应按物理路径命中：{raw}')
    # 4b. 🔴 company 内的软链指向 company 外（项目放在别的盘）⇒ 按字面路径同样命中（⛔ 只看物理路径会漏判 = 付费被放行）
    outside = pathlib.Path(t, 'external-disk/proj'); outside.mkdir(parents=True)
    (home / 'company/projects/ext').symlink_to(outside)
    rc, out, raw = run(home, home / 'company/projects/ext'); check(out and out['rule'] == 'company-no-personal-spend', f'company 内软链指向外部也应命中：{raw}')
    # 4c. `..` 规范化：~/company/../company2 不命中；~/company2/../company/projects 命中
    rc, out, raw = run(home, f"{home}/company/../company2/x"); check(out and out['rule'] is None, f'company/../company2 不应命中：{raw}')
    rc, out, raw = run(home, f"{home}/company2/../company/projects/app"); check(out and out['rule'] == 'company-no-personal-spend', f'company2/../company 应命中：{raw}')
    # 5. 🔴 文件存在但 JSON 坏了 ⇒ fail closed（rc=2），⛔ 不当成「没有策略」
    pol.write_text('{"rules": [ oops')
    rc, out, raw = run(home, home / 'company/projects/app'); check(rc == 2, f'坏 JSON 应 rc=2：{raw}')
    # 6. 结构不对 ⇒ 同样 rc=2
    for bad in ({'rules': {}}, {'rules': [{'id': 'x', 'when': {'workspaceUnder': '~/company'}, 'allow': {}}]},
                {'rules': [{'id': 'x', 'when': {'workspaceUnder': ['~/company']}, 'allow': {'upstreams': 'claude'}}]},
                {'rules': [{'when': {'workspaceUnder': ['~/company']}, 'allow': {'upstreams': []}}]}):
        pol.write_text(json.dumps(bad))
        rc, out, raw = run(home, home / 'company/projects/app'); check(rc == 2, f'结构错误应 rc=2：{bad} → {raw}')
    # 7. --file 指定别处的文件
    other = pathlib.Path(t, 'other.json'); other.write_text(json.dumps({'rules': [rule]}))
    rc, out, raw = run(home, home / 'company/projects/app', other)
    check(rc == 0 and out['rule'] == 'company-no-personal-spend' and out['file'] == str(other), f'--file 应生效：{raw}')
    # 8. 仓库里的示例文件本身必须是合法策略（只作格式说明，⛔ 不生效）
    rc, out, raw = run(home, home / 'company/projects/app', S.parent / 'policy.local.example.json')
    check(rc == 0, f'示例文件必须合法：{raw}')

print('=== local-policy.py 离线测试 ===')
print('✅ 全部通过' if not fails else '\n'.join('❌ ' + f for f in fails))
sys.exit(1 if fails else 0)
