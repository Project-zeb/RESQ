# India Multi‑Disaster Risk Prediction ETL

## Goal
Build a modular Python ETL pipeline for multi‑disaster risk modeling in India (cyclones, earthquakes, landslides, fires) using:
- Raw CSVs (cyclones, earthquakes, landslides)
- MODIS fire Parquet
- 11 years of India weather (2007–2017) for temperature and precipitation

Output is `data/gold/disasters_ml.parquet` ready for a dual‑output XGBoost model (type + severity).

## Architecture

- **Bronze**: raw CSVs land in `data/bronze/` with minimal renaming.
- **Silver**: cleaned, deduped, and enriched with Open‑Meteo weather using `cell_selection=land&elevation=auto`.
- **Gold**: temporal lags, weather‑disaster interactions, merged into `disasters_ml`.

No Airflow or external orchestration; control via `python -m pipelines.run --stage bronze|silver|gold`.

## Getting started

```bash
pip install -r requirements.txt
python -m pipelines.run --stage bronze
python -m pipelines.run --stage silver   # includes weather enrichment
python -m pipelines.run --stage gold
```

Data is stored in `data/bronze/`, `data/silver/`, `data/gold/`. Temporary API batches live in `data/temp/`.

## Weather enrichment strategy

- Weather is fetched in batches of `API_BATCH_SIZE=1000` to stay under 10k/day Open‑Meteo limit.
- Each batch is saved as `data/temp/weather_batch_*.json`; if a run fails, you can resume from that index.
- Coordinates are snapped to grid cells to avoid NaNs; Open‑Meteo `land` + `elevation=auto` is used.

## Customization

Edit `config/settings.py` to change:
- data paths
- API limits / retries
- date windows
- feature lags and columns

Validation and profiling are logged to `logs/` and `data/gold/` CSVs for debugging drift or NaNs.