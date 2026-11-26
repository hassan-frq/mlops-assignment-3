"""Publish an accepted artifact to the shared PVC and verify each ready API pod."""

import argparse
import json
import subprocess
from pathlib import Path

from app.model_store import _ModelStore


def publish(path, context, namespace):
    artifact = json.loads(path.read_text(encoding="utf-8"))
    _ModelStore().load(path)
    if artifact.get("validation", {}).get("accepted") is not True:
        raise ValueError("Only an accepted candidate can be published.")
    command = ["kubectl", "--context", context, "--namespace", namespace]
    result = subprocess.run(
        command + ["get", "pods", "-l", "app=btc-forecast,component=api", "-o", "json"],
        check=True, capture_output=True, text=True,
    )
    pods = [
        pod["metadata"]["name"]
        for pod in json.loads(result.stdout)["items"]
        if not pod["metadata"].get("deletionTimestamp")
        and any(
            item["type"] == "Ready" and item["status"] == "True"
            for item in pod.get("status", {}).get("conditions", [])
        )
    ]
    if not pods:
        raise RuntimeError("No ready API pods found.")
    # Write a temporary file on the PVC, then replace the live file atomically.
    writer = """
import json, os, pathlib, sys, tempfile
artifact = json.load(sys.stdin)
target = pathlib.Path(os.environ["MODEL_ARTIFACT_PATH"])
if target.exists():
    current = json.loads(target.read_text())
    if current["trained_through"] > artifact["trained_through"]:
        raise ValueError("A newer artifact is already deployed")
with tempfile.NamedTemporaryFile(dir=target.parent, mode="w", delete=False) as f:
    json.dump(artifact, f)
    staging = pathlib.Path(f.name)
try:
    if staging.stat().st_mode & 0o444 != 0o444:
        staging.chmod(0o644)
    staging.replace(target)
finally:
    staging.unlink(missing_ok=True)
"""
    subprocess.run(
        command + ["exec", "-i", pods[0], "-c", "api", "--", "python", "-c", writer],
        input=json.dumps(artifact), text=True, check=True,
    )
    verifier = """
import json, sys, urllib.request
expected = json.load(sys.stdin)
base = "http://127.0.0.1:5000"
for route in ("/reload", "/predict"):
    request = urllib.request.Request(
        base + route, data=b"{}", headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(request, timeout=15) as response:
        actual = json.load(response)
    assert actual["model_version"] == expected["model_version"], actual
    if route == "/predict":
        assert actual["forecast"] == expected["forecast"], actual
print(expected["model_version"], "verified")
"""
    for pod in pods:
        subprocess.run(
            command + ["exec", "-i", pod, "-c", "api", "--", "python", "-c", verifier],
            input=json.dumps(artifact), text=True, check=True,
        )
        print(f"Verified {pod}", flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("artifact", type=Path)
    parser.add_argument("--context", required=True)
    parser.add_argument("--namespace", default="default")
    args = parser.parse_args()
    publish(args.artifact, args.context, args.namespace)
