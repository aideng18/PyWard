# security_checks.py

import ast
from typing import List


def check_exec_eval_usage(tree: ast.AST) -> List[str]:
    """
    Flag any direct usage of `exec(...)` or `eval(...)` as a security risk.
    References:
      - CVE-2025-3248 (Langflow AI): abusing `exec` for unauthenticated RCE.
      - General best practice: avoid eval()/exec() on untrusted data.

    Returns a list of warnings with line numbers.
    """
    issues: List[str] = []

    class ExecEvalVisitor(ast.NodeVisitor):
        def visit_Call(self, node: ast.Call):
            if isinstance(node.func, ast.Name) and node.func.id in ("exec", "eval"):
                issues.append(
                    f"[Security][CVE-2025-3248] Line {node.lineno}: "
                    f"Use of '{node.func.id}()' detected. "
                    f"This can lead to code injection (e.g. CVE-2025-3248 in Langflow). "
                    f"Consider safer alternatives (e.g., ast.literal_eval) or explicit parsing."
                )
            self.generic_visit(node)

    ExecEvalVisitor().visit(tree)
    return issues


def check_python_json_logger_import(tree: ast.AST) -> List[str]:
    """
    Flag any import of 'python_json_logger' (the package known to be vulnerable to
    CVE-2025-27607). The vulnerability allowed RCE if a malicious party claimed
    msgspec-python313-pre on PyPI, causing python-json-logger users to load it.

    Returns a warning if that import is present.
    """
    issues: List[str] = []

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == "python_json_logger" or alias.name.startswith("python_json_logger."):
                    issues.append(
                        f"[Security][CVE-2025-27607] Line {node.lineno}: "
                        f"'python_json_logger' import detected. This package was vulnerable to RCE "
                        f"between Dec 30, 2024 and Mar 4, 2025 (CVE-2025-27607). "
                        f"Update to a patched version or remove this dependency."
                    )
        elif isinstance(node, ast.ImportFrom):
            mod = (node.module or "")
            if mod == "python_json_logger" or mod.startswith("python_json_logger."):
                issues.append(
                    f"[Security][CVE-2025-27607] Line {node.lineno}: "
                    f"'from python_json_logger import ...' detected. This package was vulnerable to RCE "
                    f"between Dec 30, 2024 and Mar 4, 2025 (CVE-2025-27607). "
                    f"Update to a patched version or remove this dependency."
                )

    return issues


def check_subprocess_usage(tree: ast.AST) -> List[str]:
    """
    Flag any use of subprocess with shell=True or format string commands, which can lead to shell injection.
    Recommendation: Use subprocess.run([...], shell=False) and avoid user-controlled formatting.
    """
    issues: List[str] = []

    class SubprocessVisitor(ast.NodeVisitor):
        def visit_Call(self, node: ast.Call):
            # Detect subprocess.run(..., shell=True) or subprocess.Popen(..., shell=True)
            if isinstance(node.func, ast.Attribute):
                attr = node.func
                if isinstance(attr.value, ast.Name) and attr.value.id == "subprocess" and attr.attr in (
                    "run", "Popen", "call", "check_output"
                ):
                    for kw in node.keywords:
                        if kw.arg == "shell":
                            # If shell=True is used
                            if isinstance(kw.value, ast.Constant) and kw.value.value is True:
                                issues.append(
                                    f"[Security] Line {node.lineno}: Use of subprocess.{attr.attr}() with shell=True. "
                                    f"Risk of shell injection. "
                                    f"Recommendation: Use a list of arguments and shell=False."
                                )
            self.generic_visit(node)

    SubprocessVisitor().visit(tree)
    return issues


def check_pickle_usage(tree: ast.AST) -> List[str]:
    """
    Flag any direct usage of pickle.load(something) or pickle.loads(something), as untrusted pickle data can lead to RCE.
    Recommendation: Use safer serialization formats (e.g., JSON) or verify signature before unpickling.
    """
    issues: List[str] = []

    class PickleVisitor(ast.NodeVisitor):
        def visit_Call(self, node: ast.Call):
            # Detect pickle.load(...) or pickle.loads(...)
            if isinstance(node.func, ast.Attribute):
                if isinstance(node.func.value, ast.Name) and node.func.value.id == "pickle" and node.func.attr in (
                    "load", "loads"
                ):
                    issues.append(
                        f"[Security] Line {node.lineno}: Use of pickle.{node.func.attr}(). "
                        f"Untrusted pickle data can lead to RCE. "
                        f"Recommendation: Use json or verify signature before unpickling."
                    )
            self.generic_visit(node)

    PickleVisitor().visit(tree)
    return issues


