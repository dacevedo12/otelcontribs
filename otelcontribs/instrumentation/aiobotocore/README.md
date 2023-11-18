# OpenTelemetry Instrumentation for aiobotocore

[![PyPI version](https://badge.fury.io/py/otelcontribs-instrumentation-aiobotocore.svg)](https://badge.fury.io/py/otelcontribs-instrumentation-aiobotocore)

This library allows tracing service requests performed by [aiobotocore](https://pypi.org/project/aiobotocore).

## Installation

```bash
pip install otelcontribs-instrumentation-aiobotocore
```

## Usage

Programmatically enable instrumentation via the following code:

```python
    from otelcontribs.instrumentation.aiobotocore import AiobotocoreInstrumentor
    import aiobotocore.session


    # Instrument aiobotocore
    AiobotocoreInstrumentor().instrument()

    # This will create a span with aiobotocore-specific attributes
    session = aiobotocore.session.get_session()
    session.set_credentials(access_key="access-key", secret_key="secret-key")

    with session.create_client("ec2", region_name="us-west-2") as ec2:
        await ec2.describe_instances()
```

## API

The `instrument` method accepts the following keyword args:

- tracer_provider (TracerProvider) - an optional tracer provider
- request_hook (Callable) - a function with extra user-defined logic to be performed before performing the request
- response_hook (Callable) - a function with extra user-defined logic to be performed after performing the request

for example:

```python
    from otelcontribs.instrumentation.aiobotocore import AiobotocoreInstrumentor
    import aiobotocore.session

    def request_hook(span, service_name, operation_name, api_params):
        # request hook logic

    def response_hook(span, service_name, operation_name, result):
        # response hook logic

    # Instrument aiobotocore with hooks
    AiobotocoreInstrumentor().instrument(request_hook=request_hook, response_hook=response_hook)

    # This will create a span with aiobotocore-specific attributes, including custom attributes added from the hooks
    session = aiobotocore.session.get_session()
    session.set_credentials(access_key="access-key", secret_key="secret-key")

    with session.create_client("ec2", region_name="us-west-2") as ec2:
        await ec2.describe_instances()
```