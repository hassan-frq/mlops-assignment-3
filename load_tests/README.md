# Prediction load test

Run from the repository root using a Python environment on your chosen drive.

```powershell
python -m pip install -r load_tests/requirements.txt
New-Item -ItemType Directory -Force load_tests/results | Out-Null
python -m locust -f load_tests/locustfile.py --host http://btc-forecast.local
```

Open http://localhost:8089. Start with 10 users and a spawn rate of 2 users per second. Check failures, then increase the user count gradually while watching CPU and HPA decisions. The test posts an empty JSON object to /predict and validates every returned seven-day forecast. Each simulated user waits 50–150 ms between requests.

For a repeatable ten-minute run, use the following command. Choose a new output prefix for each run so evidence is preserved.

```powershell
python -m locust -f load_tests/locustfile.py --host http://btc-forecast.local --headless -u 200 -r 10 -t 10m --csv load_tests/results/k8s-run1 --csv-full-history --html load_tests/results/k8s-run1.html --exit-code-on-error 1
```

Use the reachable ingress or NodePort address for your own cluster. A port-forward to a pod would exercise a single replica and cannot verify traffic distribution across the service.

In separate terminals, using the namespace where the deployment is running, capture the observations.

```powershell
kubectl get hpa btc-forecast-api --watch | Tee-Object load_tests/results/hpa-watch.txt
kubectl get pods -l app=btc-forecast --watch | Tee-Object load_tests/results/pods-watch.txt
```

Before, during and after the traffic, inspect these commands and save screenshots with timestamps.

```powershell
kubectl top pods -l app=btc-forecast
kubectl describe hpa btc-forecast-api
kubectl get deployment btc-forecast-api
```

Confirm that HPA CPU metrics are available before increasing load. The starting 200 users is a test setting, not a guarantee of scaling. This API serves cached JSON cheaply. Increase traffic gradually if CPU remains below 60%, and check whether the load generator is saturated. Record the actual observations. After load stops, keep watching through the HPA stabilization period to capture scale-down.

Save the HTML report, CSV history, screenshots of Locust charts, and HPA/pod observations for the assignment report. The local smoke test verifies the load script against the Flask API. Kubernetes autoscaling evidence must come from the cluster run.
