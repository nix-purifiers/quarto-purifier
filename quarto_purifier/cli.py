import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile


def run(args, **kwargs):
    result = subprocess.run(args, text=True, capture_output=True, **kwargs)
    if result.returncode:
        raise ValueError(result.stderr or result.stdout)
    return result.stdout


def locate(project=None, lock=None, declarations=None):
    chosen = project or os.environ.get("QUARTO_PURIFIER_PROJECT")
    root = Path(chosen or Path.cwd()).resolve()
    if not chosen:
        for candidate in (root, *root.parents):
            if (candidate / "quarto-extensions.json").exists() or (
                candidate / "quarto-purifier.lock.json"
            ).exists():
                root = candidate
                break
    return (
        root,
        Path(
            lock
            or os.environ.get(
                "QUARTO_PURIFIER_LOCK", root / "quarto-purifier.lock.json"
            )
        ).resolve(),
        Path(
            declarations
            or os.environ.get(
                "QUARTO_PURIFIER_DECLARATIONS", root / "quarto-extensions.json"
            )
        ).resolve(),
    )


def native_environment():
    env = dict(os.environ)
    for key in (
        "QUARTO_PURIFIER_EXTENSIONS",
        "QUARTO_PURIFIER_REPLAY",
        "QUARTO_PURIFIER_CAPTURE",
    ):
        env.pop(key, None)
    if "QUARTO_PURIFIER_ORIGINAL_CACHE" in env:
        original = json.loads(env.pop("QUARTO_PURIFIER_ORIGINAL_CACHE"))
        if original is None:
            env.pop("XDG_CACHE_HOME", None)
        else:
            env["XDG_CACHE_HOME"] = original
    return env


def read_declarations(path):
    data = json.loads(path.read_text())
    if (
        not isinstance(data, list)
        or not all(isinstance(x, str) and x for x in data)
        or len(set(data)) != len(data)
    ):
        raise ValueError(
            "quarto-extensions.json must contain a list of distinct native extension targets"
        )
    return data


def realize(root, lock, declarations):
    data = json.loads(lock.read_text())
    if data.get("sdk") != os.environ["QUARTO_PURIFIER_SDK_VERSION"]:
        raise ValueError("Quarto SDK changed; run quarto-purifier lock --update")
    if data.get("declarations") != read_declarations(declarations):
        raise ValueError(
            "Extension selection changed; run quarto-purifier lock --update"
        )
    sdk = os.environ["QUARTO_PURIFIER_SDK"]
    env = native_environment()
    home = Path(env.get("XDG_CACHE_HOME", str(Path.home() / ".cache")))
    key = hashlib.sha256(str(root).encode()).hexdigest()[:20]
    generation = hashlib.sha256(lock.read_bytes() + sdk.encode()).hexdigest()[:20]
    state = home / "quarto-purifier" / key / generation
    state.mkdir(parents=True, exist_ok=True)
    profile = state / "environment-profile"
    if not profile.exists():
        expression = (
            "import "
            + json.dumps(sdk + "/lib/quarto-purifier/nix/realize.nix")
            + " "
            + nix_arguments(root, lock, declarations, sdk=sdk)
        )
        run(
            [
                "nix",
                "build",
                "--impure",
                "--expr",
                expression,
                "--out-link",
                str(profile),
            ]
        )
    output = Path(json.loads(profile.read_text())["output"])
    if json.loads((output / "manifest.json").read_text())["sdk"] != data["sdk"]:
        raise ValueError("Prepared Quarto SDK differs from the lock")
    return state, output


def nix_arguments(root, lock, declarations, **extra):
    values = dict(
        root=str(root), lockFile=str(lock), declarationsFile=str(declarations), **extra
    )
    return (
        "{"
        + "".join(key + "=" + json.dumps(value) + ";" for key, value in values.items())
        + "}"
    )


def execute(root, lock, declarations, args):
    state, output = realize(root, lock, declarations)
    env = native_environment()
    env["QUARTO_PURIFIER_ORIGINAL_CACHE"] = json.dumps(env.get("XDG_CACHE_HOME"))
    env.update(
        QUARTO_PURIFIER_PROJECT=str(root),
        QUARTO_PURIFIER_LOCK=str(lock),
        QUARTO_PURIFIER_DECLARATIONS=str(declarations),
        QUARTO_PURIFIER_EXTENSIONS=str(output / "extensions"),
        XDG_CACHE_HOME=str(state / "cache"),
    )
    return subprocess.call([os.environ["QUARTO_PURIFIER_CORE"], *args], env=env)


