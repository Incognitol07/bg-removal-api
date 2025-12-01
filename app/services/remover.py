"""
Background remover service using rembg
Handles model loading, processing queue, and CPU management with lazy loading and idle timeout
"""

import asyncio
import logging
import time
from typing import List, Optional
from PIL import Image
import os
from rembg import remove, new_session
from app.core.config import settings
from app.core.utils import PerformanceLogger, generate_request_id
import threading
from concurrent.futures import ThreadPoolExecutor

logger = logging.getLogger(__name__)


class BackgroundRemoverService:
    """
    Background remover service with pure lazy loading for serverless
    Model loaded on first request, freed when container stops
    """

    def __init__(self):
        self._session = None
        self._model_loaded = False
        self._executor = None
        self._lock = threading.Lock()
        logger.info(
            "BackgroundRemoverService created (not initialized - serverless mode)"
        )

    def _load_model(self) -> None:
        """Load the rembg model (blocking operation, runs in thread pool)"""
        try:
            logger.info(f"Loading model {settings.REMBG_MODEL}...")
            start_time = time.time()

            # Create new session with specified model
            self._session = new_session(settings.REMBG_MODEL)
            self._model_loaded = True

            elapsed = time.time() - start_time
            logger.info(
                f"Model {settings.REMBG_MODEL} loaded successfully in {elapsed:.2f}s"
            )

        except Exception as e:
            logger.error(f"Error loading model {settings.REMBG_MODEL}: {e}")
            raise

    async def _ensure_model_loaded(self) -> None:
        """Ensure model is loaded (thread-safe lazy loading)"""
        if not self._model_loaded:
            with self._lock:
                if not self._model_loaded:  # Double-check pattern
                    # Create executor if not exists
                    if self._executor is None:
                        self._executor = ThreadPoolExecutor(
                            max_workers=settings.MAX_CONCURRENT_REQUESTS,
                            thread_name_prefix="bg_remover",
                        )
                        logger.info("Thread pool executor created on-demand")

                    with PerformanceLogger("Cold start - loading model"):
                        loop = asyncio.get_event_loop()
                        await loop.run_in_executor(self._executor, self._load_model)

    async def remove_background(
        self, image: Image.Image, request_id: str = None
    ) -> Image.Image:
        """
        Remove background from a single image

        Args:
            image: Input PIL Image
            request_id: Optional request ID for tracking

        Returns:
            PIL Image with background removed

        Raises:
            RuntimeError: If service not initialized
            Exception: If processing fails
        """
        if request_id is None:
            request_id = generate_request_id()

        try:
            # Ensure model is loaded (lazy loading on first request)
            await self._ensure_model_loaded()

            with PerformanceLogger("Background removal", request_id):
                # Process in thread pool to avoid blocking event loop
                loop = asyncio.get_event_loop()
                result = await loop.run_in_executor(
                    self._executor, self._process_image, image, request_id
                )

                return result

        except Exception as e:
            logger.error(f"Error removing background [req: {request_id}]: {e}")
            raise

    def _process_image(self, image: Image.Image, request_id: str) -> Image.Image:
        """
        Process image in thread pool (CPU-bound operation)

        Args:
            image: Input PIL Image
            request_id: Request ID for tracking

        Returns:
            PIL Image with background removed
        """
        try:
            with self._lock:
                # Use the loaded session
                result = remove(image, session=self._session)

            logger.debug(f"Successfully processed image [req: {request_id}]")
            return result

        except Exception as e:
            logger.error(f"Error in image processing [req: {request_id}]: {e}")
            raise

    async def remove_background_batch(
        self, images: List[Image.Image], request_id: str = None
    ) -> List[Image.Image]:
        """
        Remove background from multiple images

        Args:
            images: List of PIL Images
            request_id: Optional request ID for tracking

        Returns:
            List of PIL Images with backgrounds removed
        """
        if request_id is None:
            request_id = generate_request_id()

        if len(images) > settings.MAX_FILES_BATCH:
            raise ValueError(
                f"Batch size ({len(images)}) exceeds maximum allowed ({settings.MAX_FILES_BATCH})"
            )

        try:
            # Ensure model is loaded once for the entire batch
            await self._ensure_model_loaded()

            with PerformanceLogger(
                f"Batch background removal ({len(images)} images)", request_id
            ):
                # Process all images concurrently
                tasks = []
                for i, image in enumerate(images):
                    sub_request_id = f"{request_id}-{i+1}"
                    task = self.remove_background(image, sub_request_id)
                    tasks.append(task)

                results = await asyncio.gather(*tasks, return_exceptions=True)

                # Check for exceptions
                processed_results = []
                for i, result in enumerate(results):
                    if isinstance(result, Exception):
                        logger.error(
                            f"Failed to process image {i+1} in batch [req: {request_id}]: {result}"
                        )
                        raise result
                    processed_results.append(result)

                return processed_results

        except Exception as e:
            logger.error(f"Error in batch processing [req: {request_id}]: {e}")
            raise

    async def health_check(self) -> dict:
        """
        Perform health check of the service

        Returns:
            Dictionary with health status
        """
        try:
            # In serverless mode, service is healthy if it can start
            status = {
                "status": "healthy",
                "mode": "serverless",
                "model": settings.REMBG_MODEL,
                "model_loaded": self._model_loaded,
                "cold_start": not self._model_loaded,
                "max_concurrent": settings.MAX_CONCURRENT_REQUESTS,
            }

            return status

        except Exception as e:
            logger.error(f"Health check failed: {e}")
            return {"status": "unhealthy", "error": str(e)}

    async def cleanup(self) -> None:
        """Clean up resources on shutdown"""
        try:
            # Delete model session to free memory
            if self._session is not None:
                del self._session
                self._session = None

            self._model_loaded = False

            # Shutdown executor
            if self._executor:
                logger.info("Shutting down thread pool executor...")
                self._executor.shutdown(wait=False)  # Don't wait in serverless
                self._executor = None

            # Aggressive garbage collection
            import gc

            gc.collect()

            logger.info("Background remover service cleaned up")

        except Exception as e:
            logger.error(f"Error during cleanup: {e}")

    @property
    def is_ready(self) -> bool:
        """Check if service is ready to process requests (always true in serverless)"""
        return True  # Always ready - will lazy load on first request
