"""Manager for the SightHouse pipeline"""

from typing import Any, Set, List, Dict, Optional, Union
from base64 import b64decode
from logging import Logger
from pathlib import Path
import builtins
import shutil
import json
from celery import Celery

from sighthouse.core.utils import get_appdata_dir
from sighthouse.core.utils.repo import Repo
from sighthouse.pipeline.parser import PipelineConfig
from sighthouse.pipeline.worker import Job


class RepoCache:
    """Repository wrapper that cache files for faster lookup and retrieval.
    This class support the same method as the Repo class.
    """

    def __init__(self, repo: Repo, cache_dir_path: Union[Path, str], logger: Logger):
        self._repo = repo
        self._cache_dir = Path(cache_dir_path)
        self._cache_dir.mkdir(exist_ok=True, parents=True)
        self._cached_files: Set[str] = set()
        # In-memory cache
        self._memory_cache: Dict[str, bytes] = {}
        self._logger = logger
        self._load_existing_cache()

    def _load_existing_cache(self) -> None:
        """Load list of existing cached files and populate memory cache"""
        if self._cache_dir.exists():
            for file_path in self._cache_dir.rglob("**/*"):
                if file_path.is_file():
                    # Convert back to relative path from repo
                    relative_path = str(file_path.relative_to(self._cache_dir))
                    self._cached_files.add(relative_path)

                    # Load into memory cache
                    try:
                        with open(file_path, "rb") as fp:
                            content = fp.read()
                            self._memory_cache[relative_path] = content
                    except Exception as e:
                        self._logger.error(
                            f"Error loading {relative_path} into memory cache: {e}"
                        )

    def _get_cache_file_path(self, repo_file_path: str) -> Path:
        """Convert repository file path to cache file path"""
        # Remove leading slash if present and create cache path
        clean_path = repo_file_path.lstrip("/")
        return self._cache_dir / clean_path

    def _remove_from_cache(self, repo_file_path: str) -> None:
        """Remove file from both disk and memory cache"""
        # Remove from memory cache
        if repo_file_path in self._memory_cache:
            del self._memory_cache[repo_file_path]
            self._logger.debug(f"Removed from memory cache: {repo_file_path}")

        # Remove from disk cache
        cache_file_path = self._get_cache_file_path(repo_file_path)
        if cache_file_path.exists():
            try:
                cache_file_path.unlink()
                self._logger.debug(f"Removed from disk cache: {repo_file_path}")

                # Remove empty parent directories
                parent = cache_file_path.parent
                while parent != self._cache_dir and parent.exists():
                    try:
                        if not any(parent.iterdir()):  # Directory is empty
                            parent.rmdir()
                            parent = parent.parent
                        else:
                            break
                    except OSError:
                        break

            except Exception as e:
                self._logger.error(
                    f"Error removing file from disk cache {cache_file_path}: {e}"
                )

        # Remove from cached files set
        self._cached_files.discard(repo_file_path)

    def _save_to_cache(self, cache_file_path: Path, content: bytes):
        """Save content to cache file"""
        try:
            # Create parent directories if they don't exist
            cache_file_path.parent.mkdir(parents=True, exist_ok=True)

            with open(cache_file_path, "wb") as fp:
                fp.write(content)
        except Exception as e:
            self._logger.error(f"Error saving to cache {cache_file_path}: {e}")

    def get_file(self, repo_file_path: str) -> bytes:
        """Get file content from memory cache, disk cache, or repository"""
        # Check memory cache first
        if repo_file_path in self._memory_cache:
            self._logger.debug(f"Memory cache hit for: {repo_file_path}")
            return self._memory_cache[repo_file_path]

        cache_file_path = self._get_cache_file_path(repo_file_path)

        # Check if file exists in disk cache
        if cache_file_path.exists():
            self._logger.debug(f"Disk cache hit for: {repo_file_path}")
            with open(cache_file_path, "rb") as fp:
                content = fp.read()

            # Add to memory cache
            self._memory_cache[repo_file_path] = content
            return content

        self._logger.debug(f"Cache miss for: {repo_file_path}")
        # Check if file exists in repository before fetching
        try:
            data = self._repo.get_file(repo_file_path)
            if data is None:
                raise Exception(f"Fail to retrieve content of file {repo_file_path}")
            content = data

        except Exception as e:
            # File doesn't exist in repo, remove from cache if it was there
            if repo_file_path in self._cached_files:
                self._logger.debug(
                    f"File no longer exists in repo, removing from cache: {repo_file_path}"
                )
                self._remove_from_cache(repo_file_path)
            raise e

        # Save to disk cache
        self._save_to_cache(cache_file_path, content)
        self._cached_files.add(repo_file_path)
        # Add to memory cache
        self._memory_cache[repo_file_path] = content
        return content

    def list_directory(self, repo_dir_path: str) -> List[str]:
        """List directory and update cache with new files"""
        # Get current directory listing from repository
        current_files = self._repo.list_directory(repo_dir_path)

        # Check for new files not in cache
        repo_dir_clean = repo_dir_path.rstrip("/")
        new_files = []

        # Create set of current files with full paths
        current_full_paths = set()
        for file_path in current_files:
            # Create full path for checking
            if repo_dir_clean:
                full_file_path = (
                    f"{repo_dir_clean}/{file_path}"
                    if not file_path.startswith(repo_dir_clean)
                    else file_path
                )
            else:
                full_file_path = file_path

            current_full_paths.add(full_file_path)
            if full_file_path not in self._cached_files:
                # Ignore directories, @WARNING: Is this the right way to do it ??
                if not full_file_path.endswith("/"):
                    new_files.append(full_file_path)

        # Find cached files in this directory that no longer exist in repo
        repo_cache = self._get_cache_file_path(repo_dir_clean)
        files_to_remove = set()
        if repo_cache.exists() and repo_cache.is_dir():
            files_to_remove = {
                (str(f.relative_to(self._cache_dir)) + ("/" if f.is_dir() else ""))
                for f in repo_cache.iterdir()
            } - current_full_paths

        # Remove cached files that no longer exist in the repository directory
        if files_to_remove:
            self._logger.debug(
                f"Found {len(files_to_remove)} files to remove from cache"
            )
            for file_path in files_to_remove:
                self._remove_from_cache(file_path)

        # Cache new files
        if new_files:
            self._logger.debug(f"Found {len(new_files)} new files to cache")
            for file_path in new_files:
                try:
                    # Only cache if it's actually a file (not a directory)
                    content = self._repo.get_file(file_path)
                    if content is None:
                        raise Exception(f"Fail to retrieve content of file {file_path}")

                    cache_file_path = self._get_cache_file_path(file_path)
                    self._save_to_cache(cache_file_path, content)
                    self._cached_files.add(file_path)

                    # Add to memory cache
                    self._memory_cache[file_path] = content

                    self._logger.debug(f"Cached new file: {file_path}")
                except Exception as e:
                    self._logger.error(f"Could not cache '{file_path}': {e}")

        return current_files

    def delete_file(self, repo_file_path: str) -> None:
        """Delete file content from memory cache, disk cache & repository"""
        self._repo.delete_file(repo_file_path)
        self._remove_from_cache(repo_file_path)

    def clear_cache(self) -> None:
        """Clear the entire cache (both disk and memory)"""
        try:
            if self._cache_dir.exists():
                shutil.rmtree(self._cache_dir)
            self._cache_dir.mkdir(exist_ok=True)
            self._cached_files.clear()
            self._memory_cache.clear()
            self._logger.debug("Cache cleared")
        except Exception as e:
            self._logger.error(f"Error clearing cache: {e}")

    def get_cache_stats(self) -> Dict[str, Any]:
        """Get cache statistics"""
        memory_size_bytes = sum(len(content) for content in self._memory_cache.values())
        disk_size_bytes = sum(
            f.stat().st_size for f in self._cache_dir.rglob("*") if f.is_file()
        )

        return {
            "cached_files_count": len(self._cached_files),
            "memory_cached_files_count": len(self._memory_cache),
            "cache_directory": str(self._cache_dir),
            "disk_cache_size_mb": disk_size_bytes / (1024 * 1024),
            "memory_cache_size_mb": memory_size_bytes / (1024 * 1024),
        }


