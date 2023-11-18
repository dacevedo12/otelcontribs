{outputs, ...}: {
  dev = {
    aiobotocore.source = [
      outputs."/otelcontribs/instrumentation/aiobotocore/runtime"
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
    };
  };
}
