import os

# Define structure
structure = {
    "project": {
        "config": [
            "settings.py",
            "logging_config.py",
            "validation_rules.py"
        ],
        "data": {
            "raw": [
                "cyclones.csv",
                "earthquakes.csv",
                "landslides.csv",
                "modis_fire.parquet"
            ],
            "bronze": [],
            "silver": [],
            "gold": [],
            "temp": []
        },
        "src": {
            "core": [
                "db.py",
                "storage.py",
                "validation.py",
                "utils.py"
            ],
            "ingestion": [
                "raw_sources.py",
                "weather_pull.py"
            ],
            "processing": [
                "clean.py",
                "weather_enrich.py"
            ],
            "features": [
                "engineer.py"
            ],
            "ml": [
                "train.py"
            ],
            "monitoring": [
                "profile.py"
            ],
            "pipelines": [
                "run.py"
            ]
        },
        "logs": [],
        "README.md": None,
        "requirements.txt": None
    }
}

def create_structure(base_path, tree):
    for name, content in tree.items():
        path = os.path.join(base_path, name)

        if isinstance(content, dict):
            os.makedirs(path, exist_ok=True)
            create_structure(path, content)

        elif isinstance(content, list):
            os.makedirs(path, exist_ok=True)
            for file in content:
                file_path = os.path.join(path, file)
                if not os.path.exists(file_path):
                    open(file_path, "w").close()

        elif content is None:
            if not os.path.exists(path):
                open(path, "w").close()

# Run
create_structure(".", structure)

print("✅ Project structure created successfully.")