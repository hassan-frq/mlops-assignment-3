#!/usr/bin/env bash
# =============================================================================
# deploy-minikube.sh — Deploy the BTC-USD forecast API on Minikube and verify.
#
# Usage:
#   chmod +x deploy-minikube.sh
#   ./deploy-minikube.sh
#
# Prerequisites:
#   - minikube, kubectl, docker installed and in PATH
#   - The image is already built or will be built from the local Dockerfile
# =============================================================================
set -euo pipefail

NAMESPACE="default"
IMAGE_LOCAL="btc-forecast-api:local"
REGISTRY_IMAGE="ghcr.io/hassan-frq/mlops-assignment-3/btc-forecast-api:latest"
HOSTS_ENTRY="btc-forecast.local"

echo "============================================================"
echo " BTC-USD Forecast API — Minikube Deployment Script"
echo "============================================================"

# ---------------------------------------------------------------------------
# 1. Start Minikube (skip if already running)
# ---------------------------------------------------------------------------
echo ""
echo "[1/9] Starting Minikube..."
minikube status --profile minikube 2>/dev/null | grep -q "Running" \
  && echo "  Minikube already running." \
  || minikube start --driver=docker --cpus=4 --memory=4096 \
       --addons=ingress,metrics-server

# Enable addons if not already on
minikube addons enable ingress        2>/dev/null || true
minikube addons enable metrics-server 2>/dev/null || true

# ---------------------------------------------------------------------------
# 2. Build / load the Docker image into Minikube
# ---------------------------------------------------------------------------
echo ""
echo "[2/9] Building Docker image inside Minikube's Docker daemon..."
eval "$(minikube docker-env)"
docker build -t "${IMAGE_LOCAL}" .

# Patch the deployment to use the local image so we don't need a registry pull
# (imagePullPolicy must be Never or IfNotPresent for local images in Minikube)
# We achieve this with a kustomize-style patch applied inline.

# ---------------------------------------------------------------------------
# 3. Apply PVC
# ---------------------------------------------------------------------------
echo ""
echo "[3/9] Applying Persistent Volume Claim..."
kubectl apply -f k8s/pvc.yaml

# ---------------------------------------------------------------------------
# 4. Apply ConfigMap and Secret
# ---------------------------------------------------------------------------
echo ""
echo "[4/9] Applying ConfigMap and Secret..."
kubectl apply -f k8s/configmap.yaml
kubectl apply -f k8s/secret.yaml

# ---------------------------------------------------------------------------
# 5. Apply Deployment (with local image override)
# ---------------------------------------------------------------------------
echo ""
echo "[5/9] Applying Deployment..."
# Use sed to swap the registry image for the locally built one and set
# imagePullPolicy to Never so Minikube does not try to pull from GHCR.
kubectl apply -f - <<EOF
$(sed \
  -e "s|image: ${REGISTRY_IMAGE}|image: ${IMAGE_LOCAL}|g" \
  -e "s|imagePullPolicy: Always|imagePullPolicy: Never|g" \
  k8s/deployment.yaml)
EOF

# ---------------------------------------------------------------------------
# 6. Apply Services, Ingress, HPA
# ---------------------------------------------------------------------------
echo ""
echo "[6/9] Applying Services, Ingress, and HPA..."
kubectl apply -f k8s/service.yaml
kubectl apply -f k8s/ingress.yaml
kubectl apply -f k8s/hpa.yaml

# ---------------------------------------------------------------------------
# 7. Seed the model artifact into the PVC via a one-shot Job
# ---------------------------------------------------------------------------
echo ""
echo "[7/9] Seeding model artifact into PVC..."
kubectl apply -f - <<'SEED_JOB'
apiVersion: batch/v1
kind: Job
metadata:
  name: btc-forecast-seed
