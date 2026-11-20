"""WSGI entrypoint: initialize Redis once before serving public requests."""
from app import app, ensure_initialized, r

r.ping()
ensure_initialized()
