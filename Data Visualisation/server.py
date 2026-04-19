from flask import Flask, send_file, send_from_directory
import os

app = Flask(__name__, static_folder='.', static_url_path='')

@app.route('/')
def index():
    return send_file('unified_disaster_dashboard.html')

@app.route('/<path:filename>')
def serve_file(filename):
    """Serve any file from the current directory"""
    file_path = os.path.join('.', filename)
    if os.path.isfile(file_path):
        return send_file(file_path)
    return "File not found", 404

@app.route('/<path:directory>/<path:filename>')
def serve_subdir(directory, filename):
    """Serve files from subdirectories"""
    file_path = os.path.join(directory, filename)
    if os.path.isfile(file_path):
        return send_file(file_path)
    return "File not found", 404

@app.route('/<path:dir1>/<path:dir2>/<path:filename>')
def serve_nested(dir1, dir2, filename):
    """Serve files from nested directories"""
    file_path = os.path.join(dir1, dir2, filename)
    if os.path.isfile(file_path):
        return send_file(file_path)
    return "File not found", 404

if __name__ == '__main__':
    print("=" * 60)
    print("RESQFY Unified Disaster Dashboard Server")
    print("=" * 60)
    print("Starting server on http://localhost:2000")
    print("Press Ctrl+C to stop")
    print("=" * 60)
    app.run(host='0.0.0.0', port=2000, debug=False)
