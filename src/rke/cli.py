"""Ligne de commande : télécharger, backtester, tracer. Chaque commande est rejouable."""

from __future__ import annotations

from pathlib import Path

import typer

app = typer.Typer(help="Moteur de risque : VaR et ES par six modèles, backtests de Kupiec, "
                       "Christoffersen, Bâle et Acerbi-Székely sur un portefeuille canadien.")

WINDOW = 500          # deux ans de jours ouvrés pour estimer chaque modèle
ALPHA_VAR = 0.01      # VaR 99 %, le niveau des feux tricolores de Bâle
ALPHA_ES = 0.025      # ES 97,5 %, le niveau retenu par la FRTB


@app.callback()
def main() -> None:
    """Sous-commandes nommées."""


@app.command()
def fetch() -> None:
    """Télécharge les prix quotidiens des six FNB de la politique (Yahoo, non commités)."""
    from rke import data

    prices = data.fetch()
    typer.echo(f"{prices.shape[0]} jours, {prices.shape[1]} FNB, de {prices.index[0].date()} "
               f"à {prices.index[-1].date()} -> {data.RAW}")


@app.command()
def backtest(out: Path = Path("results")) -> None:
    """Les six modèles sur tout l'historique : tables de backtests et trois figures."""
    import time

    from rke import backtests, classeur, data, figures, models

    t0 = time.time()
    returns = data.load_returns()
    forecasts_var: dict = {}
    forecasts_es: dict = {}
    for name, fn in models.MODELS.items():
        forecasts_var[name] = fn(returns, WINDOW, ALPHA_VAR)
        forecasts_es[name] = fn(returns, WINDOW, ALPHA_ES)
    # échantillon commun : chaque modèle jugé sur exactement les mêmes jours
    common = forecasts_var["fhs"].index
    for d in (forecasts_var, forecasts_es):
        for name in d:
            d[name] = d[name].reindex(common).dropna()
            common = d[name].index
    for name in forecasts_var:
        forecasts_var[name] = forecasts_var[name].reindex(common)
        forecasts_es[name] = forecasts_es[name].reindex(common)
        typer.echo(f"  {name} : {len(forecasts_var[name])} prévisions")

    tables = out / "tables"
    tables.mkdir(parents=True, exist_ok=True)
    summary_var = backtests.summary_table(returns, forecasts_var, ALPHA_VAR)
    summary_var.to_csv(tables / "backtests_var99.csv")
    summary_es = backtests.summary_table(returns, forecasts_es, ALPHA_ES)
    summary_es.to_csv(tables / "backtests_es975.csv")

    zones = {}
    for name, fc in forecasts_var.items():
        z = backtests.basel_traffic_light(backtests.violations(returns, fc["var"]))
        z.to_csv(tables / f"feux_bale_{name}.csv")
        zones[name] = z

    figs = out / "figures"
    figs.mkdir(parents=True, exist_ok=True)
    figures.fig_var_cone(returns, forecasts_var["historique"]["var"], forecasts_var["fhs"]["var"],
                         figs / "cone_var.png")
    figures.fig_traffic_map(zones, figs / "feux_bale.png")
    figures.fig_reactivity(returns, {k: forecasts_var[k] for k in ("historique", "ewma", "fhs")},
                           "2020-01-01", "2020-09-30", figs / "reactivite_2020.png")

    # Le classeur, à formules vivantes : dans un service de risque on relit un classeur, on change
    # une case et on regarde le résultat bouger, ce qu'un tableau figé ne permet pas.
    chemin = classeur.construire(summary_var, zones, out.parent / "reports" / "tests_depassement.xlsx")
    typer.echo(f"classeur -> {chemin}")

    typer.echo(f"{len(returns)} jours, tables -> {tables}, 3 figures -> {figs}, "
               f"durée {time.time() - t0:.0f} s")


if __name__ == "__main__":
    app()
