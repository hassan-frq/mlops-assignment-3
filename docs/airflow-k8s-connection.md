# Airflow → Kubernetes Automatic Model Update

## Architecture Overview

```
┌──────────────────────────────────────────────────────────┐
│  Docker Compose (Airflow stack)                          │
│                                                          │
│  btc_etl_pipeline DAG (runs at 00:15 UTC daily)         │
│    fetch_daily_data → prepare_features →                 │
│    train_and_evaluate → publish_accepted → reload_api    │
│                                                          │
│  publish_accepted writes candidate.json to:             │
│    /app/models/forecast.json  (shared volume)            │
└──────────────────┬───────────────────────────────────────┘
                   │  Shared PVC (ReadWriteMany)
                   │  — OR — scripts/publish_k8s.py
                   ▼
┌──────────────────────────────────────────────────────────┐
│  Kubernetes (Minikube / Kind)                            │
│                                                          │
│  PVC: model-store (ReadWriteOnce / RWX)                  │
│    mountPath: /app/models                                │
│                                                          │
│  Deployment: btc-forecast-api (3 replicas)              │
│    app.before_request → store.refresh()                  │
│      └─ detects mtime change on /app/models/forecast.json│
│      └─ reloads in-memory model (zero restart needed)    │
└──────────────────────────────────────────────────────────┘
```

## How Auto-Reload Works (No Restart Required)

Every API request triggers `store.refresh()` (see `app/app.py:36`).
`ModelStore.refresh()` checks the file's `mtime`; if it changed since last
load, it reloads the JSON in-place. This means dropping a new `forecast.json`
on the shared PVC is enough — all replicas pick it up within one request.

## Integration Modes

### Mode A — Shared PVC (production / Kind with NFS or RWX storage class)

Both the Airflow worker container **and** the API pods mount the **same**
Kubernetes PVC (ReadWriteMany):

```yaml
# In Airflow's Helm values / pod template:
volumes:
  - name: model-store
    persistentVolumeClaim:
      claimName: model-store   # same PVC as the API deployment

volumeMounts:
  - name: model-store
    mountPath: /app/models
```

Airflow's `publish_accepted` task writes directly to `/app/models/forecast.json`.
The API pods detect the mtime change on the next request — **fully automatic**.

> **Minikube limitation:** Minikube uses a `standard` storage class with
> `ReadWriteOnce`, meaning only one node can mount the PVC at a time. Airflow
> (in Docker Compose) runs outside Kubernetes and cannot mount a Minikube PVC
> directly. Use Mode B on Minikube.

### Mode B — `scripts/publish_k8s.py` (Minikube / local dev handoff)

Run from the host after Airflow training completes:

```powershell
# From the repo root (PowerShell)
python -m scripts.publish_k8s handoff\forecast.json --context minikube --namespace default
```

The script:
1. Validates `validation.accepted == true` in the artifact.
2. Finds all Ready API pods via `kubectl get pods`.
3. Writes the JSON atomically to `/app/models/forecast.json` inside the first
   pod's container (via `kubectl exec`).
4. Calls `/reload` on every pod to confirm the new `model_version`.
5. Calls `/predict` on every pod and asserts the forecast matches.

### Mode C — `reload_api` Airflow task (HTTP trigger)

The DAG's final task hits `$API_RELOAD_URL` (set in Airflow's env/connections):

```python
# dags/btc_etl_pipeline.py:66
request = Request(
    os.environ["API_RELOAD_URL"], data=b"{}",
    headers={"Content-Type": "application/json"}, method="POST",
)
```

Set `API_RELOAD_URL=http://<NodePort-IP>:30080/reload` or
`http://btc-forecast.local/reload` (via Ingress) in Airflow's environment.

> When Mode A is used, the file is already written and `reload_api` forces an
> immediate hot-swap rather than waiting for the next API request.

## End-to-End Flow (Full Integration)

```
00:15 UTC  Airflow DAG wakes up
  ↓ fetch_daily_data        — downloads yesterday's BTC OHLCV
  ↓ prepare_features        — MA-7, MA-30, volatility-7
  ↓ train_and_evaluate      — LGBM regression, MAE vs last-close baseline
  ↓ publish_accepted        — writes /app/models/forecast.json (Mode A)
  ↓ reload_api              — POST /reload → API confirms new model_version
  ↓                           All replicas pick up new model on next request
```

## Configuration

| Variable | Where set | Default | Purpose |
|---|---|---|---|
| `MODEL_ARTIFACT_PATH` | ConfigMap | `/app/models/forecast.json` | Path the API reads and reload uses |
| `API_RELOAD_URL` | Airflow env | — | URL the DAG's reload_api task calls |
| `DEFAULT_FORECAST_DAYS` | ConfigMap | `7` | Fallback when `forecast_days` not in POST body |

## Verification Checklist

- [ ] `kubectl get pvc model-store` → Bound
- [ ] `kubectl exec <pod> -- ls /app/models/forecast.json` → file present
- [ ] `curl -X POST http://<ip>:30080/reload -H 'Content-Type: application/json' -d '{}'` → `{"status":"reloaded","model_version":"..."}`
- [ ] `curl -X POST http://<ip>:30080/predict -H 'Content-Type: application/json' -d '{"forecast_days":7}'` → 7 forecast entries
- [ ] Delete a pod → `kubectl get pods -w` → replacement reaches Running within ~30 s
- [ ] `kubectl get hpa btc-forecast-api` → MINPODS=2, MAXPODS=8, TARGET=60%
