import aiobotocore.session  # pylint: disable=import-error
import asyncio
import io
from moto import (
    mock_lambda,
)
from opentelemetry.instrumentation.botocore.extensions.lmbd import (
    _LambdaExtension,
)
from opentelemetry.semconv.trace import (
    SpanAttributes,
)
from opentelemetry.test.test_base import (
    TestBase,
)
from opentelemetry.trace.span import (
    Span,
)
from otelcontribs.instrumentation.aiobotocore import (
    AiobotocoreInstrumentor,
)
from typing import (
    Any,
    Awaitable,
    TypeVar,
)
from unittest import (
    mock,
)
import zipfile

T = TypeVar("T")


def async_call(coro: Awaitable[T]) -> T:
    loop = asyncio.get_event_loop()
    return loop.run_until_complete(coro)


def get_as_zip_file(file_name: str, content: str) -> bytes:
    zip_output = io.BytesIO()
    with zipfile.ZipFile(zip_output, "w", zipfile.ZIP_DEFLATED) as zip_file:
        zip_file.writestr(file_name, content)
    zip_output.seek(0)
    return zip_output.read()


def return_headers_lambda_str() -> str:
    pfunc = """
def lambda_handler(event, context):
    print("custom log event")
    headers = event.get('headers', event.get('attributes', {}))
    return headers
"""
    return pfunc


class TestLambdaExtension(TestBase):
    def setUp(self) -> None:
        super().setUp()
        AiobotocoreInstrumentor().instrument()

        session = aiobotocore.session.get_session()
        session.set_credentials(
            access_key="access-key", secret_key="secret-key"
        )
        self.region = "us-west-2"
        self.client = async_call(
            # pylint: disable=unnecessary-dunder-call
            session.create_client(
                "lambda", region_name=self.region
            ).__aenter__()
        )
        self.iam_client = async_call(
            # pylint: disable=unnecessary-dunder-call
            session.create_client("iam", region_name=self.region).__aenter__()
        )

    def tearDown(self) -> None:
        super().tearDown()
        AiobotocoreInstrumentor().uninstrument()

    def assert_span(self, operation: str) -> Span:
        spans = self.memory_exporter.get_finished_spans()
        self.assertEqual(1, len(spans))

        span = spans[0]
        self.assertEqual(operation, span.attributes[SpanAttributes.RPC_METHOD])
        self.assertEqual("Lambda", span.attributes[SpanAttributes.RPC_SERVICE])
        self.assertEqual("aws-api", span.attributes[SpanAttributes.RPC_SYSTEM])
        return span

    @staticmethod
    def _create_extension(operation: str) -> _LambdaExtension:
        mock_call_context = mock.MagicMock(operation=operation, params={})
        return _LambdaExtension(mock_call_context)

    @mock_lambda
    def test_list_functions(self) -> None:
        async_call(self.client.list_functions())
        self.assert_span("ListFunctions")

    def test_invoke_parse_arn(self) -> None:
        function_name = "my_func"
        base = f"arn:aws:lambda:{self.region}"
        arns = (
            f"{base}:000000000000:function:{function_name}",
            f"000000000000:{function_name}",
            f"{base}:000000000000:function:{function_name}:alias",
        )

        for arn in arns:
            with self.subTest(arn=arn):
                # pylint: disable=protected-access
                extension = self._create_extension("Invoke")
                extension._call_context.params["FunctionName"] = arn

                attributes: dict[str, Any] = {}
                extension.extract_attributes(attributes)

                self.assertEqual(
                    function_name, attributes[SpanAttributes.FAAS_INVOKED_NAME]
                )
