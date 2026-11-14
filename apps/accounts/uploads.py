from PIL import Image, UnidentifiedImageError
from rest_framework.exceptions import ValidationError

MAX_IMAGE_BYTES = 2 * 1024 * 1024
MAX_IMAGE_PIXELS = 16_000_000
ALLOWED_FORMATS = {"JPEG", "PNG", "WEBP"}


def validate_image_upload(file):
    if file is None:
        raise ValidationError({"detail": "No file provided."})
    if file.size > MAX_IMAGE_BYTES:
        raise ValidationError({"detail": "Image is larger than 2MB."})
    try:
        with Image.open(file) as im:
            if im.format not in ALLOWED_FORMATS:
                raise ValidationError({"detail": "Use a JPEG, PNG or WebP image."})
            if im.width * im.height > MAX_IMAGE_PIXELS:
                raise ValidationError({"detail": "Image dimensions are too large."})
            im.verify()
    except (UnidentifiedImageError, OSError, SyntaxError, ValueError):
        raise ValidationError({"detail": "That file isn't a valid image."})
    except Image.DecompressionBombError:
        raise ValidationError({"detail": "Image dimensions are too large."})
    file.seek(0)
    return file
