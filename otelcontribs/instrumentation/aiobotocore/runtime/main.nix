{
  makePythonPypiEnvironment,
  makeTemplate,
  projectPath,
  ...
}: let
  pythonRequirements = makePythonPypiEnvironment {
    name = "aiobotocore-runtime";
    sourcesYaml = ./sources.yaml;
  };
in
  makeTemplate {
    name = "aiobotocore-runtime";
    searchPaths = {
      source = [pythonRequirements];
      pythonPackage = [(projectPath "/")];
    };
  }
