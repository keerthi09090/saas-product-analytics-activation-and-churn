"""Print the saved temporal-test evaluation and portfolio success check."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd

if __package__ is None or __package__ == "":
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ml.utils import METRICS_PATH


def main() -> None:
    payload = json.loads(METRICS_PATH.read_text())
    rows = []
    for name, model in payload["models"].items():
        test = model["test"]
        rows.append(
            {
                "Model": name,
                "PR-AUC": test["pr_auc"],
                "ROC-AUC": test["roc_auc"],
                "Precision": test["precision"],
                "Recall": test["recall"],
                "F1": test["f1"],
                "Top-10% Lift": test["top_10_pct_lift"],
                "Confusion Matrix": test["confusion_matrix"],
            }
        )
    comparison = pd.DataFrame(rows)
    print("\nChurn Model Evaluation\n")
    print(comparison.to_string(index=False, float_format=lambda value: f"{value:.3f}"))

    logistic = payload["models"]["Logistic Regression"]["test"]
    tree = payload["models"]["HistGradientBoosting"]["test"]
    relative_pr_gain = (
        (tree["pr_auc"] - logistic["pr_auc"]) / logistic["pr_auc"]
        if logistic["pr_auc"]
        else 0.0
    )
    target_met = tree["top_10_pct_lift"] >= 2 or relative_pr_gain >= 0.20
    print(f"\nSelected model: {payload['selected_model']}")
    print(f"Tree PR-AUC relative improvement: {relative_pr_gain:.1%}")
    print(f"Tree top-10% lift: {tree['top_10_pct_lift']:.2f}x")
    print(f"Portfolio success target met: {'YES' if target_met else 'NO'}")


if __name__ == "__main__":
    main()
