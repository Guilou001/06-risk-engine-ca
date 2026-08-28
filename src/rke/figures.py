"""Trois figures : le cône de VaR et ses dépassements, la carte des feux de Bâle, la réactivité en 2020.

Style commun au portfolio : palette d'Okabe et Ito, axes étiquetés en unités réelles, virgule
décimale, 200 points par pouce, une idée par figure.
"""

from __future__ import annotations

from pathlib import Path

import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

OKABE_ITO = ["#0072B2", "#E69F00", "#009E73", "#D55E00", "#CC79A7", "#56B4E9", "#F0E442", "#000000"]
ZONES = {"vert": "#009E73", "jaune": "#F0E442", "rouge": "#D55E00"}


def use_style() -> None:
    import matplotlib as mpl
    from cycler import cycler
    from matplotlib.ticker import FuncFormatter

    mpl.rcParams.update({
        "figure.dpi": 200, "savefig.dpi": 200, "figure.constrained_layout.use": True,
        "font.size": 11, "axes.titlesize": 12, "axes.prop_cycle": cycler(color=OKABE_ITO),
        "axes.spines.top": False, "axes.spines.right": False,
        "axes.grid": True, "grid.alpha": 0.3, "grid.linewidth": 0.5,
        "legend.frameon": False, "lines.linewidth": 1.4,
    })
    return FuncFormatter(lambda v, _: f"{v:g}".replace(".", ","))


def fig_var_cone(returns: pd.Series, var_hist: pd.Series, var_fhs: pd.Series,
                 dest: Path) -> None:
    """Rendements quotidiens contre moins la VaR 99 % de deux modèles, dépassements FHS marqués."""
    fr = use_style()
    fig, ax = plt.subplots(figsize=(10, 4.6))
    r = returns.reindex(var_fhs.index)
    ax.plot(r.index, 100 * r, color="0.75", linewidth=0.5, label="Rendement quotidien")
    ax.plot(var_hist.index, -100 * var_hist, color=OKABE_ITO[0], label="VaR 99 % historique (500 j)")
    ax.plot(var_fhs.index, -100 * var_fhs, color=OKABE_ITO[3], linewidth=1.0,
            label="VaR 99 % simulation historique filtrée")
    hits = r[r < -var_fhs]
    ax.plot(hits.index, 100 * hits, "v", color=OKABE_ITO[3], markersize=4, linestyle="none",
            label=f"Dépassements FHS ({len(hits)})")
    ax.set_ylabel("Rendement quotidien (%)")
    ax.yaxis.set_major_formatter(fr)
    ax.set_title("La VaR filtrée descend pendant les crises, la VaR historique y arrive en retard")
    ax.legend(loc="lower left", fontsize=9, ncols=2)
    fig.savefig(dest)
    plt.close(fig)


def fig_traffic_map(zones_by_model: dict[str, pd.DataFrame], dest: Path) -> None:
    """Une cellule par modèle et par année : la couleur est la zone de Bâle, le chiffre le compte."""
    use_style()
    models = list(zones_by_model)
    years = sorted(set().union(*[set(z.index) for z in zones_by_model.values()]))
    fig, ax = plt.subplots(figsize=(11, 0.55 * len(models) + 1.6))
    for i, m in enumerate(models):
        z = zones_by_model[m]
        for j, y in enumerate(years):
            if y not in z.index:
                continue
            zone = z.loc[y, "zone"]
            ax.add_patch(plt.Rectangle((j, i), 1, 1, color=ZONES[zone], alpha=0.85))
            ax.text(j + 0.5, i + 0.5, str(int(z.loc[y, "depassements"])), ha="center", va="center",
                    fontsize=8, color="black")
    ax.set_xlim(0, len(years))
    ax.set_ylim(0, len(models))
    ax.set_xticks(np.arange(len(years)) + 0.5, [str(y) for y in years], rotation=45, fontsize=8)
    ax.set_yticks(np.arange(len(models)) + 0.5, models)
    ax.grid(False)
    ax.invert_yaxis()
    ax.set_title("Feux tricolores de Bâle, année par année : vert 0-4 dépassements, jaune 5-9, rouge 10+")
    fig.savefig(dest)
    plt.close(fig)


def fig_reactivity(returns: pd.Series, forecasts: dict[str, pd.DataFrame], start: str, end: str,
                   dest: Path) -> None:
    """Zoom sur une crise : la vitesse à laquelle chaque VaR rejoint la nouvelle volatilité."""
    fr = use_style()
    fig, ax = plt.subplots(figsize=(9, 4.4))
    r = returns.loc[start:end]
    ax.bar(r.index, 100 * r, width=1.0, color="0.8", label="Rendement quotidien")
    for (name, fc), color in zip(forecasts.items(), OKABE_ITO, strict=False):
        v = fc["var"].loc[start:end]
        ax.plot(v.index, -100 * v, color=color, label=f"VaR 99 % {name}")
    ax.set_ylabel("Rendement quotidien (%)")
    ax.yaxis.set_major_formatter(fr)
    ax.xaxis.set_major_locator(mdates.MonthLocator())
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m"))
    ax.set_title("Mars 2020 : l'EWMA et la FHS suivent le choc en quelques jours, l'historique reste figé deux ans")
    ax.legend(loc="lower right", fontsize=9)
    fig.savefig(dest)
    plt.close(fig)
