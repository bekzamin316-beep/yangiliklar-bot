"""Light-themed infographic card chart for the weekly token unlocks post.

Reproduces the CryptoRank.io "TOP N TOKEN UNLOCKS OF THE WEEK" style:
a gradient title banner, one column per token with logo, symbol/name,
date, tokens unlocked (amount + % of supply), USD value, % of market cap,
market cap, and a bottom "total supply unlocked" progress bar.

Pure matplotlib (Agg backend) — no display needed. No emoji in glyphs.
"""

import asyncio
import io
import logging
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import httpx
import matplotlib

matplotlib.use("Agg")
import matplotlib.image as mpimg
import matplotlib.pyplot as plt
from matplotlib.patches import Circle, FancyBboxPatch, Rectangle

from src.core.config import settings

logger = logging.getLogger(__name__)

LOCAL_TZ = ZoneInfo(settings.digest_timezone)

_UZ_MONTHS = [
    "yanvar", "fevral", "mart", "aprel", "may", "iyun",
    "iyul", "avgust", "sentabr", "oktabr", "noyabr", "dekabr",
]

# Light theme
_BG = "#F4F8FE"
_CARD = "#FFFFFF"
_CARD_BORDER = "#DEE7F5"
_TEXT = "#16233C"
_MUTED = "#5B6B82"
_BANNER_TOP = "#5EA2FF"
_BANNER_BOTTOM = "#2F6BFF"
_ACCENT = "#2563EB"
_PROGRESS_FILL = "#34C77B"
_PROGRESS_BG = "#E4EDF7"

_RANK_COLORS = [
    "#3B82F6",  # blue
    "#8B5CF6",  # violet
    "#10B981",  # green
    "#F59E0B",  # amber
    "#EF4444",  # red
    "#06B6D4",  # cyan
    "#EC4899",  # pink
    "#84CC16",  # lime
    "#F97316",  # orange
    "#6366F1",  # indigo
]


def _uz(date: datetime) -> str:
    return f"{date.day} {_UZ_MONTHS[date.month - 1]}"


def _uz_weekday(date: datetime) -> str:
    names = ["Du", "Se", "Ch", "Pa", "Ju", "Sh", "Ya"]
    return names[date.weekday()]


def _fmt_usd(value: float) -> str:
    """Format a USD amount compactly: 1,27 mln $ / 850 ming $."""
    v = float(value or 0)
    if abs(v) >= 1e9:
        text, unit = f"{v / 1e9:.2f}", "mlrd $"
    elif abs(v) >= 1e6:
        text, unit = f"{v / 1e6:.2f}", "mln $"
    else:
        text, unit = f"{v / 1e3:.0f}", "ming $"
    return f"{text.replace('.', ',')} {unit}"


def _fmt_tokens(value: float) -> str:
    """Format a raw token amount compactly: 7,29 mlrd / 850 mln / 12,4 mln."""
    v = float(value or 0)
    if abs(v) >= 1e9:
        text, unit = f"{v / 1e9:.2f}", "mlrd"
    elif abs(v) >= 1e6:
        text, unit = f"{v / 1e6:.2f}", "mln"
    elif abs(v) >= 1e3:
        text, unit = f"{v / 1e3:.1f}", "ming"
    else:
        text, unit = f"{v:.0f}", ""
    return f"{text.replace('.', ',')} {unit}".strip()


def _fmt_pct(value) -> str:
    try:
        return f"{str(value).replace('.', ',')}%"
    except (TypeError, ValueError):
        return "—"


def _week_range_str(start: datetime, end: datetime) -> str:
    def day_month(dt: datetime) -> str:
        return f"{dt.day} {_UZ_MONTHS[dt.month - 1]}"

    if start.month == end.month:
        return f"{start.day}–{end.day} {_UZ_MONTHS[start.month - 1].upper()} {start.year}"
    return (
        f"{day_month(start).upper()} – {day_month(end).upper()} {end.year}"
    )


def _gradient_banner(ax, x0: float, y0: float, x1: float, y1: float) -> None:
    """Draw a vertical light-blue gradient banner."""
    steps = 24
    for i in range(steps):
        t = i / (steps - 1)
        r = int(_BANNER_BOTTOM[1:3], 16) + int(
            int(_BANNER_TOP[1:3], 16) - int(_BANNER_BOTTOM[1:3], 16)
        ) * t
        g = int(_BANNER_BOTTOM[3:5], 16) + int(
            int(_BANNER_TOP[3:5], 16) - int(_BANNER_BOTTOM[3:5], 16)
        ) * t
        b = int(_BANNER_BOTTOM[5:7], 16) + int(
            int(_BANNER_TOP[5:7], 16) - int(_BANNER_BOTTOM[5:7], 16)
        ) * t
        color = f"#{int(r):02x}{int(g):02x}{int(b):02x}"
        y = y1 - (y1 - y0) * (i + 1) / steps
        h = (y1 - y0) / steps + 0.02
        ax.add_patch(Rectangle((x0, y), x1 - x0, h, facecolor=color,
                               edgecolor="none", zorder=2))
    ax.add_patch(Rectangle((x0, y0), x1 - x0, y1 - y0, facecolor="none",
                           edgecolor=_BANNER_BOTTOM, linewidth=1.2, zorder=3))


