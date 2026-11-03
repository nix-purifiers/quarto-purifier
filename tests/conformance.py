import http.server
import json
import os
from pathlib import Path
import shutil
import subprocess
import tarfile
import tempfile
import threading

repo = Path(__file__).resolve().parent.parent
sdk = Path(
    subprocess.check_output(
        ["nix", "build", str(repo) + "#", "--no-link", "--print-out-paths"], text=True
    ).strip()
)

with tempfile.TemporaryDirectory(prefix="quarto proof with spaces ") as temporary:
    temp = Path(temporary)
    root = temp / "project"
    shutil.copytree(repo / "examples/minimal", root)
    env = dict(
        os.environ,
        XDG_CACHE_HOME=str(temp / "cache"),
        QUARTO_PURIFIER_PROJECT=str(root),
    )

    def call(name, *args, success=True, extra=None, cwd=None):
        result = subprocess.run(
            [sdk / "bin" / name, *args],
            cwd=cwd or root,
            env=dict(env, **(extra or {})),
            text=True,
            capture_output=True,
            timeout=600,
        )
        assert (result.returncode == 0) == success, result
        return result

    lock = root / "quarto-purifier.lock.json"
    declarations = root / "quarto-extensions.json"
    before = lock.read_bytes()
    source = root / "index.qmd"
    original = source.read_text()
    # Neither root nor nested vendored copies may shadow the locked source.
    for location in [
        root / "_extensions/quarto-ext/fontawesome",
        root / "nested/_extensions/quarto-ext/fontawesome",
    ]:
        location.mkdir(parents=True)
        (location / "_extension.yml").write_text(
            "title: poisoned\nversion: 1.0.0\ncontributes:\n  shortcodes: [fontawesome.lua]\n"
        )
        (location / "fontawesome.lua").write_text(
            'error("unlocked extension must not load")\n'
        )
    for value in [42, 43, 42]:
        source.write_text(original.replace("Answer 42", "Answer " + str(value)))
        call("quarto", "render", "index.qmd", "--to", "html")
        html = (root / "index.html").read_text()
        assert "Answer " + str(value) in html and "fa-check" in html
    assert lock.read_bytes() == before

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"42")

        def log_message(self, *args):
            pass

    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    config = root / "_quarto.yml"
    previous_config = config.read_text()
    (root / "network.py").write_text(
        "import urllib.request\nfrom pathlib import Path\n"
        + "Path('network-result').write_bytes(urllib.request.urlopen("
        + repr("http://127.0.0.1:" + str(server.server_port) + "/")
        + ").read())\n"
    )
    config.write_text(
        previous_config.replace(
            "  type: default", "  type: default\n  pre-render: python3 network.py"
        )
    )
    try:
        call("quarto", "render", "index.qmd")
        assert (root / "network-result").read_bytes() == b"42"
    finally:
        config.write_text(previous_config)
        server.shutdown()
        server.server_close()
        (root / "network.py").unlink()
        (root / "network-result").unlink(missing_ok=True)
    nested = root / "nested/nested.qmd"
    nested.write_text(original)
    call("quarto", "render", "nested/nested.qmd", "--to", "html")
    assert "fa-check" in nested.with_suffix(".html").read_text()
    assert (
        "unlocked extension"
        in (root / "_extensions/quarto-ext/fontawesome/fontawesome.lua").read_text()
    )
    profiles = list((temp / "cache/quarto-purifier").glob("*/*/environment-profile"))
    assert len(profiles) == 1
    profile = profiles[0]
    closure = subprocess.check_output(
        ["nix-store", "--query", "--requisites", str(profile.resolve())], text=True
    )
    assert str(sdk) in closure
    output = Path(json.loads(profile.read_text())["output"])
    assert not (output / "extensions").stat().st_mode & 0o222
    for args in [
        ("add", "quarto-ext/fontawesome", "--no-prompt"),
        ("remove", "quarto-ext/fontawesome", "--no-prompt"),
    ]:
        denied = call("quarto", *args, success=False)
        assert "Nix-resolved" in denied.stderr, denied
    declarations.write_text("[]\n")
    assert (
        "selection changed"
        in call("quarto", "render", "index.qmd", success=False).stderr
    )
    declarations.write_text('["quarto-ext/fontawesome"]\n')
    external_lock, external_declarations = (
        temp / "lock.json",
        temp / "declarations.json",
    )
    lock.rename(external_lock)
    declarations.rename(external_declarations)
    external = {
        "QUARTO_PURIFIER_LOCK": str(external_lock),
        "QUARTO_PURIFIER_DECLARATIONS": str(external_declarations),
    }
    call("quarto", "render", "index.qmd", extra=external)
    archive = Path(call("quarto-purifier", "bundle", extra=external).stdout.strip())
    consumer = temp / "consumer"
    consumer.mkdir()
    with tarfile.open(archive) as released:
        released.extractall(consumer, filter="data")
    assert (
        "unlocked extension"
        not in (
            consumer / "_extensions/quarto-ext/fontawesome/fontawesome.lua"
        ).read_text()
    )
    original_expression = (
        "let f=builtins.getFlake "
        + json.dumps(str(repo))
        + ";p=import f.inputs.nixpkgs {};in p.quarto.override {rWrapper=null;python3=null;}"
    )
    ordinary = Path(
        subprocess.check_output(
            [
                "nix",
                "build",
                "--impure",
                "--no-link",
                "--print-out-paths",
                "--expr",
                original_expression,
            ],
            text=True,
        ).strip()
    )
    result = subprocess.run(
        [ordinary / "bin/quarto", "render", "index.qmd"],
        cwd=consumer,
        env=dict(os.environ, XDG_CACHE_HOME=str(temp / "consumer-cache")),
        text=True,
        capture_output=True,
    )
    assert result.returncode == 0, result
    assert "fa-check" in (consumer / "index.html").read_text()
    fake = temp / "fake-gh"
    captured = temp / "publication.json"
    fake.write_text(
        "#!/usr/bin/env python3\nimport json,sys\nfrom pathlib import Path\nPath("
        + repr(str(captured))
        + ").write_text(json.dumps(sys.argv[1:]))\n"
    )
    fake.chmod(0o755)
    call(
        "quarto-purifier",
        "publish",
        "--tag",
        "v-proof",
        extra=dict(external, QUARTO_PURIFIER_GH=str(fake)),
    )
    assert json.loads(captured.read_text()) == [
        "release",
        "upload",
        "v-proof",
        str(archive),
        "--clobber",
    ]
    fallback = temp / "fallback"
    fallback.mkdir()
    result = call(
        "quarto",
        "--version",
        extra={"QUARTO_PURIFIER_PROJECT": str(fallback)},
        cwd=fallback,
    )
    assert "ordinary impure" in result.stderr
    fake.write_text("#!/bin/sh\nprintf native-out\nprintf native-err >&2\nexit 7\n")
    result = subprocess.run(
        ["python3", "-m", "quarto_purifier.cli", "--native"],
        env=dict(
            os.environ,
            PYTHONPATH=str(sdk / "lib/quarto-purifier"),
            QUARTO_PURIFIER_ORIGINAL=str(fake),
            QUARTO_PURIFIER_PROJECT=str(fallback),
        ),
        capture_output=True,
        text=True,
    )
    assert (
        result.returncode == 7
        and result.stdout == "native-out"
        and result.stderr.endswith("native-err")
    ), result

print(
    "Native Quarto edits, immutable extensions, stale selection, private state, release consumer, publication and fallback passed"
)
