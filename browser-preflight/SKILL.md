---
name: browser-preflight
description: "Browser tool chain: preflight check + quick-use guide for browser-harness and opencli. Load before any browser/web operation. Triggers: 'browser check', 'preflight', '浏览器检查', '工具链检查', 'browser doctor', '读网页', '抓页面', 'web tools', 'opencli', 'browser-harness'."
---

# Browser Tool Chain

preflight 检查 + browser-harness / opencli 快速使用指南。加载本 skill 后可直接复制代码操作浏览器。

---

## 1. Preflight（操作前必跑）

```bash
bash ~/.claude/skills/browser-preflight/scripts/check.sh        # Mac 本地
bash ~/.claude/skills/browser-preflight/scripts/check.sh --hub   # 含 Hub
bash ~/.claude/skills/browser-preflight/scripts/check.sh --fix   # 自动修复
```

全绿才继续。有 fail 先 `--fix`，仍失败报告用户。

**不需要 preflight**：opencli `[public]` 命令、`curl` 调 Jina Reader、browser-harness `http_get()`。

---

## 2. 场景决策（先选工具再写代码）

| 我要做什么 | 用什么 | 需要 Chrome？ |
|---|---|---|
| 抓 HN/B站/知乎热榜 | `opencli <site> <cmd>` | public 不需要 |
| 读一篇普通博客文章 | Jina Reader `curl` | 不需要 |
| 读反爬页面（Reuters 等） | `opencli browser <s> extract` | 需要 |
| 读微信公众号文章 | browser-harness `js("#js_content")` | 需要 |
| 填表单/点按钮/E2E | browser-harness | 需要 |
| 截图 | browser-harness `capture_screenshot()` | 需要 |
| 查网络请求/Console | browser-harness `cdp("Network.enable")` | 需要 |
| 批量抓多个 URL | browser-harness `http_get()` + ThreadPool | 不需要 |
| 搜索信息 | `open-websearch` MCP | 不需要 |

---

## 3. browser-harness 速查

### 连接

Mac 和 Hub 都用 Chrome-Debug profile（独立于主 Chrome）：
- Mac：`--user-data-dir="~/Library/Application Support/Google/Chrome-Debug"` + port 9222
- Hub：`--user-data-dir=~/.config/chrome-debug` + port 9222
- Hub 需设 `BU_CDP_URL=http://127.0.0.1:9222`

### 基本模式

所有操作都是 heredoc 传 Python：

```bash
browser-harness <<'PY'
# helpers 已自动导入，daemon 自动启动
PY
```

Hub 上：
```bash
ssh hub 'BU_CDP_URL=http://127.0.0.1:9222 browser-harness < /tmp/script.py'
```

### 常用代码片段

#### 打开页面 + 读内容
```python
new_tab("https://example.com")  # 用 new_tab 不用 goto_url（不覆盖用户页面）
wait_for_load()
info = page_info()  # {url, title, w, h, sx, sy, pw, ph}
text = js("document.body.innerText")
print(text[:2000])
```

#### 读微信文章
```python
new_tab("https://mp.weixin.qq.com/s/xxxxx")
wait_for_load()
import time; time.sleep(3)
content = js("document.getElementById('js_content').innerText")
print(content)
```

#### 截图
```python
capture_screenshot("/tmp/shot.png")                # 当前视口
capture_screenshot("/tmp/full.png", full=True)      # 全页面
capture_screenshot("/tmp/s.png", max_dim=1800)      # 限制尺寸
```

#### 点击 + 输入
```python
# 坐标点击（穿透 iframe/shadow DOM）
click_at_xy(200, 300)

# 表单填写（React/Vue 兼容）
fill_input("#email", "user@example.com")
fill_input("#password", "secret")
press_key("Enter")
```

#### 网络请求捕获
```python
cdp("Network.enable")
new_tab("https://example.com")
wait_for_load()
import time; time.sleep(2)
for e in drain_events():
    if e.get("method") == "Network.requestWillBeSent":
        url = e["params"].get("request", {}).get("url", "")
        if url.startswith("http"):
            print(url)
```

#### CSS / DOM 检查
```python
style = js("""
    JSON.stringify((() => {
        const el = document.querySelector('h1');
        const s = getComputedStyle(el);
        return {fontSize: s.fontSize, color: s.color};
    })())
""")
print(style)
```

#### 纯 HTTP 批量抓取（不需要 Chrome）
```python
from concurrent.futures import ThreadPoolExecutor
urls = ["https://example.com", "https://httpbin.org/get"]
with ThreadPoolExecutor(max_workers=5) as pool:
    results = list(pool.map(http_get, urls))
for url, html in zip(urls, results):
    print(f"{url}: {len(html)} chars")
```