def _card(ax, x0: float, y0: float, x1: float, y1: float) -> None:
    ax.add_patch(FancyBboxPatch(
        (x0, y0), x1 - x0, y1 - y0,
        boxstyle="round,pad=0.15,rounding_size=1.2",
        facecolor=_CARD, edgecolor=_CARD_BORDER, linewidth=1.0, zorder=1,
    ))


_LOGO_BASE = "https://s2.coinmarketcap.com/static/img/coins/128x128/{crypto_id}.png"
_LOGO_UA = "Mozilla/5.0 (X11; Linux x86_64)"


async def fetch_token_logos(events: list[dict], top_n: int | None = None) -> dict:
    """Download real token logos (CoinMarketCap) for the top events.

    Returns ``{symbol: logo_bytes}``; missing/failed downloads are skipped so
    the renderer falls back to the coloured initial circle.
    """
    top_n = top_n or getattr(settings, "unlocks_top_n", 10)
    symbols = {}
    for ev in events[:top_n]:
        sym = str(ev.get("symbol", "")).upper()
        if sym:
            symbols[sym] = ev

    async with httpx.AsyncClient(timeout=8, headers={"User-Agent": _LOGO_UA},
                                 follow_redirects=True) as client:
        async def _one(sym: str, ev: dict) -> tuple[str | None, bytes | None]:
            cid = ev.get("cryptoId")
            if not cid:
                return sym, None
            try:
                r = await client.get(_LOGO_BASE.format(crypto_id=cid))
                if r.status_code == 200 and r.content:
                    return sym, r.content
            except Exception as e:
                logger.debug("Logo fetch failed for %s: %s", sym, e)
            return sym, None

        results = await asyncio.gather(
            *(_one(sym, ev) for sym, ev in symbols.items()),
            return_exceptions=True,
        )

    logos = {}
    for res in results:
        if isinstance(res, Exception):
            continue
        sym, data = res
        if sym and data:
            logos[sym] = data
    logger.info("Fetched %d/%d token logos", len(logos), len(symbols))
    return logos


