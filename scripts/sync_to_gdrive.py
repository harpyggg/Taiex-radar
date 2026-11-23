import json
import os
import sys
from pathlib import Path
from typing import Dict

from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload, MediaIoBaseDownload

SCOPES = ["https://www.googleapis.com/auth/drive"]


def get_drive_service():
    raw_json = os.getenv("GDRIVE_SERVICE_ACCOUNT_JSON", "").strip()
    if not raw_json:
        raise RuntimeError("缺少環境變數 GDRIVE_SERVICE_ACCOUNT_JSON")
    info = json.loads(raw_json)
    creds = service_account.Credentials.from_service_account_info(info, scopes=SCOPES)
    return build("drive", "v3", credentials=creds, cache_discovery=False)


def find_or_create_folder(service, name: str, parent_id: str) -> str:
    safe_name = name.replace("'", "\\'")
    q = (
        f"name = '{safe_name}' and '{parent_id}' in parents "
        f"and mimeType = 'application/vnd.google-apps.folder' and trashed = false"
    )
    res = service.files().list(q=q, fields="files(id, name)", pageSize=10).execute()
    files = res.get("files", [])
    if files:
        return files[0]["id"]

    meta = {
        "name": name,
        "mimeType": "application/vnd.google-apps.folder",
        "parents": [parent_id],
    }
    created = service.files().create(body=meta, fields="id").execute()
    return created["id"]


def list_files_in_folder(service, folder_id: str) -> Dict[str, str]:
    q = f"'{folder_id}' in parents and mimeType != 'application/vnd.google-apps.folder' and trashed = false"
    res = service.files().list(q=q, fields="files(id, name)", pageSize=200).execute()
    return {f["name"]: f["id"] for f in res.get("files", [])}


def upsert_file(service, local_path: Path, folder_id: str, existing_map: Dict[str, str]):
    name = local_path.name
    media = MediaFileUpload(str(local_path), resumable=True)
    if name in existing_map:
        file_id = existing_map[name]
        service.files().update(fileId=file_id, media_body=media).execute()
        print(f"  [UPDATE] {name}")
    else:
        meta = {"name": name, "parents": [folder_id]}
        created = service.files().create(body=meta, media_body=media, fields="id").execute()
        existing_map[name] = created["id"]
        print(f"  [CREATE] {name}")


def download_file(service, file_id: str, local_path: Path):
    local_path.parent.mkdir(parents=True, exist_ok=True)
    request = service.files().get_media(fileId=file_id)
    with open(local_path, "wb") as fh:
        downloader = MediaIoBaseDownload(fh, request)
        done = False
        while not done:
            _, done = downloader.next_chunk()


def sync_push(local_root: Path, gdrive_root_id: str):
    service = get_drive_service()
    existing_root = list_files_in_folder(service, gdrive_root_id)

    for item in sorted(local_root.rglob("*")):
        if not item.is_file():
            continue
        # 略過暫存或備份資料夾
        if "_backup_" in item.parts:
            continue

        rel_parts = item.relative_to(local_root).parts
        parent_id = gdrive_root_id
        for folder_name in rel_parts[:-1]:
            parent_id = find_or_create_folder(service, folder_name, parent_id)

        target_map = existing_root if len(rel_parts) == 1 else list_files_in_folder(service, parent_id)
        upsert_file(service, item, parent_id, target_map)


def sync_pull(local_root: Path, gdrive_root_id: str):
    service = get_drive_service()
    local_root.mkdir(parents=True, exist_ok=True)
    root_files = list_files_in_folder(service, gdrive_root_id)
    for name, file_id in root_files.items():
        download_file(service, file_id, local_root / name)
        print(f"  [PULL] {name}")


def main() -> int:
    mode = sys.argv[1] if len(sys.argv) > 1 else "push"
    local_root = Path(os.getenv("TAIFEX_BASE_DIR", "data/TAIFEX"))
    gdrive_root_id = os.getenv("GDRIVE_TAIFEX_FOLDER_ID", "").strip()
    if not gdrive_root_id:
        raise RuntimeError("缺少環境變數 GDRIVE_TAIFEX_FOLDER_ID")

    if mode == "pull":
        print(f"⬇️ 從雲端硬碟同步既有主檔至 {local_root} ...")
        sync_pull(local_root, gdrive_root_id)
    elif mode == "push":
        print(f"⬆️ 將 {local_root} 同步寫回雲端硬碟 ...")
        sync_push(local_root, gdrive_root_id)
    else:
        raise ValueError(f"不支援的同步模式: {mode}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
