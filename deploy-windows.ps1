#!/usr/bin/env pwsh
<#
.SYNOPSIS
    Full Minikube deploy + verify script for BTC Forecast API (Windows / PowerShell).

.DESCRIPTION
    Run this in a PowerShell session AFTER Docker Desktop is already open.
    Steps:
      1. Start Minikube (or reuse existing cluster)
      2. Build the Docker image inside Docker Desktop
      3. Load it into Minikube's registry
      4. Enable the ingress addon
      5. Apply all k8s/ manifests
      6. Wait for rollout + seed the model from handoff/forecast.json
      7. Print evidence (deployment, pods, svc, ingress, hpa, pvc, predictions)
      8. Pod disruption test (delete a pod and watch replacement)

.NOTES
    Requires: Docker Desktop running, minikube, kubectl on PATH.
#>

param(
    [string]$Image  = "btc-forecast-api:local",
    [string]$Ns     = "default",
    [string]$NodePort = "30080"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
$Repo = $PSScriptRoot

function Banner($msg) { Write-Host "`n=== $msg ===" -ForegroundColor Cyan }

# ─────────────────────────────────────────────────────────────────────────────
# 1. Start Minikube
# ─────────────────────────────────────────────────────────────────────────────
Banner "Starting Minikube"
$mk = minikube status --format "{{.Host}}" 2>$null
if ($mk -ne "Running") {
    minikube start --driver=docker --memory=3500 --cpus=2 --addons=metrics-server
} else {
    Write-Host "Minikube already running."
}

# ─────────────────────────────────────────────────────────────────────────────
# 2. Build image in Docker Desktop
# ─────────────────────────────────────────────────────────────────────────────
Banner "Building Docker image: $Image"
docker build -t $Image "$Repo"

# ─────────────────────────────────────────────────────────────────────────────
# 3. Load image into Minikube (avoids imagePullPolicy: Never caveat)
# ─────────────────────────────────────────────────────────────────────────────
Banner "Loading image into Minikube"
docker save $Image | minikube image load --overwrite -

# ─────────────────────────────────────────────────────────────────────────────
# 4. Patch deployment to use local image (if using local build)
# ─────────────────────────────────────────────────────────────────────────────
Banner "Patching deployment for local image"
kubectl patch deployment btc-forecast-api -n $Ns `
    --type=json `
    -p='[{"op":"replace","path":"/spec/template/spec/containers/0/image","value":"'"$Image"'"},{"op":"replace","path":"/spec/template/spec/containers/0/imagePullPolicy","value":"Never"}]' `
    2>$null ; $true   # ignore if deployment not yet applied

# ─────────────────────────────────────────────────────────────────────────────
# 5. Enable ingress addon
# ─────────────────────────────────────────────────────────────────────────────
Banner "Enabling ingress addon"
minikube addons enable ingress

# ─────────────────────────────────────────────────────────────────────────────
# 6. Apply all manifests
# ─────────────────────────────────────────────────────────────────────────────
Banner "Applying k8s manifests"
kubectl apply -f "$Repo\k8s\pvc.yaml"       -n $Ns
kubectl apply -f "$Repo\k8s\configmap.yaml" -n $Ns
kubectl apply -f "$Repo\k8s\secret.yaml"    -n $Ns
kubectl apply -f "$Repo\k8s\deployment.yaml" -n $Ns

# Patch image + pull policy after apply so it always uses local build
kubectl set image deployment/btc-forecast-api api=$Image -n $Ns
kubectl patch deployment btc-forecast-api -n $Ns `
    --type=json `
    -p='[{"op":"replace","path":"/spec/template/spec/containers/0/imagePullPolicy","value":"Never"}]'

kubectl apply -f "$Repo\k8s\service.yaml"   -n $Ns
kubectl apply -f "$Repo\k8s\ingress.yaml"   -n $Ns
kubectl apply -f "$Repo\k8s\hpa.yaml"       -n $Ns

# ─────────────────────────────────────────────────────────────────────────────
# 7. Wait for rollout
# ─────────────────────────────────────────────────────────────────────────────
Banner "Waiting for rollout (up to 5 min)"
kubectl rollout status deployment/btc-forecast-api -n $Ns --timeout=300s

# ─────────────────────────────────────────────────────────────────────────────
# 8. Seed the accepted model onto the shared PVC
# ─────────────────────────────────────────────────────────────────────────────
Banner "Seeding model from handoff/forecast.json"
$pod0 = kubectl get pods -l app=btc-forecast,component=api -n $Ns `
            -o jsonpath='{.items[0].metadata.name}'
kubectl cp "$Repo\handoff\forecast.json" "${pod0}:/app/models/forecast.json" -n $Ns -c api
# Trigger reload on each pod
foreach ($pod in (kubectl get pods -l app=btc-forecast,component=api -n $Ns -o jsonpath='{.items[*].metadata.name}' ).Split(" ")) {
    kubectl exec $pod -n $Ns -c api -- python -c "import urllib.request,json; r=urllib.request.urlopen(urllib.request.Request('http://127.0.0.1:5000/reload',data=b'{}',headers={'Content-Type':'application/json'}),timeout=10); print(json.load(r))"
    Write-Host "Reloaded $pod"
}

# ─────────────────────────────────────────────────────────────────────────────
# 9. Add hosts entry (run as admin or do manually)
# ─────────────────────────────────────────────────────────────────────────────
$minikubeIP = minikube ip
Banner "Minikube IP: $minikubeIP"
Write-Host "Add this to C:\Windows\System32\drivers\etc\hosts (requires admin):"
Write-Host "  $minikubeIP  btc-forecast.local"

# ─────────────────────────────────────────────────────────────────────────────
# 10. EVIDENCE — save to evidence-output.txt
# ─────────────────────────────────────────────────────────────────────────────
Banner "Collecting evidence"
$out = "$Repo\evidence-output.txt"
"=== EVIDENCE: $(Get-Date -Format 'u') ===" | Tee-Object -FilePath $out

"`n--- Deployment ---" | Tee-Object -Append -FilePath $out
kubectl get deployment btc-forecast-api -n $Ns -o wide | Tee-Object -Append -FilePath $out

"`n--- Pods ---" | Tee-Object -Append -FilePath $out
kubectl get pods -l app=btc-forecast -n $Ns -o wide | Tee-Object -Append -FilePath $out

"`n--- Services ---" | Tee-Object -Append -FilePath $out
kubectl get svc -l app=btc-forecast -n $Ns | Tee-Object -Append -FilePath $out

"`n--- Ingress ---" | Tee-Object -Append -FilePath $out
kubectl get ingress btc-forecast-api -n $Ns | Tee-Object -Append -FilePath $out

"`n--- HPA ---" | Tee-Object -Append -FilePath $out
kubectl get hpa btc-forecast-api -n $Ns | Tee-Object -Append -FilePath $out

"`n--- PVC ---" | Tee-Object -Append -FilePath $out
kubectl get pvc model-store -n $Ns | Tee-Object -Append -FilePath $out

"`n--- Health check ---" | Tee-Object -Append -FilePath $out
Invoke-RestMethod "http://${minikubeIP}:${NodePort}/health" | ConvertTo-Json | Tee-Object -Append -FilePath $out

"`n--- 7-day Prediction ---" | Tee-Object -Append -FilePath $out
$body = '{"forecast_days":7}'
Invoke-RestMethod -Method Post -Uri "http://${minikubeIP}:${NodePort}/predict" `
    -ContentType "application/json" -Body $body | ConvertTo-Json -Depth 5 | Tee-Object -Append -FilePath $out

# ─────────────────────────────────────────────────────────────────────────────
# 11. Pod disruption test
# ─────────────────────────────────────────────────────────────────────────────
Banner "Pod disruption test"
$victim = kubectl get pods -l app=btc-forecast,component=api -n $Ns `
              -o jsonpath='{.items[0].metadata.name}'
"`n--- Deleting pod: $victim ---" | Tee-Object -Append -FilePath $out
kubectl delete pod $victim -n $Ns | Tee-Object -Append -FilePath $out

Write-Host "Watching pod recovery for 60 s..."
$watch = kubectl get pods -l app=btc-forecast -n $Ns -w --request-timeout=60s 2>&1
$watch | Tee-Object -Append -FilePath $out

"`n--- Final pod list after recovery ---" | Tee-Object -Append -FilePath $out
kubectl get pods -l app=btc-forecast -n $Ns -o wide | Tee-Object -Append -FilePath $out

Banner "Done! Evidence saved to evidence-output.txt"
Write-Host "NodePort URL : http://${minikubeIP}:${NodePort}"
Write-Host "Ingress URL  : http://btc-forecast.local (after hosts entry)"
