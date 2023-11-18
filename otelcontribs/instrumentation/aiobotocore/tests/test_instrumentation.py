from aiobotocore.client import (  # pylint: disable=import-error
    AioBaseClient,
)
import aiobotocore.session  # pylint: disable=import-error
import asyncio
from botocore.exceptions import (
    ParamValidationError,
)
import json
from moto import (
    mock_ec2,
    mock_kinesis,
    mock_kms,
    mock_s3,
    mock_sqs,
    mock_sts,
    mock_xray,
)
from opentelemetry import (
    trace as trace_api,
)
from opentelemetry.context import (
    _SUPPRESS_HTTP_INSTRUMENTATION_KEY,
    _SUPPRESS_INSTRUMENTATION_KEY,
    attach,
    detach,
    set_value,
)
from opentelemetry.propagate import (
    get_global_textmap,
    set_global_textmap,
)
from opentelemetry.semconv.trace import (
    SpanAttributes,
)
from opentelemetry.test.mock_textmap import (
    MockTextMapPropagator,
)
from opentelemetry.test.test_base import (
    TestBase,
)
from opentelemetry.trace.span import (
    Span as SpanBase,
)
from opentelemetry.util.types import (
    AttributeValue,
)
from otelcontribs.instrumentation.aiobotocore import (
    AiobotocoreInstrumentor,
)
from typing import (
    Any,
    Awaitable,
    TypeVar,
)
from unittest.mock import (
    Mock,
    patch,
)

_REQUEST_ID_REGEX_MATCH = r"[A-Z0-9]{52}"


class Span(SpanBase):
    attributes: dict[str, str]
    name: str


T = TypeVar("T")


def async_call(coro: Awaitable[T]) -> T:
    loop = asyncio.get_event_loop()
    return loop.run_until_complete(coro)


