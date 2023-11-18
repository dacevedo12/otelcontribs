{
  makePythonPypiEnvironment,
  makeTemplate,
  projectPath,
  ...
}: let
  pythonRequirements = makePythonPypiEnvironment {
    name = "graphql-core-runtime";
    sourcesYaml = ./sources.yaml;
  };
in
  makeTemplate {
    name = "graphql-core-runtime";
    searchPaths = {
      source = [pythonRequirements];
      pythonPackage = [(projectPath "/")];
    };
  }
