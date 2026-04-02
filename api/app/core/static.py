from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from pathlib import Path

from app.core.config import settings


def _resolve_output_dir() -> Path:
    """Resolve the output directory, with fallback to /tmp/output for containers."""
    if settings.OUTPUT_DIR:
        d = Path(settings.OUTPUT_DIR)
    else:
        # Default: relative to project root
        d = Path(__file__).parent.parent.parent / "output"
    # If default is not writable (e.g. Railway volume permissions), fall back to /tmp
    try:
        d.mkdir(parents=True, exist_ok=True)
        test_file = d / ".write_test"
        test_file.write_text("ok")
        test_file.unlink()
    except PermissionError:
        d = Path("/tmp/output")
        d.mkdir(parents=True, exist_ok=True)
    return d


OUTPUT_DIR = _resolve_output_dir()


def mount_static_files(app: FastAPI) -> None:
    """Mount the output directory for file downloads."""
    app.mount("/files", StaticFiles(directory=str(OUTPUT_DIR)), name="files")
