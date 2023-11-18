{fetchNixpkgs, ...}: {
  extendingMakesDirs = ["/"];
  formatNix = {
    enable = true;
    targets = ["/"];
  };
  formatPython = {
    default = {
      targets = ["/"];
    };
  };
  imports = [./otelcontribs/makes.nix];
}
