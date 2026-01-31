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

For full API details (parameters, error codes, response formats), see the interactive docs at `/docs`.

## Configuration

Copy `.env.example` to `.env`. Key options:

| Variable                  | Default             | Description              |
| ------------------------- | ------------------- | ------------------------ |
| `REMBG_MODEL`             | `isnet-general-use` | Background removal model |
| `MAX_FILE_SIZE`           | `10485760`          | Max file size (10MB)     |
| `MAX_FILES_BATCH`         | `5`                 | Max files per batch      |
| `MAX_CONCURRENT_REQUESTS` | `4`                 | Concurrent request limit |

## Contributing

1. Fork the repo
2. Create a feature branch
3. Make changes + add tests
4. Submit a PR

## License

MIT
