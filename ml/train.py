"""Train and compare leakage-safe churn models with local MLflow tracking."""

from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

import joblib
import mlflow
import mlflow.sklearn
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, OrdinalEncoder, StandardScaler

if __package__ is None or __package__ == "":
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ml.explain import calculate_feature_importance
from ml.utils import (
    ARTIFACT_DIR,
    BASELINE_MODEL_PATH,
    CATEGORICAL_FEATURES,
    FEATURE_COLUMNS,
    IMPORTANCE_PATH,
    METRICS_PATH,
    MLRUNS_DIR,
    MODEL_PATH,
    NUMERIC_FEATURES,
    TARGET_COLUMN,
    ensure_artifact_dir,
    choose_validation_threshold,
    evaluate_probabilities,
    load_training_dataset,
    metrics_for_mlflow,
    temporal_split,
    write_json,
)


def logistic_pipeline() -> Pipeline:
    numeric = Pipeline(
        [
            ("impute", SimpleImputer(strategy="median")),
            ("scale", StandardScaler()),
        ]
    )
    categorical = Pipeline(
        [
            ("impute", SimpleImputer(strategy="most_frequent")),
            ("encode", OneHotEncoder(handle_unknown="ignore", sparse_output=False)),
        ]
    )
    preprocessing = ColumnTransformer(
        [("numeric", numeric, NUMERIC_FEATURES), ("categorical", categorical, CATEGORICAL_FEATURES)]
    )
    return Pipeline(
        [
            ("preprocess", preprocessing),
            (
                "model",
                LogisticRegression(
                    class_weight="balanced", max_iter=1_000, random_state=42
                ),
            ),
        ]
    )


def tree_pipeline() -> Pipeline:
    numeric = Pipeline([("impute", SimpleImputer(strategy="median"))])
    categorical = Pipeline(
        [
            ("impute", SimpleImputer(strategy="most_frequent")),
            (
                "encode",
                OrdinalEncoder(
                    handle_unknown="use_encoded_value", unknown_value=-1
                ),
            ),
        ]
    )
    preprocessing = ColumnTransformer(
        [("numeric", numeric, NUMERIC_FEATURES), ("categorical", categorical, CATEGORICAL_FEATURES)]
    )
    return Pipeline(
        [
            ("preprocess", preprocessing),
            (
                "model",
                HistGradientBoostingClassifier(
                    learning_rate=0.05,
                    max_iter=200,
                    max_leaf_nodes=15,
                    min_samples_leaf=8,
                    class_weight="balanced",
                    early_stopping=False,
                    random_state=42,
                ),
            ),
        ]
    )


def fit_and_measure(
    pipeline: Pipeline,
    train: pd.DataFrame,
    validation: pd.DataFrame,
    test: pd.DataFrame,
) -> tuple[Pipeline, dict[str, dict[str, object]]]:
    pipeline.fit(train[FEATURE_COLUMNS], train[TARGET_COLUMN])
    validation_probability = pipeline.predict_proba(validation[FEATURE_COLUMNS])[:, 1]
    test_probability = pipeline.predict_proba(test[FEATURE_COLUMNS])[:, 1]
    threshold = choose_validation_threshold(
        validation[TARGET_COLUMN], validation_probability
    )
    return pipeline, {
        "validation": evaluate_probabilities(
            validation[TARGET_COLUMN], validation_probability, threshold=threshold
        ),
        "test": evaluate_probabilities(
            test[TARGET_COLUMN], test_probability, threshold=threshold
        ),
    }


def selection_key(metrics: dict[str, dict[str, object]]) -> tuple[float, float]:
    validation = metrics["validation"]
    return (
        float(validation["top_10_pct_lift"]),
        float(validation["pr_auc"]),
    )


