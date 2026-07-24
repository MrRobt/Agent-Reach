# -*- coding: utf-8 -*-
"""Tests for the 4 new channels: Bluesky, Twitch (GQL), Threads, TikTok.

Covers:
  - can_handle URL matching
  - check() status / message / active_backend branches (offline, ok, error, no-creds)
  - data method error handling (network errors, malformed responses)
  - return type contracts (list[dict] / dict with error key)

These tests use mock to avoid hitting live APIs in CI.
"""

import json
from unittest.mock import patch, MagicMock
from urllib.error import URLError, HTTPError

import pytest


# =====================================================================
# Bluesky
# =====================================================================

class TestBlueskyChannel:
    """atproto 公开 API channel."""

    def test_can_handle_matches_bluesky_hosts(self):
        from agent_reach.channels.bluesky import BlueskyChannel
        ch = BlueskyChannel()
        for url in [
            "https://bsky.app/profile/alice.bsky.social",
            "https://bsky.app/profile/alice.bsky.social/post/3k...",
            "https://BSKY.APP/profile/x",
        ]:
            assert ch.can_handle(url) is True, url
        for url in ["https://example.com", "https://twitter.com/x", ""]:
            assert ch.can_handle(url) is False, url

    def test_check_ok_when_api_reachable(self):
        from agent_reach.channels.bluesky import BlueskyChannel, _get_json
        ch = BlueskyChannel()
        with patch.object(_get_json.__module__ and __import__("agent_reach.channels.bluesky", fromlist=["_get_json"]),
                          "_get_json", return_value={"actors": []}):
            # Fallback: directly patch via module
            pass
        # Use module-level patch
        with patch("agent_reach.channels.bluesky._get_json", return_value={"actors": []}):
            status, msg = ch.check()
        assert status == "ok"
        assert "atproto" in msg
        assert ch.active_backend == "atproto public API"

    def test_check_warn_when_network_unreachable(self):
        from agent_reach.channels.bluesky import BlueskyChannel
        ch = BlueskyChannel()
        with patch("agent_reach.channels.bluesky._get_json",
                   side_effect=URLError("timed out")):
            status, msg = ch.check()
        assert status == "warn"
        assert ch.active_backend is None
        assert "代理" in msg or "timeout" in msg.lower() or "timed" in msg.lower()

    def test_search_actors_returns_list(self):
        from agent_reach.channels.bluesky import BlueskyChannel
        ch = BlueskyChannel()
        mock_data = {
            "actors": [
                {
                    "did": "did:plc:abc",
                    "handle": "test.bsky.social",
                    "displayName": "Test",
                    "description": "hello",
                    "avatar": "https://cdn.bsky.app/avatar.jpg",
                    "followersCount": 100,
                    "followsCount": 50,
                    "postsCount": 10,
                    "indexedAt": "2026-01-01T00:00:00Z",
                }
            ]
        }
        with patch("agent_reach.channels.bluesky._get_json", return_value=mock_data):
            results = ch.search_actors("test", limit=1)
        assert len(results) == 1
        assert results[0]["handle"] == "test.bsky.social"
        assert results[0]["followers_count"] == 100
        assert results[0]["url"] == "https://bsky.app/profile/test.bsky.social"

    def test_search_actors_handles_error(self):
        from agent_reach.channels.bluesky import BlueskyChannel
        ch = BlueskyChannel()
        with patch("agent_reach.channels.bluesky._get_json",
                   side_effect=URLError("network")):
            results = ch.search_actors("test")
        assert isinstance(results, list)
        assert "error" in results[0]

    def test_read_url_post(self):
        from agent_reach.channels.bluesky import BlueskyChannel
        ch = BlueskyChannel()
        mock_thread = {
            "thread": {
                "post": {
                    "uri": "at://alice.bsky.social/app.bsky.feed.post/3k",
                    "cid": "bafy",
                    "author": {"handle": "alice.bsky.social", "displayName": "Alice"},
                    "record": {"text": "hello", "createdAt": "2026-01-01T00:00:00Z"},
                    "likeCount": 10, "replyCount": 2, "repostCount": 1, "indexedAt": "2026-01-01T00:00:00Z",
                },
                "replies": [],
            }
        }
        with patch("agent_reach.channels.bluesky._get_json", return_value=mock_thread):
            result = ch.read("https://bsky.app/profile/alice.bsky.social/post/3k")
        assert "error" not in result
        assert result["author_handle"] == "alice.bsky.social"
        assert result["text"] == "hello"

    def test_read_url_unsupported(self):
        from agent_reach.channels.bluesky import BlueskyChannel
        ch = BlueskyChannel()
        result = ch.read("https://bsky.app/some/other/path")
        assert "error" in result


