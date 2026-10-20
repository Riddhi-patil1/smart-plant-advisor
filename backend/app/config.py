"""Configuration. Supports local defaults and production environment variables."""
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

# Database file location (override with DB_PATH environment variable if desired)
_env_db = os.environ.get("DB_PATH")
DEFAULT_DB_PATH = Path(_env_db) if _env_db else (BASE_DIR / "data" / "plant_advisor.db")

# Path to static frontend build if serving unified app
FRONTEND_DIST = os.environ.get("FRONTEND_DIST") or str(BASE_DIR.parent / "frontend" / "dist")

# CORS origins: defaults to Vite dev origins, but can be extended via ALLOWED_ORIGINS (comma-separated)
_env_origins = os.environ.get("ALLOWED_ORIGINS")
if _env_origins:
    ALLOWED_ORIGINS = [o.strip() for o in _env_origins.split(",") if o.strip()]
else:
    ALLOWED_ORIGINS = ["http://localhost:5173", "http://127.0.0.1:5173"]
