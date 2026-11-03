{
  lib,
  runCommand,
  writeText,
  fetchurl,
  fetchgit,
  python3,
  purifier,
  core,
  sdkVersion,
  gnutar,
  gzip,
  unzip,
  ...
}:
{
  lock,
  fetchers ? { },
}:
let
  checked = purifier.checkLock lock;
  tree = purifier.tree (
    {
      name = "quarto-archives";
      inherit
        runCommand
        fetchurl
        fetchgit
        writeText
        python3
        ;
      entries = checked.entries;
    }
    // fetchers
  );
  replay = writeText "quarto-replay.json" (
    builtins.toJSON (
      builtins.listToAttrs (
        map (entry: {
          name = entry.quarto.target;
          value = entry.quarto // {
            archive = "${tree}/${entry.path}";
          };
        }) lock.entries
      )
    )
  );
  output =
    runCommand "quarto-locked-extensions"
      {
        nativeBuildInputs = [
          gnutar
          gzip
          unzip
        ];
      }
      ''
        export HOME="$TMPDIR/home" XDG_CACHE_HOME="$TMPDIR/cache"
        mkdir -p "$HOME" work
        cd work
        export QUARTO_PURIFIER_REPLAY=${replay}
        ${lib.concatMapStringsSep "\n" (
          target: "${core}/bin/quarto add ${lib.escapeShellArg target} --no-prompt"
        ) lock.data.declarations}
        mkdir -p "$out/extensions"
        if [ -d _extensions ]; then cp -r _extensions/. "$out/extensions/"; fi
        cp ${
          writeText "quarto-manifest.json" (builtins.toJSON { sdk = lock.data.sdk; })
        } "$out/manifest.json"
      '';
in
assert lib.assertMsg (
  lock.data.sdk == sdkVersion
) "Quarto SDK changed; run quarto-purifier lock --update";
{
  inherit output tree;
}
