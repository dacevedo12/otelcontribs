import aiobotocore.awsrequest  # pylint: disable=import-error
import aiobotocore.endpoint  # pylint: disable=import-error
import aiobotocore.retryhandler  # pylint: disable=import-error
from botocore.model import (
    OperationModel,
)
import pytest
from typing import (
    Any,
    Awaitable,
)


class MockedAWSResponse(
    aiobotocore.awsrequest.AioAWSResponse
):  # pylint: disable=too-few-public-methods
    """
    Patch aiobotocore to work with moto
    See https://github.com/aio-libs/aiobotocore/issues/755
    """

    def __init__(
        self, response: aiobotocore.awsrequest.AioAWSResponse
    ) -> None:
        self._response = response
        self.headers = response.headers
        self.raw = response.raw
        self.raw.raw_headers = {
            k.encode("utf-8"): str(v).encode("utf-8")
            for k, v in response.headers.items()
        }.items()
        self.status_code = response.status_code

    async def _content_prop(self) -> Awaitable[bytes]:
        return self._response.content


@pytest.fixture(autouse=True, scope="session")
def patch_aiobotocore_endpoint() -> None:
    original = aiobotocore.endpoint.convert_to_response_dict

    def patched(
        http_response: aiobotocore.awsrequest.AioAWSResponse,
        operation_model: OperationModel,
    ) -> Awaitable[dict[str, Any]]:
        return original(MockedAWSResponse(http_response), operation_model)

    aiobotocore.endpoint.convert_to_response_dict = patched


@pytest.fixture(autouse=True, scope="session")
def patch_aiobotocore_retryhandler() -> None:
    # pylint: disable=protected-access
    original = aiobotocore.retryhandler.AioCRC32Checker._check_response

    def patched(
        self: aiobotocore.retryhandler.AioCRC32Checker,
        attempt_number: int,
        response: aiobotocore.awsrequest.AioAWSResponse,
    ) -> Awaitable[None]:
        return original(self, attempt_number, [MockedAWSResponse(response[0])])

    # pylint: disable=protected-access
    aiobotocore.retryhandler.AioCRC32Checker._check_response = patched
