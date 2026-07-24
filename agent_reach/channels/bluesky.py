# -*- coding: utf-8 -*-
"""Bluesky — atproto 公开 API for posts, profiles, and search.

公开 API（public.api.bsky.app），无需认证。适合：搜用户/帖子、读 Profile、读帖子。
Tier 0，零配置。

官方文档：https://docs.bsky.app/docs/api/at-protocol-xrpc-api
"""

import json
import urllib.error
import urllib.request
import urllib.parse
from typing import Any, Dict, List

from .base import Channel

_UA = "agent-reach/1.0"
_TIMEOUT = 10
_BASE = "https://public.api.bsky.app/xrpc"


def _get_json(url: str) -> Any:
    """Fetch *url* and return parsed JSON. Raises on HTTP/network errors."""
    req = urllib.request.Request(url, headers={"User-Agent": _UA})
    with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:
        return json.loads(resp.read().decode("utf-8"))


class BlueskyChannel(Channel):
    name = "bluesky"
    description = "Bluesky 帖子、Profile 与搜索"
    backends = ["atproto public API"]
    tier = 0

    # ------------------------------------------------------------------ #
    # URL routing
    # ------------------------------------------------------------------ #

    def can_handle(self, url: str) -> bool:
        from urllib.parse import urlparse
        d = urlparse(url).netloc.lower()
        return "bsky.app" in d or "bsky.social" in d

    # ------------------------------------------------------------------ #
    # Health check
    # ------------------------------------------------------------------ #

    def check(self, config=None):  # noqa: ARG002 — config not used (public API)
        try:
            _get_json(f"{_BASE}/app.bsky.actor.searchActors?q=agent&limit=1")
            self.active_backend = self.backends[0]
            return "ok", (
                "atproto 公开 API 可用（搜索用户/帖子、读 Profile、读帖子）。"
                "无需认证。"
            )
        except Exception as e:
            self.active_backend = None
            return "warn", f"Bluesky API 连接失败（可能需要代理）：{e}"

    # ------------------------------------------------------------------ #
    # Data methods
    # ------------------------------------------------------------------ #

    def search_posts(self, query: str, limit: int = 20) -> List[Dict]:
        """搜索帖子。

        Returns list of dicts:
          uri, cid, author_handle, author_display_name, text, created_at,
          like_count, reply_count, repost_count, quote_count, indexed_at, url

        Retry policy: BSky 的反爬偶尔返回 403（IP 限流），加 2 次重试 + 指数退避。
        """
        url = (
            f"{_BASE}/app.bsky.feed.searchPosts"
            f"?q={urllib.parse.quote(query)}&limit={limit}"
        )
        last_error = None
        for attempt in range(3):
            try:
                data = _get_json(url)
                break
            except urllib.error.HTTPError as e:
                last_error = f"HTTP {e.code}: {e.reason}"
                if e.code == 403 and attempt < 2:
                    # 风控临时封禁，等 2-4-8 秒重试
                    import time as _time
                    _time.sleep(2 ** (attempt + 1))
                    continue
                return [{"error": f"search_posts failed: {last_error}"}]
            except Exception as e:
                return [{"error": f"search_posts failed: {e}"}]
        else:
            return [{"error": f"search_posts failed after 3 retries: {last_error}"}]
        results = []
        for p in (data.get("posts") or []):
            author = p.get("author") or {}
            record = p.get("record") or {}
            rkey = p.get("uri", "").split("/")[-1] if p.get("uri") else ""
            results.append(
                {
                    "uri": p.get("uri", ""),
                    "cid": p.get("cid", ""),
                    "author_handle": author.get("handle", ""),
                    "author_display_name": author.get("displayName", ""),
                    "text": record.get("text", ""),
                    "created_at": record.get("createdAt", ""),
                    "like_count": p.get("likeCount", 0),
                    "reply_count": p.get("replyCount", 0),
                    "repost_count": p.get("repostCount", 0),
                    "quote_count": p.get("quoteCount", 0),
                    "indexed_at": p.get("indexedAt", ""),
                    "url": f"https://bsky.app/profile/{author.get('handle', '')}/post/{rkey}",
                }
            )
        return results

    def search_actors(self, query: str, limit: int = 20) -> List[Dict]:
        """搜索用户（actor）。

        Returns list of dicts:
          did, handle, display_name, description, avatar, followers_count,
          follows_count, posts_count, indexed_at, url
        """
        url = (
            f"{_BASE}/app.bsky.actor.searchActors"
            f"?q={urllib.parse.quote(query)}&limit={limit}"
        )
        try:
            data = _get_json(url)
        except Exception as e:
            return [{"error": f"search_actors failed: {e}"}]
        results = []
        for a in (data.get("actors") or []):
            results.append(
                {
                    "did": a.get("did", ""),
                    "handle": a.get("handle", ""),
                    "display_name": a.get("displayName", ""),
                    "description": a.get("description", ""),
                    "avatar": a.get("avatar", ""),
                    "followers_count": a.get("followersCount", 0),
                    "follows_count": a.get("followsCount", 0),
                    "posts_count": a.get("postsCount", 0),
                    "indexed_at": a.get("indexedAt", ""),
                    "url": f"https://bsky.app/profile/{a.get('handle', '')}",
                }
            )
        return results

    def get_profile(self, handle: str) -> Dict:
        """获取用户 profile。handle 如 'alice.bsky.social' 或 DID。"""
        url = f"{_BASE}/app.bsky.actor.getProfile?actor={urllib.parse.quote(handle)}"
        try:
            a = _get_json(url)
        except Exception as e:
            return {"error": f"get_profile failed: {e}"}
        return {
            "did": a.get("did", ""),
            "handle": a.get("handle", ""),
            "display_name": a.get("displayName", ""),
            "description": a.get("description", ""),
            "avatar": a.get("avatar", ""),
            "banner": a.get("banner", ""),
            "followers_count": a.get("followersCount", 0),
            "follows_count": a.get("followsCount", 0),
            "posts_count": a.get("postsCount", 0),
            "indexed_at": a.get("indexedAt", ""),
            "url": f"https://bsky.app/profile/{a.get('handle', '')}",
        }

    def get_post_thread(self, uri: str, depth: int = 5) -> Dict:
        """获取单帖 + 父级 + 子回复。uri 是 at:// URI。"""
        url = (
            f"{_BASE}/app.bsky.feed.getPostThread"
            f"?uri={urllib.parse.quote(uri, safe='')}&depth={depth}"
        )
        try:
            data = _get_json(url)
        except Exception as e:
            return {"error": f"get_post_thread failed: {e}"}
        thread = data.get("thread") or {}
        post = thread.get("post") or {}
        author = post.get("author") or {}
        record = post.get("record") or {}
        rkey = post.get("uri", "").split("/")[-1] if post.get("uri") else ""
        return {
            "uri": post.get("uri", ""),
            "cid": post.get("cid", ""),
            "author_handle": author.get("handle", ""),
            "author_display_name": author.get("displayName", ""),
            "text": record.get("text", ""),
            "created_at": record.get("createdAt", ""),
            "like_count": post.get("likeCount", 0),
            "reply_count": post.get("replyCount", 0),
            "repost_count": post.get("repostCount", 0),
            "indexed_at": post.get("indexedAt", ""),
            "url": (
                f"https://bsky.app/profile/{author.get('handle', '')}"
                f"/post/{rkey}"
            ),
            "replies_count_in_thread": len(thread.get("replies") or []),
        }

    # ------------------------------------------------------------------ #
    # URL-based reader
    # ------------------------------------------------------------------ #

    def read(self, url: str) -> Dict:
        """Read a single post URL or profile URL.

        Supported shapes:
          https://bsky.app/profile/{handle}/post/{rkey}
          https://bsky.app/profile/{handle}
        """
        from urllib.parse import urlparse

        parts = [p for p in urlparse(url).path.split("/") if p]
        if len(parts) >= 4 and parts[0] == "profile" and parts[2] == "post":
            handle, rkey = parts[1], parts[3]
            uri = f"at://{handle}/app.bsky.feed.post/{rkey}"
            return self.get_post_thread(uri)
        if len(parts) >= 2 and parts[0] == "profile":
            return self.get_profile(parts[1])
        return {"error": f"unsupported bluesky URL: {url}"}