# =====================================================================
# Twitch (GQL)
# =====================================================================

class TestTwitchChannel:
    """Twitch 私有 GQL channel."""

    def test_can_handle_matches_twitch_hosts(self):
        from agent_reach.channels.twitch import TwitchChannel
        ch = TwitchChannel()
        for url in [
            "https://www.twitch.tv/ninja",
            "https://twitch.tv/videos/12345",
            "https://m.twitch.tv/some-streamer",
        ]:
            assert ch.can_handle(url) is True, url
        for url in ["https://example.com", "https://youtube.com/x", ""]:
            assert ch.can_handle(url) is False, url

    def test_check_ok_when_gql_responds(self):
        from agent_reach.channels.twitch import TwitchChannel
        ch = TwitchChannel()
        with patch("agent_reach.channels.twitch._post_gql",
                   return_value={"data": {"user": {"id": "1", "login": "twitch"}}}):
            status, msg = ch.check()
        assert status == "ok"
        assert ch.active_backend == "Twitch GQL (anon)"
        assert "GQL" in msg

    def test_check_error_when_client_id_invalid(self):
        from agent_reach.channels.twitch import TwitchChannel
        ch = TwitchChannel()
        with patch("agent_reach.channels.twitch._post_gql",
                   return_value={"errors": [{"message": "Invalid client ID"}]}):
            status, msg = ch.check()
        assert status == "error"
        assert ch.active_backend is None
        assert "Client-ID" in msg or "轮换" in msg

    def test_check_warn_when_network_unreachable(self):
        from agent_reach.channels.twitch import TwitchChannel
        ch = TwitchChannel()
        with patch("agent_reach.channels.twitch._post_gql",
                   side_effect=URLError("timed out")):
            status, msg = ch.check()
        assert status == "warn"
        assert ch.active_backend is None

    def test_get_user_returns_full_profile(self):
        from agent_reach.channels.twitch import TwitchChannel
        ch = TwitchChannel()
        mock_data = {
            "data": {
                "user": {
                    "id": "19571641",
                    "login": "ninja",
                    "displayName": "Ninja",
                    "description": "streamer",
                    "createdAt": "2011-01-16T04:31:20Z",
                    "profileImageURL": "https://x.png",
                    "bannerImageURL": "https://y.png",
                    "followers": {"totalCount": 19251139},
                    "roles": {"isPartner": True, "isAffiliate": False, "isStaff": None},
                    "channel": {"id": "12345"},
                }
            }
        }
        with patch("agent_reach.channels.twitch._post_gql", return_value=mock_data):
            u = ch.get_user("ninja")
        assert u["login"] == "ninja"
        assert u["followers_count"] == 19251139
        assert u["is_partner"] is True
        assert u["url"] == "https://www.twitch.tv/ninja"

    def test_get_user_handles_not_found(self):
        from agent_reach.channels.twitch import TwitchChannel
        ch = TwitchChannel()
        with patch("agent_reach.channels.twitch._post_gql",
                   return_value={"data": {"user": None}}):
            u = ch.get_user("nonexistent_user_xyz")
        assert "error" in u

    def test_get_streams_returns_list(self):
        from agent_reach.channels.twitch import TwitchChannel
        ch = TwitchChannel()
        mock_data = {
            "data": {
                "streams": {
                    "edges": [
                        {
                            "node": {
                                "id": "123",
                                "title": "live stream",
                                "viewersCount": 5000,
                                "type": "live",
                                "createdAt": "2026-07-23T08:00:00Z",
                                "game": {"id": "g1", "name": "IRL", "slug": "irl", "boxArtURL": "https://box.jpg"},
                                "broadcaster": {"id": "b1", "login": "streamer1", "displayName": "Streamer1"},
                                "previewImageURL": "https://preview.jpg",
                            }
                        }
                    ]
                }
            }
        }
        with patch("agent_reach.channels.twitch._post_gql", return_value=mock_data):
            streams = ch.get_streams(first=1)
        assert len(streams) == 1
        assert streams[0]["viewer_count"] == 5000
        assert streams[0]["game_name"] == "IRL"
        assert streams[0]["url"] == "https://www.twitch.tv/streamer1"

    def test_search_users_uses_userQuery_param(self):
        """searchUsers 字段是 userQuery,不是 query(常见错)。"""
        from agent_reach.channels.twitch import TwitchChannel, _DEFAULT_CLIENT_ID
        ch = TwitchChannel()
        captured = {}

        def fake_post(client_id, query, variables=None):
            captured["variables"] = variables
            return {
                "data": {
                    "searchUsers": {
                        "edges": [
                            {
                                "node": {
                                    "id": "1", "login": "riotgames", "displayName": "Riot Games",
                                    "description": "games", "profileImageURL": "",
                                    "followers": {"totalCount": 7000000},
                                    "stream": None,
                                }
                            }
                        ]
                    }
                }
            }

        with patch("agent_reach.channels.twitch._post_gql", side_effect=fake_post):
            users = ch.search_users("riot", first=1)
        # 关键断言:用的是 userQuery,不是 query
        assert captured["variables"]["userQuery"] == "riot"
        assert "query" not in captured["variables"]
        assert users[0]["is_live"] is False
        assert users[0]["followers_count"] == 7000000


