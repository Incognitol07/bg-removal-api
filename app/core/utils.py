"""
Utility functions for the Background Remover API
"""

import io
import uuid
from PIL import Image
from fastapi import HTTPException, UploadFile
from app.core.config import settings
import logging

logger = logging.getLogger(__name__)


def generate_request_id() -> str:
    """Generate a unique request ID"""
    return str(uuid.uuid4())


def validate_image_file(file: UploadFile) -> None:
    """
    Validate uploaded image file

    Args:
        file: The uploaded file

    Raises:
        HTTPException: If file validation fails
    """
    # Check file size
    if file.size and file.size > settings.MAX_FILE_SIZE:
        raise HTTPException(
            status_code=413,
            detail=f"File size ({file.size} bytes) exceeds maximum allowed size ({settings.MAX_FILE_SIZE} bytes)",
        )

    # Check file extension
    if file.filename:
        extension = file.filename.split(".")[-1].lower()
        if extension not in settings.ALLOWED_EXTENSIONS:
            raise HTTPException(
                status_code=400,
                detail=f"File extension '{extension}' not allowed. Allowed extensions: {settings.ALLOWED_EXTENSIONS}",
            )


async def load_image_from_upload(file: UploadFile) -> Image.Image:
    """
    Load PIL Image from uploaded file

    Args:
        file: The uploaded file

    Returns:
        PIL Image object

    Raises:
        HTTPException: If image loading fails
    """
    try:
        # Validate file
        validate_image_file(file)

        # Read file content
        content = await file.read()

        # Load image with PIL
        image = Image.open(io.BytesIO(content))

        # Convert to RGB if necessary (handles RGBA, grayscale, etc.)
        if image.mode in ("RGBA", "LA"):
            # Keep alpha channel for transparency
            pass
        elif image.mode != "RGB":
            image = image.convert("RGB")

        return image

    except Exception as e:
        logger.error(f"Error loading image from upload: {e}")
        raise HTTPException(status_code=400, detail=f"Failed to load image: {str(e)}")


def image_to_bytes(
    image: Image.Image, format: str = None, quality: int = None
) -> bytes:
    """
    Convert PIL Image to bytes

    Args:
        image: PIL Image object
        format: Output format (PNG, JPEG, WEBP)
        quality: Quality for JPEG/WEBP (1-100)

    Returns:
        Image bytes
    """
    if format is None:
        format = settings.DEFAULT_OUTPUT_FORMAT

    if quality is None:
        quality = settings.OUTPUT_QUALITY

    # Use BytesIO buffer
    buffer = io.BytesIO()

    # Save image to buffer
    if format.upper() == "JPEG":
        # Convert RGBA to RGB for JPEG
        if image.mode == "RGBA":
            # Create white background
            rgb_image = Image.new("RGB", image.size, (255, 255, 255))
            rgb_image.paste(image, mask=image.split()[-1])  # Use alpha as mask
            image = rgb_image
        elif image.mode != "RGB":
            image = image.convert("RGB")

        image.save(buffer, format=format, quality=quality, optimize=True)
    elif format.upper() == "PNG":
        image.save(buffer, format=format, optimize=True)
    elif format.upper() == "WEBP":
        image.save(buffer, format=format, quality=quality, optimize=True)
    else:
        raise ValueError(f"Unsupported format: {format}")

    return buffer.getvalue()


def get_image_info(image: Image.Image) -> dict:
    """
    Get information about an image

    Args:
        image: PIL Image object

    Returns:
        Dictionary with image information
    """
    return {
        "width": image.width,
        "height": image.height,
        "mode": image.mode,
        "format": image.format,
        "has_transparency": image.mode in ("RGBA", "LA", "P")
        and "transparency" in image.info,
    }


def get_content_type(format: str) -> str:
    """
    Get content type for image format

    Args:
        format: Image format (PNG, JPEG, WEBP)

    Returns:
        Content type string
    """
    format_map = {"PNG": "image/png", "JPEG": "image/jpeg", "WEBP": "image/webp"}

    return format_map.get(format.upper(), "application/octet-stream")


def get_system_metrics() -> dict:
    """
    Best-effort system and process metrics.

    Tries to use the optional library (`psutil`) when available.
    Falls back to conservative defaults if not present so calling code
    never raises due to missing optional deps.

    Returns a dict with keys: cpu, memory, process, disk, uptime
    """
    import time
    import os

    metrics = {
        "timestamp": time.time(),
        "cpu": {},
        "memory": {},
        "process": {},
        "disk": {},
        "uptime_seconds": None,
    }

    # psutil (optional)
    try:
        import psutil

        # CPU
        try:
            metrics["cpu"]["percent"] = psutil.cpu_percent(interval=0.1)
            metrics["cpu"]["count_logical"] = psutil.cpu_count(logical=True)
            metrics["cpu"]["count_physical"] = psutil.cpu_count(logical=False)
        except Exception:
            metrics["cpu"]["percent"] = None

        # Memory
        try:
            vm = psutil.virtual_memory()
            metrics["memory"] = {
                "total": vm.total,
                "available": vm.available,
                "used": vm.used,
                "percent": vm.percent,
            }
        except Exception:
            metrics["memory"] = {}

        # Disk (root)
        try:
            du = psutil.disk_usage("/")
            metrics["disk"] = {
                "total": du.total,
                "used": du.used,
                "free": du.free,
                "percent": du.percent,
            }
        except Exception:
            metrics["disk"] = {}

        # Uptime
        try:
            metrics["uptime_seconds"] = time.time() - psutil.boot_time()
        except Exception:
            metrics["uptime_seconds"] = None

        # Process info
        try:
            p = psutil.Process(os.getpid())
            with p.oneshot():
                mem_info = p.memory_info()
                metrics["process"] = {
                    "pid": p.pid,
                    "rss": getattr(mem_info, "rss", None),
                    "vms": getattr(mem_info, "vms", None),
                    "memory_percent": p.memory_percent(),
                    "cpu_percent": p.cpu_percent(interval=0.0),
                    "num_threads": p.num_threads(),
                }
        except Exception:
            metrics["process"] = {}

    except Exception:
        # psutil not available; provide minimal info
        try:
            # attempt to get CPU count
            import multiprocessing

            metrics["cpu"]["count_logical"] = multiprocessing.cpu_count()
        except Exception:
            metrics["cpu"]["count_logical"] = None

        metrics["cpu"]["percent"] = None
        metrics["memory"] = {}
        metrics["disk"] = {}
        metrics["process"] = {"pid": os.getpid()}

    # Try to include load average when available (Unix)
    try:
        if hasattr(os, "getloadavg"):
            metrics["load_average"] = os.getloadavg()
    except Exception:
        pass

    return metrics


class PerformanceLogger:
    """Context manager for logging performance metrics"""

    def __init__(self, operation: str, request_id: str = None):
        self.operation = operation
        self.request_id = request_id or generate_request_id()
        self.start_time = None

    def __enter__(self):
        import time

        self.start_time = time.time()
        logger.info(f"Starting {self.operation} [req: {self.request_id}]")
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        import time

        duration = time.time() - self.start_time

        if exc_type:
            logger.error(
                f"Failed {self.operation} in {duration:.3f}s [req: {self.request_id}]: {exc_val}"
            )
        else:
            logger.info(
                f"Completed {self.operation} in {duration:.3f}s [req: {self.request_id}]"
            )
