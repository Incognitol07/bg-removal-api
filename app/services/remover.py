"""
Background remover service using rembg
Handles model loading, processing queue, and GPU/CPU management
"""
import asyncio
import logging
from typing import List
from PIL import Image
from rembg import remove, new_session
from app.core.config import settings
from app.core.utils import PerformanceLogger, generate_request_id
import threading
from concurrent.futures import ThreadPoolExecutor
import queue

logger = logging.getLogger(__name__)


class BackgroundRemoverService:
    """
    Background remover service with model caching and concurrent processing
    """
    
    def __init__(self):
        self._session = None
        self._model_loaded = False
        self._executor = None
        self._processing_queue = queue.Queue(maxsize=settings.MAX_CONCURRENT_REQUESTS * 2)
        self._lock = threading.Lock()
        
    async def initialize(self) -> None:
        """Initialize the service and load the model"""
        try:
            with PerformanceLogger("Model initialization"):
                # Set model cache directory
                if settings.MODEL_CACHE_DIR:
                    os.environ['U2NET_HOME'] = settings.MODEL_CACHE_DIR
                
                # Create thread pool executor for CPU-bound tasks
                self._executor = ThreadPoolExecutor(
                    max_workers=settings.MAX_CONCURRENT_REQUESTS,
                    thread_name_prefix="bg_remover"
                )
                
                # Load model in thread pool to avoid blocking
                loop = asyncio.get_event_loop()
                await loop.run_in_executor(
                    self._executor, 
                    self._load_model
                )
                
                self._model_loaded = True
                logger.info(f"Background remover service initialized with model: {settings.REMBG_MODEL}")
                
        except Exception as e:
            logger.error(f"Failed to initialize background remover service: {e}")
            raise
    
    def _load_model(self) -> None:
        """Load the rembg model (runs in thread pool)"""
        try:
            # Create new session with specified model
            self._session = new_session(settings.REMBG_MODEL)

            logger.info(f"Model {settings.REMBG_MODEL} loaded successfully")
            
        except Exception as e:
            logger.error(f"Error loading model {settings.REMBG_MODEL}: {e}")
            raise
    
    async def remove_background(
        self, 
        image: Image.Image, 
        request_id: str = None
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
        if not self._model_loaded:
            raise RuntimeError("Background remover service not initialized")
        
        if request_id is None:
            request_id = generate_request_id()
        
        try:
            with PerformanceLogger("Background removal", request_id):
                # Process in thread pool to avoid blocking event loop
                loop = asyncio.get_event_loop()
                result = await loop.run_in_executor(
                    self._executor,
                    self._process_image,
                    image,
                    request_id
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
        self, 
        images: List[Image.Image], 
        request_id: str = None
    ) -> List[Image.Image]:
        """
        Remove background from multiple images
        
        Args:
            images: List of PIL Images
            request_id: Optional request ID for tracking
            
        Returns:
            List of PIL Images with backgrounds removed
        """
        if not self._model_loaded:
            raise RuntimeError("Background remover service not initialized")
        
        if request_id is None:
            request_id = generate_request_id()
        
        if len(images) > settings.MAX_FILES_BATCH:
            raise ValueError(f"Batch size ({len(images)}) exceeds maximum allowed ({settings.MAX_FILES_BATCH})")
        
        try:
            with PerformanceLogger(f"Batch background removal ({len(images)} images)", request_id):
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
                        logger.error(f"Failed to process image {i+1} in batch [req: {request_id}]: {result}")
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
                "status": "healthy" if self._model_loaded else "unhealthy",
                "model": settings.REMBG_MODEL,
                "model_loaded": self._model_loaded,
                "max_concurrent": settings.MAX_CONCURRENT_REQUESTS,
                "queue_size": self._processing_queue.qsize() if hasattr(self._processing_queue, 'qsize') else 0,
                "executor_active": self._executor is not None and not self._executor._shutdown
            }
            
            return status
            
        except Exception as e:
            logger.error(f"Health check failed: {e}")
            return {
                "status": "unhealthy",
                "error": str(e)
            }
    
    async def cleanup(self) -> None:
        """Clean up resources"""
        try:
            self._model_loaded = False
            
            if self._executor:
                logger.info("Shutting down thread pool executor...")
                self._executor.shutdown(wait=True, timeout=10)
                self._executor = None
            
            # Clear session
            self._session = None
            
            logger.info("Background remover service cleaned up")
            
        except Exception as e:
            logger.error(f"Error during cleanup: {e}")
    
    @property
    def is_ready(self) -> bool:
        """Check if service is ready to process requests"""
        return self._model_loaded and self._executor is not None and not self._executor._shutdown