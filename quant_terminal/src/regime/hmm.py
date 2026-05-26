"""Gaussian HMM for volatility regime detection.

Approach
--------
We model **log-returns** of a benchmark (SPY by default) as draws from a mixture
of N Gaussian states, with hidden Markov transitions. After Baum-Welch fitting:

* States are **re-labelled** by ascending volatility (state 0 = lowest σ, state
  N-1 = highest σ) so the colour mapping is stable across runs.
* We expose: per-bar state path, transition matrix, current state + probability,
  expected duration (1 / (1 - p_self)), and a stationary distribution.

Public API
----------
* ``fit_volatility_hmm(returns, n_states=3, *, n_iter=100, seed=42) -> HMMRegimeResult``
* ``label_states_by_volatility(model, X) -> mapping``

Inputs are expected to be log-returns; daily frequency by convention.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd

from src.utils.logging import get_logger

log = get_logger(__name__)


REGIME_LABELS_3 = ["LOW vol", "MID vol", "HIGH vol"]
REGIME_LABELS_4 = ["CALM", "LOW vol", "HIGH vol", "PANIC"]
REGIME_COLORS = {
    "LOW vol": "#22C55E",
    "MID vol": "#F59E0B",
    "HIGH vol": "#EF4444",
    "CALM": "#10B981",
    "PANIC": "#7F1D1D",
}


@dataclass
class HMMRegimeResult:
    n_states: int
    states: np.ndarray              # shape (T,) — 0..n_states-1 (low → high vol)
    state_probs: np.ndarray         # shape (T, n_states)
    transition_matrix: np.ndarray   # shape (n_states, n_states)
    means: np.ndarray               # shape (n_states,) — mean log-return per state
    stds: np.ndarray                # shape (n_states,) — σ per state
    state_labels: list[str]
    index: pd.Index                 # original timeseries index aligned to states
    log_likelihood: float
    aic: float
    bic: float
    converged: bool
    raw_model: Any = None           # the fitted hmmlearn.hmm.GaussianHMM

    @property
    def current_state(self) -> int:
        return int(self.states[-1])

    @property
    def current_label(self) -> str:
        return self.state_labels[self.current_state]

    @property
    def current_probs(self) -> dict[str, float]:
        return {
            lbl: float(self.state_probs[-1, i])
            for i, lbl in enumerate(self.state_labels)
        }

    @property
    def expected_duration(self) -> dict[str, float]:
        """1 / (1 − p_self) — expected bars before leaving the state."""
        out: dict[str, float] = {}
        for i, lbl in enumerate(self.state_labels):
            p_self = float(self.transition_matrix[i, i])
            out[lbl] = float(1.0 / (1.0 - p_self)) if p_self < 1.0 else float("inf")
        return out

    @property
    def stationary_distribution(self) -> np.ndarray:
        """Left eigenvector of P corresponding to eigenvalue 1 — long-run frequencies."""
        evals, evecs = np.linalg.eig(self.transition_matrix.T)
        # Find the eigenvector closest to eigenvalue 1
        idx = int(np.argmin(np.abs(evals - 1.0)))
        v = np.real(evecs[:, idx])
        v = v / v.sum()
        return np.abs(v)


def fit_volatility_hmm(
    returns: pd.Series,
    n_states: int = 3,
    *,
    n_iter: int = 200,
    seed: int = 42,
    feature: str = "abs",
) -> HMMRegimeResult:
    """Fit a Gaussian HMM on a return series and return a labelled result.

    Parameters
    ----------
    returns : pd.Series
        Log-return (or simple return) series indexed by datetime.
    n_states : int
        Number of hidden states (typically 2–4).
    n_iter : int
        Baum-Welch max iterations.
    seed : int
        Random seed for the EM initialiser — determinism across runs.
    feature : str
        ``"abs"`` (default) fits on absolute returns → volatility regimes.
        ``"raw"`` fits on signed returns → captures drift+vol jointly.
        ``"sq"`` fits on squared returns → cleanest vol proxy but noisier tails.

    Returns
    -------
    HMMRegimeResult
    """
    try:
        from hmmlearn.hmm import GaussianHMM
    except ImportError as exc:
        raise RuntimeError("hmmlearn missing — `pip install hmmlearn`") from exc

    r = pd.to_numeric(returns, errors="coerce").dropna()
    if len(r) < max(60, n_states * 30):
        raise ValueError(
            f"need at least {max(60, n_states * 30)} bars to fit a {n_states}-state HMM, "
            f"got {len(r)}"
        )
    if feature == "abs":
        x = r.abs().to_numpy().reshape(-1, 1)
    elif feature == "sq":
        x = (r.to_numpy() ** 2).reshape(-1, 1)
    else:
        x = r.to_numpy().reshape(-1, 1)

    model = GaussianHMM(
        n_components=n_states,
        covariance_type="full",
        n_iter=n_iter,
        random_state=seed,
        init_params="stmc",
    )
    model.fit(x)

    raw_states = model.predict(x)
    raw_probs = model.predict_proba(x)
    raw_means = model.means_.flatten()
    raw_stds = np.sqrt(np.array([np.sqrt(model.covars_[i, 0, 0]) ** 2 for i in range(n_states)]))

    # ---- Relabel states by ascending volatility (within-state σ) ----------
    state_sigmas = np.array([
        float(r.iloc[raw_states == s].std() if (raw_states == s).any() else 0.0)
        for s in range(n_states)
    ])
    order = np.argsort(state_sigmas)              # low σ → high σ
    perm = {old: new for new, old in enumerate(order)}
    new_states = np.array([perm[s] for s in raw_states])
    new_probs = raw_probs[:, order]
    new_means = raw_means[order]
    new_stds = raw_stds[order]
    new_trans = model.transmat_[np.ix_(order, order)]

    # ---- Labels ----------------------------------------------------------
    if n_states == 3:
        labels = REGIME_LABELS_3[:]
    elif n_states == 4:
        labels = REGIME_LABELS_4[:]
    else:
        labels = [f"State {i} (σ={new_stds[i]:.3f})" for i in range(n_states)]

    # ---- Model-selection criteria ---------------------------------------
    n = len(x)
    # Effective parameter count for a Gaussian HMM with full covariance:
    #   k = n_states - 1                         (initial probs)
    #     + n_states * (n_states - 1)            (transition matrix)
    #     + n_states                             (means, 1-D obs)
    #     + n_states                             (variances)
    k = (n_states - 1) + n_states * (n_states - 1) + 2 * n_states
    ll = float(model.score(x))
    aic = 2 * k - 2 * ll
    bic = k * np.log(n) - 2 * ll

    return HMMRegimeResult(
        n_states=n_states,
        states=new_states,
        state_probs=new_probs,
        transition_matrix=new_trans,
        means=new_means,
        stds=new_stds,
        state_labels=labels,
        index=r.index,
        log_likelihood=ll,
        aic=float(aic),
        bic=float(bic),
        converged=bool(getattr(model.monitor_, "converged", False)),
        raw_model=model,
    )


def label_states_by_volatility(result: HMMRegimeResult) -> pd.DataFrame:
    """Return a wide DataFrame: index, state, label, posterior for each label."""
    out = pd.DataFrame(index=result.index)
    out["state"] = result.states
    out["label"] = [result.state_labels[s] for s in result.states]
    for i, lbl in enumerate(result.state_labels):
        out[f"p_{lbl}"] = result.state_probs[:, i]
    return out
