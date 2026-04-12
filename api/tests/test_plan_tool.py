"""Tests for plan_tool.py — plan rasterization, cropping, and file handling."""

import pytest
import base64
from pathlib import Path
from PIL import Image
import io

from app.modules.agent.tools.plan_tool import read_plan, save_plan_to_temp, TEMP_DIR


# ── Helper: create test images ───────────────────────────────────────────────

def _create_test_image(width=800, height=600, color="white") -> bytes:
    """Create a test JPEG image in memory."""
    img = Image.new("RGB", (width, height), color)
    buf = io.BytesIO()
    img.save(buf, format="JPEG")
    return buf.getvalue()


def _create_test_pdf() -> bytes:
    """Create a minimal test PDF with a page."""
    from fpdf import FPDF
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Helvetica", size=20)
    pdf.cell(0, 20, "Test Plan - Mesada Cocina", align="C")
    pdf.rect(30, 50, 150, 80)  # Simulated countertop
    pdf.text(80, 95, "2.50 x 0.60")
    return pdf.output()


# ── save_plan_to_temp ────────────────────────────────────────────────────────

class TestSavePlanToTemp:
    def test_saves_file_to_disk(self):
        data = _create_test_image()
        path = save_plan_to_temp("test_plan.jpg", data)
        assert path.exists()
        assert path.read_bytes() == data
        # Cleanup
        path.unlink()

    def test_returns_correct_path(self):
        data = _create_test_image()
        path = save_plan_to_temp("my_plan.png", data)
        assert path == TEMP_DIR / "my_plan.png"
        path.unlink()

    def test_overwrites_existing(self):
        data1 = _create_test_image(100, 100, "red")
        data2 = _create_test_image(200, 200, "blue")
        save_plan_to_temp("overwrite_test.jpg", data1)
        path = save_plan_to_temp("overwrite_test.jpg", data2)
        assert path.read_bytes() == data2
        path.unlink()


# ── read_plan — image files ──────────────────────────────────────────────────

class TestReadPlanImage:
    @pytest.mark.asyncio
    async def test_reads_jpeg(self):
        data = _create_test_image(800, 600)
        save_plan_to_temp("test_read.jpg", data)

        result = await read_plan("test_read.jpg", [])
        # read_plan returns a list of native content blocks
        assert isinstance(result, list)
        # Should have 1 image block + 1 text block (full plan)
        image_blocks = [b for b in result if b.get("type") == "image"]
        assert len(image_blocks) == 1
        # Base64 should be valid
        decoded = base64.b64decode(image_blocks[0]["source"]["data"])
        assert len(decoded) > 0

        (TEMP_DIR / "test_read.jpg").unlink()

    @pytest.mark.asyncio
    async def test_large_image_scaled(self):
        """Images wider than FULL_PLAN_MAX_WIDTH should be scaled down."""
        data = _create_test_image(4000, 3000)
        save_plan_to_temp("test_large.jpg", data)

        result = await read_plan("test_large.jpg", [])
        assert isinstance(result, list)
        image_blocks = [b for b in result if b.get("type") == "image"]
        assert len(image_blocks) == 1
        decoded = base64.b64decode(image_blocks[0]["source"]["data"])
        img = Image.open(io.BytesIO(decoded))
        assert img.width <= 1200  # FULL_PLAN_MAX_WIDTH

        (TEMP_DIR / "test_large.jpg").unlink()


# ── read_plan — crop instructions ────────────────────────────────────────────

class TestReadPlanCrop:
    @pytest.mark.asyncio
    async def test_crop_returns_image_blocks(self):
        data = _create_test_image(800, 600)
        save_plan_to_temp("test_crop.jpg", data)

        crops = [
            {"label": "mesada_1", "x1": 0, "y1": 0, "x2": 400, "y2": 300},
            {"label": "mesada_2", "x1": 400, "y1": 0, "x2": 800, "y2": 300},
        ]
        result = await read_plan("test_crop.jpg", crops)
        assert isinstance(result, list)
        # 2 crops = 2 image blocks + 2 text blocks
        image_blocks = [b for b in result if b.get("type") == "image"]
        assert len(image_blocks) == 2

        (TEMP_DIR / "test_crop.jpg").unlink()

    @pytest.mark.asyncio
    async def test_max_2_crops_per_call(self):
        """More than 2 crops should be truncated to 2."""
        data = _create_test_image(800, 600)
        save_plan_to_temp("test_maxcrop.jpg", data)

        crops = [
            {"label": "c1", "x1": 0, "y1": 0, "x2": 200, "y2": 200},
            {"label": "c2", "x1": 200, "y1": 0, "x2": 400, "y2": 200},
            {"label": "c3", "x1": 400, "y1": 0, "x2": 600, "y2": 200},
        ]
        result = await read_plan("test_maxcrop.jpg", crops)
        image_blocks = [b for b in result if b.get("type") == "image"]
        assert len(image_blocks) == 2  # Max 2, not 3
        # Should have a truncation warning
        text_blocks = [b for b in result if b.get("type") == "text"]
        warning = [b for b in text_blocks if "Límite" in b.get("text", "")]
        assert len(warning) == 1

        (TEMP_DIR / "test_maxcrop.jpg").unlink()

    @pytest.mark.asyncio
    async def test_invalid_crop_returns_error_text(self):
        data = _create_test_image(100, 100)
        save_plan_to_temp("test_badcrop.jpg", data)

        crops = [{"label": "bad", "x1": -10, "y1": -10, "x2": 50, "y2": 50}]
        result = await read_plan("test_badcrop.jpg", crops)
        assert isinstance(result, list)
        assert len(result) >= 1

        (TEMP_DIR / "test_badcrop.jpg").unlink()


# ── read_plan — PDF files ────────────────────────────────────────────────────

class TestReadPlanPDF:
    @pytest.mark.asyncio
    async def test_reads_pdf(self):
        """PDF should be rasterized to JPEG at 300 DPI."""
        import subprocess
        try:
            subprocess.run(["pdftoppm", "-v"], capture_output=True, timeout=5)
        except (FileNotFoundError, subprocess.TimeoutExpired):
            pytest.skip("poppler-utils not installed (required for PDF rasterization)")

        pdf_data = _create_test_pdf()
        save_plan_to_temp("test_plan.pdf", pdf_data)

        result = await read_plan("test_plan.pdf", [])
        assert isinstance(result, list)
        image_blocks = [b for b in result if b.get("type") == "image"]
        assert len(image_blocks) >= 1

        (TEMP_DIR / "test_plan.pdf").unlink()


# ── read_plan — error handling ───────────────────────────────────────────────

class TestReadPlanErrors:
    @pytest.mark.asyncio
    async def test_file_not_found(self):
        result = await read_plan("nonexistent_file.pdf", [])
        assert isinstance(result, list)
        assert any("no encontrado" in b.get("text", "").lower() for b in result)

    @pytest.mark.asyncio
    async def test_corrupted_file(self):
        save_plan_to_temp("corrupted.jpg", b"not a real image")
        result = await read_plan("corrupted.jpg", [])
        assert isinstance(result, list)
        assert any("error" in b.get("text", "").lower() for b in result)

        (TEMP_DIR / "corrupted.jpg").unlink()
