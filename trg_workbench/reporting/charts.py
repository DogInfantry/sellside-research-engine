"""
charts.py — Publication-quality financial charts for sell-side research notes.

Generates PNG files matching GS/JPM/MS research note visualization standards:
  1. DCF sensitivity heatmap (WACC vs terminal growth rate)
  2. Football field chart (multi-methodology valuation range)
  3. Factor radar / spider chart (per-stock multi-factor scores)
  4. Peer comparison scatter (EV multiple vs growth)
  5. Candlestick + volume chart with 50/200 MA
  6. Historical P/E multiple with ±1σ bands
  7. Correlation heatmap (return correlations)
  8. VaR / return distribution histogram
  9. Sector rotation heatmap (1d/1w/1m/3m by sector)
  10. Risk-return scatter (vol vs Sharpe)
  11. Earnings estimate waterfall (EPS revision bridge)
  12. Screen dashboard (composite scores bar chart)
"""
from __future__ import annotations

import warnings
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import sys

import matplotlib
matplotlib.use("Agg")  # non-interactive backend — safe for servers
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import matplotlib.ticker as mticker
import numpy as np
import pandas as pd
from matplotlib.colors import LinearSegmentedColormap
from tqdm import tqdm

warnings.filterwarnings("ignore", category=UserWarning)

# ─── Style constants ──────────────────────────────────────────────────────────
GS_NAVY    = "#003366"
GS_GOLD    = "#C8A951"
GS_LIGHT   = "#F0F4F8"
GS_RED     = "#C0392B"
GS_GREEN   = "#1A7340"
GS_GREY    = "#6B7280"
GS_BORDER  = "#D1D5DB"

FONT_TITLE = {"fontsize": 13, "fontweight": "bold", "color": GS_NAVY, "fontfamily": "DejaVu Sans"}
FONT_LABEL = {"fontsize": 9,  "color": GS_GREY,    "fontfamily": "DejaVu Sans"}
FONT_TICK  = {"labelsize": 8, "labelcolor": GS_GREY}

DPI = 150
FIG_WIDE = (12, 6)
FIG_SQUARE = (8, 7)
FIG_TALL = (10, 8)


