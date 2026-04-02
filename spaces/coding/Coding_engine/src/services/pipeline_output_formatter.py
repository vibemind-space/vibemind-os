"""Pipeline output formatter - format and transform pipeline outputs."""

import json
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional


@dataclass
class FormatTemplate:
    """Output format template."""
    template_id: str = ""
    name: str = ""
    output_format: str = ""
    fields: list = field(default_factory=list)
    options: dict = field(default_factory=dict)
    created_at: float = 0.0


class PipelineOutputFormatter:
    """Format pipeline outputs into various structures."""

    FORMATS = (
        "json", "text", "csv", "markdown",
        "summary", "table", "log", "custom",
    )

    def __init__(self, max_templates: int = 5000):
        self._max_templates = max(1, max_templates)
        self._templates: Dict[str, FormatTemplate] = {}
        self._callbacks: Dict[str, Callable] = {}
        self._stats = {
            "total_templates": 0,
            "total_formatted": 0,
        }

    # --- Template Management ---

    def create_template(
        self,
        name: str,
        output_format: str = "json",
        fields: Optional[List[str]] = None,
        options: Optional[Dict] = None,
    ) -> str:
        """Create a format template."""
        if not name:
            return ""
        if output_format not in self.FORMATS:
            return ""
        if len(self._templates) >= self._max_templates:
            return ""

        tid = f"fmt-{uuid.uuid4().hex[:12]}"
        self._templates[tid] = FormatTemplate(
            template_id=tid,
            name=name,
            output_format=output_format,
            fields=list(fields or []),
            options=dict(options or {}),
            created_at=time.time(),
        )
        self._stats["total_templates"] += 1
        return tid

    def get_template(self, template_id: str) -> Optional[Dict]:
        """Get template details."""
        t = self._templates.get(template_id)
        if not t:
            return None
        return {
            "template_id": t.template_id,
            "name": t.name,
            "output_format": t.output_format,
            "fields": list(t.fields),
            "options": dict(t.options),
        }

    def remove_template(self, template_id: str) -> bool:
        """Remove a template."""
        if template_id not in self._templates:
            return False
        del self._templates[template_id]
        return True

    def list_templates(self, output_format: str = "") -> List[Dict]:
        """List templates."""
        results = []
        for t in self._templates.values():
            if output_format and t.output_format != output_format:
                continue
            results.append({
                "template_id": t.template_id,
                "name": t.name,
                "output_format": t.output_format,
                "field_count": len(t.fields),
            })
        return results

    # --- Formatting ---

    def format_output(self, template_id: str, data: Dict) -> str:
        """Format data using a template. Returns formatted string."""
        t = self._templates.get(template_id)
        if not t:
            return ""

        self._stats["total_formatted"] += 1

        # Filter to specified fields if any
        filtered = data
        if t.fields:
            filtered = {k: v for k, v in data.items() if k in t.fields}

        result = self._apply_format(t.output_format, filtered, t.options)
        self._fire("output_formatted", {"template_id": template_id, "format": t.output_format})
        return result

    def quick_format(self, data: Dict, output_format: str = "json",
                     fields: Optional[List[str]] = None,
                     options: Optional[Dict] = None) -> str:
        """Format data without a template."""
        if output_format not in self.FORMATS:
            return ""

        filtered = data
        if fields:
            filtered = {k: v for k, v in data.items() if k in fields}

        self._stats["total_formatted"] += 1
        return self._apply_format(output_format, filtered, options or {})

    def format_list(self, items: List[Dict], output_format: str = "json",
                    fields: Optional[List[str]] = None) -> str:
        """Format a list of items."""
        if output_format not in self.FORMATS:
            return ""
        if not items:
            return ""

        self._stats["total_formatted"] += 1

        if fields:
            items = [{k: v for k, v in item.items() if k in fields} for item in items]

        if output_format == "json":
            return json.dumps(items, indent=2, default=str)
        elif output_format == "csv":
            return self._list_to_csv(items)
        elif output_format == "table":
            return self._list_to_table(items)
        elif output_format == "markdown":
            return self._list_to_markdown_table(items)
        elif output_format == "text":
            lines = []
            for i, item in enumerate(items):
                lines.append(f"--- Item {i+1} ---")
                for k, v in item.items():
                    lines.append(f"  {k}: {v}")
            return "\n".join(lines)
        else:
            return json.dumps(items, default=str)

    # --- Callbacks ---

    def on_change(self, name: str, callback: Callable) -> bool:
        if name in self._callbacks:
            return False
        self._callbacks[name] = callback
        return True

    def remove_callback(self, name: str) -> bool:
        if name not in self._callbacks:
            return False
        del self._callbacks[name]
        return True

    # --- Stats ---

    def get_stats(self) -> Dict:
        return {
            **self._stats,
            "current_templates": len(self._templates),
        }

    def reset(self) -> None:
        self._templates.clear()
        self._callbacks.clear()
        self._stats = {
            "total_templates": 0,
            "total_formatted": 0,
        }

    # --- Internal ---

    def _apply_format(self, fmt: str, data: Dict, options: Dict) -> str:
        """Apply format to data."""
        if fmt == "json":
            indent = options.get("indent", 2)
            return json.dumps(data, indent=indent, default=str)
        elif fmt == "text":
            lines = []
            for k, v in data.items():
                lines.append(f"{k}: {v}")
            return "\n".join(lines)
        elif fmt == "csv":
            keys = list(data.keys())
            vals = [str(data.get(k, "")) for k in keys]
            sep = options.get("separator", ",")
            return sep.join(keys) + "\n" + sep.join(vals)
        elif fmt == "markdown":
            lines = []
            title = options.get("title", "Output")
            lines.append(f"# {title}")
            lines.append("")
            for k, v in data.items():
                lines.append(f"- **{k}**: {v}")
            return "\n".join(lines)
        elif fmt == "summary":
            parts = []
            for k, v in data.items():
                parts.append(f"{k}={v}")
            return " | ".join(parts)
        elif fmt == "table":
            keys = list(data.keys())
            vals = [str(data.get(k, "")) for k in keys]
            widths = [max(len(k), len(v)) for k, v in zip(keys, vals)]
            header = " | ".join(k.ljust(w) for k, w in zip(keys, widths))
            sep_line = "-+-".join("-" * w for w in widths)
            row = " | ".join(v.ljust(w) for v, w in zip(vals, widths))
            return f"{header}\n{sep_line}\n{row}"
        elif fmt == "log":
            ts = options.get("timestamp", "")
            prefix = f"[{ts}] " if ts else ""
            parts = [f"{k}={v}" for k, v in data.items()]
            return prefix + " ".join(parts)
        else:
            return json.dumps(data, default=str)

    def _list_to_csv(self, items: List[Dict]) -> str:
        """Convert list to CSV."""
        if not items:
            return ""
        keys = list(items[0].keys())
        lines = [",".join(keys)]
        for item in items:
            lines.append(",".join(str(item.get(k, "")) for k in keys))
        return "\n".join(lines)

    def _list_to_table(self, items: List[Dict]) -> str:
        """Convert list to text table."""
        if not items:
            return ""
        keys = list(items[0].keys())
        widths = {k: len(k) for k in keys}
        for item in items:
            for k in keys:
                widths[k] = max(widths[k], len(str(item.get(k, ""))))

        header = " | ".join(k.ljust(widths[k]) for k in keys)
        sep = "-+-".join("-" * widths[k] for k in keys)
        rows = []
        for item in items:
            rows.append(" | ".join(str(item.get(k, "")).ljust(widths[k]) for k in keys))
        return "\n".join([header, sep] + rows)

    def _list_to_markdown_table(self, items: List[Dict]) -> str:
        """Convert list to markdown table."""
        if not items:
            return ""
        keys = list(items[0].keys())
        lines = ["| " + " | ".join(keys) + " |"]
        lines.append("| " + " | ".join("---" for _ in keys) + " |")
        for item in items:
            lines.append("| " + " | ".join(str(item.get(k, "")) for k in keys) + " |")
        return "\n".join(lines)

    def _fire(self, action: str, data: Dict) -> None:
        for cb in list(self._callbacks.values()):
            try:
                cb(action, data)
            except Exception:
                pass
