# Threads（Meta Graph API）

Threads 是 Meta 推出的文本社交平台。本 channel 调 `graph.threads.net/v1.0` 官方 Graph API，**需要 Access Token**。

## 状态

- **Tier 2**（需要 App Review）
- 状态查询：`agent-reach doctor --json` 看 `threads.active_backend`

## 获取 Access Token

1. 打开 https://developers.facebook.com/apps/
2. 创建 App → 选择「Consumer」或「Business」
3. 添加产品「Threads」（**需 App Review**，通常 1-2 周）
4. App Review 通过后，在 App Dashboard 拿到 App ID + App Secret
5. 用 Graph API Explorer 生成 Access Token：
   - 打开 https://developers.facebook.com/tools/explorer/
   - 选择你的 App + Threads 权限
   - Generate Access Token
6. 设置环境变量：

```bash
export THREADS_ACCESS_TOKEN="EAAxxxxxxxxxxxxx"
```

7. 跑 `agent-reach doctor` 验证

## 数据访问

### Python API

```python
from agent_reach.channels.threads import ThreadsChannel

ch = ThreadsChannel()

# 当前账号 profile
me = ch.get_user_profile("me")
# → {id, username, name, biography, profile_picture_url, url}

# 当前账号帖子
posts = ch.get_user_threads("me", limit=25)
# → [{id, text, media_type, media_url, permalink, like_count,
#    reply_count, repost_count, timestamp, ...}]

# 搜公开帖子（2024-10 后开放，需 App 启用 search 权限）
results = ch.search("python", search_type="TOP", limit=25)
# → [{id, text, username, like_count, reply_count, permalink, ...}]
```

### 直 curl

```bash
# 当前账号
curl -s "https://graph.threads.net/v1.0/me?fields=id,username,name,threads_biography" \
  -H "Authorization: Bearer $THREADS_ACCESS_TOKEN"

# 搜帖子
curl -s "https://graph.threads.net/v1.0/search?q=python&search_type=TOP&fields=id,text,username&limit=10" \
  -H "Authorization: Bearer $THREADS_ACCESS_TOKEN"
```

## 字段说明

`get_user_profile` 返回:
- `id` — Threads 数字 ID
- `username` — `@handle`（不含 @）
- `name` — 显示名
- `biography` — bio
- `profile_picture_url` — 头像

`get_user_threads` 返回:
- `id` — 帖子 ID
- `text` — 帖子正文
- `media_type` — `TEXT_POST` / `IMAGE` / `VIDEO` / `CAROUSEL_ALBUM`
- `media_url` / `permalink`
- `like_count` / `reply_count` / `repost_count` / `quote_count`
- `timestamp` — ISO8601
- `is_quote_post` / `has_replies`

## 注意事项

> **App Review 时间**：Meta 审核通常 1-2 周，少数情况更久。建议提前申请。
>
> **Token 生命周期**：User Access Token 短期有效（约 1-2 小时），生产环境建议：
> - 用 Long-Lived Token（60 天）
> - 或用 Business User token + System User token
>
> **search 权限**：search 端点 2024-10 后开放，需要 App 显式启用 `threads_search` 权限 + 单独审核。
>
> **频率限制**：官方 rate limit，未公开具体数字。高频调用会被临时封。
