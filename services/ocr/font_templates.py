from __future__ import annotations

from dataclasses import asdict, dataclass
import json
from pathlib import Path


DEFAULT_FONT_TEMPLATE_PATH = Path("outputs/font_templates.json")
TEMPLATE_MIN_SAMPLE_COUNT = 100


@dataclass(frozen=True)
class FontTemplate:
    name: str
    font_hash: str
    card_type: str
    samples: int
    confusion_pairs: dict[str, str]
    position_pairs: dict[str, str]
    rule_counts: dict[str, int]
    confidence: float
    enabled: bool = True


PUBG_FONT_A = FontTemplate(
    name="PUBG_FONT_A",
    font_hash="3f9ab2",
    card_type="PUBG",
    samples=218,
    confusion_pairs={
        "2": "Z",
        "8": "B",
        "M": "N",
        "Q": "O",
    },
    position_pairs={
        "19:2": "Z",
    },
    rule_counts={
        "19:2>Z": 12,
        "2>Z": 12,
        "8>B": 3,
        "M>N": 3,
        "Q>O": 3,
    },
    confidence=99.3,
)


DEFAULT_TEMPLATES = (PUBG_FONT_A,)


class FontTemplateRepository:
    def __init__(self, path: Path | str = DEFAULT_FONT_TEMPLATE_PATH) -> None:
        self.path = Path(path)
        if not self.path.exists():
            self.write_templates(list(DEFAULT_TEMPLATES))

    def list_templates(self, enabled_only: bool = False) -> list[FontTemplate]:
        templates = [deserialize_template(name, value) for name, value in self._read().items()]
        if enabled_only:
            templates = [template for template in templates if template.enabled]
        return sorted(templates, key=lambda template: template.name)

    def get(self, name: str) -> FontTemplate | None:
        data = self._read().get(name)
        return deserialize_template(name, data) if isinstance(data, dict) else None

    def save(self, template: FontTemplate) -> FontTemplate:
        data = self._read()
        data[template.name] = serialize_template(template)
        self._write(data)
        return template

    def set_enabled(self, name: str, enabled: bool) -> bool:
        template = self.get(name)
        if not template:
            return False
        updated = FontTemplate(
            name=template.name,
            font_hash=template.font_hash,
            card_type=template.card_type,
            samples=template.samples,
            confusion_pairs=template.confusion_pairs,
            position_pairs=template.position_pairs,
            rule_counts=template.rule_counts,
            confidence=template.confidence,
            enabled=enabled,
        )
        self.save(updated)
        return True

    def stats(self) -> dict[str, object]:
        templates = self.list_templates()
        return {
            "template_count": len(templates),
            "enabled_count": len([template for template in templates if template.enabled]),
            "sample_count": sum(template.samples for template in templates),
            "templates": [template.name for template in templates],
        }

    def write_templates(self, templates: list[FontTemplate]) -> None:
        self._write({template.name: serialize_template(template) for template in templates})

    def _read(self) -> dict[str, dict[str, object]]:
        if not self.path.exists():
            return {}
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return {}
        if isinstance(data, dict):
            return {str(key): value for key, value in data.items() if isinstance(value, dict)}
        return {}

    def _write(self, data: dict[str, dict[str, object]]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def serialize_template(template: FontTemplate) -> dict[str, object]:
    data = asdict(template)
    data["sample_count"] = data.pop("samples")
    data["errors"] = data.pop("confusion_pairs")
    data["positions"] = data.pop("position_pairs")
    data["rule_counts"] = data.pop("rule_counts")
    data.pop("name", None)
    return data


def deserialize_template(name: str, data: dict[str, object]) -> FontTemplate:
    return FontTemplate(
        name=name,
        font_hash=str(data.get("font_hash", "")),
        card_type=str(data.get("card_type", "PUBG")),
        samples=int(data.get("sample_count", data.get("samples", 0))),
        confusion_pairs=_str_dict(data.get("errors") or data.get("confusion_pairs") or {}),
        position_pairs=_str_dict(data.get("positions") or data.get("position_pairs") or {}),
        rule_counts=_int_dict(data.get("rule_counts") or {}),
        confidence=float(data.get("confidence", 0.0)),
        enabled=bool(data.get("enabled", True)),
    )


def _str_dict(value: object) -> dict[str, str]:
    if not isinstance(value, dict):
        return {}
    return {str(key): str(item) for key, item in value.items()}


def _int_dict(value: object) -> dict[str, int]:
    if not isinstance(value, dict):
        return {}
    return {str(key): int(item) for key, item in value.items()}
