"""Le moteur sur données synthétiques : quantiles exacts, absence de fuite, récupération GARCH, juges."""

import numpy as np
import pandas as pd
import pytest
from scipy import stats

from rke.backtests import (
    acerbi_szekely_z2,
    basel_traffic_light,
    christoffersen_pvalues,
    kupiec_pvalue,
    violations,
)
from rke.models import (
    MODELS,
    ewma_variance,
    fhs_series,
    garch_fit,
    gaussian_series,
    historical_series,
)


def gauss_returns(n: int = 3000, sd: float = 0.01, seed: int = 0) -> pd.Series:
    rng = np.random.default_rng(seed)
    idx = pd.bdate_range("2010-01-01", periods=n)
    return pd.Series(rng.normal(0.0, sd, n), index=idx)


def test_gaussian_var_matches_the_true_quantile():
    r = gauss_returns()
    fc = gaussian_series(r, window=500, alpha=0.01)
    true_var = 0.01 * stats.norm.ppf(0.99)
    assert fc["var"].mean() == pytest.approx(true_var, rel=0.05)
    hit_rate = violations(r, fc["var"]).mean()
    assert 0.005 < hit_rate < 0.02              # environ 1 % de dépassements attendus


def test_historical_var_close_to_gaussian_on_normal_data():
    r = gauss_returns()
    hist = historical_series(r, window=500, alpha=0.01)["var"].mean()
    gaus = gaussian_series(r, window=500, alpha=0.01)["var"].mean()
    assert hist == pytest.approx(gaus, rel=0.15)


def test_ewma_variance_matches_hand_recursion_and_ignores_the_future():
    r = gauss_returns(300)
    sig2 = ewma_variance(r, window=100, lam=0.94)
    x = r.to_numpy()
    # récursion refaite à la main sur les 5 premiers pas
    s_hand = float(np.var(x[:100], ddof=1))
    for t in range(1, 6):
        s_hand = 0.94 * s_hand + 0.06 * x[t - 1] ** 2
        assert sig2.iloc[t] == pytest.approx(s_hand, rel=1e-12)
    shocked = r.copy()
    shocked.iloc[-1] = -0.5                     # le futur bouge, le passé ne doit pas
    pd.testing.assert_series_equal(sig2.iloc[:-1], ewma_variance(shocked, 100).iloc[:-1])


def test_fhs_scales_linearly_with_returns():
    r = gauss_returns(700)
    a = fhs_series(r, window=250, alpha=0.01)
    b = fhs_series(3.0 * r, window=250, alpha=0.01)
    assert np.allclose(3.0 * a["var"], b["var"], rtol=1e-10)


def test_garch_fit_recovers_simulated_parameters():
    rng = np.random.default_rng(7)
    omega, a, b = 2e-6, 0.08, 0.90
    n = 4000
    x = np.empty(n)
    sig2 = omega / (1 - a - b)
    for t in range(n):
        x[t] = np.sqrt(sig2) * rng.standard_normal()
        sig2 = omega + a * x[t] ** 2 + b * sig2
    om_hat, a_hat, b_hat = garch_fit(x)
    assert a_hat == pytest.approx(a, abs=0.04)
    assert b_hat == pytest.approx(b, abs=0.05)
    assert om_hat / (1 - a_hat - b_hat) == pytest.approx(omega / (1 - a - b), rel=0.3)


def test_every_model_ignores_the_last_day():
    r = gauss_returns(650)
    shocked = r.copy()
    shocked.iloc[-1] = -0.40
    for name, fn in MODELS.items():
        base = fn(r, 250, 0.01)
        again = fn(shocked, 250, 0.01)
        pd.testing.assert_frame_equal(base, again), name


def test_kupiec_accepts_the_expected_count_and_rejects_three_times_too_many():
    assert kupiec_pvalue(10, 1000, 0.01) > 0.5
    assert kupiec_pvalue(30, 1000, 0.01) < 1e-3


def test_christoffersen_flags_clustered_violations():
    scattered = pd.Series(0, index=range(1000))
    scattered.iloc[::100] = 1                   # 10 dépassements espacés
    clustered = pd.Series(0, index=range(1000))
    clustered.iloc[500:510] = 1                 # 10 dépassements consécutifs
    p_ind_scattered, _ = christoffersen_pvalues(scattered, 0.01)
    p_ind_clustered, _ = christoffersen_pvalues(clustered, 0.01)
    assert p_ind_clustered < 1e-6 < p_ind_scattered


def test_traffic_light_zones_follow_the_basel_thresholds():
    idx = pd.bdate_range("2019-01-01", "2021-12-31")
    v = pd.Series(0, index=idx)
    v.loc[v.index.year == 2019] = 0
    v.loc[(v.index.year == 2020)] = 0
    v.iloc[np.flatnonzero(v.index.year == 2020)[:7]] = 1     # 7 en 2020 -> jaune
    v.iloc[np.flatnonzero(v.index.year == 2021)[:12]] = 1    # 12 en 2021 -> rouge
    z = basel_traffic_light(v)
    assert z.loc[2019, "zone"] == "vert"
    assert z.loc[2020, "zone"] == "jaune"
    assert z.loc[2021, "zone"] == "rouge"


def test_z2_is_near_zero_when_es_is_correct():
    rng = np.random.default_rng(1)
    n = 20000
    idx = pd.bdate_range("2000-01-03", periods=n)
    r = pd.Series(rng.normal(0.0, 0.01, n), index=idx)
    alpha = 0.025
    z = stats.norm.ppf(alpha)
    var = pd.Series(-0.01 * z, index=idx)
    es = pd.Series(0.01 * stats.norm.pdf(z) / alpha, index=idx)
    z2, ratio = acerbi_szekely_z2(r, var, es, alpha)
    assert abs(z2) < 0.15
    assert ratio == pytest.approx(1.0, abs=0.1)