# pylint:disable=too-many-public-methods
class TestAiobotocoreInstrumentor(TestBase):
    """AioBotocore integration testsuite"""

    def setUp(self) -> None:
        super().setUp()
        AiobotocoreInstrumentor().instrument()

        self.session = aiobotocore.session.get_session()
        self.session.set_credentials(
            access_key="access-key", secret_key="secret-key"
        )
        self.region = "us-west-2"

    def tearDown(self) -> None:
        super().tearDown()
        AiobotocoreInstrumentor().uninstrument()

    def _make_client(self, service: str) -> AioBaseClient:
        return async_call(
            # pylint: disable=unnecessary-dunder-call
            self.session.create_client(
                service, region_name=self.region
            ).__aenter__()
        )

    def _default_span_attributes(
        self, service: str, operation: str
    ) -> dict[str, Any]:
        return {
            SpanAttributes.RPC_SYSTEM: "aws-api",
            SpanAttributes.RPC_SERVICE: service,
            SpanAttributes.RPC_METHOD: operation,
            "aws.region": self.region,
            "retry_attempts": 0,
            SpanAttributes.HTTP_STATUS_CODE: 200,
        }

    def assert_only_span(self) -> Span:
        spans = self.memory_exporter.get_finished_spans()
        self.assertEqual(1, len(spans))
        return spans[0]

    def assert_span(
        self,
        service: str,
        operation: str,
        request_id: str | None = None,
        attributes: dict[str, Any] | None = None,
    ) -> Span:
        span = self.assert_only_span()
        expected = self._default_span_attributes(service, operation)
        if attributes:
            expected.update(attributes)

        span_attributes_request_id = "aws.request_id"
        if request_id is _REQUEST_ID_REGEX_MATCH:
            actual_request_id = span.attributes[span_attributes_request_id]
            self.assertRegex(actual_request_id, _REQUEST_ID_REGEX_MATCH)
            expected[span_attributes_request_id] = actual_request_id
        elif request_id is not None:
            expected[span_attributes_request_id] = request_id

        self.assertSpanHasAttributes(span, expected)
        self.assertEqual(f"{service}.{operation}", span.name)
        return span

    @mock_ec2
    def test_traced_client(self) -> None:
        ec2 = self._make_client("ec2")

        async_call(ec2.describe_instances())

        request_id = "fdcdcab1-ae5c-489e-9c33-4637c5dda355"
        self.assert_span("EC2", "DescribeInstances", request_id=request_id)

    @mock_ec2
    def test_not_recording(self) -> None:
        mock_tracer = Mock()
        mock_span = Mock()
        mock_span.is_recording.return_value = False
        mock_tracer.start_span.return_value = mock_span
        with patch("opentelemetry.trace.get_tracer") as tracer:
            tracer.return_value = mock_tracer
            ec2 = self._make_client("ec2")
            async_call(ec2.describe_instances())
            self.assertFalse(mock_span.is_recording())
            self.assertTrue(mock_span.is_recording.called)
            self.assertFalse(mock_span.set_attribute.called)
            self.assertFalse(mock_span.set_status.called)

    @mock_s3
    def test_exception(self) -> None:
        s3_client = self._make_client("s3")

        with self.assertRaises(ParamValidationError):
            async_call(s3_client.list_objects(bucket="mybucket"))

        spans = self.memory_exporter.get_finished_spans()
        self.assertEqual(1, len(spans))
        span = spans[0]

        expected = self._default_span_attributes("S3", "ListObjects")
        expected.pop(SpanAttributes.HTTP_STATUS_CODE)
        expected.pop("retry_attempts")
        self.assertEqual(expected, span.attributes)
        self.assertIs(span.status.status_code, trace_api.StatusCode.ERROR)

        self.assertEqual(1, len(span.events))
        event = span.events[0]
        self.assertIn(SpanAttributes.EXCEPTION_STACKTRACE, event.attributes)
        self.assertIn(SpanAttributes.EXCEPTION_TYPE, event.attributes)
        self.assertIn(SpanAttributes.EXCEPTION_MESSAGE, event.attributes)

    @mock_s3
    def test_s3_client(self) -> None:
        s3_client = self._make_client("s3")

        async_call(s3_client.list_buckets())
        self.assert_span("S3", "ListBuckets")

    @mock_s3
    def test_s3_put(self) -> None:
        s3_client = self._make_client("s3")

        location = {"LocationConstraint": "us-west-2"}
        async_call(
            s3_client.create_bucket(
                Bucket="mybucket", CreateBucketConfiguration=location
            )
        )
        self.assert_span(
            "S3", "CreateBucket", request_id=_REQUEST_ID_REGEX_MATCH
        )
        self.memory_exporter.clear()

        async_call(
            s3_client.put_object(Key="foo", Bucket="mybucket", Body=b"bar")
        )
        self.assert_span("S3", "PutObject", request_id=_REQUEST_ID_REGEX_MATCH)
        self.memory_exporter.clear()

        async_call(s3_client.get_object(Bucket="mybucket", Key="foo"))
        self.assert_span("S3", "GetObject", request_id=_REQUEST_ID_REGEX_MATCH)

    @mock_sqs
    def test_sqs_client(self) -> None:
        sqs = self._make_client("sqs")

        async_call(sqs.list_queues())

        self.assert_span(
            "SQS", "ListQueues", request_id=_REQUEST_ID_REGEX_MATCH
        )

    @mock_sqs
    def test_sqs_send_message(self) -> None:
        sqs = self._make_client("sqs")
        test_queue_name = "test_queue_name"

        response = async_call(sqs.create_queue(QueueName=test_queue_name))
        self.assert_span(
            "SQS", "CreateQueue", request_id=_REQUEST_ID_REGEX_MATCH
        )
        self.memory_exporter.clear()

        queue_url = response["QueueUrl"]
        async_call(
            sqs.send_message(
                QueueUrl=queue_url, MessageBody="Test SQS MESSAGE!"
            )
        )

        self.assert_span(
            "SQS",
            "SendMessage",
            request_id=_REQUEST_ID_REGEX_MATCH,
            attributes={"aws.queue_url": queue_url},
        )

    @mock_kinesis
    def test_kinesis_client(self) -> None:
        kinesis = self._make_client("kinesis")

        async_call(kinesis.list_streams())
        self.assert_span("Kinesis", "ListStreams")

    @mock_kinesis
    def test_unpatch(self) -> None:
        kinesis = self._make_client("kinesis")

        AiobotocoreInstrumentor().uninstrument()

        async_call(kinesis.list_streams())
        self.assertEqual(0, len(self.memory_exporter.get_finished_spans()))

    @mock_ec2
    def test_uninstrument_does_not_inject_headers(self) -> None:
        headers = {}
        previous_propagator = get_global_textmap()
        try:
            set_global_textmap(MockTextMapPropagator())

            def intercept_headers(**kwargs: Any) -> None:
                headers.update(kwargs["request"].headers)

            ec2 = self._make_client("ec2")

            AiobotocoreInstrumentor().uninstrument()

            ec2.meta.events.register_first(
                "before-send.ec2.DescribeInstances", intercept_headers
            )
            with self.tracer_provider.get_tracer("test").start_span("parent"):
                async_call(ec2.describe_instances())

            self.assertNotIn(MockTextMapPropagator.TRACE_ID_KEY, headers)
            self.assertNotIn(MockTextMapPropagator.SPAN_ID_KEY, headers)
        finally:
            set_global_textmap(previous_propagator)

    @mock_sqs
    def test_double_patch(self) -> None:
        sqs = self._make_client("sqs")

        AiobotocoreInstrumentor().instrument()
        AiobotocoreInstrumentor().instrument()

        async_call(sqs.list_queues())
        self.assert_span(
            "SQS", "ListQueues", request_id=_REQUEST_ID_REGEX_MATCH
        )

    @mock_kms
    def test_kms_client(self) -> None:
        kms = self._make_client("kms")

        async_call(kms.list_keys(Limit=21))

        span = self.assert_only_span()
        self.assertEqual(
            self._default_span_attributes("KMS", "ListKeys"), span.attributes
        )

    @mock_sts
    def test_sts_client(self) -> None:
        sts = self._make_client("sts")

        async_call(sts.get_caller_identity())

        span = self.assert_only_span()
        expected = self._default_span_attributes("STS", "GetCallerIdentity")
        expected["aws.request_id"] = "c6104cbe-af31-11e0-8154-cbc7ccf896c7"
        self.assertEqual(expected, span.attributes)

    @mock_ec2
    def test_propagator_injects_into_request(self) -> None:
        headers = {}
        previous_propagator = get_global_textmap()

        def check_headers(**kwargs: Any) -> None:
            nonlocal headers
            headers = kwargs["request"].headers

        try:
            set_global_textmap(MockTextMapPropagator())

            ec2 = self._make_client("ec2")
            ec2.meta.events.register_first(
                "before-send.ec2.DescribeInstances", check_headers
            )
            async_call(ec2.describe_instances())

            request_id = "fdcdcab1-ae5c-489e-9c33-4637c5dda355"
            span = self.assert_span(
                "EC2", "DescribeInstances", request_id=request_id
            )

            self.assertIn(MockTextMapPropagator.TRACE_ID_KEY, headers)
            self.assertEqual(
                str(span.get_span_context().trace_id),
                headers[MockTextMapPropagator.TRACE_ID_KEY],
            )
            self.assertIn(MockTextMapPropagator.SPAN_ID_KEY, headers)
            self.assertEqual(
                str(span.get_span_context().span_id),
                headers[MockTextMapPropagator.SPAN_ID_KEY],
            )

        finally:
            set_global_textmap(previous_propagator)

    @mock_xray
    def test_suppress_instrumentation_xray_client(self) -> None:
        xray_client = self._make_client("xray")
        token = attach(set_value(_SUPPRESS_INSTRUMENTATION_KEY, True))
        try:
            async_call(
                xray_client.put_trace_segments(TraceSegmentDocuments=["str1"])
            )
            async_call(
                xray_client.put_trace_segments(TraceSegmentDocuments=["str2"])
            )
        finally:
            detach(token)
        self.assertEqual(0, len(self.get_finished_spans()))

    @mock_xray
    def test_suppress_http_instrumentation_xray_client(self) -> None:
        xray_client = self._make_client("xray")
        token = attach(set_value(_SUPPRESS_HTTP_INSTRUMENTATION_KEY, True))
        try:
            async_call(
                xray_client.put_trace_segments(TraceSegmentDocuments=["str1"])
            )
            async_call(
                xray_client.put_trace_segments(TraceSegmentDocuments=["str2"])
            )
        finally:
            detach(token)
        self.assertEqual(2, len(self.get_finished_spans()))

    @mock_s3
    def test_request_hook(self) -> None:
        request_hook_service_attribute_name = "request_hook.service_name"
        request_hook_operation_attribute_name = "request_hook.operation_name"
        request_hook_api_params_attribute_name = "request_hook.api_params"

        def request_hook(
            span: Span,
            service_name: str,
            operation_name: str,
            api_params: dict[str, Any],
        ) -> None:
            hook_attributes: dict[str, AttributeValue] = {
                request_hook_service_attribute_name: service_name,
                request_hook_operation_attribute_name: operation_name,
                request_hook_api_params_attribute_name: json.dumps(api_params),
            }

            span.set_attributes(hook_attributes)

        AiobotocoreInstrumentor().uninstrument()
        AiobotocoreInstrumentor().instrument(request_hook=request_hook)

        s3_client = self._make_client("s3")

        params = {
            "Bucket": "mybucket",
            "CreateBucketConfiguration": {"LocationConstraint": "us-west-2"},
        }
        async_call(s3_client.create_bucket(**params))
        self.assert_span(
            "S3",
            "CreateBucket",
            attributes={
                request_hook_service_attribute_name: "s3",
                request_hook_operation_attribute_name: "CreateBucket",
                request_hook_api_params_attribute_name: json.dumps(params),
            },
        )

    @mock_s3
    def test_response_hook(self) -> None:
        response_hook_service_attribute_name = "request_hook.service_name"
        response_hook_operation_attribute_name = "response_hook.operation_name"
        response_hook_result_attribute_name = "response_hook.result"

        def response_hook(
            span: Span,
            service_name: str,
            operation_name: str,
            result: dict[str, Any],
        ) -> None:
            hook_attributes: dict[str, AttributeValue] = {
                response_hook_service_attribute_name: service_name,
                response_hook_operation_attribute_name: operation_name,
                response_hook_result_attribute_name: len(result["Buckets"]),
            }
            span.set_attributes(hook_attributes)

        AiobotocoreInstrumentor().uninstrument()
        AiobotocoreInstrumentor().instrument(response_hook=response_hook)

        s3_client = self._make_client("s3")
        async_call(s3_client.list_buckets())
        self.assert_span(
            "S3",
            "ListBuckets",
            attributes={
                response_hook_service_attribute_name: "s3",
                response_hook_operation_attribute_name: "ListBuckets",
                response_hook_result_attribute_name: 0,
            },
        )
