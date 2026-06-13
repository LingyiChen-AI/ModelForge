"""Test-session configuration.

moto's ``mock_aws`` only intercepts boto3 calls that target the real AWS S3
endpoints. The application's default ``s3_endpoint_url`` is the MinIO address
``http://localhost:9000`` (see ``app/config.py``), which moto treats as a
pass-through and does not mock — boto3 then tries to reach the real host and
fails with a 502. For the duration of the test session we clear the endpoint
override so boto3 uses the default AWS endpoint that moto intercepts. Production
behaviour is unchanged.
"""
from app.config import settings

settings.s3_endpoint_url = None
