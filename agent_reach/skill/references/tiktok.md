# TikTok（公开 HTML，WAF 拦截）

TikTok 是字节跳动旗下短视频平台。**本 channel 务实实现，不提供完整抓取**。原因：TikTok 没有公开的、未鉴权的 API，公开主页由 Slardar WAF 拦截非浏览器请求。

## 状态

- **Tier 2**（受限）
- 状态查询：`agent-reach doctor --json` 看 `tiktok.active_backend`
- **实际可用性**：在当前网络下基本不可用（返回 WAF challenge 页）

## 现状说明

实测 TikTok 公开主页（`https://www.tiktok.com/`）：

| 测试项 | 结果 |
|---|---|
| curl 主页 | ✅ 200，但只有 1.5KB HTML |
| HTML 内容 | Slardar WAF challenge 页（"Please wait..." + base64 challenge） |
| `og:title` / `og:description` | ❌ 缺失（JS 渲染后才有） |
| `__UNIVERSAL_DATA_FOR_REHYDRATION__` JSON | ❌ 缺失 |
| `window.__INIT_PROPS__` JSON | ❌ 缺失 |

**结论**：非浏览器 UA 拿不到任何有意义的 HTML。channel 提供 `get_public_page_html` 但返回的是 WAF challenge。

## 数据访问

### Python API

```python
from agent_reach.channels.tiktok import TikTokChannel

ch = TikTokChannel()

# 拿公开主页 HTML（实际会拿到 WAF challenge）
page = ch.get_public_page_html("charlidamelio")
if "error" in page:
    print(page["error"])
else:
    print(f"HTML 长度: {page['html_total_len']}")
    print(f"Embedded JSON keys: {page['embedded_json_keys']}")
    # 正常情况下 embedded_json_keys 为空

# 简化版 user fetch
user = ch.get_user("charlidamelio")
# → {handle, url, note, has_embedded_data}

# URL-based reader
ch.read("https://www.tiktok.com/@charlidamelio")
ch.read("https://www.tiktok.com/video/12345")  # → error（视频元数据需登录）
```

## 可行的替代路径

如果需要完整 TikTok 数据，请考虑：

1. **OpenCLI 后端**（推荐桌面用户）
   - 等 jackwener/opencli 项目支持 TikTok 后，可以用 `opencli tiktok` 系列命令
   - 复用 Chrome 登录态，跟小红书/Twitter 一样

2. **TikTok Display API**（Tier 2，需 App Review）
   - 申请 https://developers.tiktok.com/
   - 拿到 access_token 后可调官方 API
   - 限制：只返回**自己账号**的数据（user info / video list）

3. **第三方抓取服务**
   - RapidAPI 上的 TikTok scraper（付费）
   - 专用爬虫服务

4. **住宅代理 + 浏览器自动化**（最复杂）
   - Playwright + 住宅 IP + 浏览器指纹
   - 维护成本高，合规风险大

## 字段说明（如果未来能拿到数据）

`get_user` 设计返回:
- `handle` — `@charlidamelio` 不带 @
- `url` — 主页 URL
- `note` — 状态说明
- `has_embedded_data` — 是否有 embedded JSON（当前永远 False）

## 注意事项

> **不建议用于批量抓取**：违反 TikTok 服务条款，可能被永久封 IP。
>
> **WAF 绕过**：需要 Residential Proxy + 浏览器 UA + Cookie。当前 channel 不实现。
>
> **本 channel 仅作占位**：等更好的实现或用户配置代理后再扩展。
