"""The mistakes every coding agent makes, that every user recognises.

Mined rules describe one repository's habits. These are different: they are the
failures that show up everywhere, and a person should not have to be burned by
them once each before the tool knows about them.

Two tiers, and the split is about false positives rather than severity:

  BINDING     the pattern is unambiguous. A live AWS key is never intentional,
              and `pdb.set_trace()` is never meant to be committed.
  ADVISORY    the pattern is usually wrong but legitimately happens - tests do
              get deleted during real refactors - so it informs and does not
              block. `injunct on <n>` promotes it if you disagree.

Every rule here is installed only when the repository shows it applies, and
every one can be switched off.
"""
from __future__ import annotations

from pathlib import Path

# regex, glob, says, binding
RULES: list[dict] = [
    # ---- secrets -------------------------------------------------------
    dict(key="aws_key", template="must_not_appear", binding=True,
         regex=r"AKIA[0-9A-Z]{16}", glob="**",
         says="Never commit an AWS access key."),
    dict(key="private_key", template="must_not_appear", binding=True,
         regex=r"-----BEGIN [A-Z ]*PRIVATE KEY-----", glob="**",
         says="Never commit a private key."),
    dict(key="token", template="must_not_appear", binding=True,
         regex=r"\b(ghp_[A-Za-z0-9]{20,}|sk-[A-Za-z0-9]{20,}|xox[baprs]-[A-Za-z0-9-]{10,})",
         glob="**", says="Never commit an API token."),

    # ---- the agent must not be able to switch the gate off -------------
    # Every other rule here assumes the gate is running. This is the one that
    # keeps it running, and it is the only rule in the pack that exists
    # BECAUSE injunct blocks rather than advises - an advisory tool has
    # nothing worth disarming.
    #
    # It is not hypothetical. This repository has been disarmed twice by the
    # thing it was restraining: an agent edited the seed corpus from outside
    # its worktree, and a plugin file went missing so every benchmark arm
    # silently became a bare agent still printing numbers that looked like
    # results.
    dict(key="self_disarm", template="forbidden_edit", binding=True,
         params={"glob": "{.injunct/**,.git/hooks/**,**/.opencode/plugins/**,opencode.json,"
                         ".claude/settings.json,.claude/settings.local.json,.claude/hooks/**}"},
         says="This turns the gate off. Change it yourself, not through the agent."),
    dict(key="disarm_ci", template="forbidden_edit", binding=True,
         params={"glob": "{.github/workflows/**,.pre-commit-config.yaml}"},
         says="This edits the checks that guard the repository."),

    # ---- protections the agent removed ---------------------------------
    # `simplifying` an authorisation check away is a classic, and the template
    # for it already existed - this is a rule, not new machinery.
    dict(key="removed_authz", template="must_not_remove", binding=False, langs={"py"},
         regex=r"@(login_required|permission_required|requires_auth|admin_required)",
         glob="**/*.py",
         says="You removed an authorisation check. Say why, or put it back."),
    dict(key="removed_csrf", template="must_not_remove", binding=False,
         regex=r"(csrf_token|CSRFProtect|csrf_exempt)",
         glob="**/*.{py,js,ts,html}",
         says="You removed a CSRF protection."),

    # ---- transport and crypto downgrades --------------------------------
    dict(key="tls_off", template="must_not_appear", binding=True, langs={"py"},
         regex=r"verify\s*=\s*False|_create_unverified_context",
         glob="**/*.py",
         says="This turns off certificate verification."),
    dict(key="weak_hash_password", template="must_not_appear", binding=False, langs={"py"},
         regex=r"(md5|sha1)\s*\(\s*[^)]*pass",
         glob="**/*.py",
         says="A password is being hashed with a broken algorithm."),
    dict(key="debug_on", template="must_not_appear", binding=False,
         regex=r"^\s*DEBUG\s*=\s*True",
         glob="**/{settings,config,conf}*.py",
         says="Debug mode is on in a config file."),

    # ---- dangerous sinks -------------------------------------------------
    dict(key="shell_injection", template="must_not_appear", binding=False, langs={"py"},
         regex=r"(os\.system\(|subprocess\.[a-z_]+\([^)]*shell\s*=\s*True)",
         glob="**/*.py",
         says="A shell command is being built at runtime."),
    # Borrowed from forge, which had to answer this to let an agent write its
    # own tools. Reads the syntax tree, so `eval` in a comment, in a string, or
    # in a variable named `evaluate` is not a finding and a real call is.
    dict(key="forge_unsafe_call", template="forge_gate", binding=False, langs={"py"},
         params={"glob": "**/*.py"},
         says="This code reaches for something that can execute arbitrary input."),
    dict(key="unsafe_deser", template="must_not_appear", binding=False, langs={"py"},
         regex=r"(pickle\.loads?\(|yaml\.load\((?![^)]*Safe))",
         glob="**/*.py",
         says="Untrusted data is being deserialised unsafely."),

    # ---- debugging left behind ----------------------------------------
    dict(key="pdb", template="must_not_appear", binding=True, langs={"py"},
         regex=r"\b(pdb|ipdb)\.set_trace\(|\bbreakpoint\(\)", glob="**/*.py",
         says="Take the debugger breakpoint out before this lands."),
    dict(key="debugger", template="must_not_appear", binding=True, langs={"js"},
         regex=r"^\s*debugger\s*;?\s*$", glob="**/*.{js,ts,jsx,tsx}",
         says="Take the debugger statement out before this lands."),
    dict(key="console", template="must_not_appear", binding=False, langs={"js"},
         regex=r"console\.(log|debug)\(", glob="**/*.{js,ts,jsx,tsx}",
         says="Leftover console.log in the code you just changed."),

    # ---- making the red go away the wrong way --------------------------
    dict(key="deleted_test", template="must_not_remove", binding=False,
         regex=r"^\s*(def test_|it\(|test\(|func Test)", glob="**/{test,tests,spec,__tests__}/**",
         says="You deleted a test. If it was wrong, say so; do not just remove it."),
    dict(key="skipped_test", template="must_not_appear", binding=False,
         regex=r"@(pytest\.mark\.)?(skip|xfail)|\.(skip|todo)\(|@unittest\.skip",
         glob="**/{test,tests,spec,__tests__}/**",
         says="You skipped a test instead of fixing it."),

    # ---- error handling quietly removed --------------------------------
    dict(key="swallowed", template="must_not_appear", binding=False, langs={"py"},
         regex=r"except[^:]*:\s*(pass|\.\.\.)\s*$", glob="**/*.py",
         says="An exception is being swallowed silently."),
    dict(key="empty_catch", template="must_not_appear", binding=False, langs={"js"},
         regex=r"catch\s*\([^)]*\)\s*\{\s*\}", glob="**/*.{js,ts,jsx,tsx}",
         says="An empty catch block hides the error."),
    dict(key="removed_raise", template="must_not_remove", binding=False, langs={"py"},
         regex=r"^\s*(raise|assert)\b", glob="**/*.py",
         says="You removed a raise or assert. Errors that were loud are now silent."),

    # ---- migrations that cannot be undone ------------------------------
    dict(key="destructive_sql", template="must_not_appear", binding=True,
         regex=r"(?i)\b(DROP\s+(TABLE|COLUMN|DATABASE)|TRUNCATE\s+TABLE)\b",
         glob="**/{migrations,migrate,db}/**",
         says="This migration destroys data and cannot be undone."),

    # ---- unfinished work presented as finished -------------------------
    dict(key="stub", template="must_not_appear", binding=False,
         regex=r"NotImplementedError|TODO: implement|FIXME|XXX:", glob="**",
         says="A stub or TODO was left in the change."),
]


