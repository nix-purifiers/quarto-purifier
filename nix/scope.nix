{
  pkgs,
  nixpkgsSrc,
  purifierSrc,
}:
pkgs.lib.makeScope pkgs.newScope (scope: {
  original = pkgs.quarto.override {
    rWrapper = null;
    python3 = null;
  };
  core = scope.original.overrideAttrs (old: {
    postInstall = (old.postInstall or "") + ''
      ${pkgs.patch}/bin/patch -d "$out" -p1 < ${../native/extensions.patch}
    '';
  });
  purifier = import (purifierSrc + "/nix/lib") { inherit (pkgs) lib; };
  sdkVersion = builtins.hashString "sha256" (
    builtins.toJSON {
      nixpkgs = toString nixpkgsSrc;
      patch = builtins.hashFile "sha256" ../native/extensions.patch;
    }
  );
  cli = scope.callPackage ./cli.nix { inherit nixpkgsSrc purifierSrc; };
  buildQuartoProject = scope.callPackage ./build-project.nix { };
})
