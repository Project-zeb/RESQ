import pandas as pd
from sklearn.model_selection import train_test_split
from config import FEATURES, TARGET, RISK_MAP, TEMPORAL_SPLIT


def _add_engineered_features(df: pd.DataFrame) -> pd.DataFrame:
    """
    Build interaction features from the 3 weather columns.
    Only uses columns that actually exist in the parquet.
    NaN inputs → NaN outputs (intentional — let the model see missingness).
    """
    df['rainfall_wind'] = df['precipitation'] * df['wind_speed']
    df['temp_precip']   = df['temperature']   * df['precipitation']
    return df


def _add_temporal_features(df: pd.DataFrame) -> pd.DataFrame:
    """
    Extract month from event_time.
    event_time is already a UTC datetime in the parquet — no parsing needed.
    """
    if 'event_time' in df.columns:
        df['month'] = pd.to_datetime(
            df['event_time'], utc=True, errors='coerce'
        ).dt.month
        print(f"[data_loader] 'month' extracted. "
              f"Range: {int(df['month'].min())}–{int(df['month'].max())}")
    else:
        print("[data_loader] WARNING: 'event_time' not found. month set to 0.")
        df['month'] = 0
    return df


def _temporal_split(df: pd.DataFrame, task='classification'):
    """
    Split into train/test by year using event_time.
    If the data years don't match TEMPORAL_SPLIT boundaries,
    falls back to stratified 80/20 random split with a warning.
    """
    if 'event_time' not in df.columns:
        print("[data_loader] WARNING: No event_time column — using random 80/20 split.")
        X = df[FEATURES]
        if task == 'classification':
            y = df[TARGET]
            return train_test_split(X, y, test_size=0.2, random_state=42, stratify=y)
        else:
            y = df['risk_score']
            return train_test_split(X, y, test_size=0.2, random_state=42)
    df['_year'] = pd.to_datetime(
        df['event_time'], utc=True, errors='coerce'
    ).dt.year

    year_min = int(df['_year'].min())
    year_max = int(df['_year'].max())
    print(f"[data_loader] Data covers years: {year_min}–{year_max}")

    train_mask = df['_year'] <= TEMPORAL_SPLIT['train_end_year']
    test_mask  = df['_year'] >= TEMPORAL_SPLIT['test_start_year']

    n_train = train_mask.sum()
    n_test  = test_mask.sum()

    # If boundaries don't match the data range, fall back to random split
    # If boundaries don't match the data range, fall back to random split
    # If boundaries don't match the data range, fall back to random split
    if n_train == 0 or n_test == 0:
        print(f"[data_loader] WARNING: Temporal split boundaries "
              f"(train≤{TEMPORAL_SPLIT['train_end_year']}, "
              f"test≥{TEMPORAL_SPLIT['test_start_year']}) don't match data range "
              f"({year_min}–{year_max}).")
        print("[data_loader] Falling back to random 80/20 split.")
        print("[data_loader] Update TEMPORAL_SPLIT in config.py to match your data years.")
        df.drop(columns=['_year'], inplace=True, errors='ignore')
        X = df[FEATURES]
        if task == 'classification':
            y = df[TARGET]
            return train_test_split(X, y, test_size=0.2, random_state=42, stratify=y)
        else:
            y = df['risk_score']
            return train_test_split(X, y, test_size=0.2, random_state=42)

    train_df = df[df['_year'] <= TEMPORAL_SPLIT['train_end_year']].copy()
    val_df   = df[df['_year'] == TEMPORAL_SPLIT['val_year']].copy()
    test_df  = df[df['_year'] >= TEMPORAL_SPLIT['test_start_year']].copy()
    df.drop(columns=['_year'], inplace=True, errors='ignore')

    print(f"[data_loader] Temporal split — Train: {len(train_df)}, Test: {len(test_df)}")

    X_train = train_df[FEATURES]
    X_val   = val_df[FEATURES]
    X_test  = test_df[FEATURES]

    if task == 'classification':
       y_train = train_df[TARGET]
       y_val   = val_df[TARGET]
       y_test  = test_df[TARGET]
    else:
        y_train = train_df['risk_score']
        y_val   = val_df['risk_score']
        y_test  = test_df['risk_score']
    return X_train, X_val, X_test, y_train, y_val, y_test

def load_and_prep_data(filepath: str, task='classification'):
    """
    Full data loading pipeline. Steps:
      1. Read parquet
      2. Add engineered interaction features
      3. Extract month from event_time
      4. Drop rows with missing target label
      5. Temporal train/test split (falls back to random if needed)

    Returns: X_train, X_test, y_train, y_test
    """
    print(f"[data_loader] Reading: {filepath}")
    df = pd.read_parquet(filepath)

    print(f"[data_loader] Shape: {df.shape}")
    print(f"[data_loader] Columns: {df.columns.tolist()}")
    print(f"[data_loader] Target distribution:\n{df[TARGET].value_counts()}\n")

    # Verify all expected raw columns exist before doing anything
    required = ['temperature', 'precipitation', 'wind_speed',
                'temperature_missing', 'precipitation_missing', 'wind_speed_missing',
                'disaster_type']
    missing_cols = [c for c in required if c not in df.columns]
    if missing_cols:
        raise ValueError(
            f"[data_loader] These expected columns are missing from the parquet: {missing_cols}\n"
            f"Actual columns: {df.columns.tolist()}"
        )

    # Step 1: Engineered features (BEFORE dropping any rows)
    df = _add_engineered_features(df)

    # Step 2: Temporal feature
    df = _add_temporal_features(df)

    # Step 3: Drop rows with no label
    before = len(df)
    df = df.dropna(subset=[TARGET])
    from config import RISK_MAP

    df['risk_score'] = df['disaster_type'].map(RISK_MAP)
    dropped = before - len(df)
    if dropped > 0:
        print(f"[data_loader] Dropped {dropped} rows with missing target label.")

    # Step 4: Verify all FEATURES exist now (catches config mismatches early)
    missing_features = [f for f in FEATURES if f not in df.columns]
    if missing_features:
        raise ValueError(
            f"[data_loader] Features listed in config.py don't exist in DataFrame: {missing_features}"
        )

    # Step 5: Split
    # Step 5: Split
    X_train, X_val, X_test, y_train, y_val, y_test = _temporal_split(df, task=task) # <-- Added task=task
    print(f"[data_loader] X_train: {X_train.shape}, X_test: {X_test.shape}")
    print(f"[data_loader] Train class distribution:\n{y_train.value_counts()}")
    print(f"[data_loader] Test class distribution:\n{y_test.value_counts()}\n")

    return X_train, X_val, X_test, y_train, y_val, y_test


def add_risk_score(df: pd.DataFrame) -> pd.DataFrame:
    """Map categorical disaster_type → numeric risk score for regression."""

    df['risk_score'] = df['disaster_type'].map(RISK_MAP)
    return df
