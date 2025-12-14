#!/bin/bash

# Load Secrets
if [ -f ".secrets.env" ]; then
    source .secrets.env
else
    echo "Error: .secrets.env not found!"
    echo "Please create it with USERNAME and TOKEN."
    exit 1
fi

echo "🔐 Setting up Docker Authentication..."

# 1. Login locally (for pushing images)
echo "1. Logging in to Docker Hub locally..."
echo "$TOKEN" | docker login -u "$USERNAME" --password-stdin

# 2. Create Kubernetes Secret (for pulling images)
echo "2. Creating Kubernetes Secret '$SECRET_NAME'..."
kubectl delete secret $SECRET_NAME --ignore-not-found
kubectl create secret docker-registry $SECRET_NAME \
  --docker-server=https://index.docker.io/v1/ \
  --docker-username=$USERNAME \
  --docker-password=$TOKEN \
  --docker-email=user@example.com

echo "✅ Auth Setup Complete!"
echo "   - Local Docker: Logged in."
echo "   - Kubernetes: Secret '$SECRET_NAME' created."
