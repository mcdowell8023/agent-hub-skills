#!/usr/bin/env python3
"""🔴 决策树完整性：§2 伪代码的每一行都必须被 pipeline-test 的用例走到。

⚠️ 为什么需要它：`pipeline-test.py` 只保证「跑过的路径行为对」，
   ⛔ 不保证「所有路径都跑过」。2026-09-10 实测发现两处：
   ① 空 `--model` 的报错分支从没被测过
   ② review 分支里有一段**死代码** —— 第 1 段的 pre-P0 检查已把非 Copilot provider 拦掉，
      那个 elif 永远为假。死代码在「当规范读」的伪代码里有害：读的人会以为拦截发生在那里。

⚠️ 多行字面量的续行、docstring、单独的 `}`/`else:` 不计入 —— Python 把整个表达式
   记在**首行**，续行天然没有行事件。⛔ 别把它们当成未覆盖。
"""
import re, sys, pathlib, io, contextlib

B = pathlib.Path(__file__).resolve().parent.parent
BODY = re.search(r"## 2\. 决策流程.*?```python\n(.*?)\n```", (B/'SKILL.md').read_text(), re.S).group(1)
L = BODY.splitlines()

# 🔴 用 code object 的 co_lines() 取【真正能产生 line 事件的行】，⛔ 不用启发式猜续行。
#    第一版用「上一行以逗号结尾」判续行，被**行尾注释**骗过（`('a','b'),   # 注释`）⇒ 5 行误报。
import textwrap
def emittable_lines(body: str) -> set:
    co = compile("def _f():\n" + textwrap.indent(body, '    '), '<SKILL.md §2>', 'exec')
    out, stack = set(), [co]
    while stack:
        c = stack.pop()
        for _, _, ln in c.co_lines():
            if ln is not None: out.add(ln - 1)      # 外层包了一层 def ⇒ 偏移 1
        stack += [k for k in c.co_consts if hasattr(k, 'co_lines')]
    return out

want = {i for i in emittable_lines(BODY) if 1 <= i <= len(L)}
hit = set()
def tracer(fr, ev, arg):
    if fr.f_code.co_filename == '<SKILL.md §2>' and ev == 'line': hit.add(fr.f_lineno - 1)
    return tracer

code = compile((B/'scripts/pipeline-test.py').read_text(), 'pipeline-test.py', 'exec')
g = {'__name__': '__main__', '__file__': str(B/'scripts/pipeline-test.py')}
buf = io.StringIO(); sys.settrace(tracer)
try:
    with contextlib.redirect_stdout(buf): exec(code, g)
except SystemExit: pass
finally: sys.settrace(None)

missed = sorted(want - hit)
pct = (len(want) - len(missed)) / len(want) * 100
print("=== §2 决策树覆盖率 ===")
print(f"应覆盖 {len(want)} 行 · 未覆盖 {len(missed)} 行 · {pct:.1f}%")
if missed:
    print("\n❌ 以下分支【没有任何用例走到】—— 要么补用例，要么它是死代码该删：")
    for n in missed: print(f"  §2:{n:<4} | {L[n-1].strip()[:100]}")
tail = buf.getvalue().strip().splitlines()[-1] if buf.getvalue().strip() else ''
print(f"\n（pipeline-test: {tail}）")
sys.exit(1 if missed else 0)
