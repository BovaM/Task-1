"""Переобучение модели ROI.

validate  dvc pull из S3 кластера, проверка схемой pandera (красный, если данные плохие)
train     dvc pull, обучение, регистрация и гейт в MLflow
promoted  идём дальше, только если гейт отдал новой версии алиас champion
rollout   перезапуск roi-service: новые поды загрузят нового champion из реестра

Образ берётся из переменной roi_image, её выставляет CI при каждом деплое.
"""
from datetime import UTC, datetime

from airflow.providers.cncf.kubernetes.operators.pod import KubernetesPodOperator
from airflow.sdk import CronTriggerTimetable, Param, dag, task
from kubernetes import client, config
from kubernetes.client import models as k8s

PULL = "uv run --no-sync dvc pull -r cluster data/college_major_roi.csv"
ENV = {"MLFLOW_TRACKING_URI": "http://mlflow.mlops:5000"}
S3 = [k8s.V1EnvFromSource(secret_ref=k8s.V1SecretEnvSource(name="s3-credentials"))]


@dag(
    schedule=CronTriggerTimetable("0 3 * * *", timezone="Europe/Moscow"),
    catchup=False,
    params={
        "C": Param(1.0, type="number", exclusiveMinimum=0, description="регуляризация LogisticRegression"),
        "gate_min_gain": Param(0.005, type="number", exclusiveMinimum=0,
                               description="минимальный прирост PR-AUC для смены champion (шум метрики ~0.0004, 3σ=0.0012)"),
    },
    tags=["roi"],
)
def roi_retrain():
    validate = KubernetesPodOperator(
        task_id="validate", name="roi-validate", namespace="mlops", in_cluster=True,
        image="{{ var.value.roi_image }}", image_pull_policy="IfNotPresent",
        cmds=["sh", "-c", f"{PULL} && uv run --no-sync python -m roi_service.data_check"],
        env_vars=ENV, env_from=S3, get_logs=True, on_finish_action="delete_pod",
    )
    train = KubernetesPodOperator(
        task_id="train", name="roi-train", namespace="mlops", in_cluster=True,
        image="{{ var.value.roi_image }}", image_pull_policy="IfNotPresent",
        cmds=["sh", "-c", f"{PULL} && uv run --no-sync python -m roi_service.train"],
        env_vars={**ENV, "C": "{{ params.C }}", "GATE_MIN_GAIN": "{{ params.gate_min_gain }}"}, env_from=S3,
        do_xcom_push=True, get_logs=True, on_finish_action="delete_pod",
    )

    @task.short_circuit
    def promoted(result: dict) -> bool:
        print(f"версия {result['version']}, pr_auc {result['pr_auc']}, champion до этого {result['champion_before']}")
        return result["promoted"]

    @task
    def rollout():

        config.load_incluster_config()
        now = datetime.now(UTC).isoformat()
        client.AppsV1Api().patch_namespaced_deployment(
            "roi-service", "default",
            {"spec": {"template": {"metadata": {"annotations": {"kubectl.kubernetes.io/restartedAt": now}}}}},
        )
        print("roi-service перезапущен", now)

    validate >> train
    promoted(train.output) >> rollout()


roi_retrain()
