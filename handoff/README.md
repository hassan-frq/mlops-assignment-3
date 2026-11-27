# Trained model handoff

The accepted `forecast.json` is an integration artifact trained through November 12, 2026. Its seven forecasts cover November 13–19. Use it to demonstrate replacing the sample fixture and verifying the API integration. Its dates are historical.

The fresh candidate trained through November 25 failed the acceptance gate. Its validation MAE was 3038.61 USD versus the last-close baseline's 2516.73 USD. The candidate is retained in `candidate.json` as report evidence and must not replace the accepted artifact.

On Waqar's machine, from the repository root with Python dependencies installed and the existing Minikube deployment running, run:

```powershell
python -m scripts.publish_k8s handoff/forecast.json --context minikube
```

The script selects ready API pods, writes to the shared PVC atomically, calls each pod's reload endpoint and verifies its version and all seven predictions. It refuses a rejected candidate or a replacement older than the live model. If any verification fails, it exits with an error and can be rerun after the cause is fixed. Run one publisher at a time, with Airflow publication paused during this manual handoff.

Capture the output and query the externally exposed API to complete the cluster evidence. Then delete a pod and confirm its replacement loads the same version from persistent storage.

The script is a manual artifact handoff. Airflow still publishes to its Compose model directory. The automated Airflow-to-Minikube storage transfer and reload connection must be verified on Waqar's machine before claiming the final Kubernetes pipeline works end to end.
