{
  root,
  lockFile,
  declarationsFile,
}:
let
  nixpkgsSrc = /. + "@nixpkgs@";
  pkgs = import nixpkgsSrc { };
  scope = import ./scope.nix {
    inherit pkgs nixpkgsSrc;
    purifierSrc = /. + "@purifier@";
  };
in
(scope.buildQuartoProject {
  src = /. + root;
  lockFile = /. + lockFile;
  declarationsFile = /. + declarationsFile;
}).release
