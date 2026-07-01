"""Tests for src.models.evaluate — MlflowClient is mocked."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from src.models import evaluate


def _make_client(prod_version=None, metrics=None):
    """Build a mock MlflowClient.

    metrics maps version -> {metric_key: value}; get_model_version/get_run are
    wired so _version_metric resolves to those values.
    """
    metrics = metrics or {}
    client = MagicMock()

    # current Production version (or none)
    if prod_version is None:
        client.get_latest_versions.return_value = []
    else:
        mv_prod = MagicMock(version=prod_version)
        client.get_latest_versions.return_value = [mv_prod]

    def get_model_version(name, version):
        return MagicMock(run_id=f"run-{version}")

    def get_run(run_id):
        version = run_id.split("-", 1)[1]
        return MagicMock(data=MagicMock(metrics=metrics.get(version, {})))

    client.get_model_version.side_effect = get_model_version
    client.get_run.side_effect = get_run
    return client


@pytest.fixture(autouse=True)
def _patch_mlflow(monkeypatch):
    monkeypatch.setattr(evaluate.mlflow, "set_tracking_uri", lambda *a, **k: None)


def _run(monkeypatch, client, new_version):
    monkeypatch.setattr(evaluate.mlflow, "MlflowClient", lambda *a, **k: client)
    return evaluate.evaluate_and_promote(new_version, model_name="stockflow")


def test_cold_start_promotes(monkeypatch):
    client = _make_client(prod_version=None, metrics={"1": {"val_auc": 0.6}})
    res = _run(monkeypatch, client, "1")
    assert res.promoted is True
    client.transition_model_version_stage.assert_called_once()


def test_promotes_when_better(monkeypatch):
    client = _make_client(
        prod_version="1", metrics={"1": {"val_auc": 0.55}, "2": {"val_auc": 0.70}}
    )
    res = _run(monkeypatch, client, "2")
    assert res.promoted is True
    assert res.version == "2"


def test_keeps_incumbent_when_worse(monkeypatch):
    client = _make_client(
        prod_version="1", metrics={"1": {"val_auc": 0.80}, "2": {"val_auc": 0.60}}
    )
    res = _run(monkeypatch, client, "2")
    assert res.promoted is False
    assert res.version == "1"
    client.transition_model_version_stage.assert_not_called()


def test_keeps_incumbent_when_new_metric_nan(monkeypatch):
    client = _make_client(
        prod_version="1",
        metrics={"1": {"val_auc": 0.60}, "2": {"val_auc": float("nan")}},
    )
    res = _run(monkeypatch, client, "2")
    assert res.promoted is False


def test_same_version_in_production_is_noop(monkeypatch):
    client = _make_client(prod_version="3", metrics={"3": {"val_auc": 0.6}})
    res = _run(monkeypatch, client, "3")
    assert res.promoted is False
    client.transition_model_version_stage.assert_not_called()
