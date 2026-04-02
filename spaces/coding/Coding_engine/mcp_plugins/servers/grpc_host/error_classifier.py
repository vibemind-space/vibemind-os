#!/usr/bin/env python3
"""
Error Classifier - Iteration 4

Klassifiziert Fehler nach Typ für gezielte Recovery-Strategien.

Features:
- Pattern-basierte Fehlererkennung
- Kategorisierung nach Fehlertyp
- Schweregrad-Bewertung
- Empfehlungen für Recovery
"""

import re
from enum import Enum
from typing import Dict, Any, List, Optional, Tuple
from dataclasses import dataclass
import logging

logger = logging.getLogger(__name__)


class ErrorType(Enum):
    """Fehlertypen mit unterschiedlichen Recovery-Strategien"""
    TRANSIENT = "transient"          # Temporär - Retry mit Backoff
    PERMISSION = "permission"        # Zugriffsrechte - Escalate
    NOT_FOUND = "not_found"          # Resource fehlt - Create/Escalate
    VALIDATION = "validation"        # Ungültige Eingabe - Fix Input
    TIMEOUT = "timeout"              # Zeitüberschreitung - Retry/Increase
    CONNECTION = "connection"        # Netzwerk - Retry mit Backoff
    RESOURCE_LIMIT = "resource_limit"  # Limits - Wait/Scale
    SYNTAX = "syntax"                # Code-Fehler - Fix Code
    TYPE_ERROR = "type_error"        # TypeScript/Typ-Fehler - Fix Types
    DEPENDENCY = "dependency"        # Fehlende Dependencies - Install
    CONFIGURATION = "configuration"  # Config-Fehler - Fix Config
    UNKNOWN = "unknown"              # Unbekannt - Escalate


class ErrorSeverity(Enum):
    """Schweregrad von Fehlern"""
    LOW = "low"           # Warnung, kann ignoriert werden
    MEDIUM = "medium"     # Sollte behoben werden
    HIGH = "high"         # Muss behoben werden
    CRITICAL = "critical"  # Blockiert weitere Ausführung


@dataclass
class ClassifiedError:
    """Ein klassifizierter Fehler"""
    original_message: str
    error_type: ErrorType
    severity: ErrorSeverity
    patterns_matched: List[str]
    suggested_action: str
    can_auto_recover: bool
    context: Dict[str, Any]

    def __repr__(self) -> str:
        return f"ClassifiedError({self.error_type.value}, {self.severity.value})"


