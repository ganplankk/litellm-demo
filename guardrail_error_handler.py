from fastapi import HTTPException
from litellm.integrations.custom_logger import CustomLogger


class GuardrailErrorHandler(CustomLogger):
    async def async_post_call_failure_hook(
        self,
        request_data,
        original_exception,
        user_api_key_dict,
        traceback_str=None,
    ):
        detail = getattr(original_exception, "detail", None)

        is_bedrock_block = (
            getattr(original_exception, "status_code", None) == 400
            and isinstance(detail, dict)
            and detail.get("error") == "Violated guardrail policy"
            and (
                "bedrock_guardrail_checks" in detail
                or "bedrock_guardrail_response" in detail
            )
        )

        if is_bedrock_block:
            return HTTPException(
                status_code=400,
                detail=(
                    "서비스 보안 정책에 따라 요청이 차단되었습니다. "
                    "개인정보나 민감한 내용을 제거한 후 다시 요청해 주세요."
                ),
            )

        return None


handler = GuardrailErrorHandler()