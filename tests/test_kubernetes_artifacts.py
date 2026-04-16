from pathlib import Path

import yaml


def _load_yaml(path: str) -> dict:
    return yaml.safe_load(Path(path).read_text())


def test_kubernetes_kustomization_references_runtime_resources() -> None:
    doc = _load_yaml("deploy/kubernetes/kustomization.yaml")
    resources = set(doc["resources"])
    assert "migrate-job.yaml" not in resources
    expected = {
        "namespace.yaml",
        "serviceaccount.yaml",
        "configmap.yaml",
        "secret.yaml",
        "api-service.yaml",
        "api-deployment.yaml",
        "worker-jobs-service.yaml",
        "worker-jobs-deployment.yaml",
        "worker-outbox-service.yaml",
        "worker-outbox-deployment.yaml",
        "api-pdb.yaml",
        "api-hpa.yaml",
    }
    assert expected.issubset(resources)



def test_api_deployment_has_probes_and_file_backed_secrets() -> None:
    doc = _load_yaml("deploy/kubernetes/api-deployment.yaml")
    container = doc["spec"]["template"]["spec"]["containers"][0]
    env_from = container["envFrom"]
    assert {entry[next(iter(entry))]["name"] for entry in env_from} == {"acp-config"}
    env = {entry["name"]: entry for entry in container["env"]}
    assert env["DATABASE_URL_FILE"]["value"] == "/var/run/acp-secrets/DATABASE_URL"
    assert env["MANAGEMENT_API_KEYS_JSON_FILE"]["value"] == "/var/run/acp-secrets/MANAGEMENT_API_KEYS_JSON"
    assert env["MANAGEMENT_PROBE_KEY"]["valueFrom"]["secretKeyRef"]["name"] == "acp-secrets"
    assert container["volumeMounts"][0]["mountPath"] == "/var/run/acp-secrets"
    readiness = container["readinessProbe"]["exec"]["command"]
    startup = container["startupProbe"]["exec"]["command"]
    assert any("MANAGEMENT_PROBE_KEY" in part for part in readiness)
    assert any("/readyz" in part for part in readiness)
    assert any("MANAGEMENT_PROBE_KEY" in part for part in startup)
    assert container["livenessProbe"]["httpGet"]["path"] == "/healthz"
    assert doc["spec"]["template"]["spec"]["volumes"][0]["secret"]["secretName"] == "acp-secrets"



def test_worker_deployments_expose_metrics_ports() -> None:
    jobs_doc = _load_yaml("deploy/kubernetes/worker-jobs-deployment.yaml")
    outbox_doc = _load_yaml("deploy/kubernetes/worker-outbox-deployment.yaml")
    jobs = jobs_doc["spec"]["template"]["spec"]["containers"][0]
    outbox = outbox_doc["spec"]["template"]["spec"]["containers"][0]
    assert jobs["ports"][0]["containerPort"] == 9101
    assert outbox["ports"][0]["containerPort"] == 9102
    assert jobs["readinessProbe"]["httpGet"]["path"] == "/readyz"
    assert outbox["livenessProbe"]["httpGet"]["path"] == "/healthz"
    assert jobs["env"][0]["name"] == "DATABASE_URL_FILE"
    assert outbox["volumeMounts"][0]["readOnly"] is True



def test_migration_job_is_a_separate_apply_step() -> None:
    doc = _load_yaml("deploy/kubernetes/migrate-job.yaml")
    container = doc["spec"]["template"]["spec"]["containers"][0]
    assert doc["kind"] == "Job"
    assert container["command"] == ["alembic", "upgrade", "head"]
    readme = Path("deploy/kubernetes/README.md").read_text()
    assert "migration job is intentionally **not** part of `kustomization.yaml`" in readme
    assert "kubectl wait --for=condition=complete job/acp-migrate" in readme


def test_external_secret_example_and_secret_readme_exist() -> None:
    external_secret = Path("deploy/kubernetes/external-secret.example.yaml").read_text()
    kube_readme = Path("deploy/kubernetes/README.md").read_text()
    secret_doc = Path("docs/SECRET_MANAGEMENT.md").read_text()

    assert "kind: ExternalSecret" in external_secret
    assert "*_FILE" in kube_readme
    assert "SECRETS_DIR" in secret_doc



def test_phase4_helm_chart_and_overlays_exist() -> None:
    chart = Path("deploy/helm/architecture-control-plane/Chart.yaml").read_text()
    values = Path("deploy/helm/architecture-control-plane/values.yaml").read_text()
    staging = Path("deploy/kubernetes/overlays/staging/kustomization.yaml").read_text()
    production = Path("deploy/kubernetes/overlays/production/kustomization.yaml").read_text()
    smoke = Path("scripts/k8s_runtime_smoke.sh").read_text()

    assert 'name: architecture-control-plane' in chart
    assert 'persistentEnabled: false' in values
    assert 'REMOTE_WORKSPACE_PERSISTENT_ENABLED' in staging
    assert 'REMOTE_WORKSPACE_PERSISTENT_ENABLED' in production
    assert 'persistent workspace track remains opt-in by default' in smoke
