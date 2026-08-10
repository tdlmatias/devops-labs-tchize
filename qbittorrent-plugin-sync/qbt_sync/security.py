"""Static, non-executing safety inspection of candidate plugin source.

Unofficial qBittorrent plugins are arbitrary Python programs. Before a URL is
ever handed to qBittorrent this module:

1. Enforces a maximum download size.
2. Confirms the payload looks like Python text.
3. Parses it with :mod:`ast` (never executing it).
4. Walks the AST for obviously dangerous constructs.
5. Records the SHA-256 of the exact bytes inspected.

This is a *heuristic* safety net, explicitly NOT a guarantee of safety. A
plugin can be malicious without tripping any rule here, and a benign plugin can
trip a rule. The tool therefore refuses HIGH-risk plugins by default but lets
the operator override with ``--include-suspicious``.
"""

from __future__ import annotations

import ast
import hashlib
import ipaddress
import socket
from typing import Iterable
from urllib.parse import urlparse

from .models import SecurityFinding, SecurityReport

MAX_PLUGIN_SIZE = 2 * 1024 * 1024  # 2 MiB


class UrlValidationError(ValueError):
    """Raised when a candidate download URL fails safety validation."""


def _is_private_host(host: str) -> bool:
    """Return True if ``host`` resolves to (or literally is) a private/internal IP.

    A DNS lookup is attempted so that a hostname pointing at an internal address
    is still rejected. If resolution fails we treat the host as unsafe.
    """

    # Literal IP?
    try:
        ip = ipaddress.ip_address(host)
        return (
            ip.is_private
            or ip.is_loopback
            or ip.is_link_local
            or ip.is_reserved
            or ip.is_multicast
            or ip.is_unspecified
        )
    except ValueError:
        pass

    lowered = host.lower()
    if lowered in {"localhost", "localhost.localdomain"} or lowered.endswith(
        (".localhost", ".local", ".internal")
    ):
        return True

    try:
        infos = socket.getaddrinfo(host, None)
    except socket.gaierror:
        # Cannot resolve -> treat as unsafe.
        return True
    for info in infos:
        addr = info[4][0]
        try:
            ip = ipaddress.ip_address(addr)
        except ValueError:  # pragma: no cover - defensive
            continue
        if (
            ip.is_private
            or ip.is_loopback
            or ip.is_link_local
            or ip.is_reserved
            or ip.is_multicast
            or ip.is_unspecified
        ):
            return True
    return False


def validate_url(url: str, *, require_https: bool = True, check_dns: bool = True) -> str:
    """Validate a candidate plugin download URL.

    Rejects non-HTTPS, ``file://``, localhost, private/internal addresses and
    malformed URLs. Returns the (unchanged) URL on success.

    :param check_dns: when False, skip the DNS-resolution based private-IP check
        (useful for offline unit tests). The literal/loopback checks still run.
    """

    if not url or not isinstance(url, str):
        raise UrlValidationError("Empty or non-string URL.")

    parsed = urlparse(url.strip())

    if parsed.scheme in {"file", "ftp", "data", ""}:
        raise UrlValidationError(f"Disallowed URL scheme: {parsed.scheme or '(none)'}")

    if require_https and parsed.scheme != "https":
        raise UrlValidationError(f"HTTPS is required; got scheme '{parsed.scheme}'.")

    if parsed.scheme not in {"http", "https"}:
        raise UrlValidationError(f"Unsupported URL scheme: {parsed.scheme}")

    host = parsed.hostname
    if not host:
        raise UrlValidationError("URL has no host component.")

    if check_dns and _is_private_host(host):
        raise UrlValidationError(
            f"Host '{host}' resolves to a private/internal/loopback address."
        )
    if not check_dns:
        # Even when DNS resolution is skipped, still reject literal loopback/
        # private IPs (IPv4 *and* IPv6, e.g. ::1) and the localhost name.
        try:
            ip = ipaddress.ip_address(host)
        except ValueError:
            if host.lower() in {"localhost", "localhost.localdomain"}:
                raise UrlValidationError(f"Host '{host}' is a loopback address.")
        else:
            if ip.is_loopback or ip.is_private or ip.is_link_local or ip.is_reserved:
                raise UrlValidationError(
                    f"Host '{host}' is a private/internal/loopback address."
                )

    return url

# Modules whose mere import is worth flagging. The weight decides risk level.
_SUSPECT_IMPORTS = {
    "subprocess": "HIGH",
    "ctypes": "HIGH",
    "pickle": "HIGH",
    "marshal": "HIGH",
    "socket": "MEDIUM",
    "shutil": "MEDIUM",
    "tempfile": "LOW",
}

