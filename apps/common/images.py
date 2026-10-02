"""One set of rules for every image RHP accepts.

Property banners, lease scans and tenant photos are all uploads of the same kind,
so the size, type and pixel limits live here rather than being restated in each
form — a rule written three times is a rule that will disagree with itself
(docs/security.md).
"""

from django.core.exceptions import ValidationError
from PIL import Image, UnidentifiedImageError

#: What RHP will store as an image. SVG is deliberately absent: it can carry script.
IMAGE_CONTENT_TYPES = frozenset({"image/jpeg", "image/png", "image/webp"})

#: A stored image is never larger than this on either side.
IMAGE_MAX_DIMENSION = 6000


def validate_image_upload(image, *, max_bytes: int, max_dimension: int = IMAGE_MAX_DIMENSION):
    """Validate an uploaded image, returning it ready for the storage backend.

    A value without ``content_type`` is a file already stored rather than a fresh
    upload; Django has validated that one, and opening it here would leave a file
    handle open for the test suite to trip over.
    """
    if not image or not hasattr(image, "content_type"):
        return image

    if image.size > max_bytes:
        raise ValidationError(
            f"That image is larger than {max_bytes // (1024 * 1024)} MB. Resize it and try again."
        )

    content_type = getattr(image, "content_type", "")
    if content_type and content_type not in IMAGE_CONTENT_TYPES:
        raise ValidationError("Upload a JPEG, PNG, or WebP image.")

    try:
        with Image.open(image) as opened:
            width, height = opened.size
    except (UnidentifiedImageError, OSError, ValueError) as error:
        raise ValidationError("That file is not an image RHP can read.") from error
    finally:
        # Pillow leaves the pointer inside the file; the storage backend needs to
        # read it from the start.
        image.seek(0)

    if width > max_dimension or height > max_dimension:
        raise ValidationError(f"That image is larger than {max_dimension}×{max_dimension} pixels.")
    return image
