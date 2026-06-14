from pydantic_settings import BaseSettings, SettingsConfigDict
class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    mlflow_tracking_uri: str = "http://localhost:5000"
    s3_endpoint_url: str = "http://localhost:9000"
    s3_access_key: str = "minioadmin"
    s3_secret_key: str = "minioadmin"
    database_url: str = "postgresql+psycopg://modelforge:modelforge@localhost:5432/modelforge"
settings = Settings()
