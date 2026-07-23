# -*- coding: utf-8 -*-
"""Twitch — Helix API for users, streams, videos, and games.

需要 Client ID + Client Secret（OAuth Client Credentials flow）。
获取方式：https://dev.twitch.tv/console/apps 注册 Application → 拿到 Client ID/Secret。

环境变量：
  TWITCH_CLIENT_ID
  TWITCH_CLIENT_SECRET

Tier 1 — 需免费 key。Token 自动缓存到 ~/.agent-reach/twitch_token.json。
"""

import json
import os
import time
import urllib.request
import urllib.parse
from pathlib import Path
from typing import Any, Dict, List, Optional

from .base import Channel

_UA = "agent-reach/1.0 (twitch channel)"
_TIMEOUT = 10
_BASE = "https://api.twitch.tv/helix"
_TOKEN_URL = "https://id.twitch.tv/oauth2/token"
_TOKEN_CACHE = Path.home() / ".agent-reach" / "twitch_token.json"


def _post_form(url: str, data: dict) -> Any:
    """POST application/x-www-form-urlencoded. Returns parsed JSON."""
    body = urllib.parse.urlencode(data).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=body,
        headers={
            "User-Agent": _UA,
            "Content-Type": "application/x-www-form-urlencoded",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _get_json(url: str, client_id: str, token: str) -> Any:
    """Authenticated GET."""
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": _UA,
            "Authorization": f"Bearer {token}",
            "Client-Id": client_id,
        },
    )
    with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:
        return json.loads(resp.read().decode("utf-8"))


