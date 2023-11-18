{outputs, ...}: {
  dev = {
    aiobotocore.source = [
      outputs."/otelcontribs/instrumentation/aiobotocore/runtime"
    ];
    graphql_core.source = [
      outputs."/otelcontribs/instrumentation/graphql_core/runtime"
    ];
  };
  lintPython = {
    modules = {
      aiobotocore = {
        searchPaths.source = [
          outputs."/otelcontribs/instrumentation/aiobotocore/runtime"
        ];
        python = "3.11";
        src = "/otelcontribs/instrumentation/aiobotocore";
      };
      graphql_core = {
        searchPaths.source = [
          outputs."/otelcontribs/instrumentation/graphql_core/runtime"
        ];
        python = "3.11";
        src = "/otelcontribs/instrumentation/graphql_core";
      };
    };
  };
}
