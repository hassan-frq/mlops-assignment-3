# Airflow and Kubernetes integration status

The Compose DAG fetches BTC data, prepares trailing features, fits AR(1), evaluates seven held-out days, publishes accepted artifacts to its shared model directory, and calls the Compose API reload endpoint.

Minikube uses a separate PVC. On the machine with cluster access, publish an accepted artifact manually with:

python -m scripts.publish_k8s models/forecast.json --context minikube

The publisher atomically writes the PVC, calls reload, and verifies versions and predictions on ready API pods. It requires kubectl credentials and an accepted artifact.

Fully automatic transfer requires an Airflow worker mounting the same PVC or invoking an authenticated transfer step before reload. Neither arrangement is configured by the default Compose file. Changing API_RELOAD_URL alone does not transfer files.

Verify the remaining integration by capturing a DAG run that publishes a newly accepted model to the PVC and matching responses from the Kubernetes service and each ready pod. Preserve real logs and timestamps.
