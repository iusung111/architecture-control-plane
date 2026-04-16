#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
CHART_DIR="$ROOT_DIR/deploy/helm/architecture-control-plane"
OVERLAY_DIR="$ROOT_DIR/deploy/kubernetes/overlays/staging"

echo "[smoke] verify helm chart files"
test -f "$CHART_DIR/Chart.yaml"
test -f "$CHART_DIR/values.yaml"

echo "[smoke] verify staging overlay"
test -f "$OVERLAY_DIR/kustomization.yaml"

echo "[smoke] persistent workspace track remains opt-in by default"
grep -q 'persistentEnabled: false' "$CHART_DIR/values.yaml"

echo "[smoke] done"
