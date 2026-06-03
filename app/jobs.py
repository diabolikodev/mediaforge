import threading
import uuid


ACTIVE_STATES = {"queued", "analyzing", "downloading", "converting", "tagging"}
RUNNING_STATES = {"analyzing", "downloading", "converting", "tagging"}
DONE_STATES = {"completed", "failed", "cancelled"}


class JobStore:
    def __init__(self):
        self._jobs = {}
        self._lock = threading.Lock()
        self._condition = threading.Condition(self._lock)
        self._queue_paused = False

    def create(self, request=None):
        job_id = str(uuid.uuid4())[:8]
        job = {
            "id": job_id,
            "status": "queued",
            "progress": 0,
            "message": "queued",
            "title": None,
            "url": (request or {}).get("url"),
            "request": dict(request or {}),
            "output_dir": None,
            "output_files": [],
            "error": None,
            "error_code": None,
            "error_detail": None,
            "cancel_requested": False,
            "mode": (request or {}).get("mode"),
            "quality": (request or {}).get("quality"),
            "video_quality": (request or {}).get("video_quality"),
        }

        with self._condition:
            self._jobs[job_id] = job
            self._condition.notify_all()

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
        with self._condition:
            job = self._jobs.get(job_id)
            if not job:
                return None

            job.update(kwargs)
            self._condition.notify_all()
            return dict(job)

    def is_cancelled(self, job_id):
        with self._lock:
            job = self._jobs.get(job_id)
            if not job:
                return True
            return bool(job.get("cancel_requested")) or job.get("status") == "cancelled"

    def wait_for_queue(self, job_id):
        with self._condition:
            while self._queue_paused:
                job = self._jobs.get(job_id)

                if not job:
                    return False

                if job.get("cancel_requested") or job.get("status") == "cancelled":
                    return False

                self._condition.wait(0.4)

            job = self._jobs.get(job_id)

            if not job:
                return False

            return not job.get("cancel_requested") and job.get("status") != "cancelled"

    def pause_queue(self):
        with self._condition:
            self._queue_paused = True
            self._condition.notify_all()
            return self.queue_status()

    def resume_queue(self):
        with self._condition:
            self._queue_paused = False
            self._condition.notify_all()
            return self.queue_status()

    def queue_status(self):
        queued = running = completed = failed = cancelled = 0

        for job in self._jobs.values():
            status = job.get("status")

            if status == "queued":
                queued += 1
            elif status in RUNNING_STATES:
                running += 1
            elif status == "completed":
                completed += 1
            elif status == "failed":
                failed += 1
            elif status == "cancelled":
                cancelled += 1

        return {
            "paused": self._queue_paused,
            "queued": queued,
            "running": running,
            "completed": completed,
            "failed": failed,
            "cancelled": cancelled,
        }

    def cancel(self, job_id):
        with self._condition:
            job = self._jobs.get(job_id)

            if not job:
                return {"cancelled": 0, "detail": "Job not found."}

            status = job.get("status")

            if status == "queued":
                job.update(
                    status="cancelled",
                    progress=0,
                    message="cancelled",
                    cancel_requested=True,
                    error=None,
                    error_code=None,
                    error_detail=None,
                )
                self._condition.notify_all()
                return {"cancelled": 1, "status": "cancelled"}

            if status in RUNNING_STATES:
                job.update(cancel_requested=True, message="cancelling")
                self._condition.notify_all()
                return {"cancelled": 1, "status": "cancelling"}

            return {"cancelled": 0, "detail": "Job is not active."}

    def cancel_queued(self):
        with self._condition:
            cancelled = 0

            for job in self._jobs.values():
                if job.get("status") == "queued":
                    job.update(
                        status="cancelled",
                        progress=0,
                        message="cancelled",
                        cancel_requested=True,
                        error=None,
                        error_code=None,
                        error_detail=None,
                    )
                    cancelled += 1

            self._condition.notify_all()
            return {"cancelled": cancelled, **self.queue_status()}

    def cancel_active(self):
        with self._condition:
            cancelled = 0

            for job in self._jobs.values():
                status = job.get("status")

                if status == "queued":
                    job.update(
                        status="cancelled",
                        progress=0,
                        message="cancelled",
                        cancel_requested=True,
                        error=None,
                        error_code=None,
                        error_detail=None,
                    )
                    cancelled += 1
                elif status in RUNNING_STATES:
                    job.update(cancel_requested=True, message="cancelling")
                    cancelled += 1

            self._condition.notify_all()
            return {"cancelled": cancelled, **self.queue_status()}

    def remove(self, job_id):
        with self._lock:
            job = self._jobs.get(job_id)

            if not job:
                return {"removed": 0, "blocked": False, "detail": "Job not found."}

            if job.get("status") in ACTIVE_STATES:
                return {"removed": 0, "blocked": True, "detail": "Cannot remove an active job."}

            del self._jobs[job_id]
            return {"removed": 1, "blocked": False}

    def clear_completed(self):
        with self._lock:
            before = len(self._jobs)
            self._jobs = {
                job_id: job
                for job_id, job in self._jobs.items()
                if job.get("status") not in DONE_STATES
            }
            return {"removed": before - len(self._jobs), "remaining": len(self._jobs)}

    def clear_by_filter(self, status_filter):
        removable = {"completed", "failed", "cancelled"}
        status_filter = str(status_filter or "").strip().lower()

        with self._lock:
            before = len(self._jobs)

            if status_filter == "done":
                self._jobs = {
                    job_id: job
                    for job_id, job in self._jobs.items()
                    if job.get("status") not in DONE_STATES
                }
            elif status_filter in removable:
                self._jobs = {
                    job_id: job
                    for job_id, job in self._jobs.items()
                    if job.get("status") != status_filter
                }
            else:
                return {
                    "removed": 0,
                    "remaining": len(self._jobs),
                    "blocked": True,
                    "detail": "Only completed, failed or cancelled jobs can be cleared by filter.",
                }

            return {
                "removed": before - len(self._jobs),
                "remaining": len(self._jobs),
                "blocked": False,
            }

    def clear_all(self):
        with self._lock:
            blocked = any(job.get("status") in ACTIVE_STATES for job in self._jobs.values())

            if blocked:
                return {
                    "removed": 0,
                    "remaining": len(self._jobs),
                    "blocked": True,
                    "detail": "Cannot clear all while jobs are active. Stop active jobs first.",
                }

            removed = len(self._jobs)
            self._jobs = {}
            return {"removed": removed, "remaining": 0, "blocked": False}


jobs = JobStore()


def run_background(target, *args, **kwargs):
    thread = threading.Thread(target=target, args=args, kwargs=kwargs, daemon=True)
    thread.start()
