"""Six modèles de VaR et d'Expected Shortfall à un jour, sans regard sur le futur.

Conventions communes. La VaR à un jour au niveau alpha (par exemple 1 %), la perte que le portefeuille
ne dépasse qu'un jour sur cent, est rapportée en POSITIF : VaR = moins le quantile alpha des rendements.
L'Expected Shortfall (ES), la perte moyenne des jours où la VaR est dépassée, est positif aussi.
Chaque fonction produit la série complète des prévisions : la prévision du jour t n'utilise que les
rendements des jours antérieurs à t (fenêtre glissante de `window` jours), ce que les tests vérifient.

1. `historical`   : quantile empirique des `window` derniers jours (simulation historique).
2. `gaussian`     : moyenne et écart-type de la fenêtre, quantile de la loi normale.
3. `student`      : loi de Student ajustée par maximum de vraisemblance (queues épaisses), réajustée
                    tous les `refit` jours.
4. `ewma`         : volatilité RiskMetrics (lambda = 0,94), quantile normal, moyenne nulle.
5. `fhs`          : simulation historique filtrée (Barone-Adesi, Giannopoulos et Vosper, 1999) : les
                    rendements sont standardisés par la volatilité EWMA du jour, puis remis à l'échelle
                    de la volatilité prévue ; le quantile est pris sur ces rendements re-scalés.
6. `garch`        : GARCH(1,1) de Bollerslev (1986), vraisemblance normale maximisée ici même (aucune
                    bibliothèque), réajusté tous les `refit` jours, innovations normales.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from scipy import optimize, stats

EWMA_LAMBDA = 0.94
REFIT = 21


def _to_frame(index: pd.Index, var: np.ndarray, es: np.ndarray) -> pd.DataFrame:
    return pd.DataFrame({"var": var, "es": es}, index=index)


def historical_series(r: pd.Series, window: int, alpha: float) -> pd.DataFrame:
    x = r.to_numpy()
    n = len(x)
    var = np.full(n, np.nan)
    es = np.full(n, np.nan)
    for t in range(window, n):
        w = x[t - window:t]
        q = np.quantile(w, alpha)
        var[t] = -q
        tail = w[w <= q]
        es[t] = -tail.mean()
    return _to_frame(r.index, var, es)[window:]


def gaussian_series(r: pd.Series, window: int, alpha: float) -> pd.DataFrame:
    mu = r.rolling(window).mean().shift(1)
    sd = r.rolling(window).std(ddof=1).shift(1)
    z = stats.norm.ppf(alpha)
    var = -(mu + sd * z)
    es = -(mu - sd * stats.norm.pdf(z) / alpha)
    out = pd.DataFrame({"var": var, "es": es}).dropna()
    return out


def student_series(r: pd.Series, window: int, alpha: float, refit: int = REFIT) -> pd.DataFrame:
    x = r.to_numpy()
    n = len(x)
    var = np.full(n, np.nan)
    es = np.full(n, np.nan)
    params: tuple[float, float, float] | None = None
    for t in range(window, n):
        if params is None or (t - window) % refit == 0:
            df, loc, scale = stats.t.fit(x[t - window:t])
            df = max(df, 2.05)                      # sous 2, la variance n'existe pas
            params = (df, loc, scale)
        df, loc, scale = params
        t_a = stats.t.ppf(alpha, df)
        var[t] = -(loc + scale * t_a)
        es[t] = -(loc - scale * stats.t.pdf(t_a, df) * (df + t_a**2) / ((df - 1.0) * alpha))
    return _to_frame(r.index, var, es)[window:]


def ewma_variance(r: pd.Series, window: int, lam: float = EWMA_LAMBDA) -> pd.Series:
    """Variance EWMA prévue pour le jour t : sigma2[t] = lam sigma2[t-1] + (1 - lam) r[t-1]^2.

    La récursion démarre au jour 1, semée sur la variance des `window` premiers jours ; les valeurs
    avant `window` ne servent qu'à standardiser (FHS), les prévisions de VaR ne commencent qu'à
    `window`, où la graine n'a vu que des jours passés : aucun regard sur le futur.
    """
    from scipy.signal import lfilter

    x = r.to_numpy()
    n = len(x)
    seed = float(np.var(x[:window], ddof=1))
    u = (1.0 - lam) * x[:-1] ** 2                   # contribution de r[t-1]^2 au jour t
    sig2 = np.full(n, np.nan)
    sig2[0] = seed
    sig2[1:], _ = lfilter([1.0], [1.0, -lam], u, zi=np.array([lam * seed]))
    return pd.Series(sig2, index=r.index)


def ewma_series(r: pd.Series, window: int, alpha: float) -> pd.DataFrame:
    sig = np.sqrt(ewma_variance(r, window))
    z = stats.norm.ppf(alpha)
    var = -sig * z
    es = sig * stats.norm.pdf(z) / alpha
    # avant `window`, la graine de la récursion regarde des jours encore à venir : on ne prévoit pas là
    return pd.DataFrame({"var": var, "es": es})[window:]


def fhs_series(r: pd.Series, window: int, alpha: float) -> pd.DataFrame:
    x = r.to_numpy()
    n = len(x)
    sig2 = ewma_variance(r, window).to_numpy()
    var = np.full(n, np.nan)
    es = np.full(n, np.nan)
    for t in range(window + 1, n):
        past = slice(t - window, t)
        z = x[past] / np.sqrt(sig2[past])           # rendements standardisés par leur vol du jour
        sim = np.sqrt(sig2[t]) * z                  # remis à l'échelle de la vol prévue pour t
        q = np.quantile(sim, alpha)
        var[t] = -q
        es[t] = -sim[sim <= q].mean()
    return _to_frame(r.index, var, es)[window + 1:]


def garch_fit(x: np.ndarray) -> tuple[float, float, float]:
    """GARCH(1,1) de moyenne nulle par maximum de vraisemblance normale : rend (omega, a, b)."""
    v = float(np.var(x, ddof=1))

    from scipy.signal import lfilter

    def nll(p: np.ndarray) -> float:
        omega, a, b = p
        if omega <= 0 or a < 0 or b < 0 or a + b >= 0.9995:
            return 1e10
        u = omega + a * x[:-1] ** 2                 # sigma2[t] = u[t-1] + b sigma2[t-1], sigma2[0] = v
        sig2 = np.empty(len(x))
        sig2[0] = v
        sig2[1:], _ = lfilter([1.0], [1.0, -b], u, zi=np.array([b * v]))
        if np.any(sig2 <= 0):
            return 1e10
        return float(0.5 * np.sum(np.log(sig2) + x**2 / sig2))

    best = None
    for a0, b0 in ((0.05, 0.90), (0.10, 0.80), (0.02, 0.95)):
        res = optimize.minimize(nll, x0=np.array([v * (1 - a0 - b0), a0, b0]), method="Nelder-Mead",
                                options={"xatol": 1e-8, "fatol": 1e-8, "maxiter": 4000})
        if best is None or res.fun < best.fun:
            best = res
    omega, a, b = best.x
    return float(omega), float(a), float(b)


def garch_series(r: pd.Series, window: int, alpha: float, refit: int = REFIT) -> pd.DataFrame:
    x = r.to_numpy()
    n = len(x)
    var = np.full(n, np.nan)
    es = np.full(n, np.nan)
    z = stats.norm.ppf(alpha)
    params: tuple[float, float, float] | None = None
    sig2_t = np.nan
    for t in range(window, n):
        if params is None or (t - window) % refit == 0:
            fit_slice = x[t - window:t]
            params = garch_fit(fit_slice)
            omega, a, b = params
            s = float(np.var(fit_slice, ddof=1))    # recursion rejouée sur la fenêtre d'ajustement
            for u in range(t - window + 1, t):
                s = omega + a * x[u - 1] ** 2 + b * s
            sig2_t = omega + a * x[t - 1] ** 2 + b * s
        else:
            omega, a, b = params
            sig2_t = omega + a * x[t - 1] ** 2 + b * sig2_t
        sig = np.sqrt(sig2_t)
        var[t] = -sig * z
        es[t] = sig * stats.norm.pdf(z) / alpha
    return _to_frame(r.index, var, es)[window:]


MODELS = {
    "historique": historical_series,
    "gaussien": gaussian_series,
    "student": student_series,
    "ewma": ewma_series,
    "fhs": fhs_series,
    "garch": garch_series,
}
