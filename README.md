# Background Remover API

An API for removing image backgrounds, built on [rembg](https://github.com/danielgatis/rembg). Runs in Docker.

## What it does

- Remove backgrounds from single images or in batches
- Output as PNG, JPEG, or WEBP
- Handles concurrent requests

## Quick Start

### Using Docker (Recommended)

1. **Clone and build**:

   ```bash
   git clone https://github.com/Incognitol07/bg-removal-api
   cd bg-remover-api
   docker build -t bg-remover-api .
   ```

2. **Run the container**:

   ```bash
   docker run -p 8000:8000 bg-remover-api
   ```

3. **Access the API**:
   - API: <http://localhost:8000>
   - Interactive docs: <http://localhost:8000/docs>
   - Health check: <http://localhost:8000/api/v1/health>

### Local Development

1. **Install dependencies**:

   ```bash
   uv sync
   ```

2. **Set environment variables**:

   ```bash
   cp .env.example .env
   # Edit .env with your settings
   ```

3. **Run the application**:

   ```bash
   uv run uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
   ```

## API Endpoints

### Core Endpoints

| Method | Endpoint         | Description                            |
| ------ | ---------------- | -------------------------------------- |
| `POST` | `/api/v1/remove` | Remove background from single image    |
| `POST` | `/api/v1/batch`  | Remove background from multiple images |
| `GET`  | `/api/v1/health` | Health check                           |
| `GET`  | `/api/v1/info`   | API information                        |

### Single Image Processing

```bash
curl -X POST "http://localhost:8000/api/v1/remove" \
  -F "file=@your_image.jpg" \
  -F "output_format=PNG" \
  -F "quality=95" \
  --output result.png
```

### Batch Processing

```bash
curl -X POST "http://localhost:8000/api/v1/batch" \
  -F "files=@image1.jpg" \
  -F "files=@image2.jpg" \
  -F "output_format=PNG" \
  --output batch_results.zip
```

## Configuration

The API is configured through environment variables. Copy `.env.example` to `.env` and modify as needed:

### Key Configuration Options

| Variable                  | Default             | Description                 |
| ------------------------- | ------------------- | --------------------------- |
| `REMBG_MODEL`             | `isnet-general-use` | Background removal model    |
| `MAX_FILE_SIZE`           | `10485760`          | Maximum file size (10MB)    |
| `MAX_FILES_BATCH`         | `5`                 | Maximum files per batch     |
| `MAX_CONCURRENT_REQUESTS` | `4`                 | Concurrent processing limit |
| `DEFAULT_OUTPUT_FORMAT`   | `PNG`               | Default output format       |

## Docker Deployment

### Production Deployment

```bash
# Build production image
docker build -t bg-remover-api:latest .
```

## Health Check

```bash
curl http://localhost:8000/api/v1/health
```

Returns service status, model info, and queue state.

## Error Handling

The API provides detailed error responses:

```json
{
  "detail": "File size (15728640 bytes) exceeds maximum allowed size (10485760 bytes)",
  "status_code": 413
}
```

Common error codes:

- `400` - Invalid input (file type, parameters)
- `413` - File too large
- `422` - Validation error
- `500` - Processing error
- `503` - Service unavailable

## API Response Headers

Successful responses include useful metadata:

```plaintext
Content-Type: image/png
Content-Disposition: attachment; filename=no_bg_image.png
X-Request-ID: 12345678-1234-1234-1234-123456789012
X-Processing-Model: isnet-general-use
X-Input-Size: 1048576
X-Output-Size: 987654
```

## Security

- File type and size validation
- Runs as non-root in Docker
- Configurable CORS
- Concurrency limits

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests
5. Submit a pull request

## License

MIT License - see LICENSE file for details.

## Support

- Docs at `/docs`
- Bugs → GitHub Issues
- Questions → GitHub Discussions