def capture(root, lock, declarations, update):
    targets = read_declarations(declarations)
    if lock.exists() and not update:
        realize(root, lock, declarations)
        return
    with tempfile.TemporaryDirectory(prefix="quarto-capture-") as temporary:
        temp = Path(temporary)
        entries = []
        for index, target in enumerate(targets):
            state = temp / str(index)
            state.mkdir()
            env = native_environment()
            env.update(
                QUARTO_PURIFIER_CAPTURE=str(state), XDG_CACHE_HOME=str(temp / "cache")
            )
            run(
                [os.environ["QUARTO_PURIFIER_CORE"], "add", target, "--no-prompt"],
                cwd=state,
                env=env,
            )
            metadata_file = state / "source.json"
            if not metadata_file.exists():
                raise ValueError(
                    "Use public HTTPS extension archives or GitHub extension targets"
                )
            metadata = json.loads(metadata_file.read_text())
            if not metadata["url"].startswith("https://"):
                raise ValueError("Use public HTTPS extension sources")
            archive = state / "source.archive"
            digest = run(["nix", "hash", "file", "--sri", str(archive)]).strip()
            run(["nix", "store", "add-file", str(archive)])
            entries.append(
                dict(
                    path="archive-" + str(index),
                    url=metadata.pop("url"),
                    hash=digest,
                    mirrors=[],
                    quarto=dict(target=target, **metadata),
                )
            )
        candidate = temp / "quarto-purifier.lock.json"
        candidate.write_text(
            json.dumps(
                dict(
                    version=1,
                    purifier="quarto",
                    sdk=os.environ["QUARTO_PURIFIER_SDK_VERSION"],
                    declarations=targets,
                    entries=entries,
                ),
                indent=2,
                sort_keys=True,
            )
            + "\n"
        )
        # Native replay inside Nix must succeed before publishing the lock.
        realize(root, candidate, declarations)
        lock.parent.mkdir(parents=True, exist_ok=True)
        staged = lock.with_name(lock.name + ".tmp")
        staged.write_bytes(candidate.read_bytes())
        staged.replace(lock)


def main_impl():
    args = sys.argv[1:]
    if args[:1] == ["--native"]:
        root, lock, declarations = locate()
        if not lock.exists():
            print(
                "quarto-purifier: no lockfile; using ordinary impure Quarto extension resolution",
                file=sys.stderr,
            )
            return subprocess.call(
                [os.environ["QUARTO_PURIFIER_ORIGINAL"], *args[1:]],
                env=native_environment(),
            )
        return execute(root, lock, declarations, args[1:])
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "action", choices=["lock", "prefetch", "exec", "bundle", "publish"]
    )
    parser.add_argument("--project", type=Path)
    parser.add_argument("--lock", type=Path)
    parser.add_argument("--declarations", type=Path)
    parser.add_argument("--update", action="store_true")
    parser.add_argument("--tag", default="v0.1.0")
    opts, rest = parser.parse_known_args(args)
    if rest[:1] == ["--"]:
        rest = rest[1:]
    root, lock, declarations = locate(opts.project, opts.lock, opts.declarations)
    if opts.action == "lock":
        capture(root, lock, declarations, opts.update)
    elif opts.action == "prefetch":
        realize(root, lock, declarations)
    elif opts.action == "exec":
        if not rest or Path(rest[0]).name != "quarto":
            raise ValueError("Pass a quarto command after --")
        return execute(root, lock, declarations, rest[1:])
    else:
        realize(root, lock, declarations)
        expression = (
            "import "
            + json.dumps(
                os.environ["QUARTO_PURIFIER_SDK"]
                + "/lib/quarto-purifier/nix/release.nix"
            )
            + " "
            + nix_arguments(root, lock, declarations)
        )
        output = Path(
            run(
                [
                    "nix",
                    "build",
                    "--impure",
                    "--no-link",
                    "--print-out-paths",
                    "--expr",
                    expression,
                ]
            ).strip()
        )
        archive = output / "quarto-project.tar.gz"
        if opts.action == "bundle":
            print(archive)
        else:
            subprocess.run(
                [
                    os.environ["QUARTO_PURIFIER_GH"],
                    "release",
                    "upload",
                    opts.tag,
                    str(archive),
                    "--clobber",
                ],
                cwd=root,
                check=True,
            )
    return 0


def main():
    try:
        raise SystemExit(main_impl())
    except (
        ValueError,
        OSError,
        KeyError,
        TypeError,
        subprocess.SubprocessError,
    ) as error:
        print("quarto-purifier: " + str(error), file=sys.stderr)
        raise SystemExit(1)


if __name__ == "__main__":
    main()
