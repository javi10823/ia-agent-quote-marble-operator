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
        assert result["ok"] is True
        assert result["filename"] == "test_read.jpg"
        assert len(result["images"]) == 1  # Full plan only
        assert result["images"][0]["label"] == "plano_completo"
        assert result["original_size"]["width"] == 800
        assert result["original_size"]["height"] == 600

        # Base64 should be valid
        decoded = base64.b64decode(result["images"][0]["base64"])
        assert len(decoded) > 0

        # Cleanup
        (TEMP_DIR / "test_read.jpg").unlink()

    @pytest.mark.asyncio
    async def test_large_image_scaled_to_2000px(self):
        """Images wider than 2000px should be scaled down."""
        data = _create_test_image(4000, 3000)
        save_plan_to_temp("test_large.jpg", data)

        result = await read_plan("test_large.jpg", [])
        assert result["ok"] is True
        # The base64 image should be scaled
        decoded = base64.b64decode(result["images"][0]["base64"])
        img = Image.open(io.BytesIO(decoded))
        assert img.width <= 2000

        (TEMP_DIR / "test_large.jpg").unlink()


# ── read_plan — crop instructions ────────────────────────────────────────────

class TestReadPlanCrop:
    @pytest.mark.asyncio
    async def test_crop_returns_extra_images(self):
        data = _create_test_image(800, 600)
        save_plan_to_temp("test_crop.jpg", data)

        crops = [
            {"label": "mesada_1", "x1": 0, "y1": 0, "x2": 400, "y2": 300},
            {"label": "mesada_2", "x1": 400, "y1": 0, "x2": 800, "y2": 300},
        ]
        result = await read_plan("test_crop.jpg", crops)
        assert result["ok"] is True
        # 1 full plan + 2 crops = 3 images
        assert len(result["images"]) == 3
        assert result["images"][1]["label"] == "mesada_1"
        assert result["images"][2]["label"] == "mesada_2"

        (TEMP_DIR / "test_crop.jpg").unlink()

    @pytest.mark.asyncio
    async def test_invalid_crop_returns_error(self):
        data = _create_test_image(100, 100)
        save_plan_to_temp("test_badcrop.jpg", data)

        crops = [{"label": "bad", "x1": -10, "y1": -10, "x2": 50, "y2": 50}]
        result = await read_plan("test_badcrop.jpg", crops)
        assert result["ok"] is True
        # Full plan should still work even if crop has issues
        assert len(result["images"]) >= 1

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
        assert result["ok"] is True
        assert len(result["images"]) >= 1
        assert result["images"][0]["label"] == "plano_completo"
        # 300 DPI A4 should be roughly 2480x3508
        assert result["original_size"]["width"] > 1000

        (TEMP_DIR / "test_plan.pdf").unlink()


# ── read_plan — error handling ───────────────────────────────────────────────

class TestReadPlanErrors:
    @pytest.mark.asyncio
    async def test_file_not_found(self):
        result = await read_plan("nonexistent_file.pdf", [])
        assert "error" in result
        assert "no encontrado" in result["error"].lower()

    @pytest.mark.asyncio
    async def test_corrupted_file(self):
        save_plan_to_temp("corrupted.jpg", b"not a real image")
        result = await read_plan("corrupted.jpg", [])
        assert "error" in result

        (TEMP_DIR / "corrupted.jpg").unlink()
