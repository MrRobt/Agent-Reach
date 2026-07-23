# -*- coding: utf-8 -*-
"""Twitch — 私有 GraphQL API (gql.twitch.tv/gql) 抓取用户/直播/视频/游戏。

不走官方 Helix OAuth 流程。直接借用 Twitch Web 客户端的 Client-ID 调私有 GQL，
无需用户申请任何凭证、无需登录账号。

Client-ID 来源：Twitch Web 前端 bundle 公开可见（任何浏览器 DevTools 都能看到）。
注意：Twitch 偶尔会轮换此 ID，doctor 会自动验证可用性；不可用时给用户明确提示。

风险与合规：
  - 这违反 Twitch 服务条款（ToS § "Abuse of Twitch Services"），仅建议只读、
    低频、个人学习使用。批量抓取可能触发 IP 限流或账号要求。
  - 公开数据，无个人隐私暴露。
  - 商业用途请走官方 Helix API。

Tier 0 — 零配置。
"""

import json
import urllib.request
from typing import Any, Dict, List, Optional

from .base import Channel

_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"
_TIMEOUT = 15
_GQL_URL = "https://gql.twitch.tv/gql"

# Twitch Web 前端的 Client-ID（公开可见，硬编码于 web bundle）。
# 如果 Twitch 轮换，doctor 会自动发现并提示用户更新。
_DEFAULT_CLIENT_ID = "kimne78kx3ncx6brgo4mv6wki5h1ko"