# Error-Pattern zu Typ Mapping
ERROR_PATTERNS: Dict[ErrorType, List[Tuple[str, ErrorSeverity]]] = {
    ErrorType.TRANSIENT: [
        (r"temporary\s+failure", ErrorSeverity.LOW),
        (r"try\s+again", ErrorSeverity.LOW),
        (r"rate\s+limit", ErrorSeverity.MEDIUM),
        (r"too\s+many\s+requests", ErrorSeverity.MEDIUM),
        (r"503\s+service\s+unavailable", ErrorSeverity.MEDIUM),
        (r"502\s+bad\s+gateway", ErrorSeverity.MEDIUM),
        (r"connection\s+reset", ErrorSeverity.MEDIUM),
        (r"ETIMEDOUT", ErrorSeverity.MEDIUM),
    ],

    ErrorType.PERMISSION: [
        (r"permission\s+denied", ErrorSeverity.HIGH),
        (r"access\s+denied", ErrorSeverity.HIGH),
        (r"EACCES", ErrorSeverity.HIGH),
        (r"not\s+authorized", ErrorSeverity.HIGH),
        (r"403\s+forbidden", ErrorSeverity.HIGH),
        (r"unauthorized", ErrorSeverity.HIGH),
        (r"authentication\s+failed", ErrorSeverity.HIGH),
        (r"invalid\s+token", ErrorSeverity.HIGH),
    ],

    ErrorType.NOT_FOUND: [
        (r"not\s+found", ErrorSeverity.MEDIUM),
        (r"no\s+such\s+file", ErrorSeverity.MEDIUM),
        (r"ENOENT", ErrorSeverity.MEDIUM),
        (r"does\s+not\s+exist", ErrorSeverity.MEDIUM),
        (r"404\s+not\s+found", ErrorSeverity.MEDIUM),
        (r"cannot\s+find", ErrorSeverity.MEDIUM),
        (r"missing", ErrorSeverity.MEDIUM),
        (r"no\s+such\s+directory", ErrorSeverity.MEDIUM),
    ],

    ErrorType.TIMEOUT: [
        (r"timeout", ErrorSeverity.MEDIUM),
        (r"timed\s+out", ErrorSeverity.MEDIUM),
        (r"deadline\s+exceeded", ErrorSeverity.MEDIUM),
        (r"operation\s+cancelled", ErrorSeverity.MEDIUM),
        (r"took\s+too\s+long", ErrorSeverity.MEDIUM),
    ],

    ErrorType.CONNECTION: [
        (r"connection\s+refused", ErrorSeverity.HIGH),
        (r"ECONNREFUSED", ErrorSeverity.HIGH),
        (r"network\s+error", ErrorSeverity.HIGH),
        (r"ENETUNREACH", ErrorSeverity.HIGH),
        (r"EHOSTUNREACH", ErrorSeverity.HIGH),
        (r"dns\s+lookup\s+failed", ErrorSeverity.HIGH),
        (r"socket\s+hang\s+up", ErrorSeverity.MEDIUM),
    ],

    ErrorType.RESOURCE_LIMIT: [
        (r"out\s+of\s+memory", ErrorSeverity.CRITICAL),
        (r"ENOMEM", ErrorSeverity.CRITICAL),
        (r"disk\s+full", ErrorSeverity.CRITICAL),
        (r"ENOSPC", ErrorSeverity.CRITICAL),
        (r"quota\s+exceeded", ErrorSeverity.HIGH),
        (r"too\s+many\s+open\s+files", ErrorSeverity.HIGH),
        (r"EMFILE", ErrorSeverity.HIGH),
    ],

    ErrorType.SYNTAX: [
        (r"SyntaxError", ErrorSeverity.HIGH),
        (r"parse\s+error", ErrorSeverity.HIGH),
        (r"unexpected\s+token", ErrorSeverity.HIGH),
        (r"invalid\s+syntax", ErrorSeverity.HIGH),
        (r"unterminated\s+string", ErrorSeverity.HIGH),
        (r"json\s+parse\s+error", ErrorSeverity.MEDIUM),
    ],

    ErrorType.TYPE_ERROR: [
        (r"TypeError", ErrorSeverity.HIGH),
        (r"TS\d{4}:", ErrorSeverity.HIGH),  # TypeScript errors
        (r"type\s+.+\s+is\s+not\s+assignable", ErrorSeverity.HIGH),
        (r"property\s+.+\s+does\s+not\s+exist", ErrorSeverity.HIGH),
        (r"cannot\s+read\s+propert", ErrorSeverity.HIGH),
        (r"undefined\s+is\s+not", ErrorSeverity.HIGH),
        (r"null\s+is\s+not", ErrorSeverity.HIGH),
    ],

    ErrorType.DEPENDENCY: [
        (r"module\s+not\s+found", ErrorSeverity.HIGH),
        (r"cannot\s+find\s+module", ErrorSeverity.HIGH),
        (r"npm\s+ERR", ErrorSeverity.HIGH),
        (r"peer\s+dependency", ErrorSeverity.MEDIUM),
        (r"missing\s+dependency", ErrorSeverity.HIGH),
        (r"unmet\s+peer", ErrorSeverity.MEDIUM),
        (r"ERESOLVE", ErrorSeverity.HIGH),
    ],

    ErrorType.CONFIGURATION: [
        (r"invalid\s+configuration", ErrorSeverity.HIGH),
        (r"config\s+error", ErrorSeverity.HIGH),
        (r"environment\s+variable.*not\s+set", ErrorSeverity.HIGH),
        (r"missing\s+env", ErrorSeverity.HIGH),
        (r"invalid\s+option", ErrorSeverity.MEDIUM),
    ],

    ErrorType.VALIDATION: [
        (r"validation\s+error", ErrorSeverity.MEDIUM),
        (r"invalid\s+input", ErrorSeverity.MEDIUM),
        (r"invalid\s+argument", ErrorSeverity.MEDIUM),
        (r"required\s+field", ErrorSeverity.MEDIUM),
        (r"must\s+be\s+a", ErrorSeverity.MEDIUM),
        (r"expected\s+.+\s+but\s+got", ErrorSeverity.MEDIUM),
    ],
}

