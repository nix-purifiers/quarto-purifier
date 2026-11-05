{
  lib,
  runCommand,
  writeText,
  fetchurl,
  fetchgit,
  python3,
  sdkVersion,
  unzip,
  purifier,
  core,
  gnutar,
  gzip,
  ...
}@scope:
{
  src,
  lockFile ? src + "/quarto-purifier.lock.json",
  declarationsFile ? src + "/quarto-extensions.json",
  fetchers ? { },
  resourceRoots ? { },
  resourceDependencies ? [ ],
  quartoArgs ? [ "render" ],
  doCheck ? false,
  checkCommand ? "",
}:
let
  lock = purifier.checkLock (
    import ./read-lock.nix { inherit lib; } { inherit src lockFile declarationsFile; }
  );
  prepared = import ./environment.nix scope { inherit lock fetchers; };
  source = lib.cleanSourceWith {
    inherit src;
    filter =
      path: type:
      !(builtins.elem (baseNameOf path) [
        ".git"
        "result"
        "__pycache__"
        "_site"
        ".quarto"
      ]);
  };
  builtProject = runCommand "quarto-project" { } ''
    cp -r ${source} source
    chmod -R u+w source
    cd source
    export HOME="$TMPDIR/home" XDG_CACHE_HOME="$TMPDIR/cache"
    export QUARTO_PURIFIER_PROJECT="$PWD" QUARTO_PURIFIER_EXTENSIONS=${prepared.output}/extensions
    mkdir -p "$HOME"
    ${core}/bin/quarto ${lib.escapeShellArgs quartoArgs}
    ${lib.optionalString doCheck checkCommand}
    rm -rf .quarto
    mkdir -p "$out"
    cp -r . "$out/"
  '';
  projections = lib.optionalAttrs (resourceRoots != { }) (
    purifier.resourceProjections {
      producer = builtProject;
      roots = resourceRoots;
      dependencies = resourceDependencies;
      inherit runCommand python3;
    }
  );
  project = builtProject // {
    inherit projections;
  };
  release =
    runCommand "quarto-native-release"
      {
        nativeBuildInputs = [
          gnutar
          gzip
        ];
      }
      ''
            test -d ${project}
          cp -r ${source} release-source
          chmod -R u+w release-source
          find release-source -type d -name _extensions -prune -exec rm -rf {} +
          rm -rf release-source/.quarto release-source/_site
          mkdir -p release-source/_extensions
          cp -r ${prepared.output}/extensions/. release-source/_extensions/
        chmod -R u+w release-source
            mkdir -p "$out"
          tar --sort=name --mtime=@1 --owner=0 --group=0 --numeric-owner -czf "$out/quarto-project.tar.gz" -C release-source .
      '';
in
{
  packages = {
    default = project;
    inherit project;
    environment = prepared.output;
  };
  tests = project;
  inherit release projections;
  fetches = lock.entries;
}
