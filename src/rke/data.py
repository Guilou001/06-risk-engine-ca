"""Données : le portefeuille de la politique du dépôt 03-portfolio-ops-ca, vu par le risque.

Le portefeuille suivi est le profil équilibré du moteur d'allocation (six FNB de Toronto, cibles
25/20/15/5/25/10), dont on mesure ici le rendement QUOTIDIEN : c'est l'échelle de temps du risque,
la VaR réglementaire se calcule à un jour. Approximation déclarée : les poids sont tenus constants
aux cibles (le dépôt 03 mesure une rotation réelle de 2,8 % par an, la dérive intra-mois est du
second ordre pour la VaR à un jour). Prix ajustés Yahoo, jamais commités (usage personnel).
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

ETFS: dict[str, float] = {
    "XIU.TO": 0.25,   # actions canadiennes (S&P/TSX 60)
    "XSP.TO": 0.20,   # actions américaines (S&P 500 couvert en CAD)
    "XIN.TO": 0.15,   # actions internationales (MSCI EAFE couvert en CAD)
    "XRE.TO": 0.05,   # immobilier coté (FPI canadiennes)
    "XBB.TO": 0.25,   # obligations canadiennes (univers)
    "XSB.TO": 0.10,   # obligations court terme
}

RAW = Path("data/raw/prix_fnb.parquet")


def fetch(dest: Path = RAW) -> pd.DataFrame:
    """Télécharge les prix ajustés quotidiens des six FNB et les écrit en parquet."""
    import yfinance as yf

    prices = yf.download(list(ETFS), period="max", auto_adjust=True, progress=False)["Close"]
    prices = prices[list(ETFS)].dropna(how="all")
    dest.parent.mkdir(parents=True, exist_ok=True)
    prices.to_parquet(dest)
    return prices


def portfolio_returns(prices: pd.DataFrame) -> pd.Series:
    """Rendement quotidien du portefeuille aux poids cibles, restreint à la période commune."""
    rets = prices.pct_change().dropna()
    weights = pd.Series(ETFS)
    port = (rets[weights.index] * weights).sum(axis=1)
    port.name = "portefeuille"
    return port


def load_returns(path: Path = RAW) -> pd.Series:
    """Charge le parquet local ; erreur claire si `rke fetch` n'a pas tourné."""
    if not path.exists():
        raise FileNotFoundError(f"{path} absent : lancer d'abord `rke fetch` (les prix ne sont pas commités)")
    return portfolio_returns(pd.read_parquet(path))