def check_yaml_load_usage(tree: ast.AST) -> List[str]:
    """
    Flag any use of yaml.load(...) without specifying SafeLoader, as it can lead to code execution.
    Recommendation: Use yaml.safe_load(...) or specify Loader=yaml.SafeLoader.
    """
    issues: List[str] = []

    class YAMLVisitor(ast.NodeVisitor):
        def visit_Call(self, node: ast.Call):
            # Detect yaml.load(...) without any arguments that enforce SafeLoader
            if isinstance(node.func, ast.Attribute):
                if isinstance(node.func.value, ast.Name) and node.func.value.id == "yaml" and node.func.attr == "load":
                    # Check if SafeLoader is specified
                    has_safe = False
                    for kw in node.keywords:
                        if kw.arg in ("Loader",) and isinstance(kw.value, ast.Attribute) and kw.value.attr == "SafeLoader":
                            has_safe = True
                    if not has_safe:
                        issues.append(
                            f"[Security] Line {node.lineno}: Use of yaml.load() without SafeLoader. "
                            f"Unsafe YAML loading can lead to code execution. "
                            f"Recommendation: Use yaml.safe_load() or specify Loader=yaml.SafeLoader."
                        )
            self.generic_visit(node)

    YAMLVisitor().visit(tree)
    return issues


def check_hardcoded_secrets(tree: ast.AST) -> List[str]:
    """
    Flag assignment of string literals that look like AWS keys, passwords, or tokens.
    Basic heuristic: variable name containing 'key', 'secret', 'password', 'token', etc., assigned to a literal string.
    Recommendation: Move secrets to environment variables or secure vaults.
    """
    issues: List[str] = []

    class SecretsVisitor(ast.NodeVisitor):
        def visit_Assign(self, node: ast.Assign):
            # Only check simple assignments (one target)
            if len(node.targets) != 1:
                return
            target = node.targets[0]
            if isinstance(target, ast.Name) and isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
                var_name = target.id.lower()
                if any(keyword in var_name for keyword in ("key", "secret", "password", "token", "passwd")):
                    issues.append(
                        f"[Security] Line {node.lineno}: Assignment to '{target.id}' with a literal string. "
                        f"Hard-coded secret detected. "
                        f"Recommendation: Store secrets in environment variables or a secrets manager."
                    )
            self.generic_visit(node)

    SecretsVisitor().visit(tree)
    return issues


def check_weak_hashing_usage(tree: ast.AST) -> List[str]:
    """
    Flag usage of hashlib.md5 or hashlib.sha1, which are considered cryptographically weak.
    Recommendation: Use hashlib.sha256 or stronger algorithms.
    """
    issues: List[str] = []

    class HashVisitor(ast.NodeVisitor):
        def visit_Attribute(self, node: ast.Attribute):
            if isinstance(node.value, ast.Name) and node.value.id == "hashlib" and node.attr in ("md5", "sha1"):
                issues.append(
                    f"[Security] Line {node.lineno}: Use of hashlib.{node.attr}(). "
                    f"{node.attr.upper()} is considered weak. "
                    f"Recommendation: Use hashlib.sha256 or stronger."
                )
            self.generic_visit(node)

    HashVisitor().visit(tree)
    return issues


def run_all_checks(tree: ast.AST) -> List[str]:
    """
    Run all security checks and return a combined list of issues.
    """
    checks = [
        check_exec_eval_usage,
        check_python_json_logger_import,
        check_subprocess_usage,
        check_pickle_usage,
        check_yaml_load_usage,
        check_hardcoded_secrets,
        check_weak_hashing_usage,
    ]
    all_issues: List[str] = []
    for check in checks:
        all_issues.extend(check(tree))
    return all_issues
