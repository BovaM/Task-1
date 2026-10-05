from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    model_path: str = "artifacts/model.joblib"
    model_name: str | None = None
    model_alias: str = "champion"
    mlflow_tracking_uri: str = "http://mlflow.localhost"
    database_url: str | None = None
    log_level: str = "INFO"

    model_config = {"env_file": ".env", "protected_namespaces": ()}

settings = Settings()