#!/bin/bash
set -e

IMAGE_NAME="uyolo.io/vsme-validator"
VERSION="${1:-latest}"

echo "Building Docker image: ${IMAGE_NAME}:${VERSION}"

docker build \
    --tag "${IMAGE_NAME}:${VERSION}" \
    --tag "${IMAGE_NAME}:latest" \
    .

echo ""
echo "Build complete!"
echo ""
echo "Image: ${IMAGE_NAME}:${VERSION}"
echo ""
echo "Run with:"
echo "  docker run -p 8080:8080 ${IMAGE_NAME}"
echo ""
echo "Test with:"
echo "  curl http://localhost:8080/health"
echo "  curl -X POST http://localhost:8080/validate -F 'file=@your-file.xlsx'"
