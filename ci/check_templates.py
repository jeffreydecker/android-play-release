#!/usr/bin/env python3
"""Checks the skills and their templates without needing an Android project.

    python3 ci/check_templates.py skills      # SKILL.md frontmatter, links, placeholders
    python3 ci/check_templates.py workflow    # renders release.yml, then runs actionlint on it
    python3 ci/check_templates.py gradle      # renders both Gradle templates, runs real builds

Standard library only. `workflow` needs actionlint (and shellcheck, which actionlint uses for
`run:` scripts) on PATH; `gradle` needs `gradle` on PATH, or GRADLE pointing at one.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SKILLS = ROOT / "skills"
SETUP = SKILLS / "play-release-setup"
TEMPLATES = SETUP / "templates"

PLACEHOLDER = re.compile(r"__[A-Z][A-Z0-9_]*__")
errors: list[str] = []


def fail(where: Path | str, message: str) -> None:
    where = where.relative_to(ROOT) if isinstance(where, Path) else where
    errors.append(f"{where}: {message}")


# --------------------------------------------------------------------------------------------
# skills: SKILL.md frontmatter, relative links, and placeholders the instructions must cover
# --------------------------------------------------------------------------------------------

# Frontmatter keys the Agent Skills format defines. Anything else is most likely a typo.
ALLOWED_KEYS = {"name", "description", "license", "allowed-tools", "metadata", "compatibility"}
NAME = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")


def parse_frontmatter(path: Path) -> tuple[dict[str, str], str] | None:
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---\n"):
        fail(path, "must start with a '---' frontmatter block")
        return None
    end = text.find("\n---\n", 4)
    if end < 0:
        fail(path, "frontmatter block is never closed with '---'")
        return None
    fields: dict[str, str] = {}
    for number, line in enumerate(text[4:end].splitlines(), start=2):
        if not line.strip() or line.startswith((" ", "\t", "#")):
            continue  # nested values (metadata) and comments
        key, sep, value = line.partition(":")
        if not sep:
            fail(path, f"line {number}: expected 'key: value', got {line!r}")
            continue
        key, value = key.strip(), value.strip()
        if key in fields:
            fail(path, f"line {number}: duplicate key {key!r}")
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "'\"":
            value = value[1:-1]
        elif value.startswith(("'", '"')):
            fail(path, f"line {number}: unterminated quote in {key!r}")
        elif ": " in value or value.endswith(":") or " #" in value:
            # Plain YAML scalars cannot contain ': ' or ' #'; a parser would reject or truncate.
            fail(path, f"line {number}: quote the value of {key!r}; it contains ': ' or ' #'")
        fields[key] = value
    return fields, text[end + 5:]


def check_skill(skill_md: Path) -> None:
    parsed = parse_frontmatter(skill_md)
    if parsed is None:
        return
    fields, body = parsed
    directory = skill_md.parent.name

    for key in fields.keys() - ALLOWED_KEYS:
        fail(skill_md, f"unknown frontmatter key {key!r}")

    name = fields.get("name", "")
    if not name:
        fail(skill_md, "frontmatter needs a name")
    else:
        if name != directory:
            fail(skill_md, f"name {name!r} must match its directory {directory!r}")
        if len(name) > 64 or not NAME.match(name):
            fail(skill_md, f"name {name!r} must be lowercase words joined by hyphens, max 64")
        if "claude" in name or "anthropic" in name:
            fail(skill_md, f"name {name!r} must not contain 'claude' or 'anthropic'")

    description = fields.get("description", "")
    if not description:
        fail(skill_md, "frontmatter needs a description")
    elif len(description) > 1024:
        fail(skill_md, f"description is {len(description)} characters; the limit is 1024")
    elif "<" in description or ">" in description:
        fail(skill_md, "description must not contain angle brackets")

    if not body.strip():
        fail(skill_md, "has no instructions after the frontmatter")


def github_slug(heading: str) -> str:
    heading = re.sub(r"[`*_]|\[([^\]]*)\]\([^)]*\)", r"\1", heading.strip().lower())
    return re.sub(r"[^\w\- ]", "", heading).replace(" ", "-")


def anchors(path: Path) -> set[str]:
    found: set[str] = set()
    counts: dict[str, int] = {}
    in_code = False
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.lstrip().startswith("```"):
            in_code = not in_code
        elif not in_code and (match := re.match(r"#{1,6}\s+(.*?)\s*#*$", line)):
            slug = github_slug(match.group(1))
            n = counts.get(slug, 0)
            counts[slug] = n + 1
            found.add(slug if n == 0 else f"{slug}-{n}")
    return found


MD_LINK = re.compile(r"\[[^\]]*\]\(([^)\s]+)(?:\s+\"[^\"]*\")?\)")
# Paths the instructions name in backticks, such as `references/play-console.md`.
CODE_PATH = re.compile(r"`((?:templates|references)/[\w./-]*)`")


def strip_code_blocks(text: str) -> str:
    return re.sub(r"^\s*```.*?^\s*```", "", text, flags=re.S | re.M)


def check_links(md: Path) -> None:
    text = strip_code_blocks(md.read_text(encoding="utf-8"))
    for target in MD_LINK.findall(text):
        if re.match(r"[a-z][a-z0-9+.-]*:", target):
            continue  # https:, mailto:, ...
        file_part, _, anchor = target.partition("#")
        resolved = (md.parent / file_part).resolve() if file_part else md
        if not resolved.exists():
            fail(md, f"link target {target!r} does not exist")
        elif anchor and resolved.suffix == ".md" and anchor not in anchors(resolved):
            fail(md, f"link {target!r}: no heading in {resolved.name} has the anchor #{anchor}")

    if md.name == "SKILL.md":
        for path in CODE_PATH.findall(text):
            # play-release names files that ship with play-release-setup, so accept any skill.
            if not any((skill / path).exists() for skill in SKILLS.iterdir()):
                fail(md, f"names `{path}`, which no skill directory contains")


def check_placeholders() -> None:
    instructions = (SETUP / "SKILL.md").read_text(encoding="utf-8")
    documented = set(PLACEHOLDER.findall(instructions))
    used: set[str] = set()
    for template in sorted(p for p in TEMPLATES.rglob("*") if p.is_file()):
        tokens = set(PLACEHOLDER.findall(template.read_text(encoding="utf-8")))
        used |= tokens
        for token in sorted(tokens - documented):
            fail(template, f"{token} is never mentioned in play-release-setup/SKILL.md, so "
                           "nothing tells the agent to fill it")
    for token in sorted(documented - used):
        fail(SETUP / "SKILL.md", f"mentions {token}, which no template contains")


def check_skills() -> None:
    skill_files = sorted(SKILLS.glob("*/SKILL.md"))
    if not skill_files:
        fail(SKILLS, "no */SKILL.md found")
    for directory in sorted(p for p in SKILLS.iterdir() if p.is_dir()):
        if not (directory / "SKILL.md").exists():
            fail(directory, "skill directory has no SKILL.md")
    for skill_md in skill_files:
        check_skill(skill_md)
    for md in sorted([ROOT / "README.md", *SKILLS.rglob("*.md")]):
        check_links(md)
    check_placeholders()


# --------------------------------------------------------------------------------------------
# workflow: fill release.yml the way SKILL.md says to, then lint every variant
# --------------------------------------------------------------------------------------------

WORKFLOW_VALUES = {
    "__JAVA_VERSION__": "21",
    "__MODULE_PATH__": ":app",
    "__MODULE_DIR__": "app",
    "__BUNDLE_TASK__": "bundleProdRelease",
    "__VARIANT__": "prodRelease",
    "__PACKAGE_NAME__": "com.example.app",
    "__ENVIRONMENT__": "play-release",
    "__GOOGLE_SERVICES_PATH__": "app/google-services.json",
}
PINNED_USE = re.compile(r"^\s*(?:-\s+)?uses:\s*([\w.-]+/[\w./-]+)@([0-9a-f]{40})\s+#\s*v\d")


def render_workflow(template: str, *, environment: bool, restore: bool) -> str:
    lines = template.splitlines(keepends=True)
    out: list[str] = []
    in_restore = False
    for line in lines:
        if "__RESTORE_FILES_BEGIN__" in line:
            in_restore = True
            continue
        if "__RESTORE_FILES_END__" in line:
            in_restore = False
            continue
        if in_restore and not restore:
            continue
        if "__ENVIRONMENT__" in line and not environment:
            # "delete that line and the comment above it"
            while out and out[-1].lstrip().startswith("#"):
                out.pop()
            continue
        out.append(line)
    text = "".join(out)
    for token, value in WORKFLOW_VALUES.items():
        text = text.replace(token, value)
    return text


def check_workflow() -> None:
    template_path = TEMPLATES / "release.yml"
    template = template_path.read_text(encoding="utf-8")

    for number, line in enumerate(template.splitlines(), start=1):
        if re.match(r"^\s*(?:-\s+)?uses:", line) and not PINNED_USE.match(line):
            fail(template_path, f"line {number}: actions must be pinned to a full commit SHA "
                                f"with a '# vX' comment: {line.strip()}")

    for marker in ("__RESTORE_FILES_BEGIN__", "__RESTORE_FILES_END__"):
        if template.count(marker) != 1:
            fail(template_path, f"expected exactly one {marker}")

    actionlint = shutil.which("actionlint")
    if actionlint is None:
        fail("workflow", "actionlint is not on PATH")
        return
    if shutil.which("shellcheck") is None:
        fail("workflow", "shellcheck is not on PATH; actionlint would skip run: scripts")
        return

    with tempfile.TemporaryDirectory() as tmp:
        workflows = Path(tmp) / ".github" / "workflows"
        workflows.mkdir(parents=True)
        for environment in (True, False):
            for restore in (True, False):
                name = f"release-env-{environment}-restore-{restore}.yml".lower()
                rendered = render_workflow(template, environment=environment, restore=restore)
                left = sorted(set(PLACEHOLDER.findall(rendered)))
                if left:
                    fail(template_path, f"{name}: filling it as SKILL.md describes leaves "
                                        f"{', '.join(left)}")
                if ("environment:" in rendered) != environment:
                    fail(template_path, f"{name}: environment line handled incorrectly")
                (workflows / name).write_text(rendered, encoding="utf-8")
        files = sorted(str(p) for p in workflows.iterdir())
        result = subprocess.run([actionlint, "-no-color", "-oneline", *files], cwd=tmp,
                                capture_output=True, text=True)
        if result.returncode != 0:
            for line in (result.stdout + result.stderr).strip().splitlines():
                fail(template_path, f"actionlint: {line}")
        else:
            print(f"actionlint passed on {len(files)} rendered variants")


# --------------------------------------------------------------------------------------------
# gradle: run each Gradle template's top-level section in a real (Android-free) build
# --------------------------------------------------------------------------------------------

SIGNING_ENV = ("KEYSTORE_FILE", "KEYSTORE_PASSWORD", "KEY_ALIAS", "KEY_PASSWORD")
ALL_ENV = dict(zip(SIGNING_ENV, ("/tmp/release.jks", "storepass", "upload", "keypass")))
ALL_PROPS = "storeFile=release.jks\nstorePassword=s\nkeyAlias=upload\nkeyPassword=k\n"

# (description, versionName, versionCodeBase, expected versionCode or None for a rejection)
VERSION_CASES = [
    ("three-part version", "1.2.3", "0", 10203),
    ("two-part version", "2.5", "0", 20500),
    ("non-zero base", "1.0", "1000000", 1010000),
    ("largest minor and patch", "3.99.99", "0", 39999),
    ("four parts are rejected", "1.2.3.4", "0", None),
    ("non-numeric parts are rejected", "1.2-beta", "0", None),
    ("minor of 100 is rejected", "1.100", "0", None),
    ("patch of 100 is rejected", "1.0.100", "0", None),
]

# (description, keystore.properties contents or None, environment, expected hasReleaseSigning)
SIGNING_CASES = [
    ("no credentials anywhere", None, {}, False),
    ("all four from the environment", None, ALL_ENV, True),
    ("all four from keystore.properties", ALL_PROPS, {}, True),
    ("properties and environment combined", "storeFile=release.jks\nkeyAlias=upload\n",
     {"KEYSTORE_PASSWORD": "s", "KEY_PASSWORD": "k"}, True),
    ("one value missing", None, {k: v for k, v in ALL_ENV.items() if k != "KEY_PASSWORD"}, False),
    ("blank values count as missing", "storeFile=\nstorePassword= \nkeyAlias=a\nkeyPassword=k\n",
     {}, False),
    ("blank property falls back to the environment", "storePassword=\n",
     ALL_ENV, True),
]

PROBE = {
    "kts": """
