"""Data quality and exploratory figures, saved as PNG."""

from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from matplotlib.colors import LinearSegmentedColormap  # noqa: E402

INK = "#0b0b0b"
INK_SECONDARY = "#52514e"
INK_MUTED = "#8a8984"
GRID = "#e6e5e1"
SURFACE = "#ffffff"
SERIES = ("#2a78d6", "#eb6834", "#1baf7a")
NEUTRAL = "#c9c8c3"
BLUE_RAMP = ("#f4f8fd", "#cde2fb", "#9ec5f4", "#6da7ec", "#3987e5", "#256abf", "#184f95", "#0d366b")

TREND_STATES = ("MO", "IL")
TREND_INDICATORS = ("DIA01", "NPW14", "TOB04")
SPREAD_INDICATORS = ("NPW14", "NPW06", "TOB04", "DIA01", "MEN02", "HEA01", "ALC06", "SDH09")


def _style() -> None:
    plt.rcParams.update(
        {
            "figure.facecolor": SURFACE,
            "axes.facecolor": SURFACE,
            "axes.edgecolor": GRID,
            "axes.labelcolor": INK_SECONDARY,
            "axes.titlecolor": INK,
            "axes.titlesize": 11,
            "axes.titleweight": "bold",
            "axes.grid": False,
            "xtick.color": INK_SECONDARY,
            "ytick.color": INK_SECONDARY,
            "font.size": 9,
            "font.family": "DejaVu Sans",
            "savefig.dpi": 160,
            "savefig.bbox": "tight",
        }
    )


def _finish(fig: plt.Figure, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, facecolor=SURFACE)
    plt.close(fig)
    return path


def _despine(ax: plt.Axes, keep_bottom: bool = True) -> None:
    for side in ("top", "right", "left"):
        ax.spines[side].set_visible(False)
    ax.spines["bottom"].set_visible(keep_bottom)


def period_label(start: int, end: int) -> str:
    return str(start) if start == end else f"{start}-{end}"


def plot_value_availability(availability: pd.DataFrame, path: Path) -> Path:
    """Stacked share of long-table rows with a value, suppressed, or not available, by topic."""
    _style()
    data = availability.sort_values("pct_value_reported")
    parts = [
        ("pct_value_reported", "Value reported", SERIES[0]),
        ("pct_suppressed", "Suppressed (small numbers or unreliable)", SERIES[1]),
        ("pct_not_available", "Not available", NEUTRAL),
    ]
    fig, ax = plt.subplots(figsize=(9, 0.32 * len(data) + 1.4))
    left = np.zeros(len(data))
    y = np.arange(len(data))
    for col, label, color in parts:
        ax.barh(
            y, data[col], left=left, color=color, height=0.72, label=label, edgecolor=SURFACE, linewidth=1.5
        )
        left += data[col].to_numpy()
    for yi, pct in zip(y, data["pct_value_reported"], strict=True):
        ax.text(1, yi, f"{pct:.0f}%", va="center", ha="left", color=SURFACE, fontsize=8, fontweight="bold")
    ax.set_yticks(y, data["topic"])
    ax.set_xlim(0, 100)
    ax.set_xlabel("Share of rows (%)")
    ax.xaxis.grid(True, color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)
    _despine(ax)
    ax.tick_params(axis="y", length=0)
    ax.legend(loc="lower center", bbox_to_anchor=(0.4, 1.0), ncol=3, frameon=False, fontsize=8.5)
    ax.set_title("Where CDC estimates are missing, by topic (all strata)", loc="left", pad=26)
    return _finish(fig, path)


def plot_panel_coverage(coverage: pd.DataFrame, path: Path) -> Path:
    """Heatmap of the share of filled panel cells by topic and reporting period."""
    _style()
    grid = coverage.pivot(index="topic", columns="period", values="pct_filled")
    grid = grid.loc[grid.mean(axis=1).sort_values(ascending=False).index]
    cmap = LinearSegmentedColormap.from_list("blue", BLUE_RAMP)
    fig, ax = plt.subplots(figsize=(1.0 * grid.shape[1] + 3.5, 0.36 * grid.shape[0] + 1.6))
    ax.imshow(grid.to_numpy(dtype=float), cmap=cmap, vmin=0, vmax=100, aspect="auto")
    for (i, j), val in np.ndenumerate(grid.to_numpy(dtype=float)):
        if np.isnan(val):
            continue
        ax.text(
            j,
            i,
            f"{val:.0f}",
            ha="center",
            va="center",
            fontsize=7.5,
            color=SURFACE if val >= 55 else INK_SECONDARY,
        )
    ax.set_xticks(range(grid.shape[1]), grid.columns, rotation=45, ha="right")
    ax.set_yticks(range(grid.shape[0]), grid.index)
    ax.set_xticks(np.arange(-0.5, grid.shape[1]), minor=True)
    ax.set_yticks(np.arange(-0.5, grid.shape[0]), minor=True)
    ax.grid(which="minor", color=SURFACE, linewidth=1.5)
    ax.tick_params(which="both", length=0)
    for spine in ax.spines.values():
        spine.set_visible(False)
    ax.set_xlabel("Reporting period (year_start-year_end)")
    ax.set_title("Wide panel coverage: % of location x indicator cells with a value", loc="left", pad=10)
    return _finish(fig, path)


