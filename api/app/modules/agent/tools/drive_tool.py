import logging
from pathlib import Path
from datetime import datetime
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from google.oauth2 import service_account

from app.core.config import settings

BASE_DIR = Path(__file__).parent.parent.parent.parent.parent
OUTPUT_DIR = BASE_DIR / "output"

SCOPES = [
    "https://www.googleapis.com/auth/drive",
    "https://www.googleapis.com/auth/spreadsheets",
]


def _get_credentials():
    import os, base64, json as json_mod
    b64 = os.environ.get("SERVICE_ACCOUNT_BASE64")
    if b64:
        info = json_mod.loads(base64.b64decode(b64).decode("utf-8"))
        return service_account.Credentials.from_service_account_info(info, scopes=SCOPES)
    else:
        return service_account.Credentials.from_service_account_file(
            settings.GOOGLE_SERVICE_ACCOUNT_FILE, scopes=SCOPES,
        )


def _get_drive_service():
    return build("drive", "v3", credentials=_get_credentials())


def _get_sheets_service():
    return build("sheets", "v4", credentials=_get_credentials())


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

        # Find generated files — scan directory for actual files instead of guessing names
        quote_dir = OUTPUT_DIR / quote_id

        # Find files by extension (more reliable than reconstructing filename)
        pdf_files = list(quote_dir.glob("*.pdf")) if quote_dir.exists() else []
        excel_files = list(quote_dir.glob("*.xlsx")) if quote_dir.exists() else []
        pdf_path = pdf_files[0] if pdf_files else quote_dir / "not_found.pdf"
        excel_path = excel_files[0] if excel_files else quote_dir / "not_found.xlsx"

        logging.info(f"Drive upload — looking for files in: {quote_dir}")
        logging.info(f"  PDF exists: {pdf_path.exists()} → {pdf_path}")
        logging.info(f"  Excel exists: {excel_path.exists()} → {excel_path}")

        uploaded_urls = []

        # Only upload Excel to Drive (PDF stays local only)
        for file_path, mime in [
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
                try:
                    service.files().delete(
                        fileId=f["id"],
                        supportsAllDrives=True,
                    ).execute()
                except Exception as e:
                    logging.warning(f"Could not delete existing file {f['id']}: {e}")

            file_metadata = {
                "name": file_path.name,
                "parents": [month_id],
                # Convert xlsx to Google Sheets native format
                "mimeType": "application/vnd.google-apps.spreadsheet",
            }
            media = MediaFileUpload(str(file_path), mimetype=mime, resumable=True)
            uploaded = service.files().create(
                body=file_metadata,
                media_body=media,
                fields="id, webViewLink",
                supportsAllDrives=True,
            ).execute()
            logging.info(f"Uploaded to Drive: {file_path.name} → {uploaded.get('webViewLink')}")

            # Set Argentine locale + alternating row colors via Sheets API
            file_id = uploaded.get("id")
            if file_id:
                try:
                    sheets_service = _get_sheets_service()

                    # Get sheet info to know row count
                    sheet_meta = sheets_service.spreadsheets().get(
                        spreadsheetId=file_id,
                        fields="sheets.properties",
                    ).execute()
                    sheet_id = sheet_meta["sheets"][0]["properties"]["sheetId"]

                    # Find "Total PESOS" row to know where content ends
                    sheet_data = sheets_service.spreadsheets().values().get(
                        spreadsheetId=file_id,
                        range="E1:E60",
                    ).execute()
                    rows_e = sheet_data.get("values", [])
                    end_row = 35  # default
                    for i, row in enumerate(rows_e):
                        if row and "Total PESOS" in str(row[0]):
                            end_row = i + 1  # 0-indexed + 1 to include this row
                            break

                    requests = [
                        # Set locale
                        {
                            "updateSpreadsheetProperties": {
                                "properties": {"locale": "es_AR"},
                                "fields": "locale",
                            }
                        },
                        # Clear all background colors first (xlsx fills conflict with banding)
                        {
                            "repeatCell": {
                                "range": {
                                    "sheetId": sheet_id,
                                    "startRowIndex": 22,
                                    "endRowIndex": end_row,
                                    "startColumnIndex": 0,
                                    "endColumnIndex": 6,
                                },
                                "cell": {
                                    "userEnteredFormat": {
                                        "backgroundColor": {"red": 1.0, "green": 1.0, "blue": 1.0},
                                    }
                                },
                                "fields": "userEnteredFormat.backgroundColor",
                            }
                        },
                        # Alternating colors ONLY on content rows (23 to Total PESOS)
                        {
                            "addBanding": {
                                "bandedRange": {
                                    "range": {
                                        "sheetId": sheet_id,
                                        "startRowIndex": 22,  # Row 23 (0-indexed)
                                        "endRowIndex": end_row,
                                        "startColumnIndex": 0,
                                        "endColumnIndex": 6,
                                    },
                                    "rowProperties": {
                                        "firstBandColor": {
                                            "red": 1.0, "green": 1.0, "blue": 1.0,
                                        },
                                        "secondBandColor": {
                                            "red": 0.937, "green": 0.937, "blue": 0.937,
                                        },
                                    },
                                }
                            }
                        },
                    ]

                    sheets_service.spreadsheets().batchUpdate(
                        spreadsheetId=file_id,
                        body={"requests": requests},
                    ).execute()
                    logging.info(f"Set locale es_AR + banding on spreadsheet {file_id}")
                except Exception as e:
                    logging.warning(f"Could not set locale/banding on spreadsheet: {e}")

            uploaded_urls.append(uploaded.get("webViewLink"))

        # Use last URL (Excel) as the main drive link — operator prefers Excel
        drive_url = uploaded_urls[-1] if uploaded_urls else None

        return {
            "ok": True,
            "drive_url": drive_url,
            "uploaded_files": len(uploaded_urls),
            "folder": f"Presupuestos/{year}/{month_folder}",
        }

    except Exception as e:
        logging.error(f"Drive upload error: {e}")
        return {"ok": False, "error": str(e)}
