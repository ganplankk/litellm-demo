#!/usr/bin/env python3
"""Create local secrets once; never rotate an existing lab's values."""

import secrets
from common import ROOT, private_write, replace_values


def main():
    path = ROOT / ".env"
    if path.exists():
        print("기존 .env를 유지합니다. 키와 DB 비밀번호를 변경하지 않았습니다.")
    else:
        values = {
            "POSTGRES_PASSWORD": secrets.token_hex(24),
            "LITELLM_MASTER_KEY": "sk-" + secrets.token_hex(32),
            "LITELLM_SALT_KEY": secrets.token_hex(32),
            "UI_PASSWORD": secrets.token_hex(24),
        }
        template = (ROOT / ".env.example").read_text(encoding="utf-8")
        private_write(path, replace_values(template, values))
        print(".env 생성 완료. AWS_REGION_NAME과 BEDROCK_MODEL을 수정하세요.")
    aws_path = ROOT / ".aws.env"
    if not aws_path.exists():
        private_write(aws_path, "# Run scripts/export_aws.py before starting LiteLLM.\n")
    print("비밀값은 화면에 출력하지 않았습니다.")


if __name__ == "__main__":
    main()