# Recovery-Empfehlungen pro Fehlertyp
RECOVERY_SUGGESTIONS: Dict[ErrorType, str] = {
    ErrorType.TRANSIENT: "Retry the operation with exponential backoff",
    ErrorType.PERMISSION: "Check file/directory permissions or escalate to user",
    ErrorType.NOT_FOUND: "Create the missing resource or verify the path",
    ErrorType.TIMEOUT: "Increase timeout or retry with smaller batch",
    ErrorType.CONNECTION: "Check network connectivity, retry with backoff",
    ErrorType.RESOURCE_LIMIT: "Free resources or scale infrastructure",
    ErrorType.SYNTAX: "Fix syntax error in the affected file",
    ErrorType.TYPE_ERROR: "Fix type definitions or type assertions",
    ErrorType.DEPENDENCY: "Run npm install or add missing dependency",
    ErrorType.CONFIGURATION: "Check and fix configuration files",
    ErrorType.VALIDATION: "Fix the invalid input data",
    ErrorType.UNKNOWN: "Analyze error manually and determine appropriate action",
}

# Welche Fehler automatisch recovered werden können
AUTO_RECOVERABLE: Dict[ErrorType, bool] = {
    ErrorType.TRANSIENT: True,
    ErrorType.PERMISSION: False,  # Braucht User-Intervention
    ErrorType.NOT_FOUND: True,    # Kann Resource erstellen
    ErrorType.TIMEOUT: True,
    ErrorType.CONNECTION: True,
    ErrorType.RESOURCE_LIMIT: False,  # Braucht Intervention
    ErrorType.SYNTAX: True,       # Agent kann Code fixen
    ErrorType.TYPE_ERROR: True,   # Agent kann Types fixen
    ErrorType.DEPENDENCY: True,   # npm install
    ErrorType.CONFIGURATION: True,  # Config fixen
    ErrorType.VALIDATION: True,
    ErrorType.UNKNOWN: False,
}


