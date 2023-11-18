from aiobotocore.client import (  # pylint: disable=import-error
    AioBaseClient,
)
from aiobotocore.endpoint import (  # pylint: disable=import-error
    AioEndpoint,
)
from botocore.exceptions import (
    ClientError,
)
from opentelemetry import (
    context as context_api,
)
from opentelemetry.context import (
    _SUPPRESS_HTTP_INSTRUMENTATION_KEY,
    _SUPPRESS_INSTRUMENTATION_KEY,
)
from opentelemetry.instrumentation.botocore import (
    _apply_response_attributes,
    _determine_call_context,
    _safe_invoke,
    BotocoreInstrumentor,
)
from opentelemetry.instrumentation.botocore.extensions import (
    _find_extension,
)
from opentelemetry.instrumentation.utils import (
    unwrap,
)
from opentelemetry.semconv.trace import (
    SpanAttributes,
)
from opentelemetry.util.types import (
    Attributes,
)
from otelcontribs.instrumentation.aiobotocore.package import (
    INSTRUMENTS,
)
from otelcontribs.instrumentation.aiobotocore.version import (
    VERSION,
)
from typing import (
    Any,
    Callable,
    Collection,
    Coroutine,
)
from wrapt import (
    wrap_function_wrapper,
)


class AiobotocoreInstrumentor(BotocoreInstrumentor):
    """An instrumentor for aiobotocore."""

    def instrumentation_dependencies(self) -> Collection[str]:
        return INSTRUMENTS

    def _instrument(self, **kwargs: Any) -> None:
        self._init_instrument(__name__, VERSION, **kwargs)

        wrap_function_wrapper(
            "aiobotocore.client",
            "AioBaseClient._make_api_call",
            self._patched_api_call,
        )

        wrap_function_wrapper(
            "aiobotocore.endpoint",
            "AioEndpoint.prepare_request",
            self._patched_endpoint_prepare_request,
        )

    def _uninstrument(self, **kwargs: None) -> None:
        unwrap(AioBaseClient, "_make_api_call")
        unwrap(AioEndpoint, "prepare_request")

    async def _patched_async_api_call(
        self,
        original_func: Callable[..., Coroutine],
        instance: AioBaseClient,
        args: tuple[str, dict[str, Any]],
        kwargs: dict[str, Any],
    ) -> Any:
        if context_api.get_value(_SUPPRESS_INSTRUMENTATION_KEY):
            return await original_func(*args, **kwargs)

        call_context = _determine_call_context(instance, args)
        if call_context is None:
            return await original_func(*args, **kwargs)

        extension = _find_extension(call_context)
        if not extension.should_trace_service_call():
            return await original_func(*args, **kwargs)

        attributes: Attributes = {
            SpanAttributes.RPC_SYSTEM: "aws-api",
            SpanAttributes.RPC_SERVICE: call_context.service_id,
            SpanAttributes.RPC_METHOD: call_context.operation,
            "aws.region": str(call_context.region),
        }

        _safe_invoke(extension.extract_attributes, attributes)

        with self._tracer.start_as_current_span(
            call_context.span_name,
            kind=call_context.span_kind,
            attributes=attributes,
        ) as span:
            _safe_invoke(extension.before_service_call, span)
            self._call_request_hook(span, call_context)

            token = context_api.attach(
                context_api.set_value(_SUPPRESS_HTTP_INSTRUMENTATION_KEY, True)
            )

            result = None
            try:
                result = await original_func(*args, **kwargs)
            except ClientError as error:
                result = getattr(error, "response", None)
                _apply_response_attributes(span, result)
                _safe_invoke(extension.on_error, span, error)
                raise
            else:
                _apply_response_attributes(span, result)
                _safe_invoke(extension.on_success, span, result)
            finally:
                context_api.detach(token)
                _safe_invoke(extension.after_service_call)

                self._call_response_hook(span, call_context, result)

            return result
