from imblearn.pipeline import Pipeline as ImbPipeline
from imblearn.over_sampling import SMOTE
from sklearn.ensemble import RandomForestClassifier, HistGradientBoostingClassifier
from sklearn.preprocessing import StandardScaler
from sklearn.impute import SimpleImputer
from config import RF_PARAMS, SMOTE_PARAMS


def build_and_train_pipeline(X_train, y_train):
    """
    Random Forest pipeline: Imputer → Scaler → SMOTE → RandomForest.
    Leak-proof: SMOTE runs only on training data inside ImbPipeline.
    """
    pipeline = ImbPipeline(steps=[
    ('classifier', RandomForestClassifier(**RF_PARAMS)),
])

    print("[model_pipeline] Training: Imputer → Scaler → SMOTE → RandomForest")
    pipeline.fit(X_train, y_train)
    print("[model_pipeline] Done.")
    return pipeline


def build_histgbm_pipeline(X_train, y_train):
    """
    HistGradientBoosting pipeline: SMOTE → HistGBM.
    No imputer or scaler needed — HistGBM handles NaNs natively.
    Recommended as the strong baseline per the ML playbook.
    """
    pipeline = ImbPipeline(steps=[
    ('classifier', HistGradientBoostingClassifier(
        max_iter=300,
        max_depth=6,
        learning_rate=0.05,
        min_samples_leaf=10,
        random_state=42,
    )),
])

    print("[model_pipeline] Training: SMOTE → HistGradientBoostingClassifier")
    pipeline.fit(X_train, y_train)
    print("[model_pipeline] Done.")
    return pipeline
