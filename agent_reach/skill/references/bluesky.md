# Bluesky（atproto 公开 API）

Bluesky 是去中心化社交网络，基于 atproto 协议。本 channel 直接调 `public.api.bsky.app` 公开 XRPC，**无需认证**。

## 状态

- **Tier 0**（零配置）
- 状态查询：`agent-reach doctor --json` 看 `bluesky.active_backend`
- **网络限制**：在 GFW 等受限网络下可能 TCP 超时，需要代理

## 数据访问

### Python API

```python
from agent_reach.channels.bluesky import BlueskyChannel

ch = BlueskyChannel()

# 搜索用户
users = ch.search_actors("python", limit=10)
# → [{did, handle, display_name, description, followers_count, follows_count, posts_count, ...}]

# 搜索帖子
posts = ch.search_posts("python", limit=20)
# → [{uri, author_handle, text, like_count, reply_count, repost_count, ...}]

# 读 profile
prof = ch.get_profile("bsky.app")
# → {did, handle, display_name, description, followers_count, ...}

# 读单帖 + 回复
thread = ch.get_post_thread("at://alice.bsky.social/app.bsky.feed.post/3k...")
# → {uri, author_handle, text, like_count, replies_count_in_thread, ...}

# URL-based reader
ch.read("https://bsky.app/profile/alice.bsky.social/post/3k...")
ch.read("https://bsky.app/profile/alice.bsky.social")
```

### 直 curl

```bash
# 搜用户
curl -s "https://public.api.bsky.app/xrpc/app.bsky.actor.searchActors?q=python&limit=5" \
  -H "User-Agent: agent-reach/1.0"

# 搜帖子
curl -s "https://public.api.bsky.app/xrpc/app.bsky.feed.searchPosts?q=python&limit=5" \
  -H "User-Agent: agent-reach/1.0"

# 用户 profile
curl -s "https://public.api.bsky.app/xrpc/app.bsky.actor.getProfile?actor=bsky.app" \
  -H "User-Agent: agent-reach/1.0"
```

## 字段说明

`search_actors` 返回:
- `did` — 去中心化标识符
- `handle` — 用户名（`xxx.bsky.social`）
- `display_name` — 显示名
- `description` — bio
- `followers_count` / `follows_count` / `posts_count` — 粉丝/关注/帖子数
- `url` — 主页 URL

`search_posts` 返回:
- `uri` — at:// URI
- `author_handle` / `author_display_name`
- `text` — 帖子正文
- `like_count` / `reply_count` / `repost_count` / `quote_count`
- `created_at` / `indexed_at`
- `url` — 帖子 URL

## 注意事项

> **公开 API 限制**：不返回 DMs、私密账号内容、关注列表。
>
> **频率控制**：公开 API 限流宽松（无明确 rate limit 文档），但高频请求可能被临时封 IP。
>
> **searchPosts 偶发 403**：BSky 的反爬会临时封 IP，过几分钟恢复。
>
> **network 受限**：本 channel 在中国大陆网络下 DNS 解析成功但 TCP 超时（典型 GFW 行为）。需要代理或换网络环境。