class TwitchChannel(Channel):
    name = "twitch"
    description = "Twitch 用户、直播、视频与游戏搜索"
    backends = ["Twitch Helix API"]
    tier = 1

    def can_handle(self, url: str) -> bool:
        from urllib.parse import urlparse
        d = urlparse(url).netloc.lower()
        return "twitch.tv" in d

    # ------------------------------------------------------------------ #
    # Token management
    # ------------------------------------------------------------------ #

    def _get_token(self, client_id: str, client_secret: str) -> Optional[str]:
        """Return cached or freshly-fetched app access token."""
        # Try cache
        if _TOKEN_CACHE.exists():
            try:
                cached = json.loads(_TOKEN_CACHE.read_text())
                if cached.get("expires_at", 0) > time.time() + 60:
                    return cached.get("token")
            except Exception:
                pass

        # Fetch new
        try:
            data = _post_form(
                _TOKEN_URL,
                {
                    "client_id": client_id,
                    "client_secret": client_secret,
                    "grant_type": "client_credentials",
                },
            )
        except Exception:
            return None

        token = data.get("access_token")
        if not token:
            return None

        # Cache (expires_in is seconds; default 3600)
        _TOKEN_CACHE.parent.mkdir(parents=True, exist_ok=True)
        _TOKEN_CACHE.write_text(
            json.dumps(
                {
                    "token": token,
                    "expires_at": time.time() + int(data.get("expires_in", 3600)),
                }
            )
        )
        return token

    # ------------------------------------------------------------------ #
    # Health check
    # ------------------------------------------------------------------ #

    def check(self, config=None):  # noqa: ARG002
        client_id = os.environ.get("TWITCH_CLIENT_ID")
        client_secret = os.environ.get("TWITCH_CLIENT_SECRET")
        if not client_id or not client_secret:
            self.active_backend = None
            return "warn", (
                "Twitch 未配置。申请 Client ID/Secret：\n"
                "  1. 打开 https://dev.twitch.tv/console/apps 注册 Application\n"
                "  2. 设置环境变量：\n"
                "       export TWITCH_CLIENT_ID=\"你的_client_id\"\n"
                "       export TWITCH_CLIENT_SECRET=\"你的_client_secret\"\n"
                "  3. 重跑 agent-reach doctor"
            )

        token = self._get_token(client_id, client_secret)
        if not token:
            self.active_backend = None
            return "error", "Twitch OAuth 获取 token 失败（client_id/secret 错或网络不通）"

        # Probe with a lightweight users call
        try:
            _get_json(f"{_BASE}/users?login=twitch", client_id, token)
            self.active_backend = self.backends[0]
            return "ok", "Twitch Helix API 可用（用户/直播/视频/游戏搜索）。"
        except Exception as e:
            self.active_backend = None
            return "error", f"Twitch API 探测失败：{e}"

    # ------------------------------------------------------------------ #
    # Data methods
    # ------------------------------------------------------------------ #

    def _auth(self):
        cid = os.environ.get("TWITCH_CLIENT_ID", "")
        sec = os.environ.get("TWITCH_CLIENT_SECRET", "")
        token = self._get_token(cid, sec) if cid and sec else None
        if not (cid and token):
            raise RuntimeError("Twitch 未配置（设 TWITCH_CLIENT_ID + TWITCH_CLIENT_SECRET）")
        return cid, token

    def get_user(self, login: str) -> Dict:
        """按 login 查用户。"""
        cid, token = self._auth()
        url = f"{_BASE}/users?login={urllib.parse.quote(login)}"
        try:
            data = _get_json(url, cid, token)
        except Exception as e:
            return {"error": f"get_user failed: {e}"}
        users = data.get("data") or []
        if not users:
            return {"error": f"user not found: {login}"}
        u = users[0]
        return {
            "id": u.get("id", ""),
            "login": u.get("login", ""),
            "display_name": u.get("display_name", ""),
            "type": u.get("type", ""),
            "broadcaster_type": u.get("broadcaster_type", ""),
            "description": u.get("description", ""),
            "profile_image_url": u.get("profile_image_url", ""),
            "offline_image_url": u.get("offline_image_url", ""),
            "view_count": u.get("view_count", 0),
            "created_at": u.get("created_at", ""),
            "url": f"https://www.twitch.tv/{u.get('login', '')}",
        }

    def get_streams(self, game_id: Optional[str] = None, user_login: Optional[str] = None,
                    language: Optional[str] = None, first: int = 20) -> List[Dict]:
        """获取直播流列表。可按 game_id / user_login / language 过滤。"""
        cid, token = self._auth()
        params: Dict[str, Any] = {"first": first}
        if game_id: params["game_id"] = game_id
        if user_login: params["user_login"] = user_login
        if language: params["language"] = language
        url = f"{_BASE}/streams?{urllib.parse.urlencode(params)}"
        try:
            data = _get_json(url, cid, token)
        except Exception as e:
            return [{"error": f"get_streams failed: {e}"}]
        results = []
        for s in (data.get("data") or []):
            results.append({
                "id": s.get("id", ""),
                "user_id": s.get("user_id", ""),
                "user_login": s.get("user_login", ""),
                "user_name": s.get("user_name", ""),
                "game_id": s.get("game_id", ""),
                "game_name": s.get("game_name", ""),
                "type": s.get("type", ""),
                "title": s.get("title", ""),
                "viewer_count": s.get("viewer_count", 0),
                "started_at": s.get("started_at", ""),
                "language": s.get("language", ""),
                "thumbnail_url": s.get("thumbnail_url", "").replace("{width}", "320").replace("{height}", "180"),
                "url": f"https://www.twitch.tv/{s.get('user_login', '')}",
            })
        return results

    def search_categories(self, query: str, first: int = 10) -> List[Dict]:
        """搜游戏分类（categories = games on Twitch）。"""
        cid, token = self._auth()
        params = {"query": query, "first": first}
        url = f"{_BASE}/search/categories?{urllib.parse.urlencode(params)}"
        try:
            data = _get_json(url, cid, token)
        except Exception as e:
            return [{"error": f"search_categories failed: {e}"}]
        results = []
        for c in (data.get("data") or []):
            results.append({
                "id": c.get("id", ""),
                "name": c.get("name", ""),
                "box_art_url": (c.get("box_art_url") or "").replace("{width}", "285").replace("{height}", "380"),
            })
        return results

    def get_videos(self, user_id: str, first: int = 10, sort: str = "time") -> List[Dict]:
        """获取用户视频(VOD)。sort: time / views / trending"""
        cid, token = self._auth()
        params = {"user_id": user_id, "first": first, "sort": sort, "type": "archive"}
        url = f"{_BASE}/videos?{urllib.parse.urlencode(params)}"
        try:
            data = _get_json(url, cid, token)
        except Exception as e:
            return [{"error": f"get_videos failed: {e}"}]
        results = []
        for v in (data.get("data") or []):
            results.append({
                "id": v.get("id", ""),
                "user_id": v.get("user_id", ""),
                "user_login": v.get("user_login", ""),
                "user_name": v.get("user_name", ""),
                "title": v.get("title", ""),
                "description": v.get("description", ""),
                "created_at": v.get("created_at", ""),
                "published_at": v.get("published_at", ""),
                "url": v.get("url", ""),
                "thumbnail_url": (v.get("thumbnail_url") or "").replace("%{width}", "320").replace("%{height}", "180"),
                "view_count": v.get("view_count", 0),
                "duration": v.get("duration", ""),
                "type": v.get("type", ""),
            })
        return results
