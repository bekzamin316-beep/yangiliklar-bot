"""Bar-chart rendering for the weekly token unlocks post.

Produces a single PNG (bytes) with a dark crypto-style horizontal bar chart:
top-N unlocks sorted by USD value, gradient rank colors, per-bar value labels
and a week-range title. Pure matplotlib (Agg backend) — no display needed.
"""

import io
import logging
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.ticker import FuncFormatter

from src.core.config import settings

logger = logging.getLogger(__name__)

LOCAL_TZ = ZoneInfo(settings.digest_timezone)

_UZ_MONTHS = [
    "yanvar", "fevral", "mart", "aprel", "may", "iyun",
    "iyul", "avgust", "sentabr", "oktabr", "noyabr", "dekabr",
]

_BG = "#0B1220"
_PANEL = "#111B2E"
_TEXT = "#E6EDF3"
_MUTED = "#8A97A8"
_GRID = "#1E2A40"

_RANK_COLORS = [
    "#FFD700",  # gold
    "#C0C0C0",  # silver
    "#CD7F32",  # bronze
    "#00D4FF",
    "#4D9FFF",
    "#7C5CFF",
    "#B44DFF",
    "#FF5C8A",
    "#FF9F43",
    "#2EE6A8",
]


def _fmt_usd(value: float) -> str:
    """Format a USD amount compactly: 1,27 mln / 850 ming."""
    v = float(value or 0)
    if abs(v) >= 1e9:
        text, unit = f"{v / 1e9:.2f}", "mlrd"
    elif abs(v) >= 1e6:
        text, unit = f"{v / 1e6:.2f}", "mln"
    else:
        text, unit = f"{v / 1e3:.0f}", "ming"
    return f"{text.replace('.', ',')} {unit} $"


def _week_range_str(start: datetime, end: datetime) -> str:
    def day_month(dt: datetime) -> str:
        return f"{dt.day} {_UZ_MONTHS[dt.month - 1]}"

    if start.month == end.month:
        return f"{start.day}–{end.day} {_UZ_MONTHS[start.month - 1].upper()} {start.year}"
    return (
        f"{day_month(start).upper()} – {day_month(end).upper()} {end.year}"
    )


def _render(events: list[dict], *, now: datetime | None = None) -> bytes:
    """Render the top-N unlocks as a horizontal bar chart PNG (bytes)."""
    ref = now or datetime.now(LOCAL_TZ)
    days_ahead = (7 - ref.weekday()) % 7 or 7
    week_start = (ref + timedelta(days=days_ahead)).replace(
        hour=0, minute=0, second=0, microsecond=0,
    )
    week_end = week_start + timedelta(days=7)

    top_n = getattr(settings, "unlocks_top_n", 10)
    top = list(events[:top_n])

    labels: list[str] = []
    values: list[float] = []
    colors: list[str] = []
    for i, ev in enumerate(top):
        nu = ev.get("nextUnlocked") or {}
        usd = float(nu.get("tokenAmountUsd") or 0.0)
        symbol = str(ev.get("symbol", "?"))
        when = ev["_when"]
        date_str = f"{when.day} {_UZ_MONTHS[when.month - 1]}"
        labels.append(f"{symbol}  ·  {date_str}")
        values.append(usd)
        colors.append(_RANK_COLORS[i % len(_RANK_COLORS)])

    fig, ax = plt.subplots(figsize=(11, max(6, 0.62 * len(top) + 2.2)))
    fig.patch.set_facecolor(_BG)
    ax.set_facecolor(_PANEL)

    y_pos = list(range(len(top)))[::-1]
    bars = ax.barh(y_pos, values, color=colors, height=0.62, zorder=3)

    ax.set_yticks(y_pos)
    ax.set_yticklabels(labels, fontsize=12, color=_TEXT)
    ax.tick_params(axis="y", length=0)

    ax.xaxis.set_major_formatter(FuncFormatter(lambda v, _p: _fmt_usd(v)))
    ax.tick_params(axis="x", colors=_MUTED, labelsize=10)
    ax.grid(axis="x", color=_GRID, linewidth=0.8, alpha=0.7, zorder=0)
    for spine in ax.spines.values():
        spine.set_visible(False)

    for bar, val in zip(bars, values):
        if val <= 0:
            continue
        ax.text(
            bar.get_width() + max(values) * 0.01,
            bar.get_y() + bar.get_height() / 2,
            _fmt_usd(val),
            va="center", ha="left", fontsize=11, fontweight="bold",
            color=_TEXT,
        )

    title = f"TOP-{len(top)} TOKEN UNLOCK — {_week_range_str(week_start, week_end - timedelta(days=1))}"
    ax.set_title(title, fontsize=15, fontweight="bold", color=_TEXT, pad=18)
    ax.text(
        0.0, -0.14,
        "Manba: CoinMarketCap",
        transform=ax.transAxes, fontsize=9, color=_MUTED,
    )
    ax.set_xlim(0, max(values) * 1.18 if values else 1)

    fig.tight_layout()
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=160, facecolor=_BG, bbox_inches="tight")
    plt.close(fig)
    buf.seek(0)
    return buf.getvalue()


def render_unlocks_chart(events: list[dict], *, now: datetime | None = None) -> bytes | None:
    """Public wrapper — returns PNG bytes or None if there is nothing to draw."""
    try:
        if not events:
            return None
        return _render(events, now=now)
    except Exception as e:
        logger.error("Failed to render unlocks chart: %s", e)
        return None
