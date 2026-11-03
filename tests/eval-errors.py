import copy
import json
from pathlib import Path
import shutil
import subprocess
import tempfile

repo = Path(__file__).resolve().parent.parent
with tempfile.TemporaryDirectory() as temporary:
    root = Path(temporary) / "project"
    shutil.copytree(repo / "examples/minimal", root)
    lock = root / "quarto-purifier.lock.json"
    original = json.loads(lock.read_text())

    def inspect():
        expression = (
            "let f=builtins.getFlake "
            + json.dumps(str(repo))
            + ";lock=f.lib.quarto-purifier.readLock {src=/. + "
            + json.dumps(str(root))
            + ";};in {inherit(lock)problems outputs;}"
        )
        return json.loads(
            subprocess.check_output(
                [
                    "nix",
                    "eval",
                    "--impure",
                    "--json",
                    "--option",
                    "allow-import-from-derivation",
                    "false",
                    "--expr",
                    expression,
                ],
                text=True,
            )
        )

    assert inspect()["problems"] == []
    assert inspect()["outputs"]["packages"] == ["default", "environment", "project"]
    (root / "index.qmd").write_text("Edited native document\n")
    assert inspect()["problems"] == []
    lock.unlink()
    assert inspect()["problems"]
    for mutate in [
        lambda d: d.update(purifier="other"),
        lambda d: d["entries"][0].update(path="../escape"),
        lambda d: d["entries"][0].update(hash="invalid"),
        lambda d: d["entries"][0]["quarto"].update(filename="../escape"),
        lambda d: d["entries"][0]["quarto"].update(targetSubdir="../escape"),
        lambda d: d["entries"][0]["quarto"].pop("owner"),
        lambda d: d.update(sdk=None),
    ]:
        data = copy.deepcopy(original)
        mutate(data)
        lock.write_text(json.dumps(data))
        assert inspect()["problems"]
    lock.write_text(json.dumps(original))
    (root / "quarto-extensions.json").write_text("[]\n")
    assert inspect()["problems"]
print("Quarto lock errors and output names validated without IFD")
