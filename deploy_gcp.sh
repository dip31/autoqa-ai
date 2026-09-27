#!/bin/bash

# Configuration
PROJECT_ID="mystic-shelter-493010-a7"
REGION="us-central1"
BACKEND_SERVICE="autoqa-backend"

echo "Using Project ID: $PROJECT_ID"
echo "Region: $REGION"

# 1. Enable APIs
echo "Enabling necessary APIs..."
gcloud services enable \
    run.googleapis.com \
    sqladmin.googleapis.com \
    cloudbuild.googleapis.com \
    secretmanager.googleapis.com \
    artifactregistry.googleapis.com

# 2. Build and Deploy Backend First to get URL
echo "Building and Deploying Backend..."
gcloud builds submit --config=cloudbuild.yaml --substitutions=_REGION=$REGION .

BACKEND_URL=$(gcloud run services describe $BACKEND_SERVICE --region $REGION --format='value(status.url)')
echo "Backend URL: $BACKEND_URL"

# 3. Build and Deploy Frontend with Backend URL
echo "Building and Deploying Frontend..."
gcloud builds submit --config=cloudbuild.yaml --substitutions=_REGION=$REGION,_BACKEND_URL=$BACKEND_URL .

FRONTEND_URL=$(gcloud run services describe autoqa-frontend --region $REGION --format='value(status.url)')

echo "------------------------------------------------"
echo "Deployment Complete!"
echo "Backend: $BACKEND_URL"
echo "Frontend: $FRONTEND_URL"
echo "------------------------------------------------"
