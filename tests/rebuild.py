from pathlib import Path
import subprocess

repo = Path(__file__).resolve().parent.parent
system = subprocess.check_output(
    ["nix", "eval", "--impure", "--raw", "--expr", "builtins.currentSystem"], text=True
).strip()
subprocess.run(
    [
        "nix",
        "build",
        "--rebuild",
        "--no-link",
        str(repo) + "#checks." + system + ".environment",
    ],
    check=True,
)
print("Native Quarto extension installation rebuilt identically")
