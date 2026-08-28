"""Intelligent Customer Signal Detector — core package."""

# Auto-load the local .env file so your API key is picked up automatically.
try:
    from pathlib import Path
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parent.parent / ".env")
except Exception:
    pass