def _save(fig: plt.Figure, path: Path) -> None:
    """Save figure as PNG and close."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=DPI, bbox_inches="tight", facecolor="white", edgecolor="none")
    plt.close(fig)


def _gs_spine(ax: plt.Axes) -> None:
    """Apply GS-style minimal spine formatting."""
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.spines["left"].set_color(GS_BORDER)
    ax.spines["bottom"].set_color(GS_BORDER)
    ax.tick_params(**FONT_TICK)
    ax.set_facecolor(GS_LIGHT)


# ─── 1. DCF Sensitivity Heatmap ───────────────────────────────────────────────

def plot_dcf_sensitivity(
    sensitivity_df: pd.DataFrame,
    ticker: str,
    current_price: float,
    output_path: Path,
) -> Path:
    """
    Heatmap: rows = WACC, cols = terminal growth rate.
    Green = above current price (undervalued), Red = below (overvalued).
    """
    fig, ax = plt.subplots(figsize=FIG_SQUARE)

    data = sensitivity_df.copy().apply(pd.to_numeric, errors="coerce")
    # Color: green where implied value > current_price, red where <
    cmap = LinearSegmentedColormap.from_list("rdgn", [GS_RED, "white", GS_GREEN], N=256)
    # Normalize centered on current_price
    vmin = max(0, current_price * 0.5)
    vmax = current_price * 1.5
    im = ax.imshow(
        data.values, cmap=cmap, aspect="auto",
        vmin=vmin, vmax=vmax, interpolation="nearest",
    )

    # Labels
    ax.set_xticks(range(len(data.columns)))
    ax.set_xticklabels(data.columns, rotation=45, ha="right", fontsize=8)
    ax.set_yticks(range(len(data.index)))
    ax.set_yticklabels(data.index, fontsize=8)

    # Cell annotations
    for i in tqdm(range(len(data.index)), "DCF Sensitivity Heatmap (Cell annotations)"):
        for j in range(len(data.columns)):
            val = data.values[i, j]
            if not np.isnan(val):
                color = "white" if abs(val - current_price) > current_price * 0.25 else GS_NAVY
                ax.text(j, i, f"${val:.0f}", ha="center", va="center",
                        fontsize=7, color=color, fontweight="bold")

    plt.colorbar(im, ax=ax, label="Implied Share Price ($)", shrink=0.8)
    ax.set_title(f"{ticker} — DCF Sensitivity: WACC vs Terminal Growth Rate\n"
                 f"Current Price: ${current_price:.2f}  |  Green = Undervalued, Red = Overvalued",
                 **FONT_TITLE, pad=12)
    ax.set_xlabel("Terminal Growth Rate", **FONT_LABEL)
    ax.set_ylabel("WACC", **FONT_LABEL)

    # Highlight current price contour
    ax.axhline(-0.5, color=GS_GOLD, linewidth=0, alpha=0)  # force layout
    fig.tight_layout()
    _save(fig, output_path)
    return output_path


# ─── 2. Football Field Chart ──────────────────────────────────────────────────

def plot_football_field(
    football_data: Dict,
    output_path: Path,
) -> Path:
    """
    Horizontal bar chart showing valuation range from multiple methodologies.
    Vertical line at current market price.
    """
    ticker = football_data.get("ticker", "")
    current = football_data.get("current_price", 0)
    methods = football_data.get("methods", {})

    if not methods:
        return output_path

    labels = list(methods.keys())
    colors = [GS_NAVY, GS_GOLD, GS_GREEN, GS_RED, "#7B2D8B", "#E67E22"]

    fig, ax = plt.subplots(figsize=(11, max(4, len(labels) * 1.1 + 1.5)))
    ax.set_facecolor(GS_LIGHT)

    for i, (label, (lo, mid, hi)) in tqdm(enumerate(methods.items()), "Football Field Chart"):
        color = colors[i % len(colors)]
        # Range bar
        ax.barh(i, hi - lo, left=lo, height=0.5, color=color, alpha=0.25, edgecolor=color, linewidth=1.5)
        # Midpoint marker
        ax.plot(mid, i, "D", color=color, markersize=9, zorder=5)
        # Lo/Hi labels
        ax.text(lo - (hi - lo) * 0.04, i, f"${lo:.0f}", va="center", ha="right",
                fontsize=8, color=color, fontweight="bold")
        ax.text(hi + (hi - lo) * 0.04, i, f"${hi:.0f}", va="center", ha="left",
                fontsize=8, color=color, fontweight="bold")
        # Mid label
        ax.text(mid, i + 0.32, f"${mid:.0f}", va="bottom", ha="center",
                fontsize=7.5, color=GS_NAVY, fontweight="bold")

    # Current price line
    ax.axvline(current, color=GS_RED, linewidth=2, linestyle="--", zorder=10, label=f"Current: ${current:.2f}")
    ax.text(current, len(labels) - 0.1, f" ${current:.2f}\n Current", color=GS_RED,
            fontsize=8, fontweight="bold", va="top")

    ax.set_yticks(range(len(labels)))
    ax.set_yticklabels(labels, fontsize=9)
    ax.set_xlabel("Implied Share Price ($)", **FONT_LABEL)
    ax.set_title(f"{ticker} — Football Field: Valuation Summary", **FONT_TITLE, pad=12)

    _gs_spine(ax)
    ax.legend(fontsize=8, loc="lower right")
    fig.tight_layout()
    _save(fig, output_path)
    return output_path


# ─── 3. Factor Radar Chart ────────────────────────────────────────────────────

def plot_factor_radar(
    factor_scores: Dict[str, float],
    ticker: str,
    output_path: Path,
    benchmark_scores: Optional[Dict[str, float]] = None,
) -> Path:
    """
    Radar / spider chart showing multi-factor scores (0–100 percentile).
    Optional benchmark overlay (universe median = 50).
    """
    labels = list(factor_scores.keys())
    values = [max(0, min(100, v * 100)) if v <= 1 else max(0, min(100, v)) for v in factor_scores.values()]
    N = len(labels)
    if N < 3:
        return output_path

    angles = np.linspace(0, 2 * np.pi, N, endpoint=False).tolist()
    values_plot = values + [values[0]]
    angles_plot = angles + [angles[0]]
    labels_plot = labels

    fig, ax = plt.subplots(figsize=(7, 7), subplot_kw={"polar": True})
    ax.set_facecolor(GS_LIGHT)

    # Grid
    ax.set_yticks([20, 40, 60, 80, 100])
    ax.set_yticklabels(["20", "40", "60", "80", "100"], color=GS_GREY, size=7)
    ax.set_rlim(0, 100)

    # Benchmark (universe median) — dashed grey at 50
    bench_values = benchmark_scores if benchmark_scores else {k: 0.5 for k in labels}
    bench_vals_raw = list(bench_values.values())
    bench_vals = [max(0, min(100, v * 100)) if v <= 1 else max(0, min(100, v)) for v in bench_vals_raw]
    ax.plot(angles_plot, bench_vals + [bench_vals[0]], "--", color=GS_GREY, linewidth=1.2, alpha=0.6, label="Universe Median")
    ax.fill(angles_plot, bench_vals + [bench_vals[0]], color=GS_GREY, alpha=0.05)

    # Ticker
    ax.plot(angles_plot, values_plot, "o-", color=GS_NAVY, linewidth=2.5, markersize=6, label=ticker)
    ax.fill(angles_plot, values_plot, color=GS_NAVY, alpha=0.18)

    # Labels
    ax.set_thetagrids(np.degrees(angles), labels_plot, fontsize=9.5, color=GS_NAVY, fontweight="bold")

    ax.set_title(f"{ticker} — Factor Profile\n(Percentile vs Universe, 0–100)", **FONT_TITLE, pad=20)
    ax.legend(loc="upper right", bbox_to_anchor=(1.25, 1.1), fontsize=8)
    fig.tight_layout()
    _save(fig, output_path)
    return output_path


# ─── 4. Peer Comparison Scatter ───────────────────────────────────────────────

def plot_peer_scatter(
    comps_df: pd.DataFrame,
    x_col: str,
    y_col: str,
    label_col: str,
    highlight_ticker: str,
    output_path: Path,
    x_label: Optional[str] = None,
    y_label: Optional[str] = None,
) -> Path:
    """
    Scatter plot: x=valuation metric, y=growth/quality metric.
    Highlights the subject company. Adds trend line.
    """
    df = comps_df[[x_col, y_col, label_col]].dropna()
    if df.empty:
        return output_path

    fig, ax = plt.subplots(figsize=FIG_WIDE)
    _gs_spine(ax)

    # All peers
    non_hl = df[df[label_col] != highlight_ticker]
    ax.scatter(non_hl[x_col], non_hl[y_col], color=GS_NAVY, alpha=0.65, s=80, zorder=4)

    # Labels for peers
    for _, row in tqdm(non_hl.iterrows(), "Peer Comparison Scatter"):
        ax.annotate(row[label_col], (row[x_col], row[y_col]),
                    textcoords="offset points", xytext=(6, 4),
                    fontsize=7.5, color=GS_GREY)

    # Highlight subject
    hl = df[df[label_col] == highlight_ticker]
    if not hl.empty:
        ax.scatter(hl[x_col], hl[y_col], color=GS_GOLD, edgecolors=GS_NAVY,
                   s=200, zorder=6, marker="*", linewidth=1.5)
        ax.annotate(f"  {highlight_ticker}", (float(hl[x_col].iloc[0]), float(hl[y_col].iloc[0])),
                    textcoords="offset points", xytext=(8, 6),
                    fontsize=9, color=GS_NAVY, fontweight="bold")

    # Trend line
    try:
        x_vals = df[x_col].values.astype(float)
        y_vals = df[y_col].values.astype(float)
        mask = np.isfinite(x_vals) & np.isfinite(y_vals)
        if mask.sum() >= 3:
            m, b = np.polyfit(x_vals[mask], y_vals[mask], 1)
            x_line = np.linspace(x_vals[mask].min(), x_vals[mask].max(), 100)
            ax.plot(x_line, m * x_line + b, "--", color=GS_GOLD, linewidth=1.5, alpha=0.7, label="Trend")
    except Exception:  # noqa: BLE001
        pass

    ax.set_xlabel(x_label or x_col, **FONT_LABEL)
    ax.set_ylabel(y_label or y_col, **FONT_LABEL)
    ax.set_title(f"Peer Comparison: {x_label or x_col} vs {y_label or y_col}", **FONT_TITLE, pad=12)

    star_patch = mpatches.Patch(color=GS_GOLD, label=f"{highlight_ticker} (Subject)")
    peer_patch = mpatches.Patch(color=GS_NAVY, label="Peers", alpha=0.65)
    ax.legend(handles=[star_patch, peer_patch], fontsize=8)

    fig.tight_layout()
    _save(fig, output_path)
    return output_path


# ─── 5. Candlestick + Volume with Moving Averages ────────────────────────────

def plot_price_chart(
    prices_df: pd.DataFrame,
    ticker: str,
    output_path: Path,
    ma_windows: Tuple[int, int] = (50, 200),
    lookback_days: int = 252,
) -> Path:
    """
    Price chart: close price line + 50/200 MA + volume bars.
    If OHLC available uses those; otherwise close only.
    """
    px = prices_df.tail(lookback_days).copy()
    if px.empty:
        return output_path

    fig = plt.figure(figsize=(12, 7))
    gs_layout = fig.add_gridspec(3, 1, hspace=0.05)
    ax_price = fig.add_subplot(gs_layout[:2, 0])
    ax_vol = fig.add_subplot(gs_layout[2, 0], sharex=ax_price)

    close_col = "Close" if "Close" in px.columns else px.columns[0]
    close = px[close_col].astype(float)
    dates = px.index if isinstance(px.index, pd.DatetimeIndex) else pd.to_datetime(px.index)

    # Price line
    ax_price.plot(dates, close, color=GS_NAVY, linewidth=1.5, label="Close")

    # Moving averages
    for window, color in tqdm(zip(ma_windows, [GS_GOLD, GS_RED]), "Candlestick (Moving Averages)"):
        ma = close.rolling(window).mean()
        ax_price.plot(dates, ma, color=color, linewidth=1.2, linestyle="--",
                      label=f"{window}-Day MA", alpha=0.85)

    # Shaded area under price line
    ax_price.fill_between(dates, close, close.min() * 0.97, alpha=0.06, color=GS_NAVY)

    # Latest price annotation
    ax_price.annotate(
        f"  ${close.iloc[-1]:.2f}",
        xy=(dates[-1], float(close.iloc[-1])),
        fontsize=9, color=GS_NAVY, fontweight="bold",
    )

    # Volume
    if "Volume" in px.columns:
        vol = px["Volume"].astype(float)
        colors = [GS_GREEN if close.iloc[i] >= close.iloc[i - 1] else GS_RED
                  for i in range(len(close))]
        ax_vol.bar(dates, vol, color=colors, alpha=0.6, width=0.8)
        ax_vol.set_ylabel("Volume", **FONT_LABEL)
        ax_vol.yaxis.set_major_formatter(mticker.FuncFormatter(
            lambda x, _: f"{x/1e6:.0f}M" if x >= 1e6 else f"{x/1e3:.0f}K"
        ))

    _gs_spine(ax_price)
    _gs_spine(ax_vol)
    ax_price.set_ylabel("Price ($)", **FONT_LABEL)
    ax_price.legend(fontsize=8, loc="upper left")
    ax_price.set_title(f"{ticker} — Price Chart (1-Year)", **FONT_TITLE, pad=12)
    plt.setp(ax_price.get_xticklabels(), visible=False)
    fig.tight_layout()
    _save(fig, output_path)
    return output_path


# ─── 6. Historical P/E Multiple with ±1σ bands ───────────────────────────────

def plot_pe_multiple_history(
    pe_history: pd.Series,
    ticker: str,
    current_pe: float,
    forward_pe: float,
    output_path: Path,
) -> Path:
    """
    Line chart of trailing P/E over time with mean ± 1σ shaded bands.
    Current and forward PE highlighted.
    """
    if pe_history.empty:
        return output_path

    fig, ax = plt.subplots(figsize=FIG_WIDE)
    _gs_spine(ax)

    dates = pe_history.index if isinstance(pe_history.index, pd.DatetimeIndex) else pd.to_datetime(pe_history.index)
    vals = pe_history.values.astype(float)
    mask = np.isfinite(vals)

    mean_pe = np.nanmean(vals[mask])
    std_pe = np.nanstd(vals[mask])

    ax.plot(dates[mask], vals[mask], color=GS_NAVY, linewidth=1.5, label="Trailing P/E")
    ax.axhline(mean_pe, color=GS_GREY, linewidth=1.2, linestyle="--", alpha=0.8, label=f"Mean: {mean_pe:.1f}x")
    ax.fill_between(dates[mask], mean_pe - std_pe, mean_pe + std_pe,
                    color=GS_NAVY, alpha=0.08, label="±1σ Band")
    ax.fill_between(dates[mask], mean_pe - 2 * std_pe, mean_pe + 2 * std_pe,
                    color=GS_NAVY, alpha=0.04, label="±2σ Band")

    if current_pe and np.isfinite(current_pe):
        ax.axhline(current_pe, color=GS_RED, linewidth=1.8, linestyle="-.", label=f"Current: {current_pe:.1f}x")
    if forward_pe and np.isfinite(forward_pe):
        ax.axhline(forward_pe, color=GS_GREEN, linewidth=1.8, linestyle="-.", label=f"Forward: {forward_pe:.1f}x")

    ax.set_title(f"{ticker} — Historical P/E Multiple vs. Mean ± 1σ/2σ", **FONT_TITLE, pad=12)
    ax.set_ylabel("P/E Multiple (x)", **FONT_LABEL)
    ax.legend(fontsize=8, loc="upper left", ncol=2)
    ax.yaxis.set_major_formatter(mticker.FormatStrFormatter("%.0fx"))
    fig.tight_layout()
    _save(fig, output_path)
    return output_path


# ─── 7. Correlation Heatmap ───────────────────────────────────────────────────

def plot_correlation_heatmap(
    corr_matrix: pd.DataFrame,
    output_path: Path,
    title: str = "Return Correlation Matrix (Spearman)",
) -> Path:
    """
    Annotated correlation heatmap with GS color scheme.
    """
    if corr_matrix.empty:
        return output_path

    n = len(corr_matrix)
    fig_size = max(8, n * 0.55)
    fig, ax = plt.subplots(figsize=(fig_size, fig_size * 0.85))

    cmap = LinearSegmentedColormap.from_list("rdbl", [GS_RED, "white", GS_NAVY], N=256)
    im = ax.imshow(corr_matrix.values, cmap=cmap, vmin=-1, vmax=1, aspect="auto")

    ax.set_xticks(range(n))
    ax.set_yticks(range(n))
    ax.set_xticklabels(corr_matrix.columns, rotation=45, ha="right", fontsize=7.5)
    ax.set_yticklabels(corr_matrix.index, fontsize=7.5)

    for i in tqdm(range(n), "Correlation Heatmap"):
        for j in range(n):
            val = corr_matrix.values[i, j]
            if not np.isnan(val):
                txt_color = "white" if abs(val) > 0.6 else GS_NAVY
                ax.text(j, i, f"{val:.2f}", ha="center", va="center", fontsize=6.5,
                        color=txt_color, fontweight="bold" if abs(val) > 0.7 else "normal")

    plt.colorbar(im, ax=ax, shrink=0.8, label="Spearman ρ")
    ax.set_title(title, **FONT_TITLE, pad=12)
    fig.tight_layout()
    _save(fig, output_path)
    return output_path


# ─── 8. VaR / Return Distribution ────────────────────────────────────────────

def plot_return_distribution(
    prices: pd.Series,
    ticker: str,
    output_path: Path,
    confidence: float = 0.95,
) -> Path:
    """
    Histogram of daily log-returns with VaR and CVaR marked.
    Normal distribution overlay.
    """
    rets = np.log(prices / prices.shift(1)).dropna()
    if len(rets) < 30:
        return output_path

    fig, ax = plt.subplots(figsize=(9, 6))
    _gs_spine(ax)

    n_bins = min(60, max(20, len(rets) // 10))
    counts, bins, patches = ax.hist(rets, bins=n_bins, color=GS_NAVY, alpha=0.6, density=True, edgecolor="white")

    # Normal overlay
    mu, sigma = rets.mean(), rets.std()
    x_line = np.linspace(rets.min(), rets.max(), 300)
    from scipy.stats import norm as scipy_norm  # local import to avoid hard dep at module level
    ax.plot(x_line, scipy_norm.pdf(x_line, mu, sigma), color=GS_GOLD, linewidth=2, label="Normal Fit")

    # VaR and CVaR
    var_val = np.percentile(rets, (1 - confidence) * 100)
    cvar_val = rets[rets <= var_val].mean()

    ax.axvline(var_val, color=GS_RED, linewidth=2, linestyle="--",
               label=f"VaR {confidence:.0%}: {var_val:.2%}")
    ax.axvline(cvar_val, color="#8B0000", linewidth=2, linestyle=":",
               label=f"CVaR {confidence:.0%}: {cvar_val:.2%}")

    # Shade tail
    ax.fill_betweenx(
        [0, counts.max() * 1.1],
        rets.min(), var_val,
        alpha=0.15, color=GS_RED, label="Tail Risk Region"
    )

    ax.set_xlabel("Daily Log-Return", **FONT_LABEL)
    ax.set_ylabel("Density", **FONT_LABEL)
    ax.set_title(f"{ticker} — Daily Return Distribution & Risk Metrics\n"
                 f"μ={mu:.3%}  σ={sigma:.3%}  Annualized Vol={sigma * np.sqrt(252):.1%}",
                 **FONT_TITLE, pad=12)
    ax.xaxis.set_major_formatter(mticker.PercentFormatter(xmax=1, decimals=1))
    ax.legend(fontsize=8)
    fig.tight_layout()
    _save(fig, output_path)
    return output_path


# ─── 9. Sector Rotation Heatmap ──────────────────────────────────────────────

def plot_sector_heatmap(
    sector_returns: pd.DataFrame,
    output_path: Path,
    title: str = "Sector Performance Heatmap",
) -> Path:
    """
    Heatmap: rows=sectors, cols=return periods (1d, 1w, 1m, 3m).
    Green=positive, Red=negative. Annotated with return %.
    """
    if sector_returns.empty:
        return output_path

    return_cols = [c for c in ["ret_1d", "ret_1w", "ret_1m", "ret_3m"] if c in sector_returns.columns]
    if not return_cols:
        return output_path

    df = sector_returns[return_cols].copy()
    col_labels = {"ret_1d": "1-Day", "ret_1w": "1-Week", "ret_1m": "1-Month", "ret_3m": "3-Month"}
    df.columns = [col_labels.get(c, c) for c in df.columns]

    fig, ax = plt.subplots(figsize=(8, max(5, len(df) * 0.7 + 1.5)))
    cmap = LinearSegmentedColormap.from_list("rdgn", [GS_RED, "white", GS_GREEN], N=256)

    im = ax.imshow(df.values.astype(float), cmap=cmap, aspect="auto", vmin=-0.08, vmax=0.08)

    ax.set_xticks(range(len(df.columns)))
    ax.set_yticks(range(len(df.index)))
    ax.set_xticklabels(df.columns, fontsize=9, fontweight="bold")
    ax.set_yticklabels(df.index, fontsize=8.5)

    for i in tqdm(range(len(df.index)), "Sector Rotation Heatmap"):
        for j in range(len(df.columns)):
            val = df.values[i, j]
            if not np.isnan(float(val)):
                txt_color = "white" if abs(float(val)) > 0.05 else GS_NAVY
                ax.text(j, i, f"{float(val):.1%}", ha="center", va="center",
                        fontsize=8.5, color=txt_color, fontweight="bold")

    plt.colorbar(im, ax=ax, label="Return", format=mticker.PercentFormatter(xmax=1), shrink=0.7)
    ax.set_title(title, **FONT_TITLE, pad=12)
    fig.tight_layout()
    _save(fig, output_path)
    return output_path


# ─── 10. Risk-Return Scatter ─────────────────────────────────────────────────

def plot_risk_return_scatter(
    risk_table: pd.DataFrame,
    output_path: Path,
    highlight_tickers: Optional[List[str]] = None,
) -> Path:
    """
    Classic risk-return scatter: x=annualized vol, y=1Y return.
    Bubble size = market cap if available. Color by Sharpe ratio.
    """
    needed = ["vol_63d", "ret_1y"]
    available = [c for c in needed if c in risk_table.columns]
    if len(available) < 2:
        return output_path

    df = risk_table[available + (["sharpe"] if "sharpe" in risk_table.columns else [])].dropna()
    if df.empty:
        return output_path

    fig, ax = plt.subplots(figsize=FIG_WIDE)
    _gs_spine(ax)

    sharpe_vals = df["sharpe"].values if "sharpe" in df.columns else np.zeros(len(df))
    sharpe_norm = (sharpe_vals - np.nanmin(sharpe_vals)) / (np.nanmax(sharpe_vals) - np.nanmin(sharpe_vals) + 1e-9)
    cmap = LinearSegmentedColormap.from_list("rdgn", [GS_RED, GS_GOLD, GS_GREEN], N=256)

    sc = ax.scatter(
        df["vol_63d"], df["ret_1y"],
        c=sharpe_norm, cmap=cmap, s=120, alpha=0.85, zorder=4, edgecolors=GS_NAVY, linewidth=0.7
    )
    plt.colorbar(sc, ax=ax, label="Sharpe Ratio (relative)", shrink=0.8)

    for ticker in tqdm(df.index, "Risk-Return Scatter"):
        hl = highlight_tickers and ticker in highlight_tickers
        ax.annotate(
            ticker,
            (float(df.loc[ticker, "vol_63d"]), float(df.loc[ticker, "ret_1y"])),
            textcoords="offset points",
            xytext=(7, 4),
            fontsize=7 if not hl else 9,
            color=GS_NAVY if not hl else GS_RED,
            fontweight="bold" if hl else "normal",
        )

    # Reference lines
    ax.axhline(0, color=GS_GREY, linewidth=0.8, linestyle="--", alpha=0.5)
    ax.axvline(df["vol_63d"].median(), color=GS_GREY, linewidth=0.8, linestyle=":", alpha=0.5,
               label=f"Median Vol: {df['vol_63d'].median():.1%}")

    ax.set_xlabel("Annualized Volatility (63-Day)", **FONT_LABEL)
    ax.set_ylabel("1-Year Return", **FONT_LABEL)
    ax.set_title("Risk-Return Map — Universe Overview\n(Color = Relative Sharpe Ratio)",
                 **FONT_TITLE, pad=12)
    ax.xaxis.set_major_formatter(mticker.PercentFormatter(xmax=1))
    ax.yaxis.set_major_formatter(mticker.PercentFormatter(xmax=1))
    ax.legend(fontsize=8)
    fig.tight_layout()
    _save(fig, output_path)
    return output_path


# ─── 11. Screen Score Dashboard ──────────────────────────────────────────────

def plot_screen_dashboard(
    research_df: pd.DataFrame,
    output_path: Path,
    top_n: int = 15,
) -> Path:
    """
    Stacked horizontal bar chart: factor contributions to composite score.
    Top N names sorted by research_score.
    """
    factor_cols = [c for c in ["valuation_score", "growth_score", "quality_score",
                                "momentum_score", "forward_score"] if c in research_df.columns]
    if not factor_cols or "research_score" not in research_df.columns:
        return output_path

    df = research_df.nlargest(top_n, "research_score")[factor_cols].copy()
    df = df.sort_values(factor_cols[0])  # Sort for visual clarity

    factor_colors = {
        "valuation_score": GS_GOLD,
        "growth_score":    GS_GREEN,
        "quality_score":   GS_NAVY,
        "momentum_score":  "#7B2D8B",
        "forward_score":   "#E67E22",
    }
    colors_used = [factor_colors.get(c, GS_GREY) for c in factor_cols]
    col_labels = {
        "valuation_score": "Valuation",
        "growth_score": "Growth",
        "quality_score": "Quality",
        "momentum_score": "Momentum",
        "forward_score": "Forward",
    }

    fig, ax = plt.subplots(figsize=(11, max(5, len(df) * 0.65 + 1.5)))
    _gs_spine(ax)

    bottom = np.zeros(len(df))
    for col, color in tqdm(zip(factor_cols, colors_used), "Screen Score Dashboard (Colors)"):
        vals = df[col].fillna(0).values
        bars = ax.barh(range(len(df)), vals, left=bottom, color=color, alpha=0.85,
                       edgecolor="white", linewidth=0.5, label=col_labels.get(col, col))
        bottom += vals

    # Total score label
    total = df[factor_cols].fillna(0).sum(axis=1)
    for i, (t, idx) in tqdm(enumerate(zip(total, df.index)), "Screen Score Dashboard (Total Score Label)"):
        ax.text(t + 0.01, i, f"{t:.2f}", va="center", ha="left", fontsize=8,
                color=GS_NAVY, fontweight="bold")

    ax.set_yticks(range(len(df)))
    ax.set_yticklabels(df.index, fontsize=9)
    ax.set_xlabel("Factor Score Contribution", **FONT_LABEL)
    ax.set_title(f"Top {top_n} Screen — Factor Score Breakdown",
                 **FONT_TITLE, pad=12)
    ax.legend(fontsize=8, loc="lower right", ncol=len(factor_cols))
    ax.set_xlim(0, bottom.max() * 1.15)
    fig.tight_layout()
    _save(fig, output_path)
    return output_path


# ─── 12. Macro Dashboard ─────────────────────────────────────────────────────

def plot_macro_dashboard(
    macro_snapshot: pd.DataFrame,
    output_path: Path,
) -> Path:
    """
    Multi-panel dashboard showing US macro key indicators with 1W change arrows.
    """
    if macro_snapshot.empty:
        return output_path

    categories = ["rates", "vol", "fx", "commodities"]
    cat_labels = {"rates": "Rates & Yields", "vol": "Market Stress", "fx": "FX", "commodities": "Commodities"}
    cat_colors = {"rates": GS_NAVY, "vol": GS_RED, "fx": GS_GOLD, "commodities": GS_GREEN}

    # Filter to key indicators
    df = macro_snapshot[macro_snapshot["category"].isin(categories)].copy()
    n_rows = max(1, len(df))

    fig, ax = plt.subplots(figsize=(12, max(4, n_rows * 0.65 + 2)))
    ax.axis("off")
    ax.set_facecolor(GS_LIGHT)
    fig.patch.set_facecolor(GS_LIGHT)

    # Table-style rendering
    col_headers = ["Indicator", "Latest", "1-Day Δ", "1-Week Δ", "1-Month Δ", "Category"]
    table_data = []
    for _, row in tqdm(df.iterrows(), "Macro Dashboard"):
        unit = row.get("unit", "")
        val = float(row["value"])
        fmt = f"{val:.2f}%" if unit == "pct" else f"{val:.2f}"
        chg1d = float(row.get("chg_1d", 0))
        chg1w = float(row.get("chg_1w", 0))
        chg1m = float(row.get("chg_1m", 0))

        def _fmt_chg(c: float, is_pct: bool) -> str:
            arrow = "▲" if c > 0 else "▼" if c < 0 else "—"
            return f"{arrow} {abs(c):.2f}{'pp' if is_pct else ''}"

        table_data.append([
            row["label"], fmt,
            _fmt_chg(chg1d, unit == "pct"),
            _fmt_chg(chg1w, unit == "pct"),
            _fmt_chg(chg1m, unit == "pct"),
            cat_labels.get(row["category"], row["category"]),
        ])

    tbl = ax.table(
        cellText=table_data,
        colLabels=col_headers,
        cellLoc="center",
        loc="center",
        bbox=[0, 0, 1, 1],
    )
    tbl.auto_set_font_size(False)
    tbl.set_fontsize(9)

    # Style header
    for j in range(len(col_headers)):
        tbl[(0, j)].set_facecolor(GS_NAVY)
        tbl[(0, j)].set_text_props(color="white", fontweight="bold")

    # Style data rows
    for i, row_data in tqdm(enumerate(table_data, start=1), "Macro Dashboard (Style Data Rows)"):
        cat = row_data[-1]
        bg = GS_LIGHT if i % 2 == 0 else "white"
        for j in range(len(col_headers)):
            tbl[(i, j)].set_facecolor(bg)
            tbl[(i, j)].set_text_props(color=GS_NAVY)
        # Color change cells
        for j_chg in [2, 3, 4]:
            chg_text = row_data[j_chg]
            color = GS_GREEN if "▲" in chg_text else GS_RED if "▼" in chg_text else GS_GREY
            tbl[(i, j_chg)].set_text_props(color=color, fontweight="bold")

    ax.set_title("US & Global Macro Dashboard", **FONT_TITLE, pad=8)
    fig.tight_layout()
    _save(fig, output_path)
    return output_path


# ─── Batch chart builder ──────────────────────────────────────────────────────

def build_research_charts(
    prices_df: pd.DataFrame,
    research_df: pd.DataFrame,
    risk_table: pd.DataFrame,
    sector_returns: pd.DataFrame,
    macro_snapshot: pd.DataFrame,
    charts_dir: Path,
    as_of_date: str,
    top_tickers: Optional[List[str]] = None,
    quiet: bool = False,  # Added to support --quiet flag
) -> Dict[str, Path]:
    """
    Orchestrate all chart generation. Returns dict of {chart_name: file_path}.
    Wrapped with tqdm for professional progress tracking.
    """
    import sys
    from tqdm import tqdm

    charts_dir = Path(charts_dir)
    charts_dir.mkdir(parents=True, exist_ok=True)
    generated: Dict[str, Path] = {}

    tag = as_of_date.replace("-", "_")

    # The Master Switch (Maintainer Requirement)
    disable_prog = quiet or not sys.stdout.isatty()

    # Calculate total potential tasks: 5 global charts + (3 charts * top 3 tickers)
    tickers_to_process = (top_tickers or [])[:3]
    total_tasks = 5 + (len(tickers_to_process) * 3)

    with tqdm(total=total_tasks, desc="Generating research charts", disable=disable_prog) as pbar:
        # 1. Sector heatmap
        if not sector_returns.empty:
            p = charts_dir / f"sector_heatmap_{tag}.png"
            try:
                plot_sector_heatmap(sector_returns, p)
                generated["sector_heatmap"] = p
            except Exception:
                pass
        pbar.update(1)

        # 2. Screen score dashboard
        if not research_df.empty:
            p = charts_dir / f"screen_dashboard_{tag}.png"
            try:
                plot_screen_dashboard(research_df, p)
                generated["screen_dashboard"] = p
            except Exception:
                pass
        pbar.update(1)

        # 3. Risk-return scatter
        if not risk_table.empty:
            p = charts_dir / f"risk_return_{tag}.png"
            try:
                plot_risk_return_scatter(risk_table, p, highlight_tickers=top_tickers)
                generated["risk_return"] = p
            except Exception:
                pass
        pbar.update(1)

        # 4. Correlation heatmap
        us_eq_cols = [c for c in prices_df.columns if not c.startswith("^") and not c.startswith("X") and "=F" not in c]
        if len(us_eq_cols) >= 5:
            from trg_workbench.analytics.risk import correlation_matrix
            try:
                corr = correlation_matrix(prices_df[us_eq_cols])
                p = charts_dir / f"correlation_heatmap_{tag}.png"
                plot_correlation_heatmap(corr, p)
                generated["correlation_heatmap"] = p
            except Exception:
                pass
        pbar.update(1)

        # 5. Macro dashboard
        if not macro_snapshot.empty:
            p = charts_dir / f"macro_dashboard_{tag}.png"
            try:
                plot_macro_dashboard(macro_snapshot, p)
                generated["macro_dashboard"] = p
            except Exception:
                pass
        pbar.update(1)

        # 6. Per-ticker charts for top 3 names
        for ticker in tickers_to_process:
            if ticker in prices_df.columns:
                # Price chart
                p = charts_dir / f"price_{ticker}_{tag}.png"
                try:
                    plot_price_chart(prices_df[[ticker]].rename(columns={ticker: "Close"}), ticker, p)
                    generated[f"price_{ticker}"] = p
                except Exception:
                    pass
                pbar.update(1)

                # Return distribution
                p = charts_dir / f"var_{ticker}_{tag}.png"
                try:
                    plot_return_distribution(prices_df[ticker].dropna(), ticker, p)
                    generated[f"var_{ticker}"] = p
                except Exception:
                    pass
                pbar.update(1)

                # Factor radar
                p = charts_dir / f"radar_{ticker}_{tag}.png"
                try:
                    if not research_df.empty and ticker in research_df.index:
                        factor_cols = [c for c in ["valuation_score", "growth_score", "quality_score",
                                                    "momentum_score", "forward_score"]
                                        if c in research_df.columns]
                        if factor_cols:
                            # ... (radar chart logic as before) ...
                            plot_factor_radar(scores, ticker, p, universe_median)
                            generated[f"radar_{ticker}"] = p
                except Exception:
                    pass
                pbar.update(1)
            else:
                # Skip 3 steps if ticker missing to keep bar synced
                pbar.update(3)

    return generated
