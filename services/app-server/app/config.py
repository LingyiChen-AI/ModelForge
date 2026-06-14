from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    database_url: str = "postgresql+psycopg://modelforge:modelforge@localhost:5432/modelforge"
    redis_url: str = "redis://localhost:6379/0"
    s3_endpoint_url: str = "http://localhost:9000"
    s3_access_key: str = "minioadmin"
    s3_secret_key: str = "minioadmin"
    s3_bucket_datasets: str = "datasets"
    mlflow_tracking_uri: str = "http://localhost:5000"
    model_server_url: str = "http://localhost:8001"
    jwt_secret: str = "dev-secret-change-me"
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 720
    internal_token: str = "modelforge-internal"
    seed_admin_email: str = "admin@modelforge.local"
    seed_admin_password: str = "admin12345"

settings = Settings()
