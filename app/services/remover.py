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
from app.core.config import settings
from app.core.utils import PerformanceLogger, generate_request_id
import threading
from concurrent.futures import ThreadPoolExecutor

logger = logging.getLogger(__name__)


class BackgroundRemoverService:
    """
    Background remover service with lazy loading, idle timeout, and concurrent processing
    """

    def __init__(self):
        self._session = None
        self._model_loaded = False
        self._executor = None
        self._lock = threading.Lock()
        self._last_used = 0.0
        self._idle_timeout = settings.MODEL_IDLE_TIMEOUT
        self._idle_checker_task: Optional[asyncio.Task] = None

    def _load_model(self) -> None:
        """Load the rembg model (blocking operation, runs in thread pool)"""
        try:
            # Lazy import: only load rembg when actually needed
            from rembg import new_session

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

    def _unload_model(self) -> None:
        """Unload the model weights from memory (keeping libraries loaded)"""
        with self._lock:
            if self._model_loaded:
                # Explicitly delete the session to free ONNX Runtime model weights
                if self._session is not None:
                    del self._session
                self._session = None
                self._model_loaded = False

                # Force garbage collection to free model weights
                import gc

                gc.collect()
                gc.collect()

                logger.info("Model weights unloaded from memory due to inactivity")

    async def _idle_checker(self) -> None:
        """Background task to check for idle timeout and unload model"""
        while True:
            try:
                await asyncio.sleep(60)  # Check every minute

                if self._model_loaded:
                    idle_time = time.time() - self._last_used
                    if idle_time > self._idle_timeout:
                        self._unload_model()
                        logger.info(
                            f"Model was idle for {idle_time:.0f}s (timeout: {self._idle_timeout}s)"
                        )

            except asyncio.CancelledError:
                logger.info("Idle checker task cancelled")
                break
            except Exception as e:
                logger.error(f"Error in idle checker: {e}")

    async def _ensure_model_loaded(self) -> None:
        """Ensure model is loaded (thread-safe lazy loading)"""
        if not self._model_loaded:
            with self._lock:
                if not self._model_loaded:  # Double-check pattern
                    with PerformanceLogger("Lazy model loading"):
                        loop = asyncio.get_event_loop()
                        await loop.run_in_executor(self._executor, self._load_model)

    async def initialize(self) -> None:
        """Initialize the service without loading model (lazy loading on first request)"""
        try:
            # Set model cache directory
            if settings.MODEL_CACHE_DIR:
                os.environ["U2NET_HOME"] = settings.MODEL_CACHE_DIR

            # Create thread pool executor for CPU-bound tasks
            # Use smaller pool (2 workers) to reduce memory footprint
            self._executor = ThreadPoolExecutor(
                max_workers=min(2, settings.MAX_CONCURRENT_REQUESTS),
                thread_name_prefix="bg_remover",
            )

            # Start idle checker task
            self._idle_checker_task = asyncio.create_task(self._idle_checker())

            logger.info(
                f"Background remover service initialized "
                f"(model: {settings.REMBG_MODEL}, lazy loading enabled, "
                f"idle timeout: {self._idle_timeout}s)"
            )

        except Exception as e:
            logger.error(f"Failed to initialize background remover service: {e}")
            raise

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
            # Update last used timestamp
            self._last_used = time.time()

            # Ensure model is loaded (lazy loading)
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
            # Import here to avoid loading until model is actually needed
            from rembg import remove

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
            # Update last used timestamp (once for the batch)
            self._last_used = time.time()

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
            status = {
                "status": "healthy" if self.is_ready else "idle",
                "model": settings.REMBG_MODEL,
                "model_loaded": self._model_loaded,
                "max_concurrent": min(2, settings.MAX_CONCURRENT_REQUESTS),
                "executor_active": self._executor is not None
                and not self._executor._shutdown,
                "idle_timeout_seconds": self._idle_timeout,
            }

            return status

        except Exception as e:
            logger.error(f"Health check failed: {e}")
            return {"status": "unhealthy", "error": str(e)}

    async def cleanup(self) -> None:
        """Clean up resources"""
        try:
            # Cancel idle checker task
            if self._idle_checker_task:
                self._idle_checker_task.cancel()
                try:
                    await self._idle_checker_task
                except asyncio.CancelledError:
                    pass

            # Unload model if loaded
            if self._model_loaded:
                self._unload_model()

            # Force final garbage collection
            import gc

            gc.collect()

            # Shutdown executor
            if self._executor:
                logger.info("Shutting down thread pool executor...")
                self._executor.shutdown(wait=True)
                self._executor = None

            logger.info("Background remover service cleaned up")

        except Exception as e:
            logger.error(f"Error during cleanup: {e}")

    @property
    def is_ready(self) -> bool:
        """Check if service is ready to process requests (executor initialized)"""
        return self._executor is not None and not self._executor._shutdown
