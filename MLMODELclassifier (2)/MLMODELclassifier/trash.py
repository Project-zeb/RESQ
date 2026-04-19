import pandas as pd
df=pd.read_parquet(r"C:\Users\QAYAD ALI\qayad-project\data-pipeline\data-pipeline\MLMODELclassifier\training_dataset.parquet")
print(df["event_time"])

df.to_csv("output.csv", index=False)

import os

output_path = os.path.abspath("output.csv")
df.to_csv(output_path, index=False)

print(f"File saved at: {output_path}")
print(f"Done! {len(df)} rows written to output.csv")