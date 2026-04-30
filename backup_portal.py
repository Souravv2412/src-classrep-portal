from datetime import datetime
from pathlib import Path
import zipfile

from app import BACKUP_DIR, DATA_DIR, PERSISTENT_ROOT, UPLOAD_FOLDER

BASE_DIR = Path(PERSISTENT_ROOT)
BACKUP_DIR_PATH = Path(BACKUP_DIR)
DATA_DIR_PATH = Path(DATA_DIR)
UPLOADS_DIR_PATH = Path(UPLOAD_FOLDER)


def create_backup():
    BACKUP_DIR_PATH.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    zip_path = BACKUP_DIR_PATH / f"src_portal_backup_{timestamp}.zip"

    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for source_dir in (DATA_DIR_PATH, UPLOADS_DIR_PATH):
            if not source_dir.exists():
                continue
            for file_path in source_dir.rglob("*"):
                if file_path.is_file():
                    archive.write(file_path, file_path.relative_to(BASE_DIR))

    print(f"Backup created: {zip_path}")


def prune_old_backups(keep_latest: int = 20):
    backups = sorted(BACKUP_DIR_PATH.glob("src_portal_backup_*.zip"), key=lambda item: item.stat().st_mtime, reverse=True)
    for old_backup in backups[keep_latest:]:
        old_backup.unlink(missing_ok=True)


if __name__ == "__main__":
    create_backup()
    prune_old_backups()
