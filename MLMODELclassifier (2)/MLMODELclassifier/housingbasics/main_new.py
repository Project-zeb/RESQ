import os
import joblib 
import pandas as pd
import numpy as np
from sklearn.model_selection import StratifiedShuffleSplit
from sklearn.pipeline import Pipeline
from sklearn.compose import ColumnTransformer
from sklearn.impute import SimpleImputer
from sklearn.preprocessing import StandardScaler, OneHotEncoder

from sklearn.ensemble import RandomForestRegressor
from sklearn.metrics import root_mean_squared_error
from sklearn.model_selection import cross_val_score
Model_File="model.pkl"
Pipeline_File='pipeline.pkl'

def build_pipeline(num_attribs,cat_attribs):
    num_pipeline=Pipeline([
        ("imputer",SimpleImputer(strategy="median")),
        ("scaler",StandardScaler())
    ])
    cat_pipeline=Pipeline([
        ("onehot",OneHotEncoder(handle_unknown="ignore"))
    
    ])
    full_pipeline=ColumnTransformer([
        ("num",num_pipeline,num_attribs),
        ("cat",cat_pipeline,cat_attribs)
    ])
    return full_pipeline
if not os.path.exists(Model_File):
    housing=pd.read_csv(r"C:\Users\QAYAD ALI\qayad-project\safeindia\weather data (2)\MLMODELclassifier\housingbasics\housing.csv")
    housing['income_cat']=pd.cut(housing["median_income"],
                                bins=[0.0,1.5,3.0,4.5,6.0,np.inf],
                                labels=[1,2,3,4,5])
    split=StratifiedShuffleSplit(n_splits=1,test_size=0.2,random_state=42)
    for train_index,test_index in split.split(housing,housing['income_cat']):
        housing.loc[test_index].drop("income_cat",axis=1).to_csv("input_data.csv",index=False)
        housing=housing.loc[train_index].drop("income_cat",axis=1)
 
    housing_labels=housing["median_house_value"].copy()
    housing_features=housing.drop("median_house_value",axis=1)
    num_attribs=housing_features.drop("ocean_proximity",axis=1).columns.tolist()
    cat_attribs=["ocean_proximity"]
    pipeline=build_pipeline(num_attribs,cat_attribs)
    housing_prepared=pipeline.fit_transform(housing_features)
    model=RandomForestRegressor(random_state=42)
    model.fit(housing_prepared,housing_labels)
    joblib.dump(model,Model_File)
    joblib.dump(pipeline,Pipeline_File)
else:
    model=joblib.load(Model_File)
    pipeline=joblib.load(Pipeline_File)
    input_data=pd.read_csv("input_data.csv")
    transformed_data=pipeline.transform(input_data)
    predictions=model.predict(transformed_data)
    input_data["predicted_median_house_value"]=predictions
    input_data.to_csv("output.csv",index=False)
    print("Inference complete")
