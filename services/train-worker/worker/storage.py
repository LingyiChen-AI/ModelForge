import io, boto3, pandas as pd
from worker.config import settings

def _client():
    return boto3.client("s3", endpoint_url=settings.s3_endpoint_url,
                        aws_access_key_id=settings.s3_access_key,
                        aws_secret_access_key=settings.s3_secret_key,
                        region_name="us-east-1")

def read_snapshot(uri: str) -> pd.DataFrame:
    _, _, rest = uri.partition("s3://")
    bucket, _, key = rest.partition("/")
    obj = _client().get_object(Bucket=bucket, Key=key)
    return pd.read_parquet(io.BytesIO(obj["Body"].read()))