def plot_state_trends(long: pd.DataFrame, catalog: pd.DataFrame, path: Path) -> Path | None:
    """Small multiples: MO and IL against the U.S. for a few adult indicators."""
    _style()
    cat = catalog.set_index("question_id")
    indicators = [q for q in TREND_INDICATORS if q in cat.index]
    if not indicators:
        return None
    fig, axes = plt.subplots(1, len(indicators), figsize=(4.2 * len(indicators), 3.6), squeeze=False)
    for ax, qid in zip(axes[0], indicators, strict=True):
        meta = cat.loc[qid]
        rows = long[
            (long["question_id"] == qid)
            & (long["data_value_type_id"] == meta["data_value_type_id"])
            & (long["stratification_category_id1"] == "OVERALL")
            & (long["year_start"] == long["year_end"])
            & long["location_abbr"].isin([*TREND_STATES, "US"])
            & long["data_value"].notna()
        ]
        for loc, color in zip(TREND_STATES, SERIES, strict=False):
            d = rows[rows["location_abbr"] == loc].sort_values("year_start")
            ax.plot(
                d["year_start"],
                d["data_value"],
                color=color,
                linewidth=2,
                marker="o",
                markersize=6,
                label=loc,
                markeredgecolor=SURFACE,
                markeredgewidth=1.5,
            )
        us = rows[rows["location_abbr"] == "US"].sort_values("year_start")
        ax.plot(
            us["year_start"], us["data_value"], color=INK_MUTED, linewidth=1.5, linestyle="--", label="U.S."
        )
        years = sorted(rows["year_start"].dropna().unique())
        ax.set_xticks(years, [str(y) for y in years])
        ax.yaxis.grid(True, color=GRID, linewidth=0.8)
        _despine(ax)
        ax.tick_params(length=0)
        ax.set_title(_wrap(meta["question"], 34), loc="left", fontsize=10)
        ax.set_ylabel(f"{meta['data_value_type']} ({meta['data_value_unit']})")
    handles, labels = axes[0][0].get_legend_handles_labels()
    fig.legend(handles, labels, loc="upper right", ncol=3, frameon=False, bbox_to_anchor=(1.0, 1.06))
    fig.suptitle(
        "Missouri and Illinois against the U.S. (overall population)",
        x=0.01,
        y=1.04,
        ha="left",
        fontsize=12,
        fontweight="bold",
        color=INK,
    )
    fig.tight_layout()
    return _finish(fig, path)


def plot_state_spread(long: pd.DataFrame, catalog: pd.DataFrame, path: Path) -> Path | None:
    """State values for selected indicators in the latest single year, IQR outliers labelled."""
    _style()
    cat = catalog.set_index("question_id")
    panels = []
    for qid in SPREAD_INDICATORS:
        if qid not in cat.index or cat.loc[qid, "data_value_unit"] != "%":
            continue
        meta = cat.loc[qid]
        rows = long[
            (long["question_id"] == qid)
            & (long["data_value_type_id"] == meta["data_value_type_id"])
            & (long["stratification_category_id1"] == "OVERALL")
            & (long["year_start"] == long["year_end"])
            & (long["location_abbr"] != "US")
            & long["data_value"].notna()
        ]
        if rows.empty:
            continue
        latest = rows[rows["year_start"] == rows["year_start"].max()]
        if len(latest) >= 10:
            panels.append((meta, latest))
    if not panels:
        return None

    fig, ax = plt.subplots(figsize=(9, 0.62 * len(panels) + 1.4))
    rng = np.random.default_rng(0)
    for i, (_meta, d) in enumerate(panels):
        q1, med, q3 = d["data_value"].quantile([0.25, 0.5, 0.75])
        ax.add_patch(plt.Rectangle((q1, i - 0.28), q3 - q1, 0.56, color=BLUE_RAMP[1], zorder=1))
        ax.plot([med, med], [i - 0.28, i + 0.28], color=SERIES[0], linewidth=2, zorder=2)
        jitter = rng.uniform(-0.18, 0.18, len(d))
        normal = ~d["is_outlier_iqr"].to_numpy()
        ax.scatter(
            d["data_value"][normal],
            i + jitter[normal],
            s=14,
            color=INK_MUTED,
            alpha=0.8,
            zorder=3,
            linewidths=0,
        )
        out = d[d["is_outlier_iqr"]]
        ax.scatter(
            out["data_value"],
            i + jitter[~normal],
            s=40,
            color=SERIES[1],
            zorder=4,
            edgecolors=SURFACE,
            linewidths=1.2,
        )
        for (_, r), dy in zip(out.iterrows(), jitter[~normal], strict=True):
            ax.annotate(
                r["location_abbr"],
                (r["data_value"], i + dy),
                xytext=(4, 4),
                textcoords="offset points",
                fontsize=7.5,
                color=INK,
            )
    labels = [
        f"{_wrap(m['question'], 44)}\n{m['data_value_type']}, {int(d['year_start'].iloc[0])}"
        for m, d in panels
    ]
    ax.set_yticks(range(len(panels)), labels, fontsize=8)
    ax.invert_yaxis()
    ax.set_xlabel("Percent of population")
    ax.xaxis.grid(True, color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)
    _despine(ax)
    ax.tick_params(length=0)
    ax.scatter([], [], s=14, color=INK_MUTED, label="State or territory")
    ax.scatter([], [], s=40, color=SERIES[1], label="IQR outlier (labelled)")
    ax.legend(loc="lower center", bbox_to_anchor=(0.35, 1.0), ncol=2, frameon=False, fontsize=8.5)
    ax.set_title("State spread for selected adult indicators (box = middle 50%)", loc="left", pad=24)
    return _finish(fig, path)


def _wrap(text: str, width: int) -> str:
    words, lines, line = str(text).split(), [], ""
    for w in words:
        if len(line) + len(w) + 1 > width and line:
            lines.append(line)
            line = w
        else:
            line = f"{line} {w}".strip()
    lines.append(line)
    return "\n".join(lines[:2]) + ("..." if len(lines) > 2 else "")
