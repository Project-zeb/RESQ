import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from sklearn.metrics import mean_squared_error, mean_absolute_error, r2_score
from sklearn.inspection import permutation_importance


def evaluate_regressor(pipeline, X_test, y_test):
    """
    Full evaluation for the risk-score regressor.
    """
    preds = pipeline.predict(X_test)

    print("\n" + "="*55)
    print("       REGRESSOR EVALUATION REPORT")
    print("="*55)

    rmse = np.sqrt(mean_squared_error(y_test, preds))
    mae  = mean_absolute_error(y_test, preds)
    r2   = r2_score(y_test, preds)

    print(f"\nRMSE  : {rmse:.4f}  (lower is better)")
    print(f"MAE   : {mae:.4f}  (lower is better)")
    print(f"R²    : {r2:.4f}  (1.0 = perfect, ≥0.7 is good)")

    # ── Residual Distribution ─────────────────────────────────
    residuals = y_test.values - preds
    print(f"\nResidual mean  : {residuals.mean():.4f}  (close to 0 = unbiased)")
    print(f"Residual std   : {residuals.std():.4f}")

    # ── Permutation Importance ────────────────────────────────
    print("\n[eval_regressor] Computing permutation importance (may take ~30s)...")
    result = permutation_importance(
        pipeline, X_test, y_test,
        n_repeats=10,
        random_state=42,
        n_jobs=-1,
    )

    imp_df = pd.DataFrame({
        'Feature':    X_test.columns,
        'Importance': result.importances_mean,
        'Std':        result.importances_std,
    }).sort_values('Importance', ascending=True)

    plt.figure(figsize=(10, 7))
    plt.barh(
        imp_df['Feature'],
        imp_df['Importance'],
        xerr=imp_df['Std'],
        color='#4A90D9',
        ecolor='grey',
        capsize=3,
    )
    plt.title('Permutation Importance — Risk Score Regressor\n(error bars = std over repeats)')
    plt.xlabel('Mean decrease in R² when feature is shuffled')
    plt.tight_layout()
    plt.savefig('regressor_importance.png', dpi=150)
    print("[eval_regressor] Importance plot saved → regressor_importance.png")
    plt.close()

    # ── Predicted vs Actual scatter ───────────────────────────
    plt.figure(figsize=(6, 6))
    plt.scatter(y_test, preds, alpha=0.4, s=15, color='#4A90D9')
    mn, mx = min(y_test.min(), preds.min()), max(y_test.max(), preds.max())
    plt.plot([mn, mx], [mn, mx], 'r--', linewidth=1.5, label='Perfect fit')
    plt.xlabel('Actual Risk Score')
    plt.ylabel('Predicted Risk Score')
    plt.title(f'Predicted vs Actual  (R²={r2:.3f})')
    plt.legend()
    plt.tight_layout()
    plt.savefig('regressor_pred_vs_actual.png', dpi=150)
    print("[eval_regressor] Pred vs actual plot saved → regressor_pred_vs_actual.png")
    plt.close()

    # ── Per-Regime ────────────────────────────────────────────
    if 'month' in X_test.columns:
        print("\n--- Per-Regime Regressor Performance ---")
        monsoon_months = [6, 7, 8, 9]
        for label, mask in [
            ('Monsoon (Jun–Sep)', X_test['month'].isin(monsoon_months)),
            ('Non-Monsoon',      ~X_test['month'].isin(monsoon_months)),
        ]:
            if mask.sum() == 0:
                continue
            r2_r = r2_score(y_test[mask], preds[mask])
            mae_r = mean_absolute_error(y_test[mask], preds[mask])
            print(f"  [{label}]  R²={r2_r:.3f}, MAE={mae_r:.4f}  (n={mask.sum()})")

    return preds
