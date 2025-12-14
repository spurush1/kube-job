#!/bin/bash

# Usage: ./push.sh <folder_name> <image_name>
# Example: ./push.sh worker-spend myuser/worker-spend:latest

FOLDER=$1
IMAGE=$2

if [ -z "$FOLDER" ] || [ -z "$IMAGE" ]; then
    echo "Usage: $0 <folder_name> <image_name>"
    exit 1
fi

if [ ! -d "$FOLDER" ]; then
    echo "Error: Directory '$FOLDER' does not exist."
    exit 1
fi

# Check if logged in (simple check)
if ! docker system info | grep -q "Username"; then
    echo "⚠️  Warning: You do not appear to be logged in to Docker Hub."
    echo "Please run 'docker login' first if the push fails."
fi

echo "🐳 Building $IMAGE from $FOLDER..."
docker build -t $IMAGE $FOLDER

echo "🚀 Pushing $IMAGE..."
docker push $IMAGE

echo "✅ Done!"
