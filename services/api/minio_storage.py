"""
LocalStorage Adapter & Bridge:
Replaces MinIO S3 object store with local filesystem storage.
Ensures 100% backward compatibility for all modules that import minio_storage,
storing all files under the codebase 'storage/' directory with zero MinIO requirement.
"""

from local_storage import LocalStorage, local_storage, STORAGE_DIR

# Backward compatible aliases
MinioStorage = LocalStorage
minio_storage = local_storage
MINIO_BUCKET_NAME = "local-storage"

__all__ = ["LocalStorage", "local_storage", "MinioStorage", "minio_storage", "STORAGE_DIR", "MINIO_BUCKET_NAME"]
