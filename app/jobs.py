import threading
import uuid


ACTIVE_STATES = {"queued", "analyzing", "downloading", "converting", "tagging"}
DONE_STATES = {"completed", "failed"}


class JobStore:
    def __init__(self):
        self._jobs = {}
        self._lock = threading.Lock()

    def create(self):
        job_id = str(uuid.uuid4())[:8]
        job = {
            "id": job_id,
            "status": "queued",
            "progress": 0,
            "message": "queued",
            "title": None,
            "output_dir": None,
            "output_files": [],
            "error": None,
            "mode": None,
            "quality": None,
            "video_quality": None,
        }

        with self._lock:
            self._jobs[job_id] = job

        return dict(job)

    def get(self, job_id):
        with self._lock:
            job = self._jobs.get(job_id)
            return dict(job) if job else None

    def list(self):
        with self._lock:
            return [dict(job) for job in self._jobs.values()]

    def active_count(self):
        with self._lock:
            return sum(1 for job in self._jobs.values() if job.get("status") in ACTIVE_STATES)

    def update(self, job_id, **kwargs):
        with self._lock:
            job = self._jobs.get(job_id)
            if not job:
                return None

            job.update(kwargs)
            return dict(job)

    def clear_completed(self):
        with self._lock:
            before = len(self._jobs)
            self._jobs = {
                job_id: job
                for job_id, job in self._jobs.items()
                if job.get("status") not in DONE_STATES
            }
            return {"removed": before - len(self._jobs), "remaining": len(self._jobs)}

    def clear_all(self):
        with self._lock:
            blocked = any(job.get("status") in ACTIVE_STATES for job in self._jobs.values())

            if blocked:
                return {
                    "removed": 0,
                    "remaining": len(self._jobs),
                    "blocked": True,
                    "detail": "Cannot clear all while jobs are running.",
                }

            removed = len(self._jobs)
            self._jobs = {}
            return {"removed": removed, "remaining": 0, "blocked": False}


jobs = JobStore()


def run_background(target, *args, **kwargs):
    thread = threading.Thread(target=target, args=args, kwargs=kwargs, daemon=True)
    thread.start()
