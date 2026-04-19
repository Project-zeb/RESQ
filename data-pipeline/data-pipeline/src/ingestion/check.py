import pandas as pd

df = pd.read_parquet(r"C:\Users\Khalid Mohammad\OneDrive\Desktop\data-pipeline\data\gold\training_dataset.parquet")
df['month'] = df['event_time'].dt.month

print(
    df.groupby(['month', 'target'])['precipitation'].mean()
)