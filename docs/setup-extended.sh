#!/usr/bin/env bash
# Agent Reach 完整安装脚本(扩展版,含 4 个新增 channel)
#
# 跨电脑使用:
#   curl -fsSL https://raw.githubusercontent.com/MrRobt/Agent-Reach/main/docs/setup-extended.sh | bash
#
# 或本地:
#   bash setup-extended.sh
#
# 包含:
#   - 基础: git clone + pip install agent-reach
#   - Tier 0: Bluesky (atproto 公开 API)
#   - Tier 0: Twitch (私有 GQL, 借用 Web 客户端 ID)
#   - OpenCLI: 小红书 / Twitter / Reddit / Facebook / Instagram
#   - Tier 1: YouTube (yt-dlp)
#   - Tier 1: Twitter (twitter-cli)
#   - Tier 2: Threads (Meta Graph API, 需 token)
#   - Tier 2: LinkedIn (linkedin-scraper-mcp, 需登录)
#   - Tier 2: TikTok (公开 HTML, 实际被 WAF 拦截, 仅作占位)
#
# 不包含:
#   - Chrome 扩展安装(需要人工在 Chrome 商店点一次)
#   - 小红书/Twitter 等平台登录态(需要 Cookie-Editor 导出)
#   - Twitch Client ID 轮换(如果借用 ID 失效,需手动改)
#   - LinkedIn MCP server 启动(需 VNC 或本地浏览器)
#   - Threads App Review(需在 Meta Developer 注册)

set -e
PINK='\033[1;35m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

log()  { echo -e "${GREEN}[+]${NC} $1"; }
warn() { echo -e "${YELLOW}[!]${NC} $1"; }
fail() { echo -e "${RED}[x]${NC} $1"; exit 1; }
note() { echo -e "${PINK}[*]${NC} $1"; }

# ---------- 0. 前置检查 ----------
log "检查 Python..."
PYTHON=$(command -v python3 || command -v python)
[ -z "$PYTHON" ] && fail "Python 3.10+ 未找到"
$PYTHON -c "import sys; assert sys.version_info >= (3,10)" || fail "需要 Python 3.10+"
log "  -> 使用 $PYTHON"

log "检查 git..."
command -v git >/dev/null || fail "git 未安装"

# ---------- 1. agent-reach 主程序 ----------
log "克隆 fork 仓库(含 Bluesky/Twitch/Threads/TikTok 4 个新 channel)..."
AGENT_REACH_DIR="$HOME/.agent-reach/Agent-Reach"
if [ -d "$AGENT_REACH_DIR" ]; then
    cd "$AGENT_REACH_DIR" && git pull -q
    log "  -> 已更新"
else
    git clone -q https://github.com/MrRobt/Agent-Reach.git "$AGENT_REACH_DIR"
    log "  -> 克隆到 $AGENT_REACH_DIR"
fi

log "安装 agent-reach..."
$PYTHON -m pip install --user "$AGENT_REACH_DIR" 2>&1 | tail -3
log "  -> 完成"

# ---------- 2. 基础 channel 安装 ----------
log "运行 agent-reach installer (基础渠道)..."
$PYTHON -m agent_reach.cli install --env=auto 2>&1 | tail -5 || warn "installer 部分失败,可手动跑"

# ---------- 3. yt-dlp (YouTube) ----------
log "确保 yt-dlp 是最新版..."
$PYTHON -m pip install --user --upgrade yt-dlp 2>&1 | tail -2

# ---------- 4. OpenCLI (小红书/Twitter/Reddit/FB/IG) ----------
log "安装 OpenCLI (浏览器复用登录态)..."
if command -v opencli >/dev/null 2>&1; then
    log "  -> opencli 已存在: $(opencli --version 2>&1 | head -1)"
else
    npm install -g @jackwener/opencli 2>&1 | tail -3
    log "  -> 完成"
fi

note "  接下来你需要手动:"
note "  1. 在 Chrome 商店装 OpenCLI 扩展: https://chromewebstore.google.com/detail/opencli/ildkmabpimmkaediidaifkhjpohdnifk"
note "  2. 装好后跑 'opencli doctor' 验证 (应显示 Extension: connected)"
note "  3. 在 Chrome 登录需要使用的平台 (小红书/Twitter/Reddit/FB/IG)"

# ---------- 5. twitter-cli (Tier 1, 需 Cookie) ----------
log "安装 twitter-cli..."
$PYTHON -m pip install --user twitter-cli 2>&1 | tail -2

note "  twitter-cli 需要认证: 浏览器登录 x.com 后用 Cookie-Editor 导出,"
note "  设置环境变量 TWITTER_AUTH_TOKEN + TWITTER_CT0"

# ---------- 6. linkedin-scraper-mcp (Tier 2, 需登录) ----------
log "安装 linkedin-scraper-mcp..."
$PYTHON -m pip install --user mcp-server-linkedin 2>&1 | tail -2
$PYTHON -m pip install --user patchright 2>&1 | tail -1 || true

note "  LinkedIn 需要 VNC 或本地浏览器登录。详见:"
note "  https://github.com/stickerdaniel/linkedin-mcp-server"

# ---------- 7. 同步 skill 副本 ----------
log "同步 skill 副本到 ~/.claude/skills/..."
SKILL_SRC="$AGENT_REACH_DIR/agent_reach/skill"
SKILL_DST="$HOME/.claude/skills/agent-reach"
mkdir -p "$SKILL_DST/references"
cp -v "$SKILL_SRC/SKILL.md" "$SKILL_DST/SKILL.md"
cp -v "$SKILL_SRC/SKILL_en.md" "$SKILL_DST/SKILL_en.md" 2>/dev/null || true
[ -d "$SKILL_SRC/references" ] && cp -rv "$SKILL_SRC/references/"* "$SKILL_DST/references/"
log "  -> 完成"

# ---------- 8. 验证 ----------
echo ""
log "=========================================="
log "  安装完成!运行 doctor 验证:"
log "=========================================="
$PYTHON -m agent_reach.cli doctor 2>&1 | head -40

echo ""
note "手动待办(脚本无法代劳):"
note "  □ Chrome 装 OpenCLI 扩展 (上面链接)"
note "  □ 浏览器登录需要的平台"
note "  □ twitter-cli 配 Cookie (TWITTER_AUTH_TOKEN + TWITTER_CT0)"
note "  □ 如用 LinkedIn,装 mcp-server-linkedin 后跑 'mcp-server-linkedin --login --no-headless' 登录"
note "  □ 如用 Threads,去 Meta Developer 注册 App + Threads 产品 + App Review (2 周)"
note ""
note "完整文档: $AGENT_REACH_DIR/docs/"
