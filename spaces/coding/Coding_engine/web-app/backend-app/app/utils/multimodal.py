"""
Multimodal file processing utilities for Gemini 3 Flash

Handles image and PDF processing for AI chat with proper validation,
resizing, and format conversion.
"""

import base64
import io
from typing import Tuple, Optional
from PIL import Image


# Image settings
MAX_IMAGE_SIZE_MB = 10
MAX_IMAGE_WIDTH = 2048
MAX_IMAGE_HEIGHT = 2048
SUPPORTED_IMAGE_FORMATS = {'PNG', 'JPEG', 'JPG', 'WEBP', 'GIF'}

# PDF settings
MAX_PDF_SIZE_MB = 20


def validate_image(data: str, mime_type: str, filename: str) -> Tuple[bool, Optional[str]]:
    """
    Validate an image file

    Args:
        data: Base64 encoded image data
        mime_type: MIME type of the image
        filename: Original filename

    Returns:
        Tuple of (is_valid, error_message)
    """
    try:
        # Check MIME type
        if not mime_type.startswith('image/'):
            return False, f"Invalid MIME type: {mime_type}"

        # Decode base64
        try:
            image_bytes = base64.b64decode(data)
        except Exception as e:
            return False, f"Invalid base64 data: {str(e)}"

        # Check file size
        size_mb = len(image_bytes) / (1024 * 1024)
        if size_mb > MAX_IMAGE_SIZE_MB:
            return False, f"Image too large: {size_mb:.1f}MB (max {MAX_IMAGE_SIZE_MB}MB)"

        # Try to open with PIL
        try:
            img = Image.open(io.BytesIO(image_bytes))
            img.verify()  # Verify it's a valid image
        except Exception as e:
            return False, f"Invalid image file: {str(e)}"

        # Check format
        img_format = img.format
        if img_format not in SUPPORTED_IMAGE_FORMATS:
            return False, f"Unsupported format: {img_format}"

        return True, None

    except Exception as e:
        return False, f"Validation error: {str(e)}"


def resize_image_if_needed(data: str, mime_type: str) -> Tuple[str, str]:
    """
    Resize image if it exceeds maximum dimensions

    Args:
        data: Base64 encoded image data
        mime_type: MIME type of the image

    Returns:
        Tuple of (new_base64_data, new_mime_type)
    """
    try:
        # Decode image
        image_bytes = base64.b64decode(data)
        img = Image.open(io.BytesIO(image_bytes))

        # Check if resizing is needed
        width, height = img.size
        if width <= MAX_IMAGE_WIDTH and height <= MAX_IMAGE_HEIGHT:
            # No resizing needed
            return data, mime_type

        # Calculate new dimensions (maintain aspect ratio)
        ratio = min(MAX_IMAGE_WIDTH / width, MAX_IMAGE_HEIGHT / height)
        new_width = int(width * ratio)
        new_height = int(height * ratio)

        # Resize
        img = img.resize((new_width, new_height), Image.Resampling.LANCZOS)

        # Convert to bytes
        output = io.BytesIO()

        # Determine format
        format_map = {
            'image/jpeg': 'JPEG',
            'image/jpg': 'JPEG',
            'image/png': 'PNG',
            'image/webp': 'WEBP',
            'image/gif': 'GIF'
        }
        img_format = format_map.get(mime_type, 'PNG')

        # Save with optimization
        if img_format == 'JPEG':
            # Convert RGBA to RGB for JPEG
            if img.mode in ('RGBA', 'LA', 'P'):
                background = Image.new('RGB', img.size, (255, 255, 255))
                if img.mode == 'P':
                    img = img.convert('RGBA')
                background.paste(img, mask=img.split()[-1] if img.mode == 'RGBA' else None)
                img = background
            img.save(output, format='JPEG', quality=85, optimize=True)
            new_mime_type = 'image/jpeg'
        elif img_format == 'PNG':
            img.save(output, format='PNG', optimize=True)
            new_mime_type = 'image/png'
        elif img_format == 'WEBP':
            img.save(output, format='WEBP', quality=85)
            new_mime_type = 'image/webp'
        elif img_format == 'GIF':
            img.save(output, format='GIF')
            new_mime_type = 'image/gif'
        else:
            # Default to PNG
            img.save(output, format='PNG', optimize=True)
            new_mime_type = 'image/png'

        # Encode back to base64
        new_data = base64.b64encode(output.getvalue()).decode('utf-8')

        return new_data, new_mime_type

    except Exception as e:
        # If resizing fails, return original
        print(f"Warning: Failed to resize image: {e}")
        return data, mime_type


def validate_pdf(data: str, mime_type: str, filename: str) -> Tuple[bool, Optional[str]]:
    """
    Validate a PDF file

    Args:
        data: Base64 encoded PDF data
        mime_type: MIME type (should be application/pdf)
        filename: Original filename

    Returns:
        Tuple of (is_valid, error_message)
    """
    try:
        # Check MIME type
        if mime_type != 'application/pdf':
            return False, f"Invalid MIME type for PDF: {mime_type}"

        # Decode base64
        try:
            pdf_bytes = base64.b64decode(data)
        except Exception as e:
            return False, f"Invalid base64 data: {str(e)}"

        # Check file size
        size_mb = len(pdf_bytes) / (1024 * 1024)
        if size_mb > MAX_PDF_SIZE_MB:
            return False, f"PDF too large: {size_mb:.1f}MB (max {MAX_PDF_SIZE_MB}MB)"

        # Basic PDF validation (check PDF header)
        if not pdf_bytes.startswith(b'%PDF-'):
            return False, "Invalid PDF file format"

        return True, None

    except Exception as e:
        return False, f"Validation error: {str(e)}"


def process_attachment(file_type: str, mime_type: str, data: str, name: str) -> Tuple[bool, Optional[str], str, str]:
    """
    Process and validate a file attachment

    Args:
        file_type: 'image' or 'pdf'
        mime_type: MIME type
        data: Base64 encoded data
        name: Filename

    Returns:
        Tuple of (is_valid, error_message, processed_data, processed_mime_type)
    """
    if file_type == 'image':
        # Validate
        is_valid, error = validate_image(data, mime_type, name)
        if not is_valid:
            return False, error, data, mime_type

        # Resize if needed
        processed_data, processed_mime = resize_image_if_needed(data, mime_type)
        return True, None, processed_data, processed_mime

    elif file_type == 'pdf':
        # Validate
        is_valid, error = validate_pdf(data, mime_type, name)
        if not is_valid:
            return False, error, data, mime_type

        # No processing needed for PDFs
        return True, None, data, mime_type

    else:
        return False, f"Unsupported file type: {file_type}", data, mime_type
