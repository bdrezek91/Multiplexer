"""Przechowywanie plikow (Etap 7) - interfejs + implementacja S3-kompatybilna (boto3).

boto3 rozmawia z kazdym S3-kompatybilnym storage (MinIO w docker-compose.yml, prawdziwy AWS S3,
Azure Blob przez S3 gateway) bez zmian kodu - jedyna roznica to `endpoint_url` w konfiguracji
(patrz app/core/config.py, zgodnie z CLAUDE.md: "mozliwosc zamiany na Azure Blob / AWS S3").
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Optional

import boto3
from botocore.exceptions import ClientError

from app.core.config import settings


class FileStorage(ABC):
    @abstractmethod
    def upload(self, key: str, data: bytes, content_type: str) -> None: ...

    @abstractmethod
    def download(self, key: str) -> bytes: ...

    @abstractmethod
    def delete(self, key: str) -> None: ...


class S3FileStorage(FileStorage):
    def __init__(self, endpoint_url: Optional[str], access_key: str, secret_key: str, bucket: str):
        """`endpoint_url=None` uzywa domyslnej rezolucji AWS - potrzebne w testach (moto
        przechwytuje ruch tylko do rozpoznawanych endpointow AWS, nie do dowolnego custom URL)."""
        self._bucket = bucket
        self._client = boto3.client(
            "s3",
            endpoint_url=endpoint_url,
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key,
            region_name="us-east-1",
        )
        self._ensure_bucket()

    def _ensure_bucket(self) -> None:
        try:
            self._client.head_bucket(Bucket=self._bucket)
        except ClientError:
            self._client.create_bucket(Bucket=self._bucket)

    def upload(self, key: str, data: bytes, content_type: str) -> None:
        self._client.put_object(Bucket=self._bucket, Key=key, Body=data, ContentType=content_type)

    def download(self, key: str) -> bytes:
        obj = self._client.get_object(Bucket=self._bucket, Key=key)
        return obj["Body"].read()

    def delete(self, key: str) -> None:
        self._client.delete_object(Bucket=self._bucket, Key=key)


def get_storage() -> FileStorage:
    """Bez cache'owania w pamieci procesu - ta sama zasada co Catalog.from_db()/get_db() od
    Etapu 4 (swiezy stan zamiast globalnego singletona), i pozwala testom uzyc moto (mock_aws)
    bez ryzyka, ze zostanie zwrocony wczesniej skonstruowany, prawdziwy klient."""
    return S3FileStorage(
        endpoint_url=settings.minio_endpoint_url,
        access_key=settings.minio_access_key,
        secret_key=settings.minio_secret_key,
        bucket=settings.minio_bucket,
    )
