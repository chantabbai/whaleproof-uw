from __future__ import annotations

from datetime import date

import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score

from whaleproof.core.verdict.weights import BACKTESTABLE, CURRENT, Weights

from .runner import BacktestRow



def _features(base: Weights) -> list[str]:
    return sorted(n for n in base.w if n in BACKTESTABLE)


def _xy(rows: list[BacktestRow], features: list[str], label: str = "r5"):
    rows = [r for r in rows if getattr(r, label) is not None]
    x = np.array([[r.scores.get(n, 0.0) if r.available.get(n) else 0.0 for n in features] for r in rows])
    y = np.array([1 if getattr(r, label) > 0 else 0 for r in rows])
    return x, y, rows


def _parity(w: dict[str, float]) -> dict[str, float]:
    return {n: v for n, v in w.items() if n in BACKTESTABLE}


def _go_hit(rows: list[BacktestRow], w: dict[str, float]) -> float | None:
    hits = []
    total = sum(abs(v) for v in w.values())
    for r in rows:
        avail = sum(abs(w[n]) for n in w if r.available.get(n))
        if not avail or r.r5 is None or r.hard_fail:
            continue
        score = 50 + 50 * sum(w[n] * r.scores.get(n, 0.0) * r.confidences.get(n, 1.0)
                              for n in w if r.available.get(n)) / avail
        if score >= 70 and avail / total >= 0.5:
            hits.append(r.r5 > 0)
    return sum(hits) / len(hits) if hits else None


def fit_weights(rows: list[BacktestRow], split: date, version: str, min_rows: int = 200,
                base: Weights = CURRENT, signed: bool = False, label: str = "r5") -> Weights:
    """L2 logistic fit on rows before `split`. signed=True keeps negative coefficients (fade that check) and scales
    so Σ|w| equals the base's backtestable budget; the default clips at 0 (original v1 path)."""
    features = _features(base)
    train = [r for r in rows if r.session_date < split]
    test = [r for r in rows if r.session_date >= split]
    xtr, ytr, _ = _xy(train, features, label)
    if len(ytr) < min_rows or len(set(ytr)) < 2:
        raise ValueError(f"need ≥{min_rows} labelled train rows with both classes, got {len(ytr)}")
    model = LogisticRegression(C=0.5, random_state=0, max_iter=1000).fit(xtr, ytr)
    coef = model.coef_[0] if signed else np.clip(model.coef_[0], 0, None)
    budget = sum(abs(base.w[n]) for n in features)
    scale = np.abs(coef).sum()
    learned = (coef / scale * budget) if scale > 0 else np.array([base.w[n] for n in features])
    w = dict(base.w)
    for n, v in zip(features, learned):
        w[n] = round(float(v), 6)
    xte, yte, test_rows = _xy(test, features, label)
    auc = float(roc_auc_score(yte, model.predict_proba(xte)[:, 1])) if len(yte) and len(set(yte)) == 2 else None
    meta = {"train_end": split.isoformat(), "n_train": int(len(ytr)), "oos_n": int(len(yte)), "oos_auc": auc,
            f"oos_go_hit_rate_{base.version}": _go_hit(test_rows, _parity(base.w)),
            "oos_go_hit_rate_new": _go_hit(test_rows, _parity(w)),
            "features": features, "base": base.version, "signed": signed, "label": label,
            "source": "L2 logistic regression, " + ("signs allowed (Σ|w| = budget)" if signed else "coef clipped ≥0")}
    return Weights(version, w, meta)
