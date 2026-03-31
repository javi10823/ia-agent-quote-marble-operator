from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from pathlib import Path

OUTPUT_DIR = Path(__file__).parent.parent.parent / "output"
OUTPUT_DIR.mkdir(exist_ok=True)


def mount_static_files(app: FastAPI) -> None:
    """Mount the output directory for file downloads."""
    app.mount("/files", StaticFiles(directory=str(OUTPUT_DIR)), name="files")