def _post_gql(client_id: str, query: str, variables: Dict[str, Any] = None) -> Any:
    """POST to Twitch GQL, return parsed JSON."""
    body = json.dumps(
        {"query": query, "variables": variables or {}}
    ).encode("utf-8")
    req = urllib.request.Request(
        _GQL_URL,
        data=body,
        headers={
            "User-Agent": _UA,
            "Client-ID": client_id,
            "Content-Type": "application/json",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:
        return json.loads(resp.read().decode("utf-8"))


class TwitchChannel(Channel):
    name = "twitch"
    description = "Twitch 用户、直播、视频与游戏（私有 GQL，无凭证）"
    backends = ["Twitch GQL (anon)"]
    tier = 0

    # ------------------------------------------------------------------ #
    # URL routing
    # ------------------------------------------------------------------ #

    def can_handle(self, url: str) -> bool:
        from urllib.parse import urlparse
        d = urlparse(url).netloc.lower()
        return "twitch.tv" in d

    # ------------------------------------------------------------------ #
    # Health check
    # ------------------------------------------------------------------ #

    def check(self, config=None):  # noqa: ARG002
        try:
            data = _post_gql(
                _DEFAULT_CLIENT_ID,
                "query { user(login: \"twitch\") { id login } }",
                None,
            )
            if "errors" in data:
                # Client-ID 可能被轮换
                msg = data["errors"][0].get("message", "")
                self.active_backend = None
                return "error", (
                    f"Twitch GQL 返回错误：{msg}。Client-ID 可能已被 Twitch 轮换，"
                    "请从 Twitch Web DevTools 重新获取并修改 _DEFAULT_CLIENT_ID。"
                )
            user = data.get("data", {}).get("user")
            if user and user.get("id"):
                self.active_backend = self.backends[0]
                return "ok", (
                    "Twitch GQL 可用（用户、直播、视频、游戏搜索）。"
                    "⚠️ 借用 Twitch Web 客户端 ID，违反 ToS，仅建议低频只读使用。"
                )
            self.active_backend = None
            return "error", "Twitch GQL 返回结构异常"
        except Exception as e:
            self.active_backend = None
            return "warn", f"Twitch GQL 连接失败（可能被 GFW 拦截）：{e}"

    # ------------------------------------------------------------------ #
    # Data methods
    # ------------------------------------------------------------------ #

    def get_user(self, login: str) -> Dict:
        """按 login 查用户。包含粉丝数、bio、profile_image 等。"""
        q = (
            "query($login: String!) {"
            "  user(login: $login) {"
            "    id login displayName description createdAt"
            "    profileImageURL(width: 300)"
            "    bannerImageURL"
            "    followers { totalCount }"
            "    roles { isPartner isAffiliate isStaff }"
            "    channel { id }"
            "  }"
            "}"
        )
        try:
            data = _post_gql(_DEFAULT_CLIENT_ID, q, {"login": login})
        except Exception as e:
            return {"error": f"get_user failed: {e}"}
        if "errors" in data:
            return {"error": data["errors"][0].get("message", "GQL error")}
        u = data.get("data", {}).get("user")
        if not u:
            return {"error": f"user not found: {login}"}
        return {
            "id": u.get("id", ""),
            "login": u.get("login", ""),
            "display_name": u.get("displayName", ""),
            "description": u.get("description", ""),
            "created_at": u.get("createdAt", ""),
            "profile_image_url": u.get("profileImageURL", ""),
            "banner_image_url": u.get("bannerImageURL", ""),
            "followers_count": (u.get("followers") or {}).get("totalCount", 0),
            "is_partner": (u.get("roles") or {}).get("isPartner", False),
            "is_affiliate": (u.get("roles") or {}).get("isAffiliate", False),
            "is_staff": (u.get("roles") or {}).get("isStaff", False),
            "url": f"https://www.twitch.tv/{u.get('login', '')}",
        }

    def get_streams(self, first: int = 20) -> List[Dict]:
        """获取直播流列表（按 viewers 降序）。

        注：Twitch GQL 的 streams 字段不接受任何 filter 参数（gameID / gameSlug /
        language / channels 均报 Unknown argument）。Filter 只能在外层做：
        先用 get_games() 拿到 game_id，再用 streams + gameID 不行；或者用
        search_channels_for_game() 通过频道搜索间接过滤。
        本方法返回的是全站热门直播榜。
        """
        q = (
            "query($first: Int!) {"
            "  streams(first: $first) {"
            "    edges { node {"
            "      id title viewersCount type createdAt"
            "      game { id name slug boxArtURL(width: 285, height: 380) }"
            "      broadcaster { id login displayName }"
            "      previewImageURL(width: 320, height: 180)"
            "    } }"
            "  }"
            "}"
        )
        try:
            data = _post_gql(_DEFAULT_CLIENT_ID, q, {"first": first})
        except Exception as e:
            return [{"error": f"get_streams failed: {e}"}]
        if "errors" in data:
            return [{"error": data["errors"][0].get("message", "GQL error")}]
        results = []
        for edge in (data.get("data", {}).get("streams", {}) or {}).get("edges", []):
            n = edge.get("node") or {}
            broadcaster = n.get("broadcaster") or {}
            game = n.get("game") or {}
            results.append({
                "id": n.get("id") or "",
                "title": n.get("title") or "",
                "viewer_count": n.get("viewersCount") or 0,
                "type": n.get("type") or "",
                "started_at": n.get("createdAt") or "",
                "broadcaster_id": broadcaster.get("id") or "",
                "broadcaster_login": broadcaster.get("login") or "",
                "broadcaster_display_name": broadcaster.get("displayName") or "",
                "game_id": game.get("id") or "",
                "game_name": game.get("name") or "",
                "game_slug": game.get("slug") or "",
                "game_box_art_url": game.get("boxArtURL") or "",
                "preview_image_url": n.get("previewImageURL") or "",
                "url": f"https://www.twitch.tv/{broadcaster.get('login') or ''}",
            })
        return results

    def search_users(self, query: str, first: int = 10) -> List[Dict]:
        """按用户名搜索。query 是 userQuery（注意参数名是 userQuery 不是 query）。

        通过 stream 字段是否非空判断 is_live。
        """
        q = (
            "query($userQuery: String!, $first: Int!) {"
            "  searchUsers(userQuery: $userQuery, first: $first) {"
            "    edges { node {"
            "      id login displayName description"
            "      profileImageURL(width: 150)"
            "      followers { totalCount }"
            "      stream { id }"
            "    } }"
            "  }"
            "}"
        )
        try:
            data = _post_gql(_DEFAULT_CLIENT_ID, q, {"userQuery": query, "first": first})
        except Exception as e:
            return [{"error": f"search_users failed: {e}"}]
        if "errors" in data:
            return [{"error": data["errors"][0].get("message", "GQL error")}]
        results = []
        for edge in (data.get("data", {}).get("searchUsers", {}) or {}).get("edges", []):
            n = edge.get("node") or {}
            results.append({
                "id": n.get("id") or "",
                "login": n.get("login") or "",
                "display_name": n.get("displayName") or "",
                "description": n.get("description") or "",
                "profile_image_url": n.get("profileImageURL") or "",
                "followers_count": (n.get("followers") or {}).get("totalCount") or 0,
                "is_live": n.get("stream") is not None,
                "url": f"https://www.twitch.tv/{n.get('login') or ''}",
            })
        return results

    def get_games(self, first: int = 20) -> List[Dict]:
        """获取热门游戏分类（默认按观众数降序）。"""
        q = (
            "query($first: Int!) {"
            "  games(first: $first) {"
            "    edges { node {"
            "      id name slug viewersCount boxArtURL(width: 285, height: 380)"
            "    } }"
            "  }"
            "}"
        )
        try:
            data = _post_gql(_DEFAULT_CLIENT_ID, q, {"first": first})
        except Exception as e:
            return [{"error": f"get_games failed: {e}"}]
        if "errors" in data:
            return [{"error": data["errors"][0].get("message", "GQL error")}]
        results = []
        for edge in (data.get("data", {}).get("games", {}) or {}).get("edges", []):
            n = edge.get("node") or {}
            results.append({
                "id": n.get("id", ""),
                "name": n.get("name", ""),
                "slug": n.get("slug", ""),
                "viewer_count": n.get("viewersCount", 0),
                "box_art_url": n.get("boxArtURL", ""),
            })
        return results

    def get_videos(self, login: str, first: int = 10) -> List[Dict]:
        """获取用户视频(VOD)，按发布时间降序。"""
        q = (
            "query($login: String!, $first: Int!) {"
            "  user(login: $login) {"
            "    id login displayName"
            "    videos(first: $first) {"
            "      edges { node {"
            "        id title viewCount lengthSeconds createdAt publishedAt"
            "        previewThumbnailURL(width: 320, height: 180)"
            "        game { id name }"
            "      } }"
            "    }"
            "  }"
            "}"
        )
        try:
            data = _post_gql(_DEFAULT_CLIENT_ID, q, {"login": login, "first": first})
        except Exception as e:
            return [{"error": f"get_videos failed: {e}"}]
        if "errors" in data:
            return [{"error": data["errors"][0].get("message", "GQL error")}]
        user = data.get("data", {}).get("user")
        if not user:
            return [{"error": f"user not found: {login}"}]
        results = []
        for edge in (user.get("videos", {}) or {}).get("edges", []):
            n = edge.get("node") or {}
            game = n.get("game") or {}
            results.append({
                "id": n.get("id", ""),
                "title": n.get("title", ""),
                "view_count": n.get("viewCount", 0),
                "length_seconds": n.get("lengthSeconds", 0),
                "created_at": n.get("createdAt", ""),
                "published_at": n.get("publishedAt", ""),
                "thumbnail_url": n.get("previewThumbnailURL", ""),
                "game_id": game.get("id", ""),
                "game_name": game.get("name", ""),
            })
        return results

    def get_top_games(self, first: int = 10, after: Optional[str] = None) -> List[Dict]:
        """Top games 排行（支持分页）。

        after: pagination cursor（上一页最后一条的 cursor）。
        """
        q = (
            "query($first: Int!, $after: Cursor) {"
            "  gameDirectoryPage(first: $first, after: $after) {"
            "    edges { cursor node {"
            "      id name slug viewersCount boxArtURL(width: 285, height: 380)"
            "    } }"
            "    pageInfo { hasNextPage endCursor }"
            "  }"
            "}"
        )
        try:
            data = _post_gql(_DEFAULT_CLIENT_ID, q, {"first": first, "after": after})
        except Exception as e:
            return [{"error": f"get_top_games failed: {e}"}]
        if "errors" in data:
            return [{"error": data["errors"][0].get("message", "GQL error")}]
        page = data.get("data", {}).get("gameDirectoryPage", {}) or {}
        results = []
        for edge in (page.get("edges") or []):
            n = edge.get("node") or {}
            results.append({
                "id": n.get("id", ""),
                "name": n.get("name", ""),
                "slug": n.get("slug", ""),
                "viewer_count": n.get("viewersCount", 0),
                "box_art_url": n.get("boxArtURL", ""),
                "cursor": edge.get("cursor", ""),
            })
        return results

    # ------------------------------------------------------------------ #
    # URL-based reader
    # ------------------------------------------------------------------ #

    def read(self, url: str) -> Dict:
        """Read a Twitch URL: channel page or video page.

        https://www.twitch.tv/{login}            -> user profile
        https://www.twitch.tv/videos/{video_id}  -> video metadata
        """
        from urllib.parse import urlparse

        parts = [p for p in urlparse(url).path.split("/") if p]
        if not parts:
            return {"error": f"unsupported Twitch URL: {url}"}
        # /videos/{id}
        if parts[0] == "videos" and len(parts) >= 2:
            return {
                "error": "video metadata 需要额外 GQL 调用（video(id)），本方法未实现",
                "video_id": parts[1],
                "url": url,
            }
        # /{login} (channel page)
        return self.get_user(parts[0])
