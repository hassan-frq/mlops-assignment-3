"""Validate compiled artifact wiring and execute embedded code on fixed data."""

import json
import subprocess
import sys
from datetime import date, timedelta

import yaml
from kfp import compiler

from kubeflow.btc_kfp_pipeline import btc_pipeline


def test_compiled_pipeline_executes_shared_feature_and_training_code(tmp_path):
    spec = tmp_path / "pipeline.yaml"
    compiler.Compiler().compile(btc_pipeline, str(spec))
    pipeline = yaml.safe_load(spec.read_text())
    tasks = pipeline["root"]["dag"]["tasks"]
    assert set(tasks) == {"ingest", "features", "train"}
    assert tasks["features"]["dependentTasks"] == ["ingest"]
    assert tasks["train"]["dependentTasks"] == ["features"]
    assert not tasks["ingest"].get("cachingOptions", {}).get("enableCache", False)

    raw = tmp_path / "raw.csv"
    rows = ["Date,Open,High,Low,Close,Volume"]
    for index in range(60):
        day = date(2026, 1, 1) + timedelta(days=index)
        price = 100 + index
        rows.append(f"{day},{price},{price},{price},{price},1000")
    raw.write_text("\n".join(rows))
    features = tmp_path / "features.csv"
    model = tmp_path / "model.json"
    metadata = tmp_path / "executor.json"
    executors = pipeline["deploymentSpec"]["executors"]
    for component, arguments in [
        ("features", [raw, features]),
        ("train", [features, model, metadata]),
    ]:
        command = executors[f"exec-{component}"]["container"]["args"]
        subprocess.run(
            [sys.executable, "-c", command[3], *map(str, arguments)], check=True
        )
    artifact = json.loads(model.read_text())
    assert len(artifact["forecast"]) == 7
    assert artifact["forecast"][0]["date"] == "2026-03-02"
    assert artifact["validation"]["accepted"]
    assert artifact["metrics"]["mae"] == 0
    recorded = json.loads(metadata.read_text())["artifacts"]
    assert recorded["model"]["artifacts"][0]["metadata"]["model_version"] == (
        artifact["model_version"]
    )
    assert recorded["metrics"]["artifacts"][0]["metadata"]["mae"] == 0
