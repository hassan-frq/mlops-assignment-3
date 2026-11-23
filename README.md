# MLOps Assignment 3

Hassan and Ahmad Waqar are building a service that forecasts the next seven daily BTC-USD closing prices. Airflow will fetch data, retrain and evaluate the model, and notify the Flask API when a new model is accepted. Kubernetes will host the API.

## Work split

| Owner | Responsibilities | First task |
| --- | --- | --- |
| Hassan | Data ingestion, feature engineering, training and evaluation, Airflow DAG, Kubeflow pipeline and compiled YAML, Docker Compose integration, and Locust load testing. | Fetch daily BTC-USD data and verify the dates and OHLCV columns. Then produce a seven-day forecast matching the sample format. |
| Ahmad Waqar | Flask endpoints and tests, model reload, Gunicorn, API Dockerfile, GitHub Actions, registry publishing, Kubernetes manifests, and pod-recovery demonstration. | Use the sample forecast to test that an empty JSON object sent to `POST /predict` returns seven dated closing prices. |
| Both | Connect training output to API storage, verify reload across replicas, run the end-to-end demonstration, and assemble the PDF report and submission links. | Compare a real training run with the live API response and confirm that the loaded model version matches. |

## Starter file

[tests/fixtures/forecast-example.json](tests/fixtures/forecast-example.json) contains synthetic example data. It records the model version, last training date, validation metrics, and seven dated closing prices in USD. Ahmad can use it for API tests while Hassan develops the training pipeline.

## Working together

### Load testing

The Locust scenario and Kubernetes evidence commands are in [load_tests/README.md](load_tests/README.md).


### Run the daily Airflow pipeline on Docker Desktop

From the repository root, use Docker with Linux containers and Compose v2. Check the storage location of your Docker engine before the first build. This setup uses Waqar's published API image and needs no local Python installation or drive-specific launcher.

On a fresh checkout, seed the API with the labeled example forecast so it can start before the first accepted training run. An existing forecast is preserved. The first accepted run replaces the example with real predictions.

```powershell
New-Item -ItemType Directory -Force models, data/airflow | Out-Null
if (!(Test-Path ./models/forecast.json)) {
    Copy-Item ./tests/fixtures/forecast-example.json ./models/forecast.json
}
```

```powershell
docker compose up --build -d
docker compose exec webserver airflow users create --username hassan --firstname Hassan --lastname Farooq --role Admin --email hassan@example.invalid
docker compose exec scheduler airflow dags unpause btc_etl_pipeline
docker compose exec scheduler airflow dags trigger btc_etl_pipeline
docker compose exec scheduler airflow dags list-runs -d btc_etl_pipeline
```

Create the local UI user once and enter a password when prompted. Open http://localhost:8080 and select the DAG's Graph view. It runs daily at 00:15 UTC. Each run fetches 365 completed candles, writes moving averages and volatility, evaluates AR(1) on the last seven days, and publishes only if it beats the last-close baseline. AR(1) uses the closing-price series. The engineered indicators are retained for analysis. Rejected candidates skip publication and reload. A successful reload must confirm the published version. Inspect dated files under `data/airflow` and compare the live version with the saved artifact.

```powershell
Invoke-RestMethod http://localhost:5000/health
(Get-Content .\models\forecast.json -Raw | ConvertFrom-Json).model_version
(Invoke-RestMethod http://localhost:5000/predict -Method Post -ContentType application/json -Body '{}').forecast
```

Use `docker compose stop` when finished.

### Run Hassan's data fetch

From the project folder in PowerShell, run the following command. The uv tool sets up Python and the script dependencies on first use.

```powershell
uv run --python 3.12 src/etl_fetch.py
```

The default fetch covers the last 365 completed UTC days. A successful run replaces `data/raw/btc_usd.csv` after checking date coverage, prices, and volume. The generated data stays local. To fetch a specific period, pass `--start YYYY-MM-DD --end YYYY-MM-DD`. The end date is exclusive.

```powershell
$prices = Import-Csv .\data\raw\btc_usd.csv
$prices.Count
$prices | Select-Object -Last 5 | Format-Table
```

### Share changes

Clone this repository once on each laptop. Start each task from an updated `main`, make changes on a separate branch, and push the branch to GitHub. Open a pull request so your teammate can review the changes before merging.
