# evaluation.py
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from sklearn.metrics import (
    log_loss, roc_auc_score, average_precision_score,
    classification_report, confusion_matrix, ConfusionMatrixDisplay,
)


def evaluate_probabilities(pipeline, X_test, y_test):
    """Full probabilistic evaluation. Returns (probas, class_names)."""
    probas  = pipeline.predict_proba(X_test)
    classes = pipeline.classes_
    preds   = pipeline.predict(X_test)

    print("       CLASSIFIER EVALUATION")
  

    # Log Loss
    loss = log_loss(y_test, probas)
    print(f"\nLog Loss          : {loss:.4f}  (lower is better)")

    # ROC-AUC
    try:
        auc = roc_auc_score(y_test, probas, multi_class='ovr', average='macro')
        print(f"ROC-AUC (macro)   : {auc:.4f}  (1.0 = perfect)")
    except ValueError as e:
        print(f"ROC-AUC           : Could not compute — {e}")

    # PR-AUC per class (most important for rare landslide class)
    print("\nPR-AUC per class  (higher = better):")
    for i, cls in enumerate(classes):
        y_bin  = (y_test == cls).astype(int)
        pr_auc = average_precision_score(y_bin, probas[:, i])
        flag   = " ← watch this" if cls == 'landslide' else ""
        print(f"  {cls:<15}: {pr_auc:.4f}{flag}")

    # Classification report
    print("\nClassification Report:")
    print(classification_report(y_test, preds, zero_division=0))

    # Plots
    _plot_confusion_matrix(y_test, preds, classes)
    _plot_feature_importances(pipeline, X_test.columns.tolist())

    # Per-regime evaluation
    if 'month' in X_test.columns:
        _evaluate_per_regime(pipeline, X_test, y_test)

    # Shortcut learning check
    _check_shortcut_learning(pipeline, X_test.columns.tolist())

    return probas, classes


def _plot_confusion_matrix(y_test, preds, classes):
    fig, ax = plt.subplots(figsize=(7, 6))
    cm   = confusion_matrix(y_test, preds, labels=classes)
    disp = ConfusionMatrixDisplay(confusion_matrix=cm, display_labels=classes)
    disp.plot(ax=ax, cmap='Blues', colorbar=False)
    ax.set_title('Confusion Matrix')
    plt.tight_layout()
    plt.savefig('confusion_matrix.png', dpi=150)
    print("[eval] Saved → confusion_matrix.png")
    plt.close()


def _plot_feature_importances(pipeline, feature_names):
    """Plot RF feature importances. Highlights 'month' in red for bias check."""
    try:
        rf          = pipeline.named_steps['classifier']
        importances = rf.feature_importances_
    except (KeyError, AttributeError):
        print("[eval] Feature importances not available for this model type.")
        return

    imp_df = pd.DataFrame({
        'Feature':    feature_names,
        'Importance': importances,
    }).sort_values('Importance', ascending=True)

    colors = ['#E84040' if f == 'month' else '#4A90D9'
              for f in imp_df['Feature']]

    plt.figure(figsize=(10, 6))
    plt.barh(imp_df['Feature'], imp_df['Importance'], color=colors)
    plt.title('Feature Importances  (red = month — check for calendar bias)')
    plt.xlabel('Importance Score')
    plt.tight_layout()
    plt.savefig('feature_importance.png', dpi=150)
    print("[eval] Saved → feature_importance.png")
    plt.close()


def _evaluate_per_regime(pipeline, X_test, y_test):
    """Separate evaluation for monsoon (Jun–Sep) vs non-monsoon months."""
    print("\n--- Per-Regime Evaluation ---")
    monsoon = X_test['month'].isin([6, 7, 8, 9])

    for label, mask in [('Monsoon (Jun–Sep)', monsoon),
                        ('Non-Monsoon',       ~monsoon)]:
        n = mask.sum()
        if n == 0:
            print(f"  [{label}]: no samples")
            continue
        preds_r = pipeline.predict(X_test[mask])
        print(f"\n  [{label}] — {n} samples")
        print(classification_report(y_test[mask], preds_r, zero_division=0))


def _check_shortcut_learning(pipeline, feature_names):
    """
    Warn if 'month' carries disproportionate importance.
    Goal: model should learn weather → event, not calendar → event.
    """
    try:
        rf          = pipeline.named_steps['classifier']
        importances = rf.feature_importances_
        if 'month' not in feature_names:
            return
        pct = (importances[feature_names.index('month')] / importances.sum()) * 100
        if pct > 20:
            print(f"\n[WARNING] 'month' = {pct:.1f}% of total importance → possible calendar bias.")
            print("          Recommended: run pipeline without 'month' and compare scores.")
        else:
            print(f"\n[eval] 'month' importance: {pct:.1f}%  (within acceptable range)")
    except (KeyError, AttributeError, ValueError):
        pass


def predict_new_data_probabilities(pipeline, new_data_df):
    """Return probability DataFrame for new observations."""
    probas  = pipeline.predict_proba(new_data_df)
    classes = pipeline.classes_
    return pd.DataFrame(probas, columns=[f"prob_{c}" for c in classes])
