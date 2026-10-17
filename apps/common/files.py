"""One set of rules for every file RHP accepts and serves.

Photos have their own rules next door (`apps/common/images.py`); this is the
document side: what may be uploaded, how large it may be, and how a stored file is
served so that the web server and the proxy never touch it (docs/security.md,
ADR-022).
"""

from pathlib import Path

from django.core.exceptions import ValidationError
from django.http import FileResponse

#: What RHP stores as a document. Deliberately an allow-list: anything not named
#: here is refused, so a new uploader cannot widen what the application accepts by
#: forgetting to say what it means. PDFs and scans first, then the office formats.
DOCUMENT_EXTENSIONS = frozenset(
    {
        ".pdf",
        ".jpg",
        ".jpeg",
        ".png",
        ".webp",
        ".doc",
        ".docx",
        ".xls",
        ".xlsx",
        ".csv",
        ".txt",
    }
)

#: Said to the uploader when the type is not one RHP takes.
DOCUMENT_TYPE_ERROR = (
    "RHP takes PDFs, JPEG, PNG and WebP images, Word and Excel documents, CSV and text files."
)


def validate_document_upload(upload, *, max_bytes: int, allowed=DOCUMENT_EXTENSIONS):
    """Validate an uploaded document, returning it ready for the storage backend.

    A value without ``content_type`` is a file already stored rather than a fresh
    upload; Django has validated that one.
    """
    if not upload or not hasattr(upload, "content_type"):
        return upload

    if upload.size > max_bytes:
        raise ValidationError(
            f"That file is larger than {max_bytes // (1024 * 1024)} MB. "
            "Compress it or split it and try again."
        )

    extension = Path(upload.name or "").suffix.lower()
    if extension not in allowed:
        raise ValidationError(DOCUMENT_TYPE_ERROR)
    return upload


def document_response(field_file, *, filename="") -> FileResponse:
    """Serve an uploaded document from the application, never from the proxy.

    Every download in RHP goes through here: a permission-checked view decides
    *whether*, and this decides *how* — private, not sniffable, and named for a
    person rather than by its storage path.
    """
    field_file.open("rb")
    if filename and not filename.lower().endswith(Path(field_file.name).suffix.lower()):
        filename += Path(field_file.name).suffix
    response = FileResponse(field_file, filename=filename)
    response["Cache-Control"] = "private, max-age=300"
    response["X-Content-Type-Options"] = "nosniff"
    return response
