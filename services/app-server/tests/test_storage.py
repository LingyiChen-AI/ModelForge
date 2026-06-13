import io, pandas as pd
import boto3, pytest
from moto import mock_aws
from app.storage import SnapshotStorage

@mock_aws
def test_write_and_read_snapshot_roundtrip():
    boto3.client("s3", region_name="us-east-1").create_bucket(Bucket="datasets")
    store = SnapshotStorage(endpoint_url=None, access_key="x", secret_key="y",
                            bucket="datasets")
    df = pd.DataFrame({"text": ["a", "b"], "label": ["x", "y"]})
    uri, checksum, rows = store.write_snapshot(dataset_id=1, version_no=1, df=df)
    assert uri.startswith("s3://datasets/dataset=1/v1/")
    assert rows == 2 and len(checksum) == 64
    back = store.read_snapshot(uri)
    assert back.equals(df)
