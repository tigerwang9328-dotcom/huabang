# Compatibility shim: Wrangler finance code expects app.api.v1.tasks.submit_async_task
# Simple implementation using FastAPI BackgroundTasks
import uuid
import logging
from datetime import datetime
from fastapi import BackgroundTasks
from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)

# In-memory task store (simple, non-persistent)
_task_store = {}

def submit_async_task(
    background: BackgroundTasks,
    task_type: str,
    task_fn,
    **kwargs
):
    task_id = str(uuid.uuid4())
    _task_store[task_id] = {
        "task_id": task_id,
        "task_type": task_type,
        "status": "pending",
        "created_at": datetime.now().isoformat(),
        "params": kwargs,
    }

    def _run():
        try:
            logger.info(f"Async task {task_id} ({task_type}) started")
            _task_store[task_id]["status"] = "running"
            result = task_fn()
            _task_store[task_id]["status"] = "completed"
            _task_store[task_id]["result"] = result
            logger.info(f"Async task {task_id} ({task_type}) completed")
        except Exception as e:
            logger.exception(f"Async task {task_id} ({task_type}) failed: {e}")
            _task_store[task_id]["status"] = "failed"
            _task_store[task_id]["error"] = str(e)

    background.add_task(_run)

    return JSONResponse(
        content={
            "task_id": task_id,
            "status": "pending",
            "message": f"Task {task_type} submitted",
        }
    )