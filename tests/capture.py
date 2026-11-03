import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile

repo = Path(__file__).resolve().parent.parent
sdk = Path(
    subprocess.check_output(
        ["nix", "build", str(repo) + "#", "--no-link", "--print-out-paths"], text=True
    ).strip()
)
with tempfile.TemporaryDirectory(prefix="quarto capture ") as temporary:
    temp = Path(temporary)
    root = temp / "project"
    shutil.copytree(repo / "examples/minimal", root)
    lock = root / "quarto-purifier.lock.json"
    lock.unlink()
    env = dict(
        os.environ,
        XDG_CACHE_HOME=str(temp / "cache"),
        QUARTO_PURIFIER_PROJECT=str(root),
    )

    def capture(*args, success=True):
        result = subprocess.run(
            [sdk / "bin/quarto-purifier", "lock", *args],
            env=env,
            text=True,
            capture_output=True,
            timeout=600,
        )
        assert (result.returncode == 0) == success, result
        return result

    capture()
    before = lock.read_bytes()
    data = json.loads(before)
    assert (
        len(data["entries"]) == 1
        and data["entries"][0]["quarto"]["owner"] == "quarto-ext"
    )
    assert not (root / "_extensions").exists()
    capture()
    assert before == lock.read_bytes()
    declarations = root / "quarto-extensions.json"
    declarations.write_text('["https://example.invalid/missing-extension.tar.gz"]\n')
    capture("--update", success=False)
    assert before == lock.read_bytes()
    declarations.write_text("[]\n")
    capture("--update")
    assert json.loads(lock.read_text())["entries"] == []
    capture()
print(
    "Native Quarto capture, stable locks, failed capture atomicity and empty extension set passed"
)
