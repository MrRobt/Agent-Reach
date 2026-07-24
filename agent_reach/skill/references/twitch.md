# Twitch（私有 GQL）

Twitch 是游戏直播为主的平台。本 channel 调 `gql.twitch.tv/gql` 私有 GQL，借用 Twitch Web 客户端公开的 Client-ID，**无需 OAuth 凭证**。

## 状态

- **Tier 0**（零配置）
- 状态查询：`agent-reach doctor --json` 看 `twitch.active_backend`
- **合规风险**：违反 Twitch ToS，仅建议低频只读使用

## 数据访问

### Python API

```python
from agent_reach.channels.twitch import TwitchChannel

ch = TwitchChannel()

# 用户 profile（含粉丝数、bio、partner 状态）
user = ch.get_user("ninja")
# → {id, login, display_name, description, followers_count,
#    is_partner, is_affiliate, profile_image_url, banner_image_url, ...}

# 热门直播流（按 viewers 降序）
streams = ch.get_streams(first=20)
# → [{id, title, viewer_count, broadcaster_*, game_*, preview_image_url, ...}]

# 搜索用户
users = ch.search_users("riot games", first=10)
# → [{id, login, display_name, followers_count, is_live, ...}]

# 热门游戏分类
games = ch.get_games(first=20)
# → [{id, name, slug, viewer_count, box_art_url, ...}]

# 用户 VOD 列表
videos = ch.get_videos("ninja", first=10)
# → [{id, title, view_count, length_seconds, thumbnail_url, game_name, ...}]

# 顶级游戏排行（支持分页）
top_games = ch.get_top_games(first=10)

# URL-based reader
ch.read("https://www.twitch.tv/ninja")           # → get_user
ch.read("https://www.twitch.tv/videos/12345")   # → 提示 video_id（未实现）
```

### 直 curl（看 schema）

```bash
# 查用户
curl -s "https://gql.twitch.tv/gql" \
  -H "Client-ID: kimne78kx3ncx6brgo4mv6wki5h1ko" \
  -H "Content-Type: application/json" \
  -d '{"query":"query { user(login: \"ninja\") { id followers { totalCount } } }"}'

# 直播流
curl -s "https://gql.twitch.tv/gql" \
  -H "Client-ID: kimne78kx3ncx6brgo4mv6wki5h1ko" \
  -H "Content-Type: application/json" \
  -d '{"query":"query { streams(first: 3) { edges { node { id title viewersCount game { name } broadcaster { login } } } } }"}'
```

## Schema 已知约束

实测 Twitch GQL schema（2026-07）：

| 端点 | 行为 |
|---|---|
| `user(login)` | ✅ 完整 |
| `streams(first)` | ⚠️ **无 filter 参数**（gameID/gameSlug/language 都报 Unknown argument） |
| `games(first)` | ✅ 默认按 viewers 降序 |
| `searchUsers(userQuery)` | ✅ `isLive` 字段不存在，用 `stream { id }` 替代 |
| `user.videos(first)` | ✅ |
| `gameDirectoryPage(first, after)` | ✅ 支持分页 |

## Client-ID 管理

`_DEFAULT_CLIENT_ID = "kimne78kx3ncx6brgo4mv6wki5h1ko"` 是 Twitch Web 客户端的 Client-ID。Twitch 偶尔会轮换，**失效时**：
1. 浏览器打开 twitch.tv
2. DevTools → Network → 任意 GQL 请求
3. 复制 Request Headers 里的 `Client-ID`
4. 修改 `agent_reach/channels/twitch.py` 里的 `_DEFAULT_CLIENT_ID`

## 注意事项

> **借用 Client-ID**：上面那个 ID 是 Twitch Web 前端 bundle 里硬编码的，公开可见但不属于用户。Twitch 偶尔轮换，doctor 会自动发现。
>
> **ToS 合规**：违反 Twitch 服务条款「Abuse of Twitch Services」，仅建议：
> - 低频只读（几分钟一次）
> - 公开数据
> - 个人学习
>
> **批量/商业抓取请走官方 Helix API**（需申请 Client ID）。
>
> **filter 限制**：streams 字段无 filter 参数，需要 game 维度的过滤请先用 `get_games()` 拿 game_id，然后在外层代码中按 game 字段手动过滤。