def _render(events: list[dict], *, now: datetime | None = None,
            logos: dict | None = None) -> bytes:
    """Render the top-N unlocks as a light infographic card chart."""
    ref = now or datetime.now(LOCAL_TZ)
    days_ahead = (7 - ref.weekday()) % 7 or 7
    week_start = (ref + timedelta(days=days_ahead)).replace(
        hour=0, minute=0, second=0, microsecond=0,
    )
    week_end = week_start + timedelta(days=7)

    top_n = getattr(settings, "unlocks_top_n", 10)
    top = list(events[:top_n])
    n = len(top)

    fig_w = max(12.5, 2.15 * n + 1.6)
    fig, ax = plt.subplots(figsize=(fig_w, 7.8))
    ax.set_xlim(0, 100)
    ax.set_ylim(0, 100)
    ax.axis("off")
    fig.patch.set_facecolor(_BG)

    # ── Title banner ─────────────────────────────────────────
    _gradient_banner(ax, 0, 88.5, 100, 100)
    ax.text(50, 95.6, f"TOP {n} TOKEN UNLOCK",
            ha="center", va="center", fontsize=20, fontweight="bold",
            color="white", zorder=4)
    ax.text(50, 90.9, _week_range_str(week_start, week_end - timedelta(days=1)),
            ha="center", va="center", fontsize=12, color="#EAF2FF", zorder=4)

    # ── Token columns ────────────────────────────────────────
    margin_x = 2.4
    col_w = (100 - 2 * margin_x) / n

    for i, ev in enumerate(top):
        x0 = margin_x + i * col_w
        x1 = x0 + col_w - 0.55
        cx = (x0 + x1) / 2
        color = _RANK_COLORS[i % len(_RANK_COLORS)]

        _card(ax, x0, 3.2, x1, 86.5)

        nu = ev.get("nextUnlocked") or {}
        unlock_usd = float(nu.get("tokenAmountUsd") or 0.0)
        unlock_pct = nu.get("tokenAmountPercentage")
        when = ev["_when"]
        symbol = str(ev.get("symbol", "?"))
        name = str(ev.get("name", ""))
        total_unlocked = ev.get("totalUnlockedPercentage")
        quotes = ev.get("quotes") or []
        market_cap = quotes[0].get("marketCap") if quotes else None

        # Logo circle with real token logo (fallback to initial)
        radius = 3.1
        logo = (logos or {}).get(symbol)
        if logo:
            try:
                arr = mpimg.imread(io.BytesIO(logo), format="png")
                im = ax.imshow(arr, extent=[cx - radius, cx + radius,
                                           82.6 - radius, 82.6 + radius],
                               zorder=6, aspect="auto")
                circle = Circle((cx, 82.6), radius, transform=ax.transData,
                                zorder=7)
                im.set_clip_path(circle)
            except Exception as e:
                logger.debug("Logo render failed for %s: %s", symbol, e)
                ax.add_patch(Circle((cx, 82.6), radius, facecolor=color,
                                    edgecolor="white", linewidth=1.6, zorder=5))
                ax.text(cx, 82.6, symbol[0], ha="center", va="center",
                        fontsize=11, fontweight="bold", color="white", zorder=6)
        else:
            ax.add_patch(Circle((cx, 82.6), radius, facecolor=color,
                                edgecolor="white", linewidth=1.6, zorder=5))
            ax.text(cx, 82.6, symbol[0], ha="center", va="center",
                    fontsize=11, fontweight="bold", color="white", zorder=6)

        # Symbol + name
        ax.text(cx, 76.9, symbol, ha="center", va="center", fontsize=13,
                fontweight="bold", color=_TEXT, zorder=4)
        ax.text(cx, 73.6, name, ha="center", va="center", fontsize=7.5,
                color=_MUTED, zorder=4)

        # Divider
        ax.add_patch(Rectangle((x0 + 2.6, 70.9), x1 - x0 - 5.2, 0.5,
                               facecolor=_CARD_BORDER, edgecolor="none", zorder=4))

        # Date
        _label(ax, cx, 68.2, "Sana")
        _value(ax, cx, 66.4, f"{_uz_weekday(when)}, {_uz(when)}", 8.6, _TEXT)

        # Tokens unlocked (amount + %)
        _label(ax, cx, 62.6, "Ochiladi")
        ax.text(cx, 59.8, _fmt_tokens(nu.get("tokenAmount") or 0),
                ha="center", va="center", fontsize=14.5, fontweight="bold",
                color=_ACCENT, zorder=4)
        ax.text(cx, 57.0, _fmt_pct(unlock_pct),
                ha="center", va="center", fontsize=9.5, fontweight="bold",
                color=_ACCENT, zorder=4)

        # Unlock value
        _label(ax, cx, 53.2, "Qiymati")
        _value(ax, cx, 51.4, _fmt_usd(unlock_usd), 9.5, _TEXT)

        # % of market cap
        _label(ax, cx, 47.6, "M.Cap ulushi")
        pct_mc = None
        if market_cap and unlock_usd:
            pct_mc = unlock_usd / market_cap * 100
        _value(ax, cx, 45.8, f"{pct_mc:.2f}".replace(".", ",") + "%" if pct_mc is not None else "—",
               8.6, _TEXT)

        # Market cap
        _label(ax, cx, 41.9, "Market Cap")
        _value(ax, cx, 40.1, _fmt_usd(market_cap) if market_cap else "—",
               8.6, _TEXT)

        # Total supply unlocked progress bar
        _label(ax, cx, 34.2, "Jami ochilgan")
        bar_y = 31.6
        bar_h = 2.9
        bar_w = x1 - x0 - 7.2
        bx0 = cx - bar_w / 2
        ax.add_patch(Rectangle((bx0, bar_y), bar_w, bar_h,
                               facecolor=_PROGRESS_BG, edgecolor="none",
                               zorder=4, joinstyle="round"))
        try:
            p = max(0.0, min(1.0, float(total_unlocked) / 100.0))
        except (TypeError, ValueError):
            p = 0.0
        if p > 0.01:
            ax.add_patch(Rectangle((bx0, bar_y), bar_w * p, bar_h,
                                   facecolor=_PROGRESS_FILL, edgecolor="none",
                                   zorder=5, joinstyle="round"))
        ax.text(cx, bar_y - 2.1, _fmt_pct(total_unlocked),
                ha="center", va="center", fontsize=8.8, fontweight="bold",
                color=_PROGRESS_FILL, zorder=4)

    # ── Footer ───────────────────────────────────────────────
    ax.text(50, 1.0, "Manba: CoinMarketCap",
            ha="center", va="center", fontsize=8.5, color=_MUTED, zorder=4)

    fig.tight_layout(pad=0.4)
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=150, facecolor=_BG, bbox_inches="tight")
    plt.close(fig)
    buf.seek(0)
    return buf.getvalue()


def _label(ax, cx: float, y: float, text: str) -> None:
    ax.text(cx, y, text.upper(), ha="center", va="center", fontsize=6.2,
            color=_MUTED, zorder=4)


def _value(ax, cx: float, y: float, text: str, size: float, color: str) -> None:
    ax.text(cx, y, text, ha="center", va="center", fontsize=size,
            fontweight="bold", color=color, zorder=4)


def render_unlocks_chart(events: list[dict], *, now: datetime | None = None,
                         logos: dict | None = None) -> bytes | None:
    """Public wrapper — returns PNG bytes or None if there is nothing to draw."""
    try:
        if not events:
            return None
        return _render(events, now=now, logos=logos)
    except Exception as e:
        logger.error("Failed to render unlocks chart: %s", e)
        return None
