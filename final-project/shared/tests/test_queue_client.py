import json
from unittest.mock import MagicMock, patch

from shared.queue_client import QueueClient


def _client_with_mock_redis():
    with patch("shared.queue_client.redis.Redis") as redis_cls:
        mock_redis = MagicMock()
        redis_cls.return_value = mock_redis
        client = QueueClient()
    return client, mock_redis


def test_push_serializes_payload_as_json():
    client, mock_redis = _client_with_mock_redis()

    client.push("factory:implement", {"task_id": "t1"})

    mock_redis.rpush.assert_called_once_with(
        "factory:implement", json.dumps({"task_id": "t1"})
    )


def test_pop_deserializes_payload_when_present():
    client, mock_redis = _client_with_mock_redis()
    mock_redis.blpop.return_value = ("factory:implement", json.dumps({"task_id": "t1"}))

    result = client.pop("factory:implement", timeout=5)

    mock_redis.blpop.assert_called_once_with("factory:implement", timeout=5)
    assert result == {"task_id": "t1"}


def test_pop_returns_none_on_timeout():
    client, mock_redis = _client_with_mock_redis()
    mock_redis.blpop.return_value = None

    assert client.pop("factory:implement", timeout=1) is None


def test_set_state_expires_after_one_day():
    client, mock_redis = _client_with_mock_redis()

    client.set_state("t1", {"status": "triaged"})

    mock_redis.setex.assert_called_once_with(
        "task:t1", 86400, json.dumps({"status": "triaged"})
    )


def test_get_state_returns_none_when_missing():
    client, mock_redis = _client_with_mock_redis()
    mock_redis.get.return_value = None

    assert client.get_state("unknown") is None
