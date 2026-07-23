# -*- coding: utf-8 -*-
"""TikTok — public web (HTML fetch, no official public API).

限制说明：
  - TikTok 没有公开的、未鉴权的 API（Display API 需 App Review 且数据有限）。
  - 公开主页（www.tiktok.com/@handle）由 JS 渲染，curl 拿到的 HTML 大多不含数据。
  - 视频元数据需要登录态或签名（X-Bogus）。
  - 本 channel 务实做法：探测主页可达性 + 提供 HTML 源码获取（让 LLM 后续解析）。
  - 拿数据请走 OpenCLI（jackwener/opencli 后续会加 TikTok）或 Display API。

Tier 2 — 网络可达但 API 受限。
"""

import re
import urllib.request
from typing import Dict

from .base import Channel

_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"
)
_TIMEOUT = 10
_PUBLIC_HOME = "https://www.tiktok.com"


def _fetch(url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": _UA})
    with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:
        return resp.read().decode("utf-8", errors="replace")


class TikTokChannel(Channel):
    name = "tiktok"
    description = "TikTok 主页（公开 HTML，JS 渲染数据有限）"
    backends = ["TikTok Web (HTML)", "OpenCLI (planned)", "Display API (TBD)"]
    tier = 2

    # ------------------------------------------------------------------ #
    # URL routing
    # ------------------------------------------------------------------ #

    def can_handle(self, url: str) -> bool:
        from urllib.parse import urlparse
        d = urlparse(url).netloc.lower()
        return "tiktok.com" in d

    # ------------------------------------------------------------------ #
    # Health check
    # ------------------------------------------------------------------ #

    def check(self, config=None):  # noqa: ARG002
        try:
            html = _fetch(_PUBLIC_HOME + "/")
            # TikTok 对非浏览器 UA 直接返回 Slardar WAF challenge 页
            if "wafchallengeid" in html or "Please wait" in html or "SlardarWAF" in html:
                self.active_backend = None
                return "warn", (
                    "TikTok 公开主页被 Slardar WAF 拦截（challenge 页），"
                    "非浏览器 UA 拿不到 HTML。本 channel 当前不可用，"
                    "需要登录态（OpenCLI 待 jackwener 支持）或 Display API（需 App Review）。"
                )
            if "<title" in html.lower():
                self.active_backend = self.backends[0]
                return "ok", (
                    "TikTok 主页可达（HTML 抓取层）。"
                    "⚠️ 即使绕过 WAF，公开主页仍由 JS 渲染，"
                    "HTML 多数不含粉丝/视频数据，强烈建议走 OpenCLI 或 Display API。"
                )
            self.active_backend = None
            return "warn", "TikTok 主页返回内容异常（无 <title> 也无 WAF 标志）"
        except Exception as e:
            self.active_backend = None
            return "warn", f"TikTok 主页不可达（可能被 GFW 拦截或网络问题）：{e}"

    # ------------------------------------------------------------------ #
    # Data methods
    # ------------------------------------------------------------------ #

    def get_public_page_html(self, handle: str) -> Dict:
        """获取 TikTok 公开主页 HTML 原始内容。

        Args:
            handle: 不带 @ 的用户名，如 'charlidamelio'

        Returns:
            dict: handle / url / html（截断到 5000 字符，完整 HTML 太大）
            或 dict 含 'error' 字段

        注意：HTML 由 JS 渲染后才有数据，原始 HTML 多数仅含脚手架 + 初始 JSON blob。
        推荐做法：把 html 喂给 LLM，让它尝试提取窗口.__INIT_PROPS__ 里的 JSON 数据。
        """
        handle = handle.lstrip("@").strip()
        if not handle or "/" in handle:
            return {"error": f"invalid handle: {handle}"}
        url = f"{_PUBLIC_HOME}/@{handle}"
        try:
            html = _fetch(url)
        except Exception as e:
            return {"error": f"fetch failed: {e}"}

        # Try to extract embedded JSON blob (TikTok injects user data in a script tag)
        embedded = {}
        # Pattern: <script id="__UNIVERSAL_DATA_FOR_REHYDRATION__" type="application/json">...</script>
        m = re.search(
            r'<script[^>]+id="__UNIVERSAL_DATA_FOR_REHYDRATION__"[^>]*>(.+?)</script>',
            html,
            re.DOTALL,
        )
        if m:
            embedded["__UNIVERSAL_DATA_FOR_REHYDRATION__"] = m.group(1)[:2000]
        # Pattern: window.__INIT_PROPS__
        m2 = re.search(r"window\.__INIT_PROPS__\s*=\s*(\{.+?\})\s*;", html, re.DOTALL)
        if m2:
            embedded["__INIT_PROPS__"] = m2.group(1)[:2000]

        return {
            "handle": handle,
            "url": url,
            "html_snippet": html[:5000],
            "html_total_len": len(html),
            "embedded_json_keys": list(embedded.keys()),
            "embedded_json_snippet": embedded,
            "note": (
                "TikTok 公开页由 JS 渲染。若 embedded_json_keys 为空，"
                "说明需要登录态或浏览器自动化（OpenCLI）。"
            ),
        }

    def get_user(self, handle: str) -> Dict:
        """Convenience: fetch public page and return a slim dict.

        实际数据可能为空，调用方应检查字段。
        """
        page = self.get_public_page_html(handle)
        if "error" in page:
            return page
        return {
            "handle": page.get("handle", ""),
            "url": page.get("url", ""),
            "note": page.get("note", ""),
            "has_embedded_data": bool(page.get("embedded_json_keys")),
        }

    # ------------------------------------------------------------------ #
    # URL-based reader
    # ------------------------------------------------------------------ #

    def read(self, url: str) -> Dict:
        from urllib.parse import urlparse

        parts = [p for p in urlparse(url).path.split("/") if p]
        if parts and parts[0].startswith("@"):
            return self.get_user(parts[0].lstrip("@"))
        if parts and parts[0] in ("video", "v"):
            return {
                "error": (
                    "TikTok 视频元数据需登录态或 Display API。"
                    "本 channel 当前只支持公开主页 HTML 抓取。"
                ),
                "url": url,
            }
        return {"error": f"unsupported TikTok URL: {url}"}