# =====================================================================
# Threads
# =====================================================================

class TestThreadsChannel:
    """Meta Graph API channel for Threads."""

    def test_can_handle_matches_threads_hosts(self):
        from agent_reach.channels.threads import ThreadsChannel
        ch = ThreadsChannel()
        for url in [
            "https://www.threads.net/@zuck",
            "https://threads.com/@meta",
            "https://www.threads.net/t/CuX7V2dBNZW",
        ]:
            assert ch.can_handle(url) is True, url
        for url in ["https://example.com", "https://twitter.com/x", ""]:
            assert ch.can_handle(url) is False, url

    def test_check_warn_when_no_token(self, monkeypatch):
        monkeypatch.delenv("THREADS_ACCESS_TOKEN", raising=False)
        from agent_reach.channels.threads import ThreadsChannel
        ch = ThreadsChannel()
        status, msg = ch.check()
        assert status == "warn"
        assert ch.active_backend is None
        assert "THREADS_ACCESS_TOKEN" in msg

    def test_check_ok_when_token_valid(self, monkeypatch):
        monkeypatch.setenv("THREADS_ACCESS_TOKEN", "fake_token_abc")
        from agent_reach.channels.threads import ThreadsChannel
        ch = ThreadsChannel()
        with patch("agent_reach.channels.threads._get_json",
                   return_value={"id": "1", "username": "test_user"}):
            status, msg = ch.check()
        assert status == "ok"
        assert ch.active_backend == "Threads Graph API"
        assert "@test_user" in msg

    def test_check_error_when_api_rejects_token(self, monkeypatch):
        monkeypatch.setenv("THREADS_ACCESS_TOKEN", "bad_token")
        from agent_reach.channels.threads import ThreadsChannel
        ch = ThreadsChannel()
        with patch("agent_reach.channels.threads._get_json",
                   side_effect=HTTPError(None, 401, "Unauthorized", None, None)):
            status, msg = ch.check()
        assert status == "error"
        assert ch.active_backend is None

    def test_get_user_profile(self, monkeypatch):
        monkeypatch.setenv("THREADS_ACCESS_TOKEN", "tok")
        from agent_reach.channels.threads import ThreadsChannel
        ch = ThreadsChannel()
        mock = {
            "id": "123",
            "username": "alice",
            "name": "Alice",
            "threads_biography": "bio here",
            "threads_profile_picture_url": "https://pic.jpg",
        }
        with patch("agent_reach.channels.threads._get_json", return_value=mock):
            u = ch.get_user_profile("me")
        assert u["username"] == "alice"
        assert u["url"] == "https://www.threads.net/@alice"

    def test_auth_raises_when_no_token(self, monkeypatch):
        monkeypatch.delenv("THREADS_ACCESS_TOKEN", raising=False)
        from agent_reach.channels.threads import ThreadsChannel
        ch = ThreadsChannel()
        with pytest.raises(RuntimeError, match="THREADS_ACCESS_TOKEN"):
            ch.get_user_profile("me")


