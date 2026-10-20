"""Start the API server: python run.py"""
import os
from app import create_app

app = create_app()

if __name__ == "__main__":
    # use_reloader=False is deliberate: the reloader would start a second process and could
    # run two simulation workers against the same database.
    port = int(os.environ.get("PORT", 5000))
    host = os.environ.get("HOST", "0.0.0.0" if os.environ.get("PORT") else "127.0.0.1")
    app.run(host=host, port=port, debug=False, use_reloader=False, threaded=True)
