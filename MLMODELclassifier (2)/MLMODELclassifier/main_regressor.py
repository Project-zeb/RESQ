# main_regressor.py
import joblib
from data_loader import load_and_prep_data
from model_pipeline_regressor import build_and_train_regressor_pipeline
from evaluation_regressor import evaluate_regressor

def run_regressor_pipeline(data_path: str):
    
    print("  RISK SCORE REGRESSION PIPELINE")
   

    # 1. Load data with task='regression'
    X_train, X_val, X_test, y_train, y_val, y_test = load_and_prep_data(data_path, task='regression')
    
    # 2. Train Regressor
    pipeline = build_and_train_regressor_pipeline(X_train, y_train)
    
    # 3. Evaluate
    print("\n[main_regressor] Validation Performance:")
    evaluate_regressor(pipeline, X_val, y_val)

    print("\n[main_regressor] Test Performance:")
    evaluate_regressor(pipeline, X_test, y_test)

    # 4. Save
    model_filename = 'risk_regressor_histgbm.pkl'
    joblib.dump(pipeline, model_filename)
    print(f"\n[main_regressor] Pipeline saved → '{model_filename}'")

    return pipeline

if __name__ == "__main__":
    DATA_FILE = 'training_dataset.parquet'
    run_regressor_pipeline(DATA_FILE)
