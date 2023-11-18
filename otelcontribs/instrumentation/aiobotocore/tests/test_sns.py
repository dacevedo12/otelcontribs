from aiobotocore.awsrequest import (  # pylint: disable=import-error
    AioAWSResponse,
)
import aiobotocore.session  # pylint: disable=import-error
import asyncio
import contextlib
from moto import (
    mock_sns,
)
from opentelemetry.semconv.trace import (
    MessagingDestinationKindValues,
    SpanAttributes,
)
from opentelemetry.test.test_base import (
    TestBase,
)
from opentelemetry.trace import (
    SpanKind,
)
from opentelemetry.trace.span import (
    Span as SpanBase,
)
from otelcontribs.instrumentation.aiobotocore import (
    AiobotocoreInstrumentor,
)
from typing import (
    Any,
    Awaitable,
    Callable,
    Dict,
    Generator,
    TypeVar,
)
from unittest import (
    mock,
)


class Span(SpanBase):
    attributes: dict[str, str]


T = TypeVar("T")


def async_call(coro: Awaitable[T]) -> T:
    loop = asyncio.get_event_loop()
    return loop.run_until_complete(coro)


class TestSnsExtension(TestBase):
    def setUp(self) -> None:
        super().setUp()
        AiobotocoreInstrumentor().instrument()

        session = aiobotocore.session.get_session()
        session.set_credentials(
            access_key="access-key", secret_key="secret-key"
        )
        self.client = async_call(
            # pylint: disable=unnecessary-dunder-call
            session.create_client("sns", region_name="us-west-2").__aenter__()
        )
        self.topic_name = "my-topic"

    def tearDown(self) -> None:
        super().tearDown()
        AiobotocoreInstrumentor().uninstrument()

    def _create_topic(self, name: str | None = None) -> str:
        if name is None:
            name = self.topic_name

        response = async_call(self.client.create_topic(Name=name))

        self.memory_exporter.clear()
        return response["TopicArn"]

    @contextlib.contextmanager
    def _mocked_aws_endpoint(self, response: AioAWSResponse) -> Generator:
        response_func = self._make_aws_response_func(response)
        with mock.patch(
            "aiobotocore.endpoint.AioEndpoint.make_request", new=response_func
        ):
            yield

    @staticmethod
    def _make_aws_response_func(
        response: AioAWSResponse,
    ) -> Callable[..., Awaitable[tuple[AioAWSResponse, AioAWSResponse]]]:
        async def _response_func(
            *_args: Any, **_kwargs: Any
        ) -> tuple[AioAWSResponse, AioAWSResponse]:
            return AioAWSResponse("http://127.0.0.1", 200, {}, "{}"), response

        return _response_func

    def assert_span(self, name: str) -> Span:
        spans = self.memory_exporter.get_finished_spans()
        self.assertEqual(1, len(spans))
        span = spans[0]

        self.assertEqual(SpanKind.PRODUCER, span.kind)
        self.assertEqual(name, span.name)
        self.assertEqual(
            "aws.sns", span.attributes[SpanAttributes.MESSAGING_SYSTEM]
        )

        return span

    def assert_injected_span(
        self, message_attrs: Dict[str, Any], span: Span
    ) -> None:
        # traceparent: <ver>-<trace-id>-<span-id>-<flags>
        trace_parent = message_attrs["traceparent"]["StringValue"].split("-")
        span_context = span.get_span_context()

        self.assertEqual(span_context.trace_id, int(trace_parent[1], 16))
        self.assertEqual(span_context.span_id, int(trace_parent[2], 16))

    @mock_sns
    def test_publish_to_topic_arn(self) -> None:
        self._test_publish_to_arn("TopicArn")

    @mock_sns
    def test_publish_to_target_arn(self) -> None:
        self._test_publish_to_arn("TargetArn")

    def _test_publish_to_arn(self, arg_name: str) -> None:
        target_arn = self._create_topic(self.topic_name)

        async_call(
            self.client.publish(
                **{
                    arg_name: target_arn,
                    "Message": "Hello message",
                }
            )
        )

        span = self.assert_span(f"{self.topic_name} send")
        self.assertEqual(
            MessagingDestinationKindValues.TOPIC.value,
            span.attributes[SpanAttributes.MESSAGING_DESTINATION_KIND],
        )
        self.assertEqual(
            self.topic_name,
            span.attributes[SpanAttributes.MESSAGING_DESTINATION],
        )
        self.assertEqual(
            target_arn,
            span.attributes[SpanAttributes.MESSAGING_DESTINATION_NAME],
        )

    @mock_sns
    def test_publish_to_phone_number(self) -> None:
        phone_number = "+10000000000"
        async_call(
            self.client.publish(
                PhoneNumber=phone_number,
                Message="Hello SNS",
            )
        )

        span = self.assert_span("phone_number send")
        self.assertEqual(
            phone_number, span.attributes[SpanAttributes.MESSAGING_DESTINATION]
        )

    @mock_sns
    def test_publish_injects_span(self) -> None:
        message_attrs: dict[str, Any] = {}
        topic_arn = self._create_topic()
        async_call(
            self.client.publish(
                TopicArn=topic_arn,
                Message="Hello Message",
                MessageAttributes=message_attrs,
            )
        )

        span = self.assert_span(f"{self.topic_name} send")
        self.assert_injected_span(message_attrs, span)

    def test_publish_batch_to_topic(self) -> None:
        topic_arn = f"arn:aws:sns:region:000000000:{self.topic_name}"
        message1_attrs: dict[str, Any] = {}
        message2_attrs: dict[str, Any] = {}
        mock_response = {
            "Successful": [
                {"Id": "1", "MessageId": "11", "SequenceNumber": "1"},
                {"Id": "2", "MessageId": "22", "SequenceNumber": "2"},
            ],
            "Failed": [],
        }

        # publish_batch not implemented by moto so mock the endpoint instead
        with self._mocked_aws_endpoint(mock_response):
            async_call(
                self.client.publish_batch(
                    TopicArn=topic_arn,
                    PublishBatchRequestEntries=[
                        {
                            "Id": "1",
                            "Message": "Hello message 1",
                            "MessageAttributes": message1_attrs,
                        },
                        {
                            "Id": "2",
                            "Message": "Hello message 2",
                            "MessageAttributes": message2_attrs,
                        },
                    ],
                )
            )

        span = self.assert_span(f"{self.topic_name} send")
        self.assertEqual(
            MessagingDestinationKindValues.TOPIC.value,
            span.attributes[SpanAttributes.MESSAGING_DESTINATION_KIND],
        )
        self.assertEqual(
            self.topic_name,
            span.attributes[SpanAttributes.MESSAGING_DESTINATION],
        )
        self.assertEqual(
            topic_arn,
            span.attributes[SpanAttributes.MESSAGING_DESTINATION_NAME],
        )

        self.assert_injected_span(message1_attrs, span)
        self.assert_injected_span(message2_attrs, span)
