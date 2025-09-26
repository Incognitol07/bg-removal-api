"""
API routes for background remover
"""

from typing import List, Optional
from fastapi import APIRouter, Depends, File, UploadFile, HTTPException, Query, Request
from fastapi.responses import Response
from app.core.config import settings
from app.core.utils import (
    load_image_from_upload,
    image_to_bytes,
    get_image_info,
    get_content_type,
    generate_request_id,
    PerformanceLogger,
)
from app.core.utils import get_system_metrics
from app.services.remover import BackgroundRemoverService
from app.services.auth import get_api_key
import logging

logger = logging.getLogger(__name__)

# Create router
router = APIRouter(tags=["Background Remover"])

# Simple in-memory cache for metrics to avoid heavy system calls on every request
_metrics_cache = {"data": None, "ts": 0}
_METRICS_TTL = 2.0  # seconds


@router.get("/health")
async def health_check(request: Request):
    """
    Health check endpoint

    Returns:
        Health status of the service
    """
    try:
        remover_service: BackgroundRemoverService = request.app.state.remover_service
        health_status = await remover_service.health_check()

        # Return appropriate status code
        status_code = 200
        if health_status.get("status") == "unhealthy":
            status_code = 503
        elif health_status.get("status") == "degraded":
            status_code = 206

        return {
            "content": health_status,
            "status_code": status_code
        }

    except Exception as e:
        logger.error(f"Health check error: {e}")
        raise HTTPException(status_code=503, detail="Service unavailable")


@router.post("/remove", dependencies=[Depends(get_api_key)])
async def remove_background(
    request: Request,
    file: UploadFile = File(..., description="Image file to remove background from"),
    output_format: Optional[str] = Query(
        default=None,
        description="Output format (PNG, JPEG, WEBP)",
        regex="^(PNG|JPEG|WEBP|png|jpeg|webp)$",
    ),
    quality: Optional[int] = Query(
        default=None, description="Output quality for JPEG/WEBP (1-100)", ge=1, le=100
    ),
):
    """
    Remove background from a single image

    Args:
        file: Image file to process
        output_format: Output format (PNG, JPEG, WEBP)
        quality: Output quality for JPEG/WEBP (1-100)

    Returns:
        Processed image with background removed
    """
    request_id = generate_request_id()

    try:
        # Get remover service
        remover_service: BackgroundRemoverService = request.app.state.remover_service

        if not remover_service.is_ready:
            raise HTTPException(
                status_code=503, detail="Background remover service not ready"
            )

        with PerformanceLogger("Single image API processing", request_id):
            # Load image from upload
            image = await load_image_from_upload(file)

            # Log input image info
            input_info = get_image_info(image)
            logger.info(f"Processing image: {input_info} [req: {request_id}]")

            # Remove background
            result_image = await remover_service.remove_background(image, request_id)

            # Convert to bytes
            format_to_use = (
                output_format.upper()
                if output_format
                else settings.DEFAULT_OUTPUT_FORMAT
            )
            quality_to_use = quality if quality else settings.OUTPUT_QUALITY

            image_bytes = image_to_bytes(result_image, format_to_use, quality_to_use)

            # Prepare response
            content_type = get_content_type(format_to_use)
            filename = f"no_bg_{file.filename.rsplit('.', 1)[0] if file.filename else 'image'}.{format_to_use.lower()}"

            logger.info(f"Successfully processed image [req: {request_id}]")

            return Response(
                content=image_bytes,
                media_type=content_type,
                headers={
                    "Content-Disposition": f"attachment; filename={filename}",
                    "X-Request-ID": request_id,
                    "X-Input-Size": str(len(await file.read())),
                    "X-Output-Size": str(len(image_bytes)),
                    "X-Processing-Model": settings.REMBG_MODEL,
                },
            )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error processing single image [req: {request_id}]: {e}")
        raise HTTPException(status_code=500, detail=f"Processing failed: {str(e)}")