spec:
  ttlSecondsAfterFinished: 120
  template:
    spec:
      securityContext:
        runAsUser: 999
        fsGroup: 999
      restartPolicy: OnFailure
      containers:
        - name: seed
          image: btc-forecast-api:local
          imagePullPolicy: Never
          command:
            - sh
            - -c
            - |
              mkdir -p /app/models
              cp /app/tests/fixtures/forecast-example.json /app/models/forecast.json
              echo "Seed complete."
          volumeMounts:
            - name: model-store
              mountPath: /app/models
      volumes:
        - name: model-store
          persistentVolumeClaim:
            claimName: model-store
SEED_JOB

echo "  Waiting for seed job to complete..."
kubectl wait --for=condition=complete job/btc-forecast-seed --timeout=120s

# ---------------------------------------------------------------------------
# 8. Wait for all Deployment replicas to be ready
# ---------------------------------------------------------------------------
echo ""
echo "[8/9] Waiting for Deployment rollout..."
kubectl rollout status deployment/btc-forecast-api --timeout=180s

# ---------------------------------------------------------------------------
# 9. Verify everything
# ---------------------------------------------------------------------------
echo ""
echo "[9/9] Verification"
echo "------------------------------------------------------------"

echo ""
echo "--- Deployment ---"
kubectl get deployment btc-forecast-api -o wide

echo ""
echo "--- Pods ---"
kubectl get pods -l app=btc-forecast -o wide

echo ""
echo "--- Services ---"
kubectl get svc -l app=btc-forecast

echo ""
echo "--- Ingress ---"
kubectl get ingress btc-forecast-api

echo ""
echo "--- HPA ---"
kubectl get hpa btc-forecast-api

echo ""
echo "--- PVC ---"
kubectl get pvc model-store

# Minikube Ingress IP
MINIKUBE_IP=$(minikube ip)
echo ""
echo "Minikube IP: ${MINIKUBE_IP}"
echo "Add this line to /etc/hosts (or C:\\Windows\\System32\\drivers\\etc\\hosts on Windows):"
echo "  ${MINIKUBE_IP}  ${HOSTS_ENTRY}"

# Health check via NodePort (no /etc/hosts change required)
NODE_PORT=$(kubectl get svc btc-forecast-api-nodeport \
  -o jsonpath='{.spec.ports[0].nodePort}')
NODE_URL="http://${MINIKUBE_IP}:${NODE_PORT}"

echo ""
echo "--- Health check via NodePort (${NODE_URL}/health) ---"
curl -sf "${NODE_URL}/health" | python3 -m json.tool || echo "Health check failed — pods may still be starting."

# 7-day prediction via Ingress (requires /etc/hosts)
echo ""
echo "--- 7-day prediction via Ingress (http://${HOSTS_ENTRY}/predict) ---"
echo "  (This will fail if ${HOSTS_ENTRY} is not in /etc/hosts)"
curl -sf -H "Content-Type: application/json" \
     -d '{"forecast_days": 7}' \
     "http://${HOSTS_ENTRY}/predict" | python3 -m json.tool || \
  echo "  Skipped (add ${MINIKUBE_IP} ${HOSTS_ENTRY} to hosts file first)."

# 7-day prediction via NodePort (always works)
echo ""
echo "--- 7-day prediction via NodePort ---"
curl -sf -H "Content-Type: application/json" \
     -d '{"forecast_days": 7}' \
     "${NODE_URL}/predict" | python3 -m json.tool

echo ""
echo "--- Pod disruption test: delete one pod and watch replacement ---"
VICTIM=$(kubectl get pods -l app=btc-forecast -o jsonpath='{.items[0].metadata.name}')
echo "Deleting pod: ${VICTIM}"
kubectl delete pod "${VICTIM}"
echo "Watching replacement (Ctrl-C to stop):"
kubectl get pods -l app=btc-forecast -w &
WATCH_PID=$!
sleep 20
kill "${WATCH_PID}" 2>/dev/null || true

echo ""
echo "Final pod list:"
kubectl get pods -l app=btc-forecast -o wide

echo ""
echo "============================================================"
echo " Deployment complete."
echo " NodePort URL : ${NODE_URL}"
echo " Ingress URL  : http://${HOSTS_ENTRY}  (after /etc/hosts update)"
echo "============================================================"
