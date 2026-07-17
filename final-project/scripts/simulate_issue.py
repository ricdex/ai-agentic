#!/usr/bin/env python3
"""
Simulate a GitHub webhook locally for testing the factory without a real webhook.
Usage: python scripts/simulate_issue.py --repo owner/repo --title "Bug: ..." --body "..."
"""
import argparse
import hashlib
import hmac
import json
import os
import time
import requests


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", required=True, help="owner/repo")
    parser.add_argument("--title", required=True)
    parser.add_argument("--body", default="")
    parser.add_argument("--url", default="http://localhost:8000/webhook")
    args = parser.parse_args()

    secret = os.environ.get("GITHUB_WEBHOOK_SECRET", "test-secret")

    payload = {
        "action": "opened",
        "issue": {
            "number": int(time.time()) % 10000,
            "title": args.title,
            "body": args.body,
            "labels": [],
        },
        "repository": {"full_name": args.repo},
    }

    body = json.dumps(payload).encode()
    sig = "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()

    resp = requests.post(
        args.url,
        data=body,
        headers={
            "Content-Type": "application/json",
            "X-GitHub-Event": "issues",
            "X-Hub-Signature-256": sig,
        },
    )
    print(f"Status: {resp.status_code}")
    print(f"Response: {resp.json()}")


if __name__ == "__main__":
    main()
