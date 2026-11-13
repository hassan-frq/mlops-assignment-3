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
