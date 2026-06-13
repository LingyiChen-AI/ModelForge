import hashlib, io
import boto3, pandas as pd

class SnapshotStorage:
    def __init__(self, endpoint_url, access_key, secret_key, bucket):
        self.bucket = bucket
        self.s3 = boto3.client(
            "s3", endpoint_url=endpoint_url,
            aws_access_key_id=access_key, aws_secret_access_key=secret_key,
            region_name="us-east-1")

    def write_snapshot(self, dataset_id: int, version_no: int, df: pd.DataFrame):
        buf = io.BytesIO()
        df.to_parquet(buf, index=False)
        data = buf.getvalue()
        checksum = hashlib.sha256(data).hexdigest()
        key = f"dataset={dataset_id}/v{version_no}/data.parquet"
        self.s3.put_object(Bucket=self.bucket, Key=key, Body=data)
        return f"s3://{self.bucket}/{key}", checksum, len(df)

    def read_snapshot(self, uri: str) -> pd.DataFrame:
        key = uri.split(f"s3://{self.bucket}/", 1)[1]
        obj = self.s3.get_object(Bucket=self.bucket, Key=key)
        return pd.read_parquet(io.BytesIO(obj["Body"].read()))

def build_storage() -> "SnapshotStorage":
    from app.config import settings
    return SnapshotStorage(settings.s3_endpoint_url, settings.s3_access_key,
                           settings.s3_secret_key, settings.s3_bucket_datasets)
