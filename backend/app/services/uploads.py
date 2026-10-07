import re
from pathlib import Path
from uuid import uuid4

UPLOAD_DIRECTORY = Path(__file__).resolve().parents[2] / "uploads"


def save_telegram_image(content: bytes, file_path: str) -> tuple[str, Path]:
    suffix = Path(file_path).suffix.lower()
    if not re.fullmatch(r"\.[a-z0-9]{1,10}", suffix):
        suffix = ".jpg"

    UPLOAD_DIRECTORY.mkdir(parents=True, exist_ok=True)
    image_path = UPLOAD_DIRECTORY / f"{uuid4().hex}{suffix}"
    try:
        image_path.write_bytes(content)
    except OSError:
        image_path.unlink(missing_ok=True)
        raise

    return f"/uploads/{image_path.name}", image_path
