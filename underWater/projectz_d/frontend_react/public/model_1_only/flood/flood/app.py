# app.py
from flask import Flask, render_template, jsonify
from data_engine import load_disaster_data
import os

app = Flask(__name__)

@app.route('/')
def dashboard():
    """Serves the main HTML interface."""
    return render_template('dashboard.html')

@app.route('/api/flood-data')
def get_flood_data():
    """Lightweight API endpoint to serve the JSON data to the frontend."""
    df = load_disaster_data('flood')
    # Convert DataFrame to a list of dictionaries for JSON
    return jsonify(df.to_dict(orient='records'))

if __name__ == '__main__':
    print("\n🌊 RESQFY LOCAL SERVER INITIALIZED")
    print("👉 Go to: http://127.0.0.1:5000\n")
    app.run(debug=True, port=5000)