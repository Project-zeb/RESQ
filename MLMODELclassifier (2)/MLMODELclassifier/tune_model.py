# tune_model.py
import pandas as pd
from sklearn.model_selection import RandomizedSearchCV, TimeSeriesSplit
from imblearn.pipeline import Pipeline as ImbPipeline
from imblearn.over_sampling import SMOTE
from sklearn.ensemble import RandomForestClassifier, HistGradientBoostingClassifier
from sklearn.preprocessing import StandardScaler
from sklearn.impute import SimpleImputer
from data_loader import load_and_prep_data


def tune_rf_pipeline(data_path: str):
    """
    Tune the Random Forest pipeline.
    Uses macro-F1 scoring to balance all classes including rare landslide.
    """
    print("[tune] Loading data for Random Forest tuning...")
    X_train, X_val, X_test, y_train, y_val, y_test = load_and_prep_data(data_path)
    pipeline = ImbPipeline(steps=[
             ('classifier', HistGradientBoostingClassifier(random_state=42))
])
    param_distributions = {
        'smote__sampling_strategy':          ['not majority', 'auto'],
        'classifier__n_estimators':          [100, 300, 500],
        'classifier__max_depth':             [5, 8, 12, None],
        'classifier__min_samples_split':     [2, 5, 10],
        'classifier__min_samples_leaf':      [1, 2, 4],
    }

    search = RandomizedSearchCV(
        pipeline,
        param_distributions=param_distributions,
        n_iter=20,
        scoring='f1_macro',
        cv=3,             # Use 3 here; switch to TimeSeriesSplit(n_splits=3) if data is time-ordered
        n_jobs=-1,
        random_state=42,
        verbose=2,
    )

    print("\n[tune] Starting Random Forest hyperparameter search...")
    search.fit(X_train, y_train)

    print("\n--- RF Tuning Complete ---")
    print(f"Best Macro-F1: {search.best_score_:.4f}")
    print("\nUpdate config.py RF_PARAMS with:")
    for key, value in search.best_params_.items():
        clean_key = key.replace('classifier__', '').replace('smote__', '').replace('imputer__', '')
        print(f"  '{clean_key}': {repr(value)}")

    return search


def tune_histgbm_pipeline(data_path: str):
    """
    Tune the HistGradientBoosting pipeline — the recommended strong baseline.
    HistGBM handles NaNs natively, so no imputer needed.
    """
    print("[tune] Loading data for HistGBM tuning...")
    X_train, X_val, X_test, y_train, y_val, y_test = load_and_prep_data(data_path)
    pipeline = ImbPipeline(steps=[
        ('smote',      SMOTE(random_state=42, k_neighbors=1)),
        ('classifier', HistGradientBoostingClassifier(random_state=42)),
    ])

    param_distributions = {
        'classifier__max_iter':       [100, 200, 300, 500],
        'classifier__max_depth':      [4, 6, 8, None],
        'classifier__learning_rate':  [0.01, 0.05, 0.1],
        'classifier__min_samples_leaf': [5, 10, 20],
        'classifier__l2_regularization': [0.0, 0.1, 1.0],
    }

    search = RandomizedSearchCV(
        pipeline,
        param_distributions=param_distributions,
        n_iter=20,
        scoring='f1_macro',
        cv=3,
        n_jobs=-1,
        random_state=42,
        verbose=2,
    )

    print("\n[tune] Starting HistGBM hyperparameter search...")
    search.fit(X_train, y_train)

    print("\n--- HistGBM Tuning Complete ---")
    print(f"Best Macro-F1: {search.best_score_:.4f}")
    print("\nUpdate model_pipeline.py build_histgbm_pipeline() with:")
    for key, value in search.best_params_.items():
        clean_key = key.replace('classifier__', '').replace('smote__', '')
        print(f"  '{clean_key}': {repr(value)}")

    return search


if __name__ == "__main__":
    DATA_FILE = 'training_dataset.parquet'

    # Tune Random Forest
    tune_rf_pipeline(DATA_FILE)

    # Tune HistGBM (recommended — uncomment to run)
    # tune_histgbm_pipeline(DATA_FILE)