# =====================================================================
# TikTok
# =====================================================================

class TestTikTokChannel:
    """TikTok HTML fetch (WAF-limited) channel."""

    def test_can_handle_matches_tiktok_hosts(self):
        from agent_reach.channels.tiktok import TikTokChannel
        ch = TikTokChannel()
        for url in [
            "https://www.tiktok.com/@charlidamelio",
            "https://tiktok.com/@user",
            "https://www.tiktok.com/video/12345",
        ]:
            assert ch.can_handle(url) is True, url
        for url in ["https://example.com", "https://youtube.com/x", ""]:
            assert ch.can_handle(url) is False, url

    def test_check_warn_when_waf_blocks(self):
        from agent_reach.channels.tiktok import TikTokChannel
        ch = TikTokChannel()
        waf_html = (
            '<!DOCTYPE html><html><head><script id="slardar-config" '
            'type="application/json">{"slardarClient":"SlardarWAF"}</script></head>'
            '<body>Please wait...<p id="wci"></p></body></html>'
        )
        with patch("agent_reach.channels.tiktok._fetch", return_value=waf_html):
            status, msg = ch.check()
        assert status == "warn"
        assert ch.active_backend is None
        assert "WAF" in msg or "拦截" in msg

    def test_check_warn_on_network_error(self):
        from agent_reach.channels.tiktok import TikTokChannel
        ch = TikTokChannel()
        with patch("agent_reach.channels.tiktok._fetch",
                   side_effect=URLError("network unreachable")):
            status, msg = ch.check()
        assert status == "warn"
        assert "不可达" in msg or "拦截" in msg

    def test_get_public_page_html_returns_waf_page(self):
        """诚实返回 — 当 TikTok 返回 WAF challenge 时,channel 不撒谎。"""
        from agent_reach.channels.tiktok import TikTokChannel
        ch = TikTokChannel()
        waf_html = '<html><body>Please wait...<p id="wci"></p></body></html>'
        with patch("agent_reach.channels.tiktok._fetch", return_value=waf_html):
            page = ch.get_public_page_html("charlidamelio")
        assert page["handle"] == "charlidamelio"
        assert page["url"] == "https://www.tiktok.com/@charlidamelio"
        # WAF 标志
        assert page["embedded_json_keys"] == []
        assert "JS 渲染" in page["note"]

    def test_get_public_page_html_rejects_invalid_handle(self):
        from agent_reach.channels.tiktok import TikTokChannel
        ch = TikTokChannel()
        result = ch.get_public_page_html("user/with/slash")
        assert "error" in result

    def test_read_url_unsupported_video(self):
        from agent_reach.channels.tiktok import TikTokChannel
        ch = TikTokChannel()
        result = ch.read("https://www.tiktok.com/video/12345")
        assert "error" in result
        assert "登录态" in result["error"] or "Display API" in result["error"]
