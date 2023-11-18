import asyncio
from graphql import (
    graphql,
    graphql_sync,
    GraphQLField,
    GraphQLObjectType,
    GraphQLSchema,
    GraphQLString,
)
from graphql.type.definition import (
    GraphQLResolveInfo,
)
from opentelemetry.test.test_base import (
    TestBase,
)
from otelcontribs.instrumentation.graphql_core import (
    GraphQLCoreInstrumentor,
)
from typing import (
    Awaitable,
    TypeVar,
)

T = TypeVar("T")


def async_call(coro: Awaitable[T]) -> T:
    loop = asyncio.get_event_loop()
    return loop.run_until_complete(coro)


class TestGraphQLCoreInstrumentor(TestBase):
    def setUp(self) -> None:
        super().setUp()
        GraphQLCoreInstrumentor().instrument()

    def tearDown(self) -> None:
        super().tearDown()
        GraphQLCoreInstrumentor().uninstrument()

    def test_graphql(self) -> None:
        async def resolve_hello(
            _parent: None, _info: GraphQLResolveInfo
        ) -> str:
            await asyncio.sleep(0)
            return "Hello world!"

        schema = GraphQLSchema(
            query=GraphQLObjectType(
                name="RootQueryType",
                fields={
                    "hello": GraphQLField(GraphQLString, resolve=resolve_hello)
                },
            )
        )

        result = async_call(graphql(schema, "query Test { hello }"))
        self.assertEqual(result.errors, None)
        assert result.data is not None
        self.assertEqual(result.data["hello"], "Hello world!")

        spans = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans), 6)

        parse_span = spans[0]
        self.assertEqual("graphql.parse", parse_span.name)
        self.assertEqual(
            "query Test { hello }", parse_span.attributes["graphql.document"]
        )

        validate_span = spans[1]
        self.assertEqual("graphql.validate", validate_span.name)
        self.assertEqual(
            "query Test { hello }",
            validate_span.attributes["graphql.document"],
        )

        resolve_span = spans[2]
        self.assertEqual("graphql.resolve", resolve_span.name)
        self.assertEqual(
            "hello", resolve_span.attributes["graphql.field.name"]
        )

        execute_span = spans[3]
        self.assertEqual("graphql.execute", execute_span.name)
        self.assertEqual(
            "query Test { hello }", execute_span.attributes["graphql.document"]
        )
        self.assertEqual(
            "query", execute_span.attributes["graphql.operation.type"]
        )
        self.assertEqual(
            "Test", execute_span.attributes["graphql.operation.name"]
        )

        resolve_await_span = spans[4]
        self.assertEqual("graphql.resolve.await", resolve_await_span.name)
        self.assertEqual(
            "hello", resolve_await_span.attributes["graphql.field.name"]
        )

        execute_await_span = spans[5]
        self.assertEqual("graphql.execute.await", execute_await_span.name)
        self.assertEqual(
            "query Test { hello }",
            execute_await_span.attributes["graphql.document"],
        )
        self.assertEqual(
            "query", execute_await_span.attributes["graphql.operation.type"]
        )
        self.assertEqual(
            "Test", execute_await_span.attributes["graphql.operation.name"]
        )

    def test_graphql_sync(self) -> None:
        def resolve_hello(_parent: None, _info: GraphQLResolveInfo) -> str:
            return "Hello world!"

        schema = GraphQLSchema(
            query=GraphQLObjectType(
                name="RootQueryType",
                fields={
                    "hello": GraphQLField(GraphQLString, resolve=resolve_hello)
                },
            )
        )

        result = graphql_sync(schema, "query Test { hello }")
        self.assertEqual(result.errors, None)
        assert result.data is not None
        self.assertEqual(result.data["hello"], "Hello world!")

        spans = self.memory_exporter.get_finished_spans()
        self.assertEqual(len(spans), 4)

        parse_span = spans[0]
        self.assertEqual("graphql.parse", parse_span.name)
        self.assertEqual(
            "query Test { hello }", parse_span.attributes["graphql.document"]
        )

        validate_span = spans[1]
        self.assertEqual("graphql.validate", validate_span.name)
        self.assertEqual(
            "query Test { hello }",
            validate_span.attributes["graphql.document"],
        )

        resolve_span = spans[2]
        self.assertEqual("graphql.resolve", resolve_span.name)
        self.assertEqual(
            "hello", resolve_span.attributes["graphql.field.name"]
        )

        execute_span = spans[3]
        self.assertEqual("graphql.execute", execute_span.name)
        self.assertEqual(
            "query Test { hello }", execute_span.attributes["graphql.document"]
        )
        self.assertEqual(
            "query", execute_span.attributes["graphql.operation.type"]
        )
        self.assertEqual(
            "Test", execute_span.attributes["graphql.operation.name"]
        )
