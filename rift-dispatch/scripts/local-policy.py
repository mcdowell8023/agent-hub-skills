#!/usr/bin/env python3
"""rift-dispatch 本地用户策略（SKILL §3.2g，最高优先级）—— 派发前跑一次，打印命中的规则。

  python3 scripts/local-policy.py --cwd <派发工作目录> [--file <策略文件>]

策略文件默认 ~/.config/rift-dispatch/policy.local.json，⛔ 不在任何仓库里、⛔ 不推送。
输出一行 JSON：{"file": 路径|null, "rule": id|null, "allow": {...}|null, "fallback": {...}|null, "reason": ...}
退出码：0 = 正常（含「没有策略文件」）· 2 = 策略文件存在但读不出 / 结构不对（🔴 fail closed：⛔ 当成没有策略放行）。
匹配：字面路径（展开 ~ + normpath）**或**物理路径（realpath）任一在 workspaceUnder 某个根之下即命中 ——
只看物理路径会漏掉「公司目录里的项目软链到别的盘」（= 付费被放行）；多判只会更严。
"""
import argparse, json, os, sys

DEFAULT = os.path.join('~', '.config', 'rift-dispatch', 'policy.local.json')


class PolicyError(Exception):
    pass


def load(path):
    """文件不存在 ⇒ None；存在但读不出 / 结构不对 ⇒ PolicyError。"""
    path = os.path.expanduser(path)
    if not os.path.exists(path):
        return None
    try:
        with open(path, encoding='utf-8') as f:
            data = json.load(f)
    except (OSError, ValueError) as err:
        raise PolicyError(f'读不出策略文件 {path}: {err}') from err
    rules = data.get('rules') if isinstance(data, dict) else None
    if not isinstance(rules, list):
        raise PolicyError(f'{path}: 顶层必须是 {{"rules": [...]}}')
    for i, r in enumerate(rules):
        roots = (r.get('when') or {}).get('workspaceUnder') if isinstance(r, dict) else None
        allow = r.get('allow') if isinstance(r, dict) else None
        if not isinstance(r, dict) or not isinstance(r.get('id'), str) or not r['id']:
            raise PolicyError(f'{path}: rules[{i}] 缺 id')
        if not isinstance(roots, list) or not roots or not all(isinstance(x, str) for x in roots):
            raise PolicyError(f'{path}: rules[{i}].when.workspaceUnder 必须是非空字符串数组')
        if not isinstance(allow, dict) or not isinstance(allow.get('upstreams', []), list):
            raise PolicyError(f'{path}: rules[{i}].allow.upstreams 必须是数组')
        fb = r.get('fallback')
        if fb is not None and not (isinstance(fb, dict) and all(isinstance(fb.get(k), str) for k in ('upstream', 'model', 'thinking'))):
            raise PolicyError(f'{path}: rules[{i}].fallback 需要 upstream / model / thinking 三个字符串')
    return data


def _under(path, root):
    return path == root or path.startswith(root.rstrip('/') + '/')


def match(policy, cwd):
    lit = os.path.normpath(os.path.expanduser(cwd))
    phy = os.path.realpath(lit)
    for r in (policy or {}).get('rules', []):
        for root in r['when']['workspaceUnder']:
            rt = os.path.normpath(os.path.expanduser(root))
            if _under(lit, rt) or _under(phy, os.path.realpath(rt)):
                return r
    return None


def main():
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('--cwd', required=True)
    ap.add_argument('--file', default=DEFAULT)
    a = ap.parse_args()
    try:
        policy = load(a.file)
    except PolicyError as err:
        print(json.dumps({'ok': False, 'error': str(err)}, ensure_ascii=False))
        sys.exit(2)
    r = match(policy, a.cwd)
    print(json.dumps({'ok': True, 'file': os.path.expanduser(a.file) if policy is not None else None,
                      'rule': r['id'] if r else None, 'allow': r['allow'] if r else None,
                      'fallback': r.get('fallback') if r else None, 'reason': r.get('reason') if r else None},
                     ensure_ascii=False))


if __name__ == '__main__':
    main()
