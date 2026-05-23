from pathlib import Path
from shutil import copyfileobj
from uuid import uuid4

from fastapi import UploadFile

from ..config import settings


def _safe_suffix(filename: str | None) -> str:
    if not filename:
        return "jpg"
    suffix = Path(filename).suffix.lower().lstrip(".")
    if suffix in {"jpg", "jpeg", "png", "gif", "webp", "heic", "heif"}:
        return suffix
    return "jpg"


async def upload_photo(file: UploadFile) -> str:
    settings.local_photo_dir.mkdir(parents=True, exist_ok=True)
    key = f"{uuid4()}.{_safe_suffix(file.filename)}"
    destination = settings.local_photo_dir / key
    file.file.seek(0)
    with destination.open("wb") as output:
        copyfileobj(file.file, output)
    return f"{settings.backend_url.rstrip('/')}{settings.media_photos_path}/{key}"
