"""Compare a newly trained model against the current Production model and,
if it is better (or none exists yet), promote it in the MLflow registry.

Environment variables:
    MLFLOW_TRACKING_URI    MLflow server (default: http://localhost:5000)
    MLFLOW_MODEL_NAME      Registered model name (default: stockflow)
"""

from __future__ import annotations

import logging
import math
import os
from dataclasses import dataclass

import mlflow

logger = logging.getLogger(__name__)

PRODUCTION = "Production"


@dataclass
class PromotionResult:
    """Outcome of an evaluate-and-promote decision."""

    promoted: bool
    version: str | None
    reason: str
    new_metric: float = float("nan")
    prod_metric: float = float("nan")


def _version_metric(
    client: mlflow.MlflowClient, model_name: str, version: str, metric_key: str
) -> float:
    """Fetch a logged metric for the run behind a given model version."""
    mv = client.get_model_version(model_name, version)
    run = client.get_run(mv.run_id)
    return run.data.metrics.get(metric_key, float("nan"))


def _production_version(
    client: mlflow.MlflowClient, model_name: str
) -> str | None:
    """Return the current Production version number, or None if unset."""
    versions = client.get_latest_versions(model_name, stages=[PRODUCTION])
    return versions[0].version if versions else None


def evaluate_and_promote(
    new_version: str,
    model_name: str | None = None,
    metric_key: str = "val_auc",
) -> PromotionResult:
    """Promote ``new_version`` to Production iff it beats the incumbent.

    Cold start (no Production model) promotes unconditionally. A higher
    ``metric_key`` wins; if the new metric is NaN (e.g. single-class
    validation slice), promotion is skipped unless there is no incumbent.
    """
    mlflow.set_tracking_uri(os.getenv("MLFLOW_TRACKING_URI", "http://localhost:5000"))
    model_name = model_name or os.getenv("MLFLOW_MODEL_NAME", "stockflow")
    client = mlflow.MlflowClient()

    new_metric = _version_metric(client, model_name, new_version, metric_key)
    prod_version = _production_version(client, model_name)

    def promote(reason: str) -> PromotionResult:
        client.transition_model_version_stage(
            name=model_name,
            version=new_version,
            stage=PRODUCTION,
            archive_existing_versions=True,
        )
        logger.info("Promoted %s v%s to Production: %s", model_name, new_version, reason)
        return PromotionResult(True, new_version, reason, new_metric)

    # Cold start: nothing in Production yet.
    if prod_version is None:
        return promote("no incumbent Production model")

    # Same version already in Production — nothing to do.
    if prod_version == new_version:
        return PromotionResult(
            False, new_version, "version already in Production", new_metric
        )

    prod_metric = _version_metric(client, model_name, prod_version, metric_key)

    if math.isnan(new_metric):
        return PromotionResult(
            False, prod_version, f"new {metric_key} is NaN — keeping incumbent",
            new_metric, prod_metric,
        )

    if math.isnan(prod_metric) or new_metric > prod_metric:
        return promote(
            f"{metric_key} {new_metric:.4f} > incumbent {prod_metric:.4f}"
        )

    return PromotionResult(
        False, prod_version,
        f"{metric_key} {new_metric:.4f} <= incumbent {prod_metric:.4f}",
        new_metric, prod_metric,
    )
