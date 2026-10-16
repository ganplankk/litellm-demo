#!/usr/bin/env python3
"""After docker compose pull, pin the downloaded images by registry digest."""

import json
import subprocess
import sys
from common import ROOT, private_write, read_env, replace_values


def main():
    path = ROOT / ".env"
    try:
        values = read_env(path)
        updates = {}
        for key in ("LITELLM_IMAGE", "POSTGRES_IMAGE"):
            reference = values[key]
            if "@sha256:" in reference:
                continue
            result = subprocess.run(
                ["docker", "image", "inspect", reference, "--format", "{{json .RepoDigests}}"],
                check=True, capture_output=True, text=True, timeout=30,
            )
            digests = json.loads(result.stdout)
            if not digests or not all(isinstance(v, str) and "@sha256:" in v for v in digests):
                raise ValueError("No repository digest")
            updates[key] = digests[0]
        private_write(path, replace_values(path.read_text(encoding="utf-8"), updates))
    except (OSError, subprocess.SubprocessError, ValueError, KeyError):
        print("고정 실패. Docker 실행 상태와 docker compose pull 성공 여부를 확인하세요.", file=sys.stderr)
        return 1
    print("두 이미지의 digest 고정 완료. 재시작해도 같은 이미지가 사용됩니다.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
