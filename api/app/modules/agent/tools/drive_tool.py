import logging
from pathlib import Path
from datetime import datetime
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from google.oauth2 import service_account

from app.core.config import settings

BASE_DIR = Path(__file__).parent.parent.parent.parent.parent
OUTPUT_DIR = BASE_DIR / "output"

SCOPES = ["https://www.googleapis.com/auth/drive"]


def _get_drive_service():
    import os, base64, json as json_mod
    b64 = os.environ.get("SERVICE_ACCOUNT_BASE64")
    if b64:
        info = json_mod.loads(base64.b64decode(b64).decode("utf-8"))
        creds = service_account.Credentials.from_service_account_info(info, scopes=SCOPES)
    else:
        creds = service_account.Credentials.from_service_account_file(
            settings.GOOGLE_SERVICE_ACCOUNT_FILE, scopes=SCOPES,
        )
    return build("drive", "v3", credentials=creds)


def _get_or_create_folder(service, name: str, parent_id: str) -> str:
    """Get folder by name under parent, or create it. Supports Shared Drives."""
    query = (
        f"name='{name}' and "
        f"'{parent_id}' in parents and "
        f"mimeType='application/vnd.google-apps.folder' and "
        f"trashed=false"
    )
    results = service.files().list(
        q=query,
        fields="files(id)",
        supportsAllDrives=True,
        includeItemsFromAllDrives=True,
    ).execute()
    files = results.get("files", [])
    if files:
        return files[0]["id"]

    folder = service.files().create(
        body={
            "name": name,
            "mimeType": "application/vnd.google-apps.folder",
            "parents": [parent_id],
        },
        fields="id",
        supportsAllDrives=True,
    ).execute()
    return folder["id"]


async def upload_to_drive(
    quote_id: str,
    client_name: str,
    material: str,
    date_str: str,
) -> dict:
    """
    Upload PDF and Excel to Google Drive (Shared Drive).
    Folder structure: Presupuestos/YYYY/MM-Mes/
    """
    try:
        service = _get_drive_service()
        root_folder = settings.GOOGLE_DRIVE_FOLDER_ID

        # Build date-based folder structure
        now = datetime.now()
        year = str(now.year)
        month_map = {
            1: "01-Enero", 2: "02-Febrero", 3: "03-Marzo",
            4: "04-Abril", 5: "05-Mayo", 6: "06-Junio",
            7: "07-Julio", 8: "08-Agosto", 9: "09-Septiembre",
            10: "10-Octubre", 11: "11-Noviembre", 12: "12-Diciembre",
        }
        month_folder = month_map[now.month]

        presupuestos_id = _get_or_create_folder(service, "Presupuestos", root_folder)
        year_id = _get_or_create_folder(service, year, presupuestos_id)
        month_id = _get_or_create_folder(service, month_folder, year_id)

        # Find generated files (sanitize date same as document_tool)
        quote_dir = OUTPUT_DIR / quote_id
        date_clean = date_str.replace("/", ".")
        filename_base = f"{client_name} - {material} - {date_clean}"
        filename_base = filename_base.replace("/", "-").replace("\\", "-")
        pdf_path = quote_dir / f"{filename_base}.pdf"
        excel_path = quote_dir / f"{filename_base}.xlsx"

        logging.info(f"Drive upload — looking for files in: {quote_dir}")
        logging.info(f"  PDF exists: {pdf_path.exists()} → {pdf_path}")
        logging.info(f"  Excel exists: {excel_path.exists()} → {excel_path}")

        uploaded_urls = []

        for file_path, mime in [
            (pdf_path, "application/pdf"),
            (excel_path, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"),
        ]:
            if not file_path.exists():
                logging.warning(f"File not found, skipping: {file_path}")
                continue

            # Delete existing file with same name if present
            query = (
                f"name='{file_path.name}' and "
                f"'{month_id}' in parents and "
                f"trashed=false"
            )
            existing = service.files().list(
                q=query,
                fields="files(id)",
                supportsAllDrives=True,
                includeItemsFromAllDrives=True,
            ).execute()
            for f in existing.get("files", []):
                service.files().delete(
                    fileId=f["id"],
                    supportsAllDrives=True,
                ).execute()

            file_metadata = {"name": file_path.name, "parents": [month_id]}
            media = MediaFileUpload(str(file_path), mimetype=mime, resumable=True)
            uploaded = service.files().create(
                body=file_metadata,
                media_body=media,
                fields="id, webViewLink",
                supportsAllDrives=True,
            ).execute()
            logging.info(f"Uploaded to Drive: {file_path.name} → {uploaded.get('webViewLink')}")
            uploaded_urls.append(uploaded.get("webViewLink"))

        drive_url = uploaded_urls[0] if uploaded_urls else None

        return {
            "ok": True,
            "drive_url": drive_url,
            "uploaded_files": len(uploaded_urls),
            "folder": f"Presupuestos/{year}/{month_folder}",
        }

    except Exception as e:
        logging.error(f"Drive upload error: {e}")
        return {"ok": False, "error": str(e)}