@router.post("/batch", dependencies=[Depends(get_api_key)])
async def remove_background_batch(
    request: Request,
    files: List[UploadFile] = File(..., description="Multiple image files to process"),
    output_format: Optional[str] = Query(
        default=None,
        description="Output format (PNG, JPEG, WEBP)",
        regex="^(PNG|JPEG|WEBP|png|jpeg|webp)$",
    ),
    quality: Optional[int] = Query(
        default=None, description="Output quality for JPEG/WEBP (1-100)", ge=1, le=100
    ),
):
    """
    Remove background from multiple images

    Args:
        files: List of image files to process
        output_format: Output format (PNG, JPEG, WEBP)
        quality: Output quality for JPEG/WEBP (1-100)

    Returns:
        ZIP file containing processed images
    """
    request_id = generate_request_id()

    try:
        # Validate batch size
        if len(files) > settings.MAX_FILES_BATCH:
            raise HTTPException(
                status_code=400,
                detail=f"Too many files. Maximum allowed: {settings.MAX_FILES_BATCH}",
            )

        if len(files) == 0:
            raise HTTPException(status_code=400, detail="No files provided")

        # Get remover service
        remover_service: BackgroundRemoverService = request.app.state.remover_service

        if not remover_service.is_ready:
            raise HTTPException(
                status_code=503, detail="Background remover service not ready"
            )

        with PerformanceLogger(
            f"Batch API processing ({len(files)} files)", request_id
        ):
            # Load all images
            images = []
            filenames = []

            for file in files:
                image = await load_image_from_upload(file)
                images.append(image)
                filenames.append(file.filename or f"image_{len(filenames)+1}")

            logger.info(
                f"Loaded {len(images)} images for batch processing [req: {request_id}]"
            )

            # Process batch
            result_images = await remover_service.remove_background_batch(
                images, request_id
            )

            # Create ZIP response
            import zipfile
            import io

            zip_buffer = io.BytesIO()
            format_to_use = (
                output_format.upper()
                if output_format
                else settings.DEFAULT_OUTPUT_FORMAT
            )
            quality_to_use = quality if quality else settings.OUTPUT_QUALITY

            with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zip_file:
                for i, (result_image, original_filename) in enumerate(
                    zip(result_images, filenames)
                ):
                    # Convert image to bytes
                    image_bytes = image_to_bytes(
                        result_image, format_to_use, quality_to_use
                    )

                    # Create output filename
                    base_name = (
                        original_filename.rsplit(".", 1)[0]
                        if "." in original_filename
                        else original_filename
                    )
                    output_filename = f"no_bg_{base_name}.{format_to_use.lower()}"

                    # Add to ZIP
                    zip_file.writestr(output_filename, image_bytes)

            zip_bytes = zip_buffer.getvalue()

            logger.info(
                f"Successfully processed batch of {len(files)} images [req: {request_id}]"
            )

            return Response(
                content=zip_bytes,
                media_type="application/zip",
                headers={
                    "Content-Disposition": f"attachment; filename=batch_no_bg_{request_id[:8]}.zip",
                    "X-Request-ID": request_id,
                    "X-Files-Processed": str(len(files)),
                    "X-Processing-Model": settings.REMBG_MODEL,
                },
            )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error processing batch [req: {request_id}]: {e}")
        raise HTTPException(
            status_code=500, detail=f"Batch processing failed: {str(e)}"
        )


@router.get("/info")
async def api_info():
    """
    Get API information and capabilities

    Returns:
        API configuration and limits
    """
    return {
        "api_version": "1.0.0",
        "current_model": settings.REMBG_MODEL,
        "configuration": {
            "max_file_size_mb": settings.MAX_FILE_SIZE / (1024 * 1024),
            "max_files_batch": settings.MAX_FILES_BATCH,
            "allowed_extensions": settings.ALLOWED_EXTENSIONS,
            "supported_output_formats": ["PNG", "JPEG", "WEBP"],
            "default_output_format": settings.DEFAULT_OUTPUT_FORMAT,
            "max_concurrent_requests": settings.MAX_CONCURRENT_REQUESTS,
            "request_timeout_seconds": settings.REQUEST_TIMEOUT,
        },
        "features": {
            "single_image_processing": True,
            "batch_processing": True,
            "multiple_output_formats": True,
            "quality_control": True,
        },
    }


@router.get("/metrics", dependencies=[Depends(get_api_key)])
async def metrics():
    """
    Return best-effort system and process metrics.

    This endpoint is intentionally lightweight and best-effort: if optional
    packages like `psutil` are not installed, the endpoint will
    still return a minimal payload.
    """
    import time

    now = time.time()
    # Use cached metrics if fresh
    if _metrics_cache["data"] is None or (now - _metrics_cache["ts"]) > _METRICS_TTL:
        try:
            data = get_system_metrics()
        except Exception as e:
            # Defensive: never raise to the client because of metrics helper
            logger.error(f"Error collecting metrics: {e}")
            data = {"error": str(e)}

        _metrics_cache["data"] = data
        _metrics_cache["ts"] = now

    return _metrics_cache["data"]
