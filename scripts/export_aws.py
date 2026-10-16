#!/usr/bin/env python3
"""Resolve an AWS CLI v2 profile and export its current credentials to Compose."""

import argparse
import json
import subprocess
import sys
from common import ROOT, private_write


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", required=True, help="WSL AWS CLI profile name")
    args = parser.parse_args()
    try:
        result = subprocess.run(
            ["aws", "configure", "export-credentials", "--profile", args.profile,
             "--format", "process", "--no-cli-pager"],
            check=True, capture_output=True, text=True, timeout=120,
        )
        credentials = json.loads(result.stdout)
        values = {
            "AWS_ACCESS_KEY_ID": credentials["AccessKeyId"],
            "AWS_SECRET_ACCESS_KEY": credentials["SecretAccessKey"],
            # Empty value clears a previous temporary token for static profiles.
            "AWS_SESSION_TOKEN": credentials.get("SessionToken") or "",
        }
        if not values["AWS_ACCESS_KEY_ID"] or not values["AWS_SECRET_ACCESS_KEY"]:
            raise ValueError("Empty credentials")
        if any(not isinstance(v, str) or any(c in v for c in "\r\n'$")
               for v in values.values()):
            raise ValueError("Unexpected credential format")
        # Single quotes prevent Compose interpolation. No secrets reach stdout.
        text = "# Generated locally; do not commit or share.\n"
        text += "\n".join(k + "='" + v + "'" for k, v in values.items()) + "\n"
        private_write(ROOT / ".aws.env", text)
    except (FileNotFoundError, subprocess.SubprocessError, ValueError, KeyError, OSError):
        print("내보내기 실패. AWS CLI v2 설치·프로필·로그인 유효기간을 확인하세요.", file=sys.stderr)
        print("기존 .aws.env는 유지했습니다. aws sts get-caller-identity --profile 프로필명 으로 확인하세요.", file=sys.stderr)
        return 1
    print(".aws.env 저장 완료. 비밀값은 출력하지 않았습니다.")
    print("자격 증명 만료:", credentials.get("Expiration") or "CLI가 만료 시각을 반환하지 않음")
    print("이미 실행 중이면: docker compose up -d --force-recreate litellm")
    return 0


if __name__ == "__main__":
    sys.exit(main())
