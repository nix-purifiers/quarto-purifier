{
  lib,
  stdenvNoCC,
  makeWrapper,
  python3,
  nix,
  gh,
  git,
  cacert,
  gnutar,
  gzip,
  unzip,
  original,
  core,
  sdkVersion,
  nixpkgsSrc,
  purifierSrc,
}:
stdenvNoCC.mkDerivation {
  pname = "quarto-purifier";
  version = "0.1.0";
  src = ../..;
  nativeBuildInputs = [ makeWrapper ];
  dontBuild = true;
  installPhase = ''
    mkdir -p "$out/bin" "$out/lib/quarto-purifier"
    cp -r quarto_purifier nix lib-overlays pkgs native "$out/lib/quarto-purifier/"
    install -m755 bin/quarto-purifier "$out/bin/quarto-purifier"
    for file in realize release; do
      substituteInPlace "$out/lib/quarto-purifier/nix/$file.nix" --replace-fail '@nixpkgs@' '${nixpkgsSrc}' --replace-fail '@purifier@' '${purifierSrc}'
    done
    wrapProgram "$out/bin/quarto-purifier" \
      --prefix PATH : ${
        lib.makeBinPath [
          python3
          nix
          gh
          git
          gnutar
          gzip
          unzip
        ]
      } \
      --set-default SSL_CERT_FILE ${cacert}/etc/ssl/certs/ca-bundle.crt \
      --set-default QUARTO_PURIFIER_GH ${gh}/bin/gh \
      --set QUARTO_PURIFIER_ORIGINAL ${original}/bin/quarto \
      --set QUARTO_PURIFIER_CORE ${core}/bin/quarto \
      --set QUARTO_PURIFIER_SDK_VERSION ${sdkVersion} \
      --set QUARTO_PURIFIER_SDK "$out"
    makeWrapper "$out/bin/quarto-purifier" "$out/bin/quarto" --add-flags '--native'
  '';
  meta = {
    description = "Quarto with locked Nix-resolved extensions";
    homepage = "https://nix-purifiers.github.io/";
    license = lib.licenses.mit;
    platforms = [
      "x86_64-linux"
      "aarch64-linux"
    ];
    mainProgram = "quarto-purifier";
  };
}
