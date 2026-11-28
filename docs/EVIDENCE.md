# Submission evidence inventory

The final report distinguishes measured results, earlier local validation, and unverified integration.

- GitHub Actions run 46037314740 succeeded on main. Original logs are in the submission evidence archive.
- A fresh local run passed 45 tests. Recompilation matched the checked-in Kubeflow YAML.
- Scheduled and manual Airflow runs passed all five tasks in Hassan's Compose setup on November 14. The external runtime was disconnected during final assembly.
- Original Kubernetes screenshots came from a3.zip, raw results from a3 results.zip, and the HPA chart was supplied separately.
- The smoke CSV records 18,706 requests and zero failures. The longer run records 32,300 requests and 96 failures.
- HPA logs show 2 to 8 replicas and a return to 2.
- Original API screenshots show example-001. The repository reports a later trained-model handoff and 16-second recovery, but original captures for those later claims were not verified.
- Generated screenshots in docs/screenshots are excluded from the final report and evidence package.
- The accepted artifact was trained through November 12. The November 25 candidate failed the acceptance gate.
- Kubeflow compilation and local component commands passed. Cluster execution remains unverified.
- The manual Kubernetes publisher is available. Automatic transfer from the Compose model directory into the Minikube PVC remains pending.
