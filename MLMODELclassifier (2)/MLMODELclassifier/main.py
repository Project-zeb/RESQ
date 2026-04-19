# main.py
import joblib
from data_loader import load_and_prep_data
from model_pipeline import build_and_train_pipeline, build_histgbm_pipeline
from evaluation import evaluate_probabilities, predict_new_data_probabilities


def run_pipeline(data_path: str, use_histgbm: bool = False):
    """
    Full end-to-end classifier pipeline.

    Args:
        data_path:    Path to the .parquet training dataset.
        use_histgbm:  If True, use HistGradientBoostingClassifier instead of RF.
                      HistGBM is NaN-native and often more accurate — recommended
                      as the strong baseline per the ML playbook.
    """
    print("\n" + "="*55)
    print("  DISASTER CLASSIFICATION PIPELINE — SafeIndia")
    print("="*55)

    # Step 1: Load and prepare data
    X_train, X_val, X_test, y_train, y_val, y_test = load_and_prep_data(data_path)
    # Step 2: Train the model
    if use_histgbm:
        print("\n[main] Using HistGBM pipeline (NaN-native, recommended).")
        pipeline = build_histgbm_pipeline(X_train, y_train)
        model_filename = 'hazard_pipeline_histgbm.pkl'
    else:
        print("\n[main] Using Random Forest pipeline (with SMOTE + custom weights).")
        pipeline = build_and_train_pipeline(X_train, y_train)
        model_filename = 'hazard_pipeline_rf.pkl'

    # Step 3: Evaluate
    print("\n[main] Validation Performance:")
    evaluate_probabilities(pipeline, X_val, y_val)

    print("\n[main] Test Performance:")
    evaluate_probabilities(pipeline, X_test, y_test)

    # Step 4: Save pipeline
    joblib.dump(pipeline, model_filename)
    print(f"\n[main] Pipeline saved → '{model_filename}'")

    return pipeline


if __name__ == "__main__":
    DATA_FILE = 'training_dataset.parquet'

    # Run with Random Forest (original approach)
    rf_pipeline = run_pipeline(DATA_FILE, use_histgbm=True)

    # Uncomment to run with HistGBM (recommended strong baseline):
    # hgb_pipeline = run_pipeline(DATA_FILE, use_histgbm=True)
