# OpenTelemetry Instrumentation for graphql-core

[![PyPI version](https://badge.fury.io/py/otelcontribs-instrumentation-graphql-core.svg)](https://badge.fury.io/py/otelcontribs-instrumentation-graphql-core)

This library allows tracing the parsing, validation and execution of queries performed by [graphql-core](https://pypi.org/project/graphql-core).

## Installation

```bash
pip install otelcontribs-instrumentation-graphql-core
```

## Usage

Programmatically enable instrumentation via the following code:

```python
    # Instrument GraphQL-core
    from otelcontribs.instrumentation.graphql_core import GraphQLCoreInstrumentor

    GraphQLCoreInstrumentor().instrument()

    # This will create a span with GraphQL-specific attributes
    from graphql import (
        GraphQLField,
        GraphQLObjectType,
        GraphQLSchema,
        GraphQLString,
        graphql,
    )

    def resolve_hello(parent, info):
        return "Hello world!"

    schema = GraphQLSchema(
        query=GraphQLObjectType(
            name="RootQueryType",
            fields={
                "hello": GraphQLField(GraphQLString, resolve=resolve_hello)
            },
        )
    )

    await graphql(schema, "{ hello }")
```

## API

The `instrument` method accepts the following keyword args:

- tracer_provider (TracerProvider) - an optional tracer provider
- skip_default_resolvers (Boolean) - whether to skip spans for default resolvers. True by default
- skip_introspection_query (Boolean) - whether to skip introspection queries. True by default

for example:

```python
    # Instrument GraphQL-core
    from otelcontribs.instrumentation.graphql_core import GraphQLCoreInstrumentor

    GraphQLCoreInstrumentor().instrument(
        skip_default_resolvers=False,
        skip_introspection_query=False,
    )
```
