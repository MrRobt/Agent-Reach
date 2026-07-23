# -*- coding: utf-8 -*-
"""Threads — Meta Graph API for profiles, posts, and search.

需要 Access Token（user 或 page token）。获取流程：
  1. 在 https://developers.facebook.com/apps/ 创建 App
  2. 添加 "Threads" 产品（需 App Review，可能 1-2 周）
  3. 用 Graph API Explorer 生成 Access Token
  4. 设置环境变量 THREADS_ACCESS_TOKEN

环境变量：
  THREADS_ACCESS_TOKEN

Tier 2 — 需 App Review。

参考：https://developers.facebook.com/docs/threads
"""

import json
import os
import urllib.request
import urllib.parse
from typing import Any, Dict, List, Optional

from .base import Channel

_UA = "agent-reach/1.0 (threads channel)"
_TIMEOUT = 10
_BASE = "https://graph.threads.net/v1.0"


def _get_json(url: str, token: str) -> Any:
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": _UA,
            "Authorization": f"Bearer {token}",
        },
    )
    with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:
        return json.loads(resp.read().decode("utf-8"))


class ThreadsChannel(Channel):
    name = "threads"
    description = "Threads 帖子、Profile 与搜索（Meta Graph API）"
    backends = ["Threads Graph API"]
    tier = 2

    def can_handle(self, url: str) -> bool:
        from urllib.parse import urlparse
        d = urlparse(url).netloc.lower()
        return "threads.net" in d or "threads.com" in d

    def check(self, config=None):  # noqa: ARG002
        token = os.environ.get("THREADS_ACCESS_TOKEN")
        if not token:
            self.active_backend = None
            return "warn", (
                "Threads 未配置。获取 Access Token：\n"
                "  1. 在 https://developers.facebook.com/apps/ 创建 App + 加 Threads 产品\n"
                "  2. Graph API Explorer 拿 token\n"
                "  3. export THREADS_ACCESS_TOKEN=\"你的_token\"\n"
                "  4. 重跑 agent-reach doctor"
            )

        # Probe with /me
        try:
            data = _get_json(f"{_BASE}/me?fields=id,username", token)
            self.active_backend = self.backends[0]
            return "ok", (
                f"Threads Graph API 可用（当前账号：@{data.get('username', '?')}）。"
                f"完整文档：https://developers.facebook.com/docs/threads"
            )
        except Exception as e:
            self.active_backend = None
            return "error", f"Threads API 探测失败：{e}"

    def _auth(self) -> str:
        token = os.environ.get("THREADS_ACCESS_TOKEN", "")
        if not token:
            raise RuntimeError("Threads 未配置（设 THREADS_ACCESS_TOKEN）")
        return token

    # ------------------------------------------------------------------ #
    # Data methods
    # ------------------------------------------------------------------ #

    def get_user_profile(self, user_id: str = "me") -> Dict:
        """获取用户 profile。user_id 默认 me（当前 token 对应的账号）。"""
        token = self._auth()
        fields = "id,username,name,threads_profile_picture_url,threads_biography"
        url = f"{_BASE}/{user_id}?fields={fields}"
        try:
            u = _get_json(url, token)
        except Exception as e:
            return {"error": f"get_user_profile failed: {e}"}
        return {
            "id": u.get("id", ""),
            "username": u.get("username", ""),
            "name": u.get("name", ""),
            "biography": u.get("threads_biography", ""),
            "profile_picture_url": u.get("threads_profile_picture_url", ""),
            "url": f"https://www.threads.net/@{u.get('username', '')}",
        }

    def get_user_threads(self, user_id: str = "me", limit: int = 25,
                         fields: Optional[str] = None) -> List[Dict]:
        """获取用户帖子列表。user_id 默认 me。"""
        token = self._auth()
        if not fields:
            fields = (
                "id,media_product_type,media_type,media_url,permalink,"
                "text,username,timestamp,shortcode,thumbnail_url,"
                "is_quote_post,has_replies,like_count,reply_count,repost_count,quote_count"
            )
        params = {"fields": fields, "limit": limit}
        url = f"{_BASE}/{user_id}/threads?{urllib.parse.urlencode(params)}"
        try:
            data = _get_json(url, token)
        except Exception as e:
            return [{"error": f"get_user_threads failed: {e}"}]
        results = []
        for p in (data.get("data") or []):
            results.append({
                "id": p.get("id", ""),
                "media_product_type": p.get("media_product_type", ""),
                "media_type": p.get("media_type", ""),
                "media_url": p.get("media_url", ""),
                "permalink": p.get("permalink", ""),
                "text": p.get("text", ""),
                "username": p.get("username", ""),
                "timestamp": p.get("timestamp", ""),
                "shortcode": p.get("shortcode", ""),
                "thumbnail_url": p.get("thumbnail_url", ""),
                "is_quote_post": p.get("is_quote_post", False),
                "has_replies": p.get("has_replies", False),
                "like_count": p.get("like_count", 0),
                "reply_count": p.get("reply_count", 0),
                "repost_count": p.get("repost_count", 0),
                "quote_count": p.get("quote_count", 0),
                "url": p.get("permalink", ""),
            })
        return results

    def search(self, query: str, search_type: str = "TOP", limit: int = 25) -> List[Dict]:
        """搜索公开帖子（2024-10 后开放，需 App 启用 search 权限）。

        search_type: TOP（热门） / RECENT（最新）
        """
        token = self._auth()
        fields = (
            "id,media_product_type,media_type,media_url,permalink,"
            "text,username,timestamp,like_count,reply_count"
        )
        params = {
            "q": query,
            "search_type": search_type,
            "fields": fields,
            "limit": limit,
        }
        url = f"{_BASE}/search?{urllib.parse.urlencode(params)}"
        try:
            data = _get_json(url, token)
        except Exception as e:
            return [{"error": f"search failed: {e}"}]
        results = []
        for p in (data.get("data") or []):
            results.append({
                "id": p.get("id", ""),
                "media_type": p.get("media_type", ""),
                "media_url": p.get("media_url", ""),
                "permalink": p.get("permalink", ""),
                "text": p.get("text", ""),
                "username": p.get("username", ""),
                "timestamp": p.get("timestamp", ""),
                "like_count": p.get("like_count", 0),
                "reply_count": p.get("reply_count", 0),
                "url": p.get("permalink", ""),
            })
        return results
