# config.py

# ── 1. RAW FEATURES that exist directly in the parquet ────────────────────
RAW_FEATURES = [
    'temperature',
    'precipitation',
    'wind_speed',
    'lat',
    'lon',
]

# ── 2. MISSINGNESS FLAGS — already in parquet, use as-is ─────────────────
# DO NOT recreate these. They were pre-computed and stored in the file.
# They encode WHY data is missing — a real signal, not noise.
MISSINGNESS_FLAGS = [
    'temperature_missing',
    'precipitation_missing',
    'wind_speed_missing',
]

# ── 3. ENGINEERED FEATURES — created in data_loader.py ───────────────────
# Built from the 3 available weather columns.
# NaN inputs → NaN outputs intentionally (tree model handles them).
ENGINEERED_FEATURES = [
    'rainfall_wind',    # precipitation × wind_speed  — cyclone signal
    'temp_precip',      # temperature   × precipitation — monsoon context
]

# ── 4. TEMPORAL FEATURE — extracted from event_time ──────────────────────
# month is a first-class feature: precipitation is only predictive
# during monsoon months (June–Sep). Model needs the seasonal context.
TEMPORAL_FEATURES = [
    'month',
]

# ── 5. FULL FEATURE LIST PASSED TO THE MODEL ─────────────────────────────
FEATURES = (
    RAW_FEATURES
    + MISSINGNESS_FLAGS
    + ENGINEERED_FEATURES
    + TEMPORAL_FEATURES
)

# ── 6. TARGET ─────────────────────────────────────────────────────────────
TARGET = 'disaster_type'

# ── 7. RISK SCORE MAP (regressor target) ─────────────────────────────────
RISK_MAP = {
    'none':       0.0,
    'earthquake': 0.6,
    'cyclone':    0.8,
    'landslide':  1.0,
}

# ── 8. CUSTOM CLASS WEIGHTS (Random Forest classifier) ───────────────────
# landslide is rarest and highest-consequence → 50x penalty for missing it.
CUSTOM_WEIGHTS = {
    'none':       1,
    'earthquake': 1,
    'cyclone':    1,
    'landslide':  50,
}

# ── 9. RANDOM FOREST PARAMETERS ──────────────────────────────────────────
RF_PARAMS = {
    'n_estimators':      300,
    'max_depth':         8,
    'min_samples_split': 5,
    'random_state':      42,
    'class_weight':      CUSTOM_WEIGHTS,
}

# ── 10. SMOTE PARAMETERS ─────────────────────────────────────────────────
# Only landslide is upsampled. k_neighbors=1 because original landslide
# samples are very few — higher k would error.
SMOTE_PARAMS = {
    'random_state':      42,
    'sampling_strategy': {'landslide': 100},
    'k_neighbors':       1,
}

# ── 11. TEMPORAL SPLIT BOUNDARIES ────────────────────────────────────────
# Used in data_loader._temporal_split()
# Adjust these if your data covers a different date range.
TEMPORAL_SPLIT = {
    'train_end_year':  2014,
    'val_year':        2015,
    'test_start_year': 2016,
}
