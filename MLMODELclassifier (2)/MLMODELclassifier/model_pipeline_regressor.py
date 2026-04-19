from sklearn.pipeline import Pipeline
from sklearn.pipeline import Pipeline
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.impute import SimpleImputer


def build_and_train_regressor_pipeline(X_train, y_train):
    pipeline = Pipeline(steps=[
        ('imputer', SimpleImputer(strategy='median')), # <-- Added safety imputer
        ('regressor', HistGradientBoostingRegressor(
            max_iter=300,
            max_depth=6,
            learning_rate=0.05,
            min_samples_leaf=10,
            random_state=42,
        )),
    ])
    print("[model_pipeline_regressor] Training: Imputer → HistGBM Regressor")
    pipeline.fit(X_train, y_train)
    return pipeline
    