#### 等待
```python
wait_for_load(timeout=15)                          # 等 readyState complete
wait_for_element(".result", timeout=10)             # 等 DOM 元素出现
wait_for_element("#btn", visible=True, timeout=5)   # 等元素可见
wait_for_network_idle(timeout=10, idle_ms=500)      # 等网络请求结束
wait(2)                                             # 简单等待
```

#### Tab 管理
```python
tabs = list_tabs(include_chrome=False)  # 列出所有 tab
switch_tab(tabs[0])                     # 切换
new_tab("https://...")                  # 新建
close_tab()                             # 关闭当前
ensure_real_tab()                       # 确保在真实页面上
```

### 注意事项

- **用 `new_tab()` 不用 `goto_url()`** — goto 覆盖用户当前页面
- **每次操作后截图验证** — 不要盲操作
- **heredoc 用 `<<'PY'`** — 单引号防 shell 转义
- **登录页停下来问用户** — 不自动填密码

---

## 4. opencli 速查

### 基本用法

```bash
opencli <site> <cmd> [options]
opencli <site> --help              # 查看所有命令
opencli <site> <cmd> --help        # 查看参数
```

### 通用选项

```bash
-f, --format <fmt>   # table / plain / json / yaml / md / csv
--limit <n>           # 限制条数
-v, --verbose         # 调试
--profile <name>      # 多账号
```

### 四种命令类型

| 类型 | 需要 Chrome？ | 数量 |
|---|---|---|
| `[public]` | 不需要 | 317 |
| `[cookie]` | 需要 Browser Bridge | 711 |
| `[intercept]` | 需要 Browser Bridge | 6 |
| `[ui]` | 需要 Browser Bridge | 167 |

### 常用命令

```bash
# 热榜/新闻（public，零浏览器）
opencli hackernews top --limit 5 -f json
opencli 36kr hot
opencli arxiv search "LLM agent" --limit 5

# 开发
opencli npm search lodash -f json
opencli pypi search requests
opencli stackoverflow search "rust async"

# 天气
opencli wttr current Shanghai

# 社交（需登录）
opencli bilibili hot
opencli zhihu hot
opencli weibo hot
opencli xiaohongshu search "关键词"

# 金融
opencli xueqiu hot-stock
opencli eastmoney hot-rank
opencli binance price BTCUSDT

# 登录
opencli <site> login     # 打开浏览器登录
opencli <site> whoami    # 验证
```

### browser 子命令（v1.8.4+）

```bash
opencli browser <session> open "https://..."    # 打开
opencli browser <session> state                  # 页面状态 + 元素索引
opencli browser <session> click 3                # 点击第 3 个元素
opencli browser <session> type 5 "hello"         # 输入
opencli browser <session> extract                # 页面转 Markdown
opencli browser <session> screenshot             # 截图
opencli browser <session> eval "document.title"  # 执行 JS
opencli browser <session> network                # 网络请求
opencli browser <session> analyze "url"          # 分析未知站点
opencli browser <session> close                  # 关闭会话
```

`<session>` 同名复用 Tab，不同名隔离。**用完必须 close**，否则残留 Tab 组。

### 诊断

```bash
opencli doctor        # Daemon + Extension + Connectivity
opencli auth status   # 各站点登录状态
```

---

## 5. Jina Reader（最简单的读网页方式）

```bash
curl -s -H "Accept: text/markdown" "https://r.jina.ai/<url>"
```

零浏览器、零依赖。但读不了 JS 渲染页面（微信等），会被反爬封（Reuters 等）。

---

## 6. 故障速查

| 症状 | 原因 | 修复 |
|---|---|---|
| browser-harness 报 403 / DevToolsActivePort not found | Chrome 没开远程调试 | 跑 `check.sh --fix`，或手动启动 Chrome-Debug |
| opencli 报 Extension not connected | Chrome-Debug 里没装 OpenCLI 扩展 | `chrome://extensions` → 加载已解压扩展 |
| Hub Chrome CDP 不可达 | Hub Chrome 没在跑 | `check.sh --fix --hub` |
| 微信文章"环境异常" | 新 Chrome profile 无 `_qimei` 指纹 | 用户手动访问一篇微信文章完成验证 |
| opencli 残留 Tab 组 | session 没 close | `opencli browser <s> close` |
| Hub 操作超时 | SSH 断连 | scp 脚本到 Hub 再执行 |

---

## 7. Mac Chrome-Debug 启动

preflight `--fix` 会自动处理。手动启动：

```bash
/Applications/Google\ Chrome.app/Contents/MacOS/Google\ Chrome \
  --remote-debugging-port=9222 \
  --user-data-dir="$HOME/Library/Application Support/Google/Chrome-Debug" \
  --no-first-run about:blank &
```

不影响主 Chrome。首次启动后需手动装 OpenCLI 扩展一次。
