{ lib }:
{
  src,
  lockFile ? src + "/quarto-purifier.lock.json",
  declarationsFile ? src + "/quarto-extensions.json",
}:
let
  read = path: if builtins.pathExists path then builtins.fromJSON (builtins.readFile path) else null;
  raw = read lockFile;
  data = if builtins.isAttrs raw then raw else { };
  entries = data.entries or [ ];
  declarations = read declarationsFile;
  component =
    s:
    builtins.isString s
    && builtins.match "[A-Za-z0-9_.+-]+" s != null
    && !(builtins.elem s [
      "."
      ".."
    ]);
  valid =
    (data.version or null) == 1
    && (data.purifier or null) == "quarto"
    && builtins.isString (data.sdk or null)
    && builtins.isList declarations
    && builtins.all builtins.isString declarations
    && builtins.length (lib.unique declarations) == builtins.length declarations
    && (data.declarations or null) == declarations
    && builtins.isList entries
    && builtins.length entries == builtins.length declarations
    && builtins.all (
      entry:
      builtins.isAttrs entry
      && component (entry.path or null)
      && builtins.isString (entry.url or null)
      && lib.hasPrefix "https://" entry.url
      && builtins.isString (entry.hash or null)
      && builtins.match "sha256-[A-Za-z0-9+/]{43}=" entry.hash != null
      && builtins.isList (entry.mirrors or null)
      && builtins.all builtins.isString entry.mirrors
      && builtins.isAttrs (entry.quarto or null)
      && builtins.isString (entry.quarto.target or null)
      && component (entry.quarto.filename or null)
      && entry.quarto ? owner
      && entry.quarto ? targetSubdir
      && (entry.quarto.owner == null || component entry.quarto.owner)
      && (
        entry.quarto.targetSubdir == null
        || (
          builtins.isString entry.quarto.targetSubdir
          && !(lib.hasPrefix "/" entry.quarto.targetSubdir)
          && builtins.all component (lib.splitString "/" entry.quarto.targetSubdir)
        )
      )
    ) entries
    && map (entry: entry.quarto.target) entries == declarations
    && builtins.length (lib.unique (map (entry: entry.path) entries)) == builtins.length entries;
in
{
  purifier = "quarto";
  inherit data entries;
  problems = lib.optional (
    !valid
  ) "Quarto lock is missing, malformed, or stale; run quarto-purifier lock --update";
  outputs = {
    packages = [
      "default"
      "environment"
      "project"
    ];
    tests = [ "default" ];
    release = [ "default" ];
  };
}