class PipelineManager:
    """Manager for the SightHouse pipeline"""

    DEFAULT_CACHE_PATH = get_appdata_dir() / "cache"

    def __init__(self, worker_url: str, repo_url: str, logger: Logger):
        repo = Repo(repo_url, secure=False)
        self._repo = RepoCache(
            repo, self.DEFAULT_CACHE_PATH / (repo._uri["host"] or "local"), logger
        )
        self._celery_app = Celery(
            broker=worker_url,
            backend=worker_url,
        )
        self._logger = logger

    def start_pipeline(self, pipeline: Union[Path, str]) -> None:
        """Start pipeline from the given configuration"""

        config = PipelineConfig.load(pipeline)

        # Query worker metadata
        inspect = self._celery_app.control.inspect()
        instances = inspect._request("worker_metadata") or {}

        # Unsure that all necessary worker are present
        required = set(w.package for w in config.workers)
        missing = required - set(meta["id"] for meta in instances.values())
        if missing:
            raise ValueError(f"Missing worker from pipeline: {', '.join(missing)}")

        for root in config.roots:
            exec_chain = config.create_execution_chain(root.name)
            job = Job(exec_chain, {})
            self._logger.debug(
                f"Sending task to {job.package}:\n{json.dumps(job.to_dict(), indent=2)}"
            )
            self._celery_app.send_task(
                "do_work",
                queue=job.package,
                kwargs={"job_dict": job.to_dict()},
            )

    def inspect_workers(self) -> dict:
        """Return stats about the current wokrer and there jobs

        Return an object like this:
        ```
        {
          "workers": [
            {
              "Worker 1": {
                "scheduled": [...],
                "active": [...],
                "reserved": [...]
              }
            },
            ...
          ]
        }
        ```

        """

        # Query worker metadata
        inspect = self._celery_app.control.inspect()
        instances = inspect._request("worker_metadata") or {}

        scheduled = inspect.scheduled()
        active = inspect.active()
        reserved = inspect.reserved()

        # Iterate over each worker and check if we have at least one worker for each of our ouputs
        workers = []
        for worker_id, meta in instances.items():
            workers.append(
                {
                    meta["id"]: {
                        "scheduled": scheduled[worker_id],
                        "active": active[worker_id],
                        "reserved": reserved[worker_id],
                    }
                }
            )

        return {"workers": workers}

    def _get_processing_jobs(self) -> List[Dict[str, Any]]:
        """Return the jobs hidden in the redis queue, waiting to be processed.
        This method is a hack as celery does not report all the jobs in the queue,
        only the ones took by workers
        """

        if not hasattr(self._celery_app.backend, "redis"):
            raise NotImplementedError(
                "This method is only implemented for redis backend"
            )

        # Query worker metadata
        inspect = self._celery_app.control.inspect()

        # Build a set of all the queues
        queues = inspect.active_queues()
        names: Set[str] = set()
        # Create a set of all the queues used by workers
        for worker, payload in queues.items():
            names = names.union(set(queue["name"] for queue in payload))

        # Now iterate over all of them using redis command as we know it's the backend
        for queue in names:
            count = self._celery_app.backend.client.llen(queue)
            self._logger.debug(f"Queue '{queue}' has {count} task")
            if count <= 0:
                continue

            jobs = []
            # Number of jobs we query from redis
            batch_size = 1000
            for i in range(0, count, batch_size):
                self._logger.debug(f"Processing {batch_size} jobs out of {count}")
                tasks = self._celery_app.backend.client.lrange(
                    queue, i, min(i + batch_size - 1, count - 1)
                )
                for task in tasks:
                    # By default tasks are encoded either as JSON, RAW or Pickle
                    decoded = self._celery_app.backend.decode(task)
                    # "Decoded" task still have their payload encoded as base64
                    encoding = decoded.get("properties", {}).get("body_encoding")
                    if encoding != "base64":
                        self._logger.warning(f"Unsupported encoding '{encoding}'")
                    else:
                        # Expecting an JSON array of [input, data, callbacks]
                        job_dict = json.loads(b64decode(decoded.get("body")))[1]
                        jobs.append(job_dict.get("job_dict"))

        return jobs

    def stats(self, state: Optional[str] = None, package: Optional[str] = None) -> dict:
        """Return stats about the pipeline. Optionnaly filter by state and/or package is supplied.

        Returns an object like this:
        ```
        {
          "Package 1": {
            "success": 165,
            "processing": 10,
            "failure": 0
          },
          "Package 2": {
            "success": 5,
            "processing": 0,
            "failure": 1
          }
        }
        ```
        """
        if state is not None and (
            not isinstance(state, str)
            or state not in ["success", "failed", "processing"]
        ):
            raise ValueError(
                "Invalid state. Expecting either 'success', 'failed', 'processing' or None"
            )

        if package is not None and not isinstance(package, str):
            raise TypeError("Invalid package type")

        stats = {}
        if not state or state == "success":
            # List success
            for path in list(map(Path, self._repo.list_directory("success/"))):
                worker: Optional[str] = path.name
                if package is None or package == worker:
                    count = len(self._repo.list_directory(str(path) + "/"))
                    stats[worker] = {"success": count, "failure": 0, "processing": 0}

        if not state or state == "failed":
            # List failure
            for path in list(map(Path, self._repo.list_directory("failed/"))):
                worker = path.name
                if package is None or package == worker:
                    count = len(self._repo.list_directory(str(path) + "/"))
                    if worker in stats:
                        stats[worker].update({"failure": count})
                    else:
                        stats[worker] = {
                            "success": 0,
                            "failure": count,
                            "processing": 0,
                        }

        if not state or state == "processing":
            # List processing
            for job in self._get_processing_jobs():
                worker = Job.from_dict(job).package
                if worker in stats:
                    stats[worker].update(
                        {"processing": stats[worker].get("processing", 0) + 1}
                    )
                else:
                    stats[worker] = {"success": 0, "failure": 0, "processing": 1}

        return stats

    def list_jobs(
        self,
        state: Optional[str] = None,
        package: Optional[str] = None,
        filters: Optional[str] = None,
        group_by: Optional[str] = None,
        max_jobs: int = -1,
    ):
        if state is not None and (
            not isinstance(state, str)
            or state not in ["success", "failed", "processing"]
        ):
            raise ValueError(
                "Invalid state. Expecting either 'success', 'failed', 'processing' or None"
            )

        if package is not None and not isinstance(package, str):
            raise TypeError("Invalid package type")

        if filters is not None and not isinstance(filters, str):
            raise TypeError("Invalid filters type")

        if group_by is not None and not isinstance(group_by, str):
            raise TypeError("Invalid group_by type")

        jobs_files = []
        processing_jobs = []
        if not state or state == "success":
            # List success
            for path in list(map(Path, self._repo.list_directory("success/"))):
                worker = path.name
                if package is None or package == worker:
                    jobs_files += self._repo.list_directory(str(path) + "/")

        if not state or state == "failed":
            # List failure
            for path in list(map(Path, self._repo.list_directory("failed/"))):
                worker = path.name
                if package is None or package == worker:
                    jobs_files += self._repo.list_directory(str(path) + "/")

        if not state or state == "processing":
            # List processing
            processing_jobs = self._get_processing_jobs()

        if filters is not None:
            # Filter is supplied, we have to parse the jobs
            def apply_filter(data: dict) -> bool:
                self._logger.warning(
                    "Warning: Using 'eval' for filtering jobs can execute arbitrary "
                    "code on your machine. Proceed with caution!"
                )
                result = eval(filters, {"__builtins__": None, **data}, {})
                if not isinstance(result, bool):
                    raise TypeError("Filter did not returned a boolean value")

                return result

            jobs_files = list(
                builtins.filter(
                    lambda job: apply_filter(json.loads(self._repo.get_file(job))),
                    jobs_files,
                )
            )
            processing_jobs = list(builtins.filter(apply_filter, processing_jobs))

        if group_by:
            group: Dict[str, Any] = {}

            # Group by key
            def apply_group_by(data: dict) -> None:
                if group_by not in data.keys():
                    raise ValueError(f"Cannot group jobs by '{group_by}'")

                value = data[group_by]
                if value in group:
                    group[value]["count"] += 1
                else:
                    group[value] = {"value": value, "count": 1}

            # Group by for files
            for job in jobs_files:
                data = json.loads(self._repo.get_file(job))
                apply_group_by(data)

            # Group by for processing jobs
            for j in processing_jobs:
                apply_group_by(j)

            if max_jobs < 0:
                max_jobs = len(group)

            for elem in sorted(group.values(), key=lambda e: -e["count"])[0:max_jobs]:
                print(
                    f"The following value for key '{group_by}' occurs #{elem['count']} "
                    f"accross jobs:\n{elem['value']}\n"
                )

        else:
            total_jobs = jobs_files + list(
                map(lambda e: e.get("job_metadata", {}).get("id"), processing_jobs)
            )
            if max_jobs < 0:
                max_jobs = len(total_jobs)
            # List job
            for job in total_jobs[0:max_jobs]:
                print(Path(job).stem)

    def restart_jobs(self, jobs: List[str]) -> bool:
        """Restart the given jobs"""
        if not isinstance(jobs, list) or not all(isinstance(x, str) for x in jobs):
            raise TypeError("Invalid job list. Expecting a list of string")

        remote_jobs = []
        # List success & failure
        for path in list(map(Path, self._repo.list_directory("success/"))):
            remote_jobs += self._repo.list_directory(str(path) + "/")
        for path in list(map(Path, self._repo.list_directory("failed/"))):
            remote_jobs += self._repo.list_directory(str(path) + "/")

        # We have to map UUID to path on the repo
        job_uuids = {Path(e).stem: e for e in remote_jobs if Path(e).stem in jobs}
        missing = list(filter(lambda e: e not in job_uuids, jobs))
        if len(missing) > 0:
            # Handle defacto pending jobs as they should not be allowed to restart
            raise Exception(f"Missing at least one job: '{missing[0]}'")

        # Restart each job
        for uuid, file in job_uuids.items():
            job = Job.from_dict(json.loads(self._repo.get_file(file)))
            if job.job_metadata.get("state") != "failed":
                self._logger.warning(
                    f"Restarting '{uuid}' will likely create unwanted "
                    "behavior as the job did not failed"
                )

            # Filter field we have to remove
            for key in ["error", "state", "id"]:
                if key in job.job_metadata:
                    del job.job_metadata[key]

            worker = Path(file).parent.name
            # Delete job from repo
            self._repo.delete_file(file)
            # Add task
            self._celery_app.send_task(
                "do_work",
                queue=worker,
                task_id=uuid,
                kwargs={"job_dict": job.to_dict()},
            )
            self._logger.info(f"Restarting job '{uuid}'")

        return True
