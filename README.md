В качестве датасета я использовал один из датасетов с кэггл - нужно проследить закономерность между местом учебы и тем насколько полученный диплом позволяет потом оплатить обучение в этом месте [датасет вот](https://www.kaggle.com/datasets/sergionefedov/college-major-roi)

Для выполнения данного задания я использовал uv, FastAPI, scikit-learn, Postgres, Docker, Kubernetes (kind) 

## Тесты

### Базовые случаи
```powershell
uv sync
uv run pytest
```

### Поднятие докера
```powershell
docker compose up -d --build
curl.exe -X POST localhost:8000/v1/predict -H "Content-Type: application/json" -d "@good.json"
curl.exe -i -X POST localhost:8000/v1/predict -H "Content-Type: application/json" -d '{"foo": 1}'
docker compose exec db psql -U postgres -d roi-service -c "SELECT request_id, score, latency_ms, status_code FROM predictions;"
```

### Кластеры и кубернетис
```powershell
kind create cluster --name mlpro
kind load docker-image roi-service:1.0 --name mlpro
kubectl apply -f k8s/
kubectl rollout status deploy/postgres
kubectl rollout status deploy/roi-service
kubectl port-forward svc/roi-service 8080:80
```

После запуска
```powershell
curl.exe -X POST localhost:8080/v1/predict -H "Content-Type: application/json" -d "@good.json"
kubectl exec -it deploy/postgres -- psql -U postgres -d roi-service -c "SELECT request_id, score, status_code FROM predictions;"
```




