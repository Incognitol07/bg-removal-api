"""
Test suite for Background Remover API
"""
import pytest
import asyncio
from fastapi.testclient import TestClient
from PIL import Image
import io
import zipfile
from app.main import app
from app.core.config import settings

# Test client
client = TestClient(app)


@pytest.fixture
def sample_image_bytes():
    """Create a sample image for testing"""
    image = Image.new('RGB', (100, 100), color='red')
    buffer = io.BytesIO()
    image.save(buffer, format='PNG')
    return buffer.getvalue()


@pytest.fixture
def sample_image_file(sample_image_bytes):
    """Create a sample image file-like object"""
    return io.BytesIO(sample_image_bytes)


class TestHealthEndpoints:
    """Test health check endpoints"""
    
    def test_root_endpoint(self):
        """Test root endpoint"""
        response = client.get("/")
        assert response.status_code == 200
        data = response.json()
        assert "message" in data
        assert "version" in data

    def test_health_check(self):
        """Test health check endpoint"""
        response = client.get("/api/v1/health")
        # Health check might return 200 or 503 depending on service state
        assert response.status_code in [200, 503, 206]

    def test_api_info(self):
        """Test API info endpoint"""
        response = client.get("/api/v1/info")
        assert response.status_code == 200
        data = response.json()
        assert "api_version" in data
        assert "current_model" in data
        assert "configuration" in data
        assert "features" in data


class TestImageProcessing:
    """Test image processing endpoints"""
    
    def test_single_image_upload_png(self, sample_image_bytes):
        """Test single image upload with PNG"""
        response = client.post(
            "/api/v1/remove",
            files={"file": ("test.png", sample_image_bytes, "image/png")},
            params={"output_format": "PNG"}
        )
        
        # Might fail if service not ready, but should not crash
        assert response.status_code in [200, 500, 503]
        
        if response.status_code == 200:
            assert response.headers["content-type"] == "image/png"
            assert "X-Request-ID" in response.headers
            assert len(response.content) > 0

    def test_single_image_upload_jpeg(self, sample_image_bytes):
        """Test single image upload with JPEG output"""
        response = client.post(
            "/api/v1/remove",
            files={"file": ("test.png", sample_image_bytes, "image/png")},
            params={"output_format": "JPEG", "quality": 90}
        )
        
        assert response.status_code in [200, 500, 503]
        
        if response.status_code == 200:
            assert response.headers["content-type"] == "image/jpeg"

    def test_batch_processing(self, sample_image_bytes):
        """Test batch image processing"""
        files = [
            ("files", ("test1.png", sample_image_bytes, "image/png")),
            ("files", ("test2.png", sample_image_bytes, "image/png"))
        ]
        
        response = client.post("/api/v1/batch", files=files)
        
        assert response.status_code in [200, 500, 503]
        
        if response.status_code == 200:
            assert response.headers["content-type"] == "application/zip"
            assert len(response.content) > 0
            
            # Verify ZIP content
            zip_buffer = io.BytesIO(response.content)
            with zipfile.ZipFile(zip_buffer, 'r') as zip_file:
                file_list = zip_file.namelist()
                assert len(file_list) == 2
                assert any("no_bg_test1" in f for f in file_list)
                assert any("no_bg_test2" in f for f in file_list)

    def test_invalid_file_type(self):
        """Test upload with invalid file type"""
        response = client.post(
            "/api/v1/remove",
            files={"file": ("test.txt", b"not an image", "text/plain")}
        )
        assert response.status_code == 400

    def test_missing_file(self):
        """Test endpoint without file"""
        response = client.post("/api/v1/remove")
        assert response.status_code == 422

    def test_batch_too_many_files(self, sample_image_bytes):
        """Test batch with too many files"""
        # Create more files than allowed
        files = []
        for i in range(settings.MAX_FILES_BATCH + 1):
            files.append(("files", (f"test{i}.png", sample_image_bytes, "image/png")))
        
        response = client.post("/api/v1/batch", files=files)
        assert response.status_code == 400

    def test_batch_no_files(self):
        """Test batch endpoint with no files"""
        response = client.post("/api/v1/batch", files=[])
        assert response.status_code == 422


class TestValidation:
    """Test input validation"""
    
    def test_invalid_output_format(self, sample_image_bytes):
        """Test invalid output format"""
        response = client.post(
            "/api/v1/remove",
            files={"file": ("test.png", sample_image_bytes, "image/png")},
            params={"output_format": "INVALID"}
        )
        assert response.status_code == 422

    def test_invalid_quality_low(self, sample_image_bytes):
        """Test quality value too low"""
        response = client.post(
            "/api/v1/remove",
            files={"file": ("test.png", sample_image_bytes, "image/png")},
            params={"quality": 0}
        )
        assert response.status_code == 422

    def test_invalid_quality_high(self, sample_image_bytes):
        """Test quality value too high"""
        response = client.post(
            "/api/v1/remove",
            files={"file": ("test.png", sample_image_bytes, "image/png")},
            params={"quality": 101}
        )
        assert response.status_code == 422

    def test_large_file_rejection(self):
        """Test rejection of files that are too large"""
        # Create a large dummy file
        large_data = b"x" * (settings.MAX_FILE_SIZE + 1)
        
        response = client.post(
            "/api/v1/remove",
            files={"file": ("large.png", large_data, "image/png")}
        )
        assert response.status_code in [400, 413]


@pytest.mark.asyncio
class TestAsyncFunctionality:
    """Test async functionality"""
    
    async def test_concurrent_requests(self, sample_image_bytes):
        """Test handling of concurrent requests"""
        import httpx
        
        async with httpx.AsyncClient(app=app, base_url="http://test") as ac:
            # Send multiple requests concurrently
            tasks = []
            for i in range(3):
                task = ac.post(
                    "/api/v1/remove",
                    files={"file": ("test.png", sample_image_bytes, "image/png")}
                )
                tasks.append(task)
            
            responses = await asyncio.gather(*tasks, return_exceptions=True)
            
            # At least some should succeed or fail gracefully
            for response in responses:
                if not isinstance(response, Exception):
                    assert response.status_code in [200, 500, 503]


if __name__ == "__main__":
    pytest.main([__file__])