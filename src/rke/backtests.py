"""Les backtests : un modèle de VaR ne se juge pas à sa théorie mais à ses dépassements.

Un dépassement (une violation) est un jour où la perte réalisée excède la VaR annoncée la veille.
À 99 %, on en attend un jour sur cent : ni beaucoup plus (le modèle sous-estime le risque), ni
beaucoup moins (il immobilise trop de capital). Quatre juges :

1. Kupiec (1995), le test de couverture : le NOMBRE de dépassements est-il compatible avec 1 % ?
2. Christoffersen (1998), le test d'indépendance : les dépassements arrivent-ils en grappes ?
   Un modèle lent à réagir viole plusieurs jours de suite, ce que Kupiec ne voit pas.
3. Les feux tricolores de Bâle : le compte de dépassements sur environ 250 jours ouvrés classe le
   modèle en zone verte (0 à 4), jaune (5 à 9, majoration de capital) ou rouge (10 et plus).
4. Acerbi et Székely (2014) pour l'ES : les jours de dépassement, la perte moyenne réalisée
   vaut-elle l'ES annoncé ? La statistique Z2 vaut zéro si oui, elle est négative si l'ES
   sous-estime les pertes de queue.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from scipy import stats


def violations(returns: pd.Series, var: pd.Series) -> pd.Series:
    """Un par jour où le rendement tombe sous moins la VaR annoncée pour ce jour."""
    aligned = returns.reindex(var.index)
    return (aligned < -var).astype(int)


def _xlogx(k: float, p: float) -> float:
    return 0.0 if k == 0 else k * np.log(p)


def _kupiec_lr(n_violations: int, n_obs: int, alpha: float) -> float:
    x, n = n_violations, n_obs
    p_hat = x / n
    ll_null = _xlogx(n - x, 1 - alpha) + _xlogx(x, alpha)
    ll_alt = (_xlogx(n - x, 1 - p_hat) if p_hat < 1 else 0.0) + _xlogx(x, p_hat if p_hat > 0 else 1.0)
    return -2.0 * (ll_null - ll_alt)


def kupiec_pvalue(n_violations: int, n_obs: int, alpha: float) -> float:
    """Test de couverture non conditionnelle : LR contre khi-deux à 1 degré de liberté."""
    return float(stats.chi2.sf(_kupiec_lr(n_violations, n_obs, alpha), df=1))


def christoffersen_pvalues(viol: pd.Series, alpha: float) -> tuple[float, float]:
    """(p indépendance, p couverture conditionnelle) : transitions 0->1 contre 1->1, khi-deux."""
    v = viol.to_numpy()
    prev, curr = v[:-1], v[1:]
    n00 = int(np.sum((prev == 0) & (curr == 0)))
    n01 = int(np.sum((prev == 0) & (curr == 1)))
    n10 = int(np.sum((prev == 1) & (curr == 0)))
    n11 = int(np.sum((prev == 1) & (curr == 1)))
    pi = (n01 + n11) / max(n00 + n01 + n10 + n11, 1)
    pi0 = n01 / max(n00 + n01, 1)
    pi1 = n11 / max(n10 + n11, 1)
    ll_null = _xlogx(n00 + n10, 1 - pi) + _xlogx(n01 + n11, pi)
    ll_alt = _xlogx(n00, 1 - pi0) + _xlogx(n01, pi0) + _xlogx(n10, 1 - pi1) + _xlogx(n11, pi1)
    lr_ind = -2.0 * (ll_null - ll_alt)
    p_ind = float(stats.chi2.sf(lr_ind, df=1))
    lr_uc = _kupiec_lr(int(v.sum()), len(v), alpha)
    p_cc = float(stats.chi2.sf(lr_uc + lr_ind, df=2))
    return p_ind, p_cc


def basel_traffic_light(viol: pd.Series) -> pd.DataFrame:
    """Compte des dépassements par année civile et zone de Bâle (vert 0-4, jaune 5-9, rouge 10+).

    Le comité calibre les seuils pour 250 jours ; les années comptent ici 249 à 252 jours ouvrés,
    l'écart est déclaré dans la colonne n_jours.
    """
    rows = []
    for year, grp in viol.groupby(viol.index.year):
        n = int(grp.sum())
        zone = "vert" if n <= 4 else ("jaune" if n <= 9 else "rouge")
        rows.append({"annee": year, "n_jours": len(grp), "depassements": n, "zone": zone})
    return pd.DataFrame(rows).set_index("annee")


def acerbi_szekely_z2(returns: pd.Series, var: pd.Series, es: pd.Series,
                      alpha: float) -> tuple[float, float]:
    """Statistique Z2 d'Acerbi-Székely (leur test 2) et ratio perte/ES des jours de dépassement.

    Z2 = somme( r_t 1{r_t < -VaR_t} / (T alpha ES_t) ) + 1, avec alpha le niveau NOMINAL de la VaR
    testée ; zéro en espérance si l'ES est juste, négatif s'il sous-estime les pertes de queue.
    Le ratio est la perte moyenne réalisée les jours de dépassement divisée par l'ES moyen annoncé
    ces jours-là (1 = juste).
    """
    r = returns.reindex(var.index)
    hit = r < -var
    t_obs = len(r)
    if hit.sum() == 0:
        return np.nan, np.nan
    z2 = float((r[hit] / (t_obs * alpha * es[hit])).sum() + 1.0)
    ratio = float((-r[hit]).mean() / es[hit].mean())
    return z2, ratio


def summary_table(returns: pd.Series, forecasts: dict[str, pd.DataFrame], alpha: float) -> pd.DataFrame:
    """Une ligne par modèle : dépassements observés et attendus, Kupiec, Christoffersen, ES."""
    rows = {}
    for name, fc in forecasts.items():
        viol = violations(returns, fc["var"])
        n, x = len(viol), int(viol.sum())
        p_ind, p_cc = christoffersen_pvalues(viol, alpha)
        z2, ratio = acerbi_szekely_z2(returns, fc["var"], fc["es"], alpha)
        rows[name] = {
            "n_jours": n,
            "depassements": x,
            "attendus": round(alpha * n, 1),
            "taux_pct": 100.0 * x / n,
            "p_kupiec": kupiec_pvalue(x, n, alpha),
            "p_independance": p_ind,
            "p_couverture_cond": p_cc,
            "z2_acerbi_szekely": z2,
            "ratio_perte_sur_es": ratio,
            "var_moyenne_pct": 100.0 * float(fc["var"].mean()),
        }
    return pd.DataFrame(rows).T
