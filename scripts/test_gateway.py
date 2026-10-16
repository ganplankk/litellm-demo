#!/usr/bin/env python3
"""Test model discovery; --invoke also makes one short, billable Bedrock call."""

import argparse
import getpass
import json
import os
import sys
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from common import ROOT, read_env


def call(base, key, path, payload=None):
    headers = {"Authorization": "Bearer " + key, "anthropic-version": "2023-06-01"}
    data = None
    if payload is not None:
        headers["Content-Type"] = "application/json"
        data = json.dumps(payload).encode("utf-8")
    request = Request(base + path, data=data, headers=headers)
    with urlopen(request, timeout=120) as response:
        return json.load(response)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--invoke", action="store_true")
    parser.add_argument("--base-url", help="Default: http://localhost:<LITELLM_PORT>")
    args = parser.parse_args()
    port = read_env(ROOT / ".env").get("LITELLM_PORT", "4000") if (ROOT / ".env").exists() else "4000"
    base = (args.base_url or "http://localhost:" + port).rstrip("/")
    key = os.environ.get("LITELLM_TEST_KEY") or getpass.getpass("LiteLLM Virtual Key (입력 숨김): ")
    if not key:
        print("Virtual Key가 필요합니다.", file=sys.stderr)
        return 1
    try:
        models = call(base, key, "/v1/models")
        ids = [model["id"] for model in models.get("data", [])]
        print("접근 가능한 모델:", ", ".join(ids))
        if "claude-lab" not in ids:
            print("claude-lab 없음: config.yaml 및 Virtual Key의 허용 모델을 확인하세요.", file=sys.stderr)
            return 1
        if args.invoke:
            print("Bedrock에 짧은 요청 1건을 전송합니다. API 사용료가 발생합니다.")
            response = call(base, key, "/v1/messages", {
                "model": "claude-lab", "max_tokens": 128,
                "messages": [{"role": "user", "content": "한국어로 '연결 성공'이라고 짧게 답해주세요."}],
            })
            output = "\n".join(item.get("text", "") for item in response.get("content", [])
                               if item.get("type") == "text")
            if not output:
                raise ValueError("No text response")
            print("모델 응답:", output)
            print("사용량:", json.dumps(response.get("usage", {}), ensure_ascii=False))
        else:
            print("모델 목록 확인 성공. 실제 추론은 --invoke 옵션으로 별도 확인하세요.")
    except HTTPError as error:
        print("HTTP", error.code, "오류. README 문제 해결 표와 LiteLLM 로그를 확인하세요.", file=sys.stderr)
        return 1
    except (URLError, OSError, ValueError, KeyError, TypeError):
        print("접속 또는 응답 해석 실패. URL·컨테이너 상태·로그를 확인하세요.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
