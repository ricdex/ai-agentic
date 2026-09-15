from unittest.mock import MagicMock, patch

import pytest

from shared.github_client import GitHubClient


def _client():
    return GitHubClient()


@patch("shared.github_client.requests.request")
def test_get_issue_calls_expected_endpoint(mock_request):
    mock_response = MagicMock(content=b'{"number": 1}')
    mock_response.json.return_value = {"number": 1}
    mock_request.return_value = mock_response

    result = _client().get_issue("org/repo", 1)

    mock_request.assert_called_once()
    args = mock_request.call_args.args
    assert args[0] == "GET"
    assert args[1] == "https://api.github.com/repos/org/repo/issues/1"
    assert result == {"number": 1}


@patch("shared.github_client.requests.request")
def test_post_comment_sends_body_as_json(mock_request):
    mock_response = MagicMock(content=b"{}")
    mock_response.json.return_value = {}
    mock_request.return_value = mock_response

    _client().post_comment("org/repo", 1, "Listo")

    kwargs = mock_request.call_args.kwargs
    assert kwargs["json"] == {"body": "Listo"}


@patch("shared.github_client.requests.request")
def test_req_raises_on_http_error(mock_request):
    mock_response = MagicMock(content=b"")
    mock_response.raise_for_status.side_effect = RuntimeError("404 Not Found")
    mock_request.return_value = mock_response

    with pytest.raises(RuntimeError, match="404"):
        _client().get_issue("org/repo", 999)


@patch("shared.github_client.requests.request")
def test_add_label_posts_labels_list(mock_request):
    mock_response = MagicMock(content=b"")
    mock_request.return_value = mock_response

    _client().add_label("org/repo", 1, ["bug", "needs-triage"])

    kwargs = mock_request.call_args.kwargs
    assert kwargs["json"] == {"labels": ["bug", "needs-triage"]}


@patch("shared.github_client.requests.request")
def test_req_returns_empty_dict_when_no_content(mock_request):
    mock_response = MagicMock(content=b"")
    mock_request.return_value = mock_response

    result = _client()._req("GET", "/repos/org/repo")

    assert result == {}