def _looks_like(repo: Path) -> set[str]:
    """Only install what this repository can actually trip over."""
    langs: set[str] = set()
    if any(repo.glob("**/*.py")) or (repo / "pyproject.toml").is_file():
        langs.add("py")
    if (repo / "package.json").is_file() or any(repo.glob("**/*.ts")) \
            or any(repo.glob("**/*.js")):
        langs.add("js")
    return langs


def applicable(repo: Path) -> list[dict]:
    langs = _looks_like(Path(repo))
    pool = RULES + NATIVE + sleeper_rules()
    return [r for r in pool if not r.get("langs") or (r["langs"] & langs)]


def manifest_pairs(repo: Path) -> list[dict]:
    """A manifest and its lockfile move together, or the next install differs."""
    repo = Path(repo)
    out = []
    for manifest, lock in (("package.json", "package-lock.json"),
                           ("package.json", "yarn.lock"),
                           ("package.json", "pnpm-lock.yaml"),
                           ("pyproject.toml", "poetry.lock"),
                           ("pyproject.toml", "uv.lock"),
                           ("Gemfile", "Gemfile.lock"),
                           ("go.mod", "go.sum")):
        if (repo / manifest).is_file() and (repo / lock).is_file():
            out.append(dict(key=f"lock_{lock}", template="co_change", binding=True,
                            trigger=manifest, required=lock,
                            says=f"Changing {manifest} means updating {lock} too."))
    return out


