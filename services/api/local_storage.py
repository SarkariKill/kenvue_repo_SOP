import io
import logging
import mimetypes
import os
import shutil
from typing import List, Optional, Tuple

logger = logging.getLogger(__name__)

# Determine project storage directory
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
# Fallback to 2 directories up if running from services/api, or current working dir if at root
if os.path.exists(os.path.join(os.getcwd(), "services")):
    PROJECT_ROOT = os.getcwd()
else:
    PROJECT_ROOT = os.path.abspath(os.path.join(CURRENT_DIR, "..", ".."))

DEFAULT_STORAGE_DIR = os.path.join(PROJECT_ROOT, "storage")
STORAGE_DIR = os.getenv("STORAGE_DIR", DEFAULT_STORAGE_DIR)


class LocalStorage:
    """
    Local filesystem storage manager replacing MinIO for SOP PDF assets,
    extracted images, visual table crops, generated PDFs, and session summaries.
    Stores all files directly under the codebase 'storage/' directory with
    dedicated subfolders (images/, tables/, users/, templates/, skills/, data/, indexes/).
    """

    def __init__(self, storage_dir: Optional[str] = None):
        self.storage_dir = os.path.abspath(storage_dir or STORAGE_DIR)
        self.bucket_name = "local-storage"
        self._ensure_directories()

    def _ensure_directories(self):
        """Ensure base storage directory and primary subfolders exist."""
        subfolders = [
            "images",
            "tables",
            "users",
            "templates",
            "skills",
            "data",
            "indexes",
            "artifacts",
        ]
        os.makedirs(self.storage_dir, exist_ok=True)
        for sub in subfolders:
            os.makedirs(os.path.join(self.storage_dir, sub), exist_ok=True)
        logger.info("LocalStorage initialized at: %s", self.storage_dir)

    def _resolve_path(self, object_name: str) -> str:
        """
        Resolve a logical object_name (e.g. 'images/conv123/img_0.png')
        to an absolute local filesystem path under storage_dir.
        """
        clean_name = object_name.strip().replace("\\", "/").lstrip("/")
        full_path = os.path.normpath(os.path.join(self.storage_dir, clean_name))
        # Ensure path stays within storage_dir (security against directory traversal)
        if not full_path.startswith(self.storage_dir):
            raise ValueError(f"Path traversal detected: {object_name}")
        return full_path

    def upload_file_bytes(
        self,
        object_name: str,
        data: bytes,
        content_type: str = "application/octet-stream",
        metadata: Optional[dict] = None,
    ) -> bool:
        """
        Store raw bytes into the local storage folder under the corresponding subfolder.
        """
        try:
            target_path = self._resolve_path(object_name)
            os.makedirs(os.path.dirname(target_path), exist_ok=True)
            with open(target_path, "wb") as f:
                f.write(data)
            logger.info("Saved local artifact: %s (%d bytes)", target_path, len(data))
            return True
        except Exception as e:
            logger.error("Failed to save local artifact %s: %s", object_name, e)
            return False

    def get_file_bytes(self, object_name: str) -> Tuple[Optional[bytes], str]:
        """
        Retrieve raw file bytes and inferred content type from local storage.
        """
        try:
            target_path = self._resolve_path(object_name)
        except Exception as e:
            logger.error("Invalid object name %s: %s", object_name, e)
            return None, "application/octet-stream"

        if not os.path.exists(target_path) or not os.path.isfile(target_path):
            logger.warning("Local storage file not found: %s", target_path)
            return None, "application/octet-stream"

        try:
            with open(target_path, "rb") as f:
                data = f.read()

            content_type, _ = mimetypes.guess_type(target_path)
            if not content_type:
                ext = os.path.splitext(target_path)[1].lower()
                if ext == ".png":
                    content_type = "image/png"
                elif ext in (".jpg", ".jpeg"):
                    content_type = "image/jpeg"
                elif ext == ".pdf":
                    content_type = "application/pdf"
                elif ext == ".json":
                    content_type = "application/json"
                elif ext in (".txt", ".md"):
                    content_type = "text/plain; charset=utf-8"
                else:
                    content_type = "application/octet-stream"

            return data, content_type
        except Exception as e:
            logger.error("Failed to read local file %s: %s", target_path, e)
            return None, "application/octet-stream"

    def remove_file(self, object_name: str) -> bool:
        """
        Delete a single file from local storage.
        """
        try:
            target_path = self._resolve_path(object_name)
            if os.path.exists(target_path) and os.path.isfile(target_path):
                os.remove(target_path)
                logger.info("Removed local storage file: %s", target_path)
                return True
        except Exception as e:
            logger.warning("Could not delete local file %s: %s", object_name, e)
            return False
        return False

    def remove_directory_prefix(self, prefix: str) -> int:
        """
        Delete all files matching a path prefix in local storage.
        """
        try:
            target_prefix = self._resolve_path(prefix)
        except Exception:
            return 0

        deleted_count = 0
        if os.path.exists(target_prefix):
            if os.path.isdir(target_prefix):
                try:
                    for root, dirs, files in os.walk(target_prefix):
                        deleted_count += len(files)
                    shutil.rmtree(target_prefix, ignore_errors=True)
                    logger.info("Removed local directory %s (%d files)", target_prefix, deleted_count)
                    return deleted_count
                except Exception as e:
                    logger.warning("Error deleting directory %s: %s", target_prefix, e)
            elif os.path.isfile(target_prefix):
                try:
                    os.remove(target_prefix)
                    return 1
                except Exception:
                    return 0

        # Also check if prefix is a partial name prefix
        parent_dir = os.path.dirname(target_prefix)
        prefix_base = os.path.basename(target_prefix)
        if os.path.exists(parent_dir) and os.path.isdir(parent_dir):
            for item in os.listdir(parent_dir):
                if item.startswith(prefix_base):
                    full_item = os.path.join(parent_dir, item)
                    try:
                        if os.path.isdir(full_item):
                            for root, dirs, files in os.walk(full_item):
                                deleted_count += len(files)
                            shutil.rmtree(full_item, ignore_errors=True)
                        else:
                            os.remove(full_item)
                            deleted_count += 1
                    except Exception:
                        pass
        return deleted_count

    def file_exists(self, object_name: str) -> bool:
        """Check if a file exists in local storage."""
        try:
            target_path = self._resolve_path(object_name)
            return os.path.exists(target_path) and os.path.isfile(target_path)
        except Exception:
            return False

    def list_objects(self, prefix: str = "") -> List[str]:
        """List all object names matching prefix in local storage."""
        results = []
        try:
            target_dir = self._resolve_path(prefix)
            if not os.path.exists(target_dir):
                return []
            if os.path.isfile(target_dir):
                return [prefix]

            for root, dirs, files in os.walk(target_dir):
                for f in files:
                    full_path = os.path.join(root, f)
                    rel_path = os.path.relpath(full_path, self.storage_dir).replace("\\", "/")
                    results.append(rel_path)
        except Exception as e:
            logger.warning("Could not list local storage objects for prefix %s: %s", prefix, e)
        return results


# Global singleton instance
local_storage = LocalStorage()