# Dotted attribute calls that are dangerous, e.g. ``os.system`` / ``os.remove``.
_SUSPECT_ATTR_CALLS = {
    ("os", "system"): "HIGH",
    ("os", "popen"): "HIGH",
    ("os", "remove"): "MEDIUM",
    ("os", "unlink"): "MEDIUM",
    ("os", "rmdir"): "MEDIUM",
    ("os", "removedirs"): "MEDIUM",
    ("os", "rename"): "MEDIUM",
    ("os", "chmod"): "MEDIUM",
    ("shutil", "rmtree"): "HIGH",
    ("importlib", "import_module"): "MEDIUM",
    ("pickle", "loads"): "HIGH",
    ("pickle", "load"): "HIGH",
    ("marshal", "loads"): "HIGH",
}

# Bare builtin calls that are dangerous.
_SUSPECT_BUILTINS = {
    "eval": "HIGH",
    "exec": "HIGH",
    "compile": "MEDIUM",
    "__import__": "MEDIUM",
    "input": "LOW",
}

_RISK_ORDER = {"UNKNOWN": 0, "LOW": 1, "MEDIUM": 2, "HIGH": 3}


def sha256_hex(data: bytes) -> str:
    """Return the hex SHA-256 digest of ``data``."""

    return hashlib.sha256(data).hexdigest()


def _looks_like_python(text: str) -> bool:
    """Cheap sanity check that the payload is Python text, not HTML/binary."""

    stripped = text.lstrip()
    if not stripped:
        return False
    lowered = stripped[:200].lower()
    if lowered.startswith(("<!doctype", "<html", "<?xml")):
        return False
    # qBittorrent plugins are subclasses; nearly all reference these tokens.
    indicators = ("import ", "def ", "class ", "#", "qBittorrent", "search")
    return any(token in text for token in indicators)


def _escalate(current: str, candidate: str) -> str:
    if _RISK_ORDER.get(candidate, 0) > _RISK_ORDER.get(current, 0):
        return candidate
    return current


class _DangerVisitor(ast.NodeVisitor):
    """Collect suspicious constructs without executing anything."""

    def __init__(self) -> None:
        self.findings: list[SecurityFinding] = []
        self.risk = "LOW"

    def _add(self, category: str, detail: str, level: str, lineno: int | None) -> None:
        self.findings.append(SecurityFinding(category, detail, lineno))
        self.risk = _escalate(self.risk, level)

    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            root = alias.name.split(".")[0]
            if root in _SUSPECT_IMPORTS:
                self._add(
                    "import",
                    f"imports module '{alias.name}'",
                    _SUSPECT_IMPORTS[root],
                    node.lineno,
                )
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        root = (node.module or "").split(".")[0]
        if root in _SUSPECT_IMPORTS:
            self._add(
                "import",
                f"imports from module '{node.module}'",
                _SUSPECT_IMPORTS[root],
                node.lineno,
            )
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:
        func = node.func
        if isinstance(func, ast.Name):
            if func.id in _SUSPECT_BUILTINS:
                self._add(
                    "call",
                    f"calls builtin '{func.id}()'",
                    _SUSPECT_BUILTINS[func.id],
                    node.lineno,
                )
        elif isinstance(func, ast.Attribute) and isinstance(func.value, ast.Name):
            key = (func.value.id, func.attr)
            if key in _SUSPECT_ATTR_CALLS:
                self._add(
                    "call",
                    f"calls '{func.value.id}.{func.attr}()'",
                    _SUSPECT_ATTR_CALLS[key],
                    node.lineno,
                )
        self.generic_visit(node)


def inspect_source(data: bytes) -> SecurityReport:
    """Statically inspect plugin bytes and return a :class:`SecurityReport`.

    The source is *never* executed. Size and encoding are validated first, then
    the AST is walked for dangerous constructs.
    """

    report = SecurityReport(sha256=sha256_hex(data), size_bytes=len(data))

    if len(data) > MAX_PLUGIN_SIZE:
        report.risk = "HIGH"
        report.error = (
            f"Plugin exceeds maximum size ({len(data)} > {MAX_PLUGIN_SIZE} bytes)."
        )
        report.findings.append(
            SecurityFinding("size", report.error, None)
        )
        return report

    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        try:
            text = data.decode("latin-1")
        except Exception:  # pragma: no cover - defensive
            report.risk = "HIGH"
            report.error = "Plugin is not decodable text."
            return report

    if not _looks_like_python(text):
        report.risk = "HIGH"
        report.error = "Payload does not appear to be Python source."
        report.findings.append(SecurityFinding("format", report.error, None))
        return report

    try:
        tree = ast.parse(text)
    except SyntaxError as exc:
        report.risk = "HIGH"
        report.syntax_valid = False
        report.error = f"Python syntax error: {exc.msg} (line {exc.lineno})."
        report.findings.append(SecurityFinding("syntax", report.error, exc.lineno))
        return report

    report.syntax_valid = True

    visitor = _DangerVisitor()
    visitor.visit(tree)
    report.findings.extend(visitor.findings)
    report.risk = visitor.risk if visitor.findings else "LOW"
    return report


def summarise_findings(findings: Iterable[SecurityFinding]) -> str:
    """Produce a compact, human-readable one-line summary of findings."""

    items = [f"{f.category}:{f.detail}" for f in findings]
    return "; ".join(items) if items else "no findings"