tasks.register("printProbe") {
    val code = appVersionCode
    val signing = hasReleaseSigning
    doLast { println("versionCode=$code"); println("signing=$signing") }
}
""",
    "groovy": """
tasks.register("printProbe") {
    def code = appVersionCode
    def signing = hasReleaseSigning
    doLast { println("versionCode=$code"); println("signing=$signing") }
}
""",
}


def top_level_section(template: str) -> str:
    """Everything before the commented-out android { } fragment."""
    marker = re.search(r"^// =+\n// Inside android", template, flags=re.M)
    return template[: marker.start()] if marker else template


def build_file(dsl: str, version: str, base: str) -> str:
    name = "signing-and-version.gradle.kts" if dsl == "kts" else "signing-and-version.gradle"
    section = top_level_section((TEMPLATES / name).read_text(encoding="utf-8"))
    section = section.replace("__VERSION_NAME__", version).replace("__VERSION_CODE_BASE__", base)
    header = "import java.util.Properties\n\n" if dsl == "kts" else ""
    return header + section + PROBE[dsl]


def run_gradle(project: Path, env_overrides: dict[str, str], *tasks: str):
    gradle = os.environ.get("GRADLE") or shutil.which("gradle")
    env = {k: v for k, v in os.environ.items() if k not in SIGNING_ENV}
    env.update(env_overrides)
    # --warning-mode=fail turns deprecations (the Gradle 10 removals) into failures.
    # --configuration-cache backs the template's claim that its lookups are cache-safe; every
    # run reuses the cache from the run before, so a stale value would show up as a wrong answer.
    command = [gradle, "-q", "--console=plain", "--warning-mode=fail", "--configuration-cache",
               "-p", str(project), *tasks]
    return subprocess.run(command, env=env, capture_output=True, text=True)


def check_gradle() -> None:
    if not (os.environ.get("GRADLE") or shutil.which("gradle")):
        fail("gradle", "gradle is not on PATH")
        return
    for dsl in ("kts", "groovy"):
        label = f"signing-and-version.gradle{'.kts' if dsl == 'kts' else ''}"
        template_path = TEMPLATES / label
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp)
            settings = "settings.gradle.kts" if dsl == "kts" else "settings.gradle"
            (project / settings).write_text('rootProject.name = "probe"\n')
            script = project / ("build.gradle.kts" if dsl == "kts" else "build.gradle")

            for description, version, base, expected in VERSION_CASES:
                script.write_text(build_file(dsl, version, base))
                result = run_gradle(project, {}, "printProbe")
                where = f"{label} [{description}]"
                if expected is None:
                    if result.returncode == 0:
                        fail(template_path, f"[{description}] {version!r} was accepted")
                    elif version not in result.stderr:
                        fail(template_path, f"[{description}] failed without naming the "
                                            f"version:\n{result.stderr.strip()}")
                    else:
                        print(f"ok  {where}")
                    continue
                if result.returncode != 0:
                    fail(template_path, f"[{description}] build failed:\n{result.stderr.strip()}")
                    continue
                lines = result.stdout.split()
                want = [f"versionCode={expected}", "signing=false"]
                if lines != want:
                    fail(template_path, f"[{description}] printed {lines}, expected {want}")
                    continue
                # release.yml reads the version exactly like this to compare it with the tag.
                result = run_gradle(project, {}, "printVersionName")
                printed = result.stdout.strip().splitlines()[-1:] if result.returncode == 0 else []
                if printed != [version]:
                    fail(template_path, f"[{description}] printVersionName gave {printed}, "
                                        f"expected [{version!r}]:\n{result.stderr.strip()}")
                else:
                    print(f"ok  {where}")

            script.write_text(build_file(dsl, "1.0", "0"))
            properties = project / "keystore.properties"
            for description, contents, env, expected in SIGNING_CASES:
                if contents is None:
                    properties.unlink(missing_ok=True)
                else:
                    properties.write_text(contents)
                result = run_gradle(project, env, "printProbe")
                if result.returncode != 0:
                    fail(template_path, f"[{description}] build failed:\n{result.stderr.strip()}")
                elif f"signing={str(expected).lower()}" not in result.stdout.split():
                    fail(template_path, f"[{description}] expected hasReleaseSigning="
                                        f"{expected}, got:\n{result.stdout.strip()}")
                else:
                    print(f"ok  {label} [{description}]")


CHECKS = {"skills": check_skills, "workflow": check_workflow, "gradle": check_gradle}


def main(argv: list[str]) -> int:
    names = argv or list(CHECKS)
    unknown = [n for n in names if n not in CHECKS]
    if unknown:
        print(f"unknown check(s): {', '.join(unknown)}; choose from {', '.join(CHECKS)}")
        return 2
    for name in names:
        CHECKS[name]()
    for error in errors:
        if os.environ.get("GITHUB_ACTIONS"):
            # Workflow commands end at a newline, so multi-line output must be escaped.
            print("::error::" + error.replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A"))
        else:
            print(f"error: {error}")
    if not errors:
        print(f"{', '.join(names)}: all checks passed")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
