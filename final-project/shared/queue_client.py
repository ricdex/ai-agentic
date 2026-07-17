import json
import os
from typing import Optional
import redis

QUEUE_IMPLEMENT = "factory:implement"
QUEUE_REVIEW = "factory:review"
QUEUE_SPEC_PENDING = "factory:spec_pending"


class QueueClient:
    def __init__(self):
        self.r = redis.Redis(
            host=os.environ["REDIS_HOST"],
            port=int(os.environ.get("REDIS_PORT", "6379")),
            password=os.environ.get("REDIS_PASSWORD"),
            decode_responses=True,
        )

    def push(self, queue: str, data: dict) -> None:
        self.r.rpush(queue, json.dumps(data))

    def pop(self, queue: str, timeout: int = 30) -> Optional[dict]:
        result = self.r.blpop(queue, timeout=timeout)
        if result:
            _, value = result
            return json.loads(value)
        return None

    def set_state(self, task_id: str, state: dict) -> None:
        self.r.setex(f"task:{task_id}", 86400, json.dumps(state))

    def get_state(self, task_id: str) -> Optional[dict]:
        value = self.r.get(f"task:{task_id}")
        return json.loads(value) if value else None