# ---- checks that need no regex, only the code itself ---------------------

NATIVE = [
    dict(key="blast_radius", template="blast_radius", binding=False, langs={"py"},
         params={"max_untouched": 0},
         says="You changed a function's shape without updating its callers."),
    dict(key="no_quadratic", template="no_quadratic", binding=False, langs={"py"},
         params={"glob": "**/*.py"},
         says="The code you just added has a quadratic shape in it."),
]

# ---- borrowed from sleeper, when it is present ---------------------------

SLEEPER = [
    dict(key="sleeper_deps", gate="deps",
         says="The agent imported something this project does not declare."),
    dict(key="sleeper_docs", gate="docs",
         says="The documentation no longer matches the code."),
    dict(key="sleeper_complexity", gate="complexity",
         says="The measured cost does not match what the code claims."),
    dict(key="sleeper_redundancy", gate="redundancy",
         says="This repository already has a function that does this."),
]


def forge_home() -> Path | None:
    """Where forge lives, if it is anywhere.

    forge is the sibling project that lets an agent WRITE its own tools. To do
    that safely it had to answer a question we also need answered - is this
    Python code doing something it should not be allowed to do - and it answers
    it by walking the syntax tree rather than by matching text. We had two
    regexes for the same job and they were the weaker tool.
    """
    import os

    env = os.environ.get("INJUNCT_FORGE")
    if env and (Path(env) / "forge" / "safety.py").is_file():
        return Path(env)
    sibling = Path(__file__).resolve().parents[2] / "forge"
    if (sibling / "forge" / "safety.py").is_file():
        return sibling
    return None


def forge_available() -> bool:
    return forge_home() is not None


def sleeper_home() -> Path | None:
    """Where sleeper lives, if it is anywhere.

    Installed, or pointed at by INJUNCT_SLEEPER, or sitting next to this
    repository - which is the normal case, since they are sibling projects.
    """
    import os

    env = os.environ.get("INJUNCT_SLEEPER")
    if env and (Path(env) / "sleeper" / "__init__.py").is_file():
        return Path(env)
    sibling = Path(__file__).resolve().parents[2] / "sleeper"
    if (sibling / "sleeper" / "__init__.py").is_file():
        return sibling
    return None


def sleeper_available() -> bool:
    from . import shell
    if shell.run('python -c "import sleeper"', Path.cwd()).returncode == 0:
        return True
    return sleeper_home() is not None


def sleeper_rules() -> list[dict]:
    """Four gates borrowed rather than rebuilt - but only if it is installed.

    Advisory at the provisional bar: sleeper cannot always confirm offline, and
    an unconfirmed answer is not the same as a verdict.
    """
    if not sleeper_available():
        return []
    return [dict(key=r["key"], template="sleeper_gate", binding=False, langs={"py"},
                 params={"gate": r["gate"], "at_least": "provisional",
                         "glob": "**/*.py"},
                 says=r["says"]) for r in SLEEPER]
