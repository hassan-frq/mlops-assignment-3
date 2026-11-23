"""Compile portable container components with the repository source embedded."""

import argparse
from pathlib import Path

from kfp import compiler, dsl

ROOT = Path(__file__).resolve().parents[1]
IMAGE = "python:3.11-slim"


def source(name):
    return (ROOT / "src" / name).read_text(encoding="utf-8")


def container(code, args, packages=()):
    # Source is compiled into YAML so pods need no repository checkout or PVC.
    return dsl.ContainerSpec(
        image=IMAGE,
        command=["sh", "-ec"],
        args=[
            'if [ -n "$1" ]; then pip install --no-cache-dir $1; fi; '
            'shift; exec python -c "$@"',
            "--",
            " ".join(packages),
            code,
            *args,
        ],
    )


@dsl.container_component
def ingest(start_date: str, end_date: str, raw: dsl.Output[dsl.Dataset]):
    code = source("etl_fetch.py").split('if __name__ == "__main__":')[0]
    code += """
import sys
fetch(date.fromisoformat(sys.argv[1]), date.fromisoformat(sys.argv[2]), Path(sys.argv[3]))
"""
    return container(code, [start_date, end_date, raw.path], ("yfinance==1.8.0",))


@dsl.container_component
def features(raw: dsl.Input[dsl.Dataset], processed: dsl.Output[dsl.Dataset]):
    code = source("features.py") + """
import sys
prepare_features(sys.argv[1], sys.argv[2])
"""
    return container(code, [raw.path, processed.path], ("pandas==2.3.3",))


@dsl.container_component
def train(
    processed: dsl.Input[dsl.Dataset],
    model: dsl.Output[dsl.Model],
    metrics: dsl.Output[dsl.Metrics],
):
    code = source("train_forecast.py").split('if __name__ == "__main__":')[0]
    code += """
import sys
artifact = train(Path(sys.argv[1]), Path(sys.argv[2]))
# KFP executor metadata makes these values visible in the pipeline UI.
metadata = dict(artifact["metrics"])
metadata.update(artifact["validation"])
result = {"artifacts": {
    "metrics": {"artifacts": [{"metadata": metadata}]},
    "model": {"artifacts": [{"metadata": {
        "model_version": artifact["model_version"],
        "accepted": artifact["validation"]["accepted"]
    }}]}
}}
path = Path(sys.argv[3])
path.parent.mkdir(parents=True, exist_ok=True)
path.write_text(json.dumps(result), encoding="utf-8")
"""
    return container(
        code, [processed.path, model.path, dsl.PIPELINE_TASK_EXECUTOR_OUTPUT_PATH_PLACEHOLDER]
    )


@dsl.pipeline(name="btc-seven-day-forecast")
def btc_pipeline(start_date: str, end_date: str):
    """Dates are UTC. End is exclusive. Outputs retain rejected candidates too."""
    fetched = ingest(start_date=start_date, end_date=end_date)
    fetched.set_caching_options(False)
    engineered = features(raw=fetched.outputs["raw"])
    train(processed=engineered.outputs["processed"])


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output", default=str(Path(__file__).with_suffix(".yaml"))
    )
    args = parser.parse_args()
    compiler.Compiler().compile(btc_pipeline, args.output)