def main() -> None:
    ensure_artifact_dir()
    MLRUNS_DIR.mkdir(parents=True, exist_ok=True)
    frame = load_training_dataset()
    train, validation, test, periods = temporal_split(frame)
    models = {
        "Logistic Regression": logistic_pipeline(),
        "HistGradientBoosting": tree_pipeline(),
    }
    trained: dict[str, Pipeline] = {}
    results: dict[str, dict[str, dict[str, object]]] = {}

    mlflow.set_tracking_uri(MLRUNS_DIR.as_uri())
    mlflow.set_experiment("saas_churn_prediction")
    for model_name, pipeline in models.items():
        fitted, metrics = fit_and_measure(
            pipeline, train, validation, test
        )
        trained[model_name] = fitted
        results[model_name] = metrics
        with mlflow.start_run(run_name=model_name):
            run_params = {
                "model_name": model_name,
                "training_date": date.today().isoformat(),
                "feature_count": len(FEATURE_COLUMNS),
                "train_rows": len(train),
                "validation_rows": len(validation),
                "test_rows": len(test),
                "prediction_horizon_days": 30,
                "temporal_split": True,
                "class_weight": "balanced",
            }
            if model_name == "Logistic Regression":
                run_params.update({"max_iter": 1_000, "scaling": "standard"})
            else:
                run_params.update(
                    {
                        "learning_rate": 0.05,
                        "max_iter": 200,
                        "max_leaf_nodes": 15,
                        "min_samples_leaf": 8,
                    }
                )
            mlflow.log_params(run_params)
            mlflow.log_dict({"features": FEATURE_COLUMNS}, "feature_list.json")
            mlflow.log_metrics(metrics_for_mlflow(metrics["validation"], "validation"))
            mlflow.log_metrics(metrics_for_mlflow(metrics["test"], "test"))
            mlflow.sklearn.log_model(fitted, artifact_path="model")

    selected_name = max(results, key=lambda name: selection_key(results[name]))
    selected_pipeline = trained[selected_name]
    bundle = {
        "pipeline": selected_pipeline,
        "model_name": selected_name,
        "features": FEATURE_COLUMNS,
        "prediction_horizon_days": 30,
        "risk_thresholds": {"high": 0.60, "medium": 0.30},
        "split_periods": periods,
    }
    joblib.dump(bundle, MODEL_PATH)
    joblib.dump(
        {
            "pipeline": trained["Logistic Regression"],
            "model_name": "Logistic Regression",
            "features": FEATURE_COLUMNS,
        },
        BASELINE_MODEL_PATH,
    )

    importance = calculate_feature_importance(
        selected_pipeline, test, test[TARGET_COLUMN]
    )
    importance.to_csv(IMPORTANCE_PATH, index=False)

    churn_rows = int(frame[TARGET_COLUMN].sum())
    payload = {
        "generated_on": date.today().isoformat(),
        "prediction_horizon_days": 30,
        "selected_model": selected_name,
        "selection_rule": "highest validation top-10% lift, then validation PR-AUC",
        "class_balance": {
            "total_rows": len(frame),
            "churn_rows": churn_rows,
            "non_churn_rows": len(frame) - churn_rows,
            "churn_rate": float(frame[TARGET_COLUMN].mean()),
        },
        "split_periods": periods,
        "models": results,
    }
    write_json(METRICS_PATH, payload)

    comparison = pd.DataFrame(
        [
            {
                "Model": name,
                "PR-AUC": values["test"]["pr_auc"],
                "ROC-AUC": values["test"]["roc_auc"],
                "Precision": values["test"]["precision"],
                "Recall": values["test"]["recall"],
                "F1": values["test"]["f1"],
                "Top-10% Lift": values["test"]["top_10_pct_lift"],
            }
            for name, values in results.items()
        ]
    )
    print("\nTemporal split")
    print(f"Train: {', '.join(periods['train'])} ({len(train)} rows)")
    print(f"Validation: {periods['validation'][0]} ({len(validation)} rows)")
    print(f"Test: {periods['test'][0]} ({len(test)} rows)")
    print("\nModel comparison (future test month)\n")
    print(comparison.to_string(index=False, float_format=lambda value: f"{value:.3f}"))
    print(f"\nSelected model: {selected_name}")
    print(f"Saved: {MODEL_PATH.relative_to(ARTIFACT_DIR.parent)}")
    print(f"MLflow tracking: {MLRUNS_DIR.relative_to(ARTIFACT_DIR.parent)}")


if __name__ == "__main__":
    main()
