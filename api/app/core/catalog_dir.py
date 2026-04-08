"""Resolve catalog directory with persistent volume support.

On Railway with a volume mounted, catalogs are copied to the volume
on first boot and served from there. Edits via the config UI persist
across deploys.

Without a volume (local dev), catalogs are served from the source code.
"""
import logging
import shutil
from pathlib import Path

from app.core.config import settings

logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).parent.parent.parent  # api/
SOURCE_CATALOG_DIR = BASE_DIR / "catalog"


def _resolve_catalog_dir() -> Path:
    """Resolve catalog directory, copying to volume if configured."""
    volume_dir = settings.CATALOG_VOLUME_DIR
    if not volume_dir:
        return SOURCE_CATALOG_DIR

    vol_path = Path(volume_dir)
    try:
        vol_path.mkdir(parents=True, exist_ok=True)

        # Copy source catalogs to volume on first boot (if volume is empty)
        source_files = list(SOURCE_CATALOG_DIR.glob("*.json"))
        vol_files = list(vol_path.glob("*.json"))

        if not vol_files and source_files:
            # First boot: copy all catalogs to volume
            for src in source_files:
                dst = vol_path / src.name
                shutil.copy2(src, dst)
            logger.info(f"Copied {len(source_files)} catalogs to volume: {vol_path}")
        else:
            # Subsequent boots: copy ONLY new catalogs (don't overwrite edits)
            for src in source_files:
                dst = vol_path / src.name
                if not dst.exists():
                    shutil.copy2(src, dst)
                    logger.info(f"Copied new catalog to volume: {src.name}")

        logger.info(f"Using persistent catalog dir: {vol_path} ({len(list(vol_path.glob('*.json')))} files)")
        return vol_path

    except Exception as e:
        logger.warning(f"Could not use volume for catalogs ({e}), falling back to source dir")
        return SOURCE_CATALOG_DIR


CATALOG_DIR = _resolve_catalog_dir()
