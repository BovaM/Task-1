#!/usr/bin/env bash
# Локальный аналог job deploy из .github/workflows/ci.yaml: те же шаги в том же порядке,
# kind load docker-image 

set -euo pipefail
trap 'rm -f health.json pred.json' EXIT

CLUSTER=${KIND_CLUSTER:-mlpro}
IMAGE=${IMAGE:-roi-service:local}
DB_PASSWORD=${DB_PASSWORD:-postgres}
U="http://roi.localhost"
H="Host: roi.localhost"
MLFLOW_URL="http://mlflow.localhost"

cd "$(dirname "$0")/.."

echo "== образ и kind"
kubectl config use-context "kind-$CLUSTER" >/dev/null
docker build -t "$IMAGE" .
kind load docker-image "$IMAGE" --name "$CLUSTER"

echo "== секреты"
kubectl create secret generic roi-service-secrets \
  --from-literal=POSTGRES_PASSWORD="$DB_PASSWORD" \
  --from-literal=DATABASE_URL="postgresql://postgres:$DB_PASSWORD@postgres:5432/roi_service" \
  --dry-run=client -o yaml | kubectl apply -f -

echo "== база"
kubectl apply -f k8s/postgres.yaml
kubectl rollout status deploy/postgres --timeout=180s

echo "== сервис"
kubectl apply -f k8s/
kubectl set image deploy/roi-service api="$IMAGE"
kubectl rollout status deploy/roi-service --timeout=180s

echo "== мониторинг и DAG"
kubectl apply -f k8s/monitoring/
kubectl -n mlops create configmap airflow-dags --from-file=dags/ \
  --dry-run=client -o yaml | kubectl apply -f -
kubectl -n mlops exec deploy/airflow -- airflow variables set roi_image "$IMAGE"

echo "== smoke"
curl --fail -s --retry 5 --retry-all-errors -H "$H" "$U/health" | tee health.json; echo
CHAMPION=$(curl --fail -s "$MLFLOW_URL/api/2.0/mlflow/registered-models/alias?name=roi&alias=champion" | jq -r .model_version.version)
echo "champion в реестре: $CHAMPION"
grep -Eq "\"model_version\":\"$CHAMPION\"" health.json

curl --fail -s -X POST -H "$H" "$U/v1/predict" -H "Content-Type: application/json" -d @good.json | tee pred.json; echo
jq -e '.score >= 0 and .score <= 1 and (.positive_roi == 0 or .positive_roi == 1)' pred.json >/dev/null

sleep 2

curl --fail -s -H "$H" "$U/metrics" | grep -q "^roi_model_info{version=\"$CHAMPION\""

RID=$(jq -r .request_id pred.json)
kubectl exec deploy/postgres -- psql -U postgres -d roi_service -tAc "SELECT count(*) FROM predictions WHERE request_id = '$RID'" | grep -qx 1

echo "Готово: сервис отвечает моделью $CHAMPION, строка $RID в базе, метрики в /metrics"