class ErrorClassifier:
    """
    Klassifiziert Fehler basierend auf Pattern-Matching.

    Analysiert Fehlermeldungen und ermittelt:
    - Fehlertyp
    - Schweregrad
    - Recovery-Empfehlung
    """

    def __init__(self):
        # Compile patterns für Effizienz
        self._compiled_patterns: Dict[ErrorType, List[Tuple[re.Pattern, ErrorSeverity]]] = {}

        for error_type, patterns in ERROR_PATTERNS.items():
            self._compiled_patterns[error_type] = [
                (re.compile(pattern, re.IGNORECASE), severity)
                for pattern, severity in patterns
            ]

        logger.info("ErrorClassifier initialized")

    def classify(self, error_message: str) -> ClassifiedError:
        """
        Klassifiziert eine Fehlermeldung.

        Args:
            error_message: Die Fehlermeldung

        Returns:
            ClassifiedError mit Typ, Schweregrad und Empfehlung
        """
        matched_patterns: List[str] = []
        highest_severity = ErrorSeverity.LOW
        detected_type = ErrorType.UNKNOWN

        # Durch alle Patterns iterieren
        for error_type, patterns in self._compiled_patterns.items():
            for pattern, severity in patterns:
                if pattern.search(error_message):
                    matched_patterns.append(pattern.pattern)

                    # Ersten Match verwenden, aber höchste Severity merken
                    if detected_type == ErrorType.UNKNOWN:
                        detected_type = error_type

                    if self._severity_order(severity) > self._severity_order(highest_severity):
                        highest_severity = severity

        # Context extrahieren
        context = self._extract_context(error_message)

        return ClassifiedError(
            original_message=error_message,
            error_type=detected_type,
            severity=highest_severity,
            patterns_matched=matched_patterns,
            suggested_action=RECOVERY_SUGGESTIONS.get(detected_type, "Unknown error"),
            can_auto_recover=AUTO_RECOVERABLE.get(detected_type, False),
            context=context
        )

    def _severity_order(self, severity: ErrorSeverity) -> int:
        """Gibt numerischen Wert für Severity-Vergleich"""
        order = {
            ErrorSeverity.LOW: 0,
            ErrorSeverity.MEDIUM: 1,
            ErrorSeverity.HIGH: 2,
            ErrorSeverity.CRITICAL: 3,
        }
        return order.get(severity, 0)

    def _extract_context(self, error_message: str) -> Dict[str, Any]:
        """Extrahiert zusätzlichen Kontext aus der Fehlermeldung"""
        context = {}

        # Datei-Pfad extrahieren
        file_match = re.search(r'(?:in|at|file:?)\s*["\']?([/\\]?[\w./\\-]+\.\w+)', error_message)
        if file_match:
            context["file"] = file_match.group(1)

        # Zeilennummer extrahieren
        line_match = re.search(r'(?:line|:)(\d+)', error_message)
        if line_match:
            context["line"] = int(line_match.group(1))

        # TypeScript Error Code extrahieren
        ts_match = re.search(r'(TS\d{4})', error_message)
        if ts_match:
            context["ts_code"] = ts_match.group(1)

        # HTTP Status Code extrahieren
        http_match = re.search(r'(\d{3})\s+\w+', error_message)
        if http_match:
            context["http_status"] = int(http_match.group(1))

        return context

    def classify_multiple(self, error_messages: List[str]) -> List[ClassifiedError]:
        """Klassifiziert mehrere Fehlermeldungen"""
        return [self.classify(msg) for msg in error_messages]

    def get_dominant_type(self, errors: List[ClassifiedError]) -> ErrorType:
        """Ermittelt den dominanten Fehlertyp aus einer Liste"""
        if not errors:
            return ErrorType.UNKNOWN

        type_counts: Dict[ErrorType, int] = {}
        for err in errors:
            type_counts[err.error_type] = type_counts.get(err.error_type, 0) + 1

        return max(type_counts, key=type_counts.get)

    def get_summary(self, errors: List[ClassifiedError]) -> Dict[str, Any]:
        """Erstellt eine Zusammenfassung mehrerer Fehler"""
        if not errors:
            return {"count": 0}

        type_counts: Dict[str, int] = {}
        severity_counts: Dict[str, int] = {}
        auto_recoverable = 0

        for err in errors:
            type_name = err.error_type.value
            sev_name = err.severity.value

            type_counts[type_name] = type_counts.get(type_name, 0) + 1
            severity_counts[sev_name] = severity_counts.get(sev_name, 0) + 1

            if err.can_auto_recover:
                auto_recoverable += 1

        return {
            "count": len(errors),
            "by_type": type_counts,
            "by_severity": severity_counts,
            "auto_recoverable": auto_recoverable,
            "needs_intervention": len(errors) - auto_recoverable,
            "dominant_type": self.get_dominant_type(errors).value
        }


# =============================================================================
# Test
# =============================================================================

def test_classifier():
    """Test der ErrorClassifier Funktionalität"""
    print("=== Error Classifier Test ===\n")

    classifier = ErrorClassifier()

    # Test-Fehlermeldungen
    test_errors = [
        "Error: ENOENT: no such file or directory, open '/app/config.json'",
        "TS2339: Property 'foo' does not exist on type 'Bar'",
        "npm ERR! ERESOLVE unable to resolve dependency tree",
        "Error: connect ECONNREFUSED 127.0.0.1:5432",
        "EACCES: permission denied, mkdir '/root'",
        "Error: Request timeout after 30000ms",
        "SyntaxError: Unexpected token ';'",
        "TypeError: Cannot read property 'map' of undefined",
        "Error: rate limit exceeded, try again in 60 seconds",
    ]

    print("Classifying errors:\n")
    classified = []

    for error in test_errors:
        result = classifier.classify(error)
        classified.append(result)

        print(f"Error: {error[:60]}...")
        print(f"  Type: {result.error_type.value}")
        print(f"  Severity: {result.severity.value}")
        print(f"  Auto-recoverable: {result.can_auto_recover}")
        print(f"  Action: {result.suggested_action[:50]}...")
        print(f"  Context: {result.context}")
        print()

    print("Summary:")
    summary = classifier.get_summary(classified)
    print(f"  {summary}")

    print("\n=== Test Complete ===")


if __name__ == "__main__":
    test_classifier()
