"""Deterministic infographic rendering engine."""

import html as html_lib
import logging
import math
import re
from dataclasses import dataclass, field
from typing import Any

from app.schemas.image import DiagramNode, VisualSpec

logger = logging.getLogger(__name__)

ASPECT_RATIO_DIMS: dict[str, tuple[int, int]] = {
    "1:1": (1600, 1600),
    "4:5": (1600, 2000),
    "16:9": (1600, 900),
}


@dataclass
class LayoutStage:
    number: int
    heading: str
    text: str
    visual: str
    x: int = 0
    y: int = 0
    width: int = 300
    height: int = 220


@dataclass
class LayoutPlan:
    layout: str
    title: str
    subtitle: str
    category: str
    day: int
    stages: list[LayoutStage] = field(default_factory=list)
    theme: str = "light_editorial"


def _sanitize_text(value: Any, fallback: str = "") -> str:
    if value is None:
        return fallback
    text = str(value).strip()
    text = text.replace("node1", "").replace("node2", "")
    text = text.replace("p1", "").replace("p2", "")
    text = text.replace("Concept element", "")
    text = re.sub(r"\s+", " ", text)
    text = text.strip(" -:|")
    return text or fallback


def _layout_from_spec(spec: VisualSpec) -> str:
    layout = getattr(spec, "layout", None) or getattr(spec, "diagram_type", None) or "process"
    normalized = str(layout).strip().lower().replace(" ", "_")
    aliases = {
        "process": "process",
        "steps": "process",
        "flowchart": "flow",
        "flow": "flow",
        "comparison": "comparison",
        "timeline": "timeline",
        "list": "process",
        "lifecycle": "cycle",
        "architecture": "flow",
        "hierarchy": "pyramid",
        "before_after": "before_after",
        "problem_solution": "problem_solution",
        "document_pipeline": "document_pipeline",
        "four_step": "four_step",
        "cycle": "cycle",
        "pyramid": "pyramid",
    }
    return aliases.get(normalized, "process")


def _stage_visual_from_node(node: DiagramNode) -> str:
    title = (node.title or "").lower()
    if "python" in title:
        return "python"
    if "install" in title or "download" in title:
        return "download"
    if "path" in title or "config" in title:
        return "terminal"
    if "document" in title or "chunk" in title:
        return "document"
    if "search" in title or "retriev" in title:
        return "search"
    if "ai" in title or "brain" in title:
        return "brain"
    if "result" in title or "answer" in title:
        return "brain"
    if "code" in title or "editor" in title:
        return "laptop"
    if "database" in title:
        return "database"
    if "api" in title or "server" in title:
        return "server"
    return "document"


def build_layout_plan(spec: VisualSpec) -> LayoutPlan:
    layout = _layout_from_spec(spec)
    category = _sanitize_text(getattr(spec, "category", "") or spec.diagram_type or "PROCESS", "PROCESS")
    title = _sanitize_text(spec.title, "Untitled")
    subtitle = _sanitize_text(spec.subtitle, "")

    if getattr(spec, "story", None):
        ordered = list(spec.story.values()) if isinstance(spec.story, dict) else list(spec.story)
        stages = []
        for index, item in enumerate(ordered[:4], start=1):
            if isinstance(item, dict):
                heading = _sanitize_text(item.get("heading") or item.get("title") or f"Step {index}", f"Step {index}")
                text = _sanitize_text(item.get("text") or item.get("description") or "Key step", "Key step")
                visual = _sanitize_text(item.get("visual") or item.get("type") or _stage_visual_from_node(DiagramNode(step=index, title=heading, description=text)), "document")
            else:
                heading = _sanitize_text(item, f"Step {index}")
                text = "Key step"
                visual = _stage_visual_from_node(DiagramNode(step=index, title=heading, description=text))
            stages.append(LayoutStage(number=index, heading=heading, text=text, visual=visual))
        if not stages:
            stages = [LayoutStage(number=i + 1, heading=_sanitize_text(node.title, f"Step {i + 1}"), text=_sanitize_text(node.description, "Key step"), visual=_stage_visual_from_node(node)) for i, node in enumerate(spec.nodes[:4])]
        return LayoutPlan(layout=layout, title=title, subtitle=subtitle, category=category.upper(), day=spec.day_number, stages=stages, theme=getattr(spec, "theme", "light_editorial"))

    stages = [
        LayoutStage(
            number=index + 1,
            heading=_sanitize_text(node.title, f"Step {index + 1}"),
            text=_sanitize_text(node.description, "Key step"),
            visual=_stage_visual_from_node(node),
        )
        for index, node in enumerate(spec.nodes[:4])
    ]
    return LayoutPlan(layout=layout, title=title, subtitle=subtitle, category=category.upper(), day=spec.day_number, stages=stages, theme=getattr(spec, "theme", "light_editorial"))


def _arrow_marker() -> str:
    return """<defs><marker id='arrowHead' viewBox='0 0 10 10' refX='8' refY='5' markerWidth='7' markerHeight='7' orient='auto-start-reverse'><path d='M 0 0 L 10 5 L 0 10 z' fill='#2563EB'/></marker></defs>"""


def _component_document(x: int, y: int, w: int, h: int, fill: str = '#FFFFFF') -> str:
    return f'''
    <g transform="translate({x},{y})">
      <rect x="0" y="0" width="{w}" height="{h}" rx="18" fill="{fill}" stroke="#CFE1FF" stroke-width="3"/>
      <rect x="16" y="18" width="{w-32}" height="14" rx="7" fill="#DCEEFF"/>
      <rect x="16" y="44" width="{w-32}" height="10" rx="5" fill="#EAF3FF"/>
      <rect x="16" y="64" width="{w-52}" height="10" rx="5" fill="#EAF3FF"/>
      <rect x="16" y="90" width="{w-38}" height="10" rx="5" fill="#EAF3FF"/>
      <path d="M{w-30} {h-22} l18 18 v-18 z" fill="#2563EB" opacity="0.12"/>
    </g>
    '''


def _component_chunks(x: int, y: int, w: int, h: int) -> str:
    pieces = []
    for i in range(5):
        pieces.append(f'<rect x="{i*26 + 10}" y="{30 + (i % 2) * 12}" width="90" height="88" rx="14" fill="#FFFFFF" stroke="#BFDBFE" stroke-width="3"/>')
    return f'''
    <g transform="translate({x},{y})">
      <rect x="0" y="0" width="{w}" height="{h}" rx="20" fill="#F1F9FF" stroke="#DCEEFF" stroke-width="2"/>
      {''.join(pieces)}
      <path d="M10 120 h120" stroke="#2563EB" stroke-width="6" stroke-linecap="round"/>
      <path d="M122 120 h90" stroke="#93C5FD" stroke-width="6" stroke-linecap="round"/>
    </g>
    '''


def _component_search(x: int, y: int, w: int, h: int) -> str:
    return f'''
    <g transform="translate({x},{y})">
      <circle cx="{w*0.45}" cy="{h*0.45}" r="40" fill="#FFFFFF" stroke="#2563EB" stroke-width="6"/>
      <path d="M{w*0.65} {h*0.68} L{w*0.8} {h*0.82}" stroke="#2563EB" stroke-width="8" stroke-linecap="round"/>
      <path d="M{w*0.18} {h*0.22} h{w*0.28} v{h*0.2} h- {w*0.28} z" fill="#DCEEFF" opacity="0.6"/>
      <rect x="18" y="120" width="{w-36}" height="26" rx="13" fill="#ECF8FF" stroke="#CFE1FF"/>
    </g>
    '''


def _component_brain(x: int, y: int, w: int, h: int) -> str:
    return f'''
    <g transform="translate({x},{y})">
      <rect x="15" y="30" width="{w-30}" height="{h-40}" rx="22" fill="#EAF5FF" stroke="#BFE0FF" stroke-width="3"/>
      <circle cx="{w*0.3}" cy="{h*0.45}" r="18" fill="#2563EB" opacity="0.14"/>
      <circle cx="{w*0.58}" cy="{h*0.45}" r="18" fill="#2563EB" opacity="0.14"/>
      <path d="M{w*0.18} {h*0.42} Q{w*0.26} {h*0.2} {w*0.42} {h*0.38} Q{w*0.5} {h*0.14} {w*0.72} {h*0.38} Q{w*0.84} {h*0.42} {w*0.78} {h*0.64} Q{w*0.7} {h*0.82} {w*0.42} {h*0.82} Q{w*0.2} {h*0.82} {w*0.18} {h*0.42} z" fill="#FFFFFF" stroke="#2563EB" stroke-width="4"/>
      <path d="M{w*0.34} {h*0.52} L{w*0.7} {h*0.52}" stroke="#2563EB" stroke-width="5" stroke-linecap="round"/>
      <path d="M{w*0.42} {h*0.35} L{w*0.52} {h*0.45} L{w*0.62} {h*0.35}" stroke="#2563EB" stroke-width="5" stroke-linecap="round" stroke-linejoin="round" fill="none"/>
    </g>
    '''


def _component_python(x: int, y: int, w: int, h: int) -> str:
    return f'''
    <g transform="translate({x},{y})">
      <rect x="18" y="24" width="{w-36}" height="{h-28}" rx="20" fill="#FFFFFF" stroke="#CFE1FF" stroke-width="3"/>
      <path d="M{w*0.3} {h*0.35} h{w*0.18} a18 18 0 0 1 18 18 v8 a18 18 0 0 1 -18 18 h-18" fill="none" stroke="#2563EB" stroke-width="10" stroke-linecap="round"/>
      <path d="M{w*0.7} {h*0.35} h-18 a18 18 0 0 0 -18 18 v8 a18 18 0 0 0 18 18 h18" fill="none" stroke="#43C6E8" stroke-width="10" stroke-linecap="round"/>
      <circle cx="{w*0.5}" cy="{h*0.5}" r="18" fill="#DCEEFF"/>
      <path d="M{w*0.47} {h*0.42} v16 M{w*0.39} {h*0.5} h16" stroke="#17365D" stroke-width="5" stroke-linecap="round"/>
    </g>
    '''


def _component_laptop(x: int, y: int, w: int, h: int) -> str:
    return f'''
    <g transform="translate({x},{y})">
      <rect x="18" y="15" width="{w-36}" height="{h-44}" rx="18" fill="#FFFFFF" stroke="#CFE1FF" stroke-width="3"/>
      <path d="M10 {h-22} h{w-20} l20 20 H0 z" fill="#DCEEFF"/>
      <rect x="50" y="42" width="{w-100}" height="22" rx="10" fill="#EAF3FF"/>
      <rect x="60" y="70" width="{w-120}" height="18" rx="9" fill="#BFDBFE"/>
    </g>
    '''


def _component_terminal(x: int, y: int, w: int, h: int) -> str:
    return f'''
    <g transform="translate({x},{y})">
      <rect x="0" y="0" width="{w}" height="{h}" rx="18" fill="#0F172A"/>
      <circle cx="22" cy="18" r="6" fill="#43C6E8"/>
      <circle cx="40" cy="18" r="6" fill="#F59E0B"/>
      <circle cx="58" cy="18" r="6" fill="#35B779"/>
      <path d="M36 82 L88 82" stroke="#43C6E8" stroke-width="7" stroke-linecap="round"/>
      <path d="M36 104 L130 104" stroke="#DCEEFF" stroke-width="7" stroke-linecap="round"/>
      <path d="M30 130 L122 130" stroke="#DCEEFF" stroke-width="7" stroke-linecap="round"/>
    </g>
    '''


def _component_server(x: int, y: int, w: int, h: int) -> str:
    return f'''
    <g transform="translate({x},{y})">
      <rect x="22" y="58" width="{w-44}" height="{h-80}" rx="20" fill="#FFFFFF" stroke="#CFE1FF" stroke-width="3"/>
      <path d="M22 102 h{w-44}" stroke="#DCEEFF" stroke-width="5"/>
      <path d="M22 142 h{w-44}" stroke="#DCEEFF" stroke-width="5"/>
      <rect x="38" y="82" width="30" height="16" rx="8" fill="#DCEEFF"/>
      <rect x="38" y="122" width="30" height="16" rx="8" fill="#DCEEFF"/>
      <circle cx="{w*0.75}" cy="{h*0.42}" r="26" fill="#EAF5FF" stroke="#2563EB" stroke-width="4"/>
      <path d="M{w*0.72} {h*0.42} l20 20 M{w*0.72} {h*0.42} l20 -20" stroke="#2563EB" stroke-width="5" stroke-linecap="round"/>
    </g>
    '''


def _component_database(x: int, y: int, w: int, h: int) -> str:
    return f'''
    <g transform="translate({x},{y})">
      <ellipse cx="{w*0.5}" cy="26" rx="90" ry="22" fill="#DCEEFF"/>
      <rect x="{w*0.18}" y="26" width="{w*0.64}" height="{h*0.44}" rx="18" fill="#FFFFFF" stroke="#CFE1FF" stroke-width="3"/>
      <ellipse cx="{w*0.5}" cy="{h*0.6}" rx="90" ry="22" fill="#EAF5FF"/>
      <rect x="{w*0.18}" y="{h*0.6}" width="{w*0.64}" height="{h*0.22}" rx="16" fill="#FFFFFF" stroke="#CFE1FF" stroke-width="3"/>
      <path d="M{w*0.18} 30 V{h*0.78} M{w*0.82} 30 V{h*0.78}" stroke="#93C5FD" stroke-width="3"/>
    </g>
    '''


def _component_download(x: int, y: int, w: int, h: int) -> str:
    return f'''
    <g transform="translate({x},{y})">
      <rect x="6" y="14" width="{w-12}" height="{h-18}" rx="18" fill="#FFFFFF" stroke="#CFE1FF" stroke-width="3"/>
      <path d="M{w*0.5} {h*0.28} v{h*0.38}" stroke="#2563EB" stroke-width="7" stroke-linecap="round"/>
      <path d="M{w*0.3} {h*0.62} L{w*0.5} {h*0.82} L{w*0.7} {h*0.62}" stroke="#2563EB" stroke-width="7" stroke-linecap="round" stroke-linejoin="round" fill="none"/>
      <path d="M28 {h-20} h{w-56}" stroke="#93C5FD" stroke-width="7" stroke-linecap="round"/>
    </g>
    '''


def _component_by_name(kind: str, x: int, y: int, w: int, h: int) -> str:
    mapping = {
        "document": _component_document,
        "chunks": _component_chunks,
        "database": _component_database,
        "search": _component_search,
        "brain": _component_brain,
        "python": _component_python,
        "laptop": _component_laptop,
        "download": _component_download,
        "terminal": _component_terminal,
        "server": _component_server,
    }
    fn = mapping.get(kind, _component_document)
    return fn(x, y, w, h)


def _render_process_layout(plan: LayoutPlan) -> str:
    stages = plan.stages[:4]
    width = 1600
    start_x = 140
    gap = 34
    card_w = (width - 2 * start_x - gap * (len(stages) - 1)) // max(1, len(stages))
    card_h = 240
    stage_y = 320
    parts = []
    for i, stage in enumerate(stages):
        x = start_x + i * (card_w + gap)
        parts.append(f'''
        <g>
          <rect x="{x}" y="{stage_y}" width="{card_w}" height="{card_h}" rx="26" fill="#FFFFFF" stroke="#D7E9FF" stroke-width="2"/>
          <circle cx="{x + 44}" cy="{stage_y + 42}" r="20" fill="#2563EB"/>
          <text x="{x + 44}" y="{stage_y + 48}" text-anchor="middle" font-size="18" font-weight="800" fill="#FFFFFF">{stage.number}</text>
          <text x="{x + 76}" y="{stage_y + 56}" font-size="22" font-weight="800" fill="#0F172A">{html_lib.escape(stage.heading[:22])}</text>
          <text x="{x + 30}" y="{stage_y + 92}" font-size="15" fill="#475569">{html_lib.escape(stage.text[:36])}</text>
        </g>
        ''')
        parts.append(_component_by_name(stage.visual, x + 62, stage_y + 108, card_w - 120, 100))
        if i < len(stages) - 1:
            arrow_x = x + card_w + 12
            parts.append(f'''<path d="M {arrow_x} {stage_y + 110} L {arrow_x + 26} {stage_y + 110}" stroke="#2563EB" stroke-width="5" marker-end="url(#arrowHead)" fill="none"/>''')
    return "".join(parts)


def _render_document_pipeline_layout(plan: LayoutPlan) -> str:
    parts = []
    parts.append('<rect x="120" y="280" width="210" height="200" rx="26" fill="#F4F9FF" stroke="#DCEEFF" stroke-width="2"/>')
    parts.append('<rect x="400" y="280" width="210" height="200" rx="26" fill="#F4F9FF" stroke="#DCEEFF" stroke-width="2"/>')
    parts.append('<rect x="690" y="280" width="210" height="200" rx="26" fill="#F4F9FF" stroke="#DCEEFF" stroke-width="2"/>')
    parts.append('<rect x="980" y="280" width="210" height="200" rx="26" fill="#F4F9FF" stroke="#DCEEFF" stroke-width="2"/>')
    parts.append('<rect x="1240" y="280" width="210" height="200" rx="26" fill="#F4F9FF" stroke="#DCEEFF" stroke-width="2"/>')

    stage_boxes = []
    positions = [(130, 290), (410, 290), (700, 290), (990, 290), (1260, 290)]
    for i, stage in enumerate(plan.stages[:5]):
        x, y = positions[i]
        stage_boxes.append(f'<circle cx="{x + 34}" cy="{y + 34}" r="18" fill="#2563EB"/><text x="{x + 34}" y="{y + 40}" text-anchor="middle" font-size="16" fill="#fff" font-weight="800">{stage.number}</text>')
        stage_boxes.append(f'<text x="{x + 66}" y="{y + 42}" font-size="20" font-weight="800" fill="#0F172A">{html_lib.escape(stage.heading[:18])}</text>')
        stage_boxes.append(f'<text x="{x + 26}" y="{y + 82}" font-size="14" fill="#475569">{html_lib.escape(stage.text[:30])}</text>')
        if stage.visual in {"document", "download"}:
            stage_boxes.append(_component_document(x + 34, y + 90, 140, 100))
        elif stage.visual == "chunks":
            stage_boxes.append(_component_chunks(x + 34, y + 90, 140, 100))
        elif stage.visual == "search":
            stage_boxes.append(_component_search(x + 36, y + 90, 140, 100))
        elif stage.visual == "brain":
            stage_boxes.append(_component_brain(x + 30, y + 90, 150, 100))

    parts.append(''.join(stage_boxes))
    for i in range(4):
        x = 330 + i * 290
        parts.append(f'<path d="M {x} 380 L {x + 70} 380" stroke="#2563EB" stroke-width="5" marker-end="url(#arrowHead)" fill="none"/>')
    return ''.join(parts)


def _render_before_after_layout(plan: LayoutPlan) -> str:
    stages = plan.stages[:2]
    label_y = 300
    x1 = 150
    x2 = 820
    w = 420
    h = 320
    parts = [
        f'<text x="{x1 + 120}" y="{label_y}" font-size="20" font-weight="800" fill="#17365D">BEFORE</text>',
        f'<text x="{x2 + 120}" y="{label_y}" font-size="20" font-weight="800" fill="#17365D">AFTER</text>',
        f'<rect x="{x1}" y="{label_y + 20}" width="{w}" height="{h}" rx="28" fill="#F4F9FF" stroke="#DCEEFF" stroke-width="2"/>',
        f'<rect x="{x2}" y="{label_y + 20}" width="{w}" height="{h}" rx="28" fill="#F4F9FF" stroke="#DCEEFF" stroke-width="2"/>',
    ]
    if stages:
        parts.append(f'<text x="{x1 + 28}" y="{label_y + 70}" font-size="26" font-weight="800" fill="#0F172A">{html_lib.escape(stages[0].heading[:20])}</text>')
        parts.append(f'<text x="{x2 + 28}" y="{label_y + 70}" font-size="26" font-weight="800" fill="#0F172A">{html_lib.escape(stages[1].heading[:20])}</text>')
    parts.append(_component_document(x1 + 80, label_y + 120, 220, 150))
    parts.append(_component_search(x2 + 80, label_y + 120, 220, 150))
    parts.append(f'<path d="M {x1 + w} {label_y + 170} L {x2} {label_y + 170}" stroke="#2563EB" stroke-width="6" marker-end="url(#arrowHead)" fill="none"/>')
    return ''.join(parts)


def _render_timeline_layout(plan: LayoutPlan) -> str:
    stages = plan.stages[:4]
    positions = [180, 480, 780, 1080]
    parts = []
    for i, stage in enumerate(stages):
        x = positions[i]
        parts.append(f'<rect x="{x}" y="300" width="220" height="250" rx="28" fill="#FFFFFF" stroke="#DCEEFF" stroke-width="2"/>')
        parts.append(f'<circle cx="{x + 28}" cy="326" r="18" fill="#2563EB"/><text x="{x + 28}" y="{332}" text-anchor="middle" font-size="16" fill="#fff" font-weight="800">{stage.number}</text>')
        parts.append(f'<text x="{x + 54}" y="{332}" font-size="22" font-weight="800" fill="#0F172A">{html_lib.escape(stage.heading[:18])}</text>')
        parts.append(f'<text x="{x + 28}" y="{368}" font-size="15" fill="#475569">{html_lib.escape(stage.text[:28])}</text>')
        parts.append(_component_by_name(stage.visual, x + 40, y=390, w=140, h=120))
        if i < len(stages) - 1:
            next_x = positions[i + 1]
            parts.append(f'<path d="M {x + 220} 430 L {next_x} 430" stroke="#2563EB" stroke-width="5" marker-end="url(#arrowHead)" fill="none"/>')
    return ''.join(parts)


def _render_cycle_layout(plan: LayoutPlan) -> str:
    stages = plan.stages[:4]
    cx, cy = 800, 440
    radius = 220
    angles = [math.radians(45), math.radians(135), math.radians(225), math.radians(315)]
    parts = []
    for i, stage in enumerate(stages):
        a = angles[i]
        x = cx + radius * math.cos(a)
        y = cy + radius * math.sin(a)
        card_w, card_h = 210, 150
        rect_x = x - card_w / 2
        rect_y = y - card_h / 2
        parts.append(f'<rect x="{rect_x}" y="{rect_y}" width="{card_w}" height="{card_h}" rx="26" fill="#FFFFFF" stroke="#DCEEFF" stroke-width="2"/>')
        parts.append(f'<circle cx="{rect_x + 28}" cy="{rect_y + 28}" r="18" fill="#2563EB"/><text x="{rect_x + 28}" y="{rect_y + 33}" text-anchor="middle" font-size="16" fill="#fff" font-weight="800">{stage.number}</text>')
        parts.append(f'<text x="{rect_x + 54}" y="{rect_y + 36}" font-size="21" font-weight="800" fill="#0F172A">{html_lib.escape(stage.heading[:18])}</text>')
        parts.append(f'<text x="{rect_x + 26}" y="{rect_y + 76}" font-size="14" fill="#475569">{html_lib.escape(stage.text[:28])}</text>')
        parts.append(_component_by_name(stage.visual, int(rect_x + 44), int(rect_y + 82), 120, 54))
    parts.append(f'<circle cx="{cx}" cy="{cy}" r="120" fill="#F3F9FF" stroke="#DDA7" stroke-width="2"/>')
    return ''.join(parts)


def _render_flow_layout(plan: LayoutPlan) -> str:
    stages = plan.stages[:4]
    x_positions = [180, 500, 820, 1140]
    parts = []
    for i, stage in enumerate(stages):
        x = x_positions[i]
        parts.append(f'<rect x="{x}" y="300" width="220" height="220" rx="26" fill="#FFFFFF" stroke="#DCEEFF" stroke-width="2"/>')
        parts.append(f'<circle cx="{x + 28}" cy="332" r="18" fill="#2563EB"/><text x="{x + 28}" y="{338}" text-anchor="middle" font-size="16" fill="#fff" font-weight="800">{stage.number}</text>')
        parts.append(f'<text x="{x + 58}" y="{334}" font-size="22" font-weight="800" fill="#0F172A">{html_lib.escape(stage.heading[:18])}</text>')
        parts.append(f'<text x="{x + 28}" y="{370}" font-size="15" fill="#475569">{html_lib.escape(stage.text[:28])}</text>')
        parts.append(_component_by_name(stage.visual, x + 44, 392, 120, 90))
        if i < len(stages) - 1:
            next_x = x_positions[i + 1]
            parts.append(f'<path d="M {x + 220} {410} L {next_x} {410}" stroke="#2563EB" stroke-width="5" marker-end="url(#arrowHead)" fill="none"/>')
    return ''.join(parts)


def _render_pyramid_layout(plan: LayoutPlan) -> str:
    stages = plan.stages[:4]
    y_positions = [560, 470, 380, 290]
    width = [520, 400, 300, 200]
    x_base = 540
    parts = []
    for i, stage in enumerate(stages):
        w = width[i]
        h = 110
        x = x_base + (520 - w) / 2
        y = y_positions[i]
        parts.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="22" fill="#FFFFFF" stroke="#DCEEFF" stroke-width="2"/>')
        parts.append(f'<circle cx="{x + 26}" cy="{y + 28}" r="16" fill="#2563EB"/><text x="{x + 26}" y="{y + 34}" text-anchor="middle" font-size="14" fill="#fff" font-weight="800">{stage.number}</text>')
        parts.append(f'<text x="{x + 52}" y="{y + 34}" font-size="18" font-weight="800" fill="#0F172A">{html_lib.escape(stage.heading[:20])}</text>')
        parts.append(f'<text x="{x + 20}" y="{y + 70}" font-size="13" fill="#475569">{html_lib.escape(stage.text[:28])}</text>')
    return ''.join(parts)


def _render_problem_solution_layout(plan: LayoutPlan) -> str:
    stages = plan.stages[:2]
    left_x, right_x = 170, 880
    y = 300
    w, h = 420, 320
    parts = [
        f'<rect x="{left_x}" y="{y}" width="{w}" height="{h}" rx="28" fill="#F7FBFF" stroke="#DCEEFF" stroke-width="2"/>',
        f'<rect x="{right_x}" y="{y}" width="{w}" height="{h}" rx="28" fill="#F7FBFF" stroke="#DCEEFF" stroke-width="2"/>',
        f'<text x="{left_x + 28}" y="{y + 52}" font-size="20" font-weight="800" fill="#17365D">PROBLEM</text>',
        f'<text x="{right_x + 28}" y="{y + 52}" font-size="20" font-weight="800" fill="#17365D">SOLUTION</text>',
    ]
    if stages:
        parts.append(f'<text x="{left_x + 28}" y="{y + 86}" font-size="24" font-weight="800" fill="#0F172A">{html_lib.escape(stages[0].heading[:20])}</text>')
        parts.append(f'<text x="{right_x + 28}" y="{y + 86}" font-size="24" font-weight="800" fill="#0F172A">{html_lib.escape(stages[1].heading[:20])}</text>')
    parts.append(_component_document(left_x + 80, y + 110, 230, 150))
    parts.append(_component_brain(right_x + 70, y + 120, 230, 140))
    parts.append(f'<path d="M {left_x + w} {y + 180} L {right_x} {y + 180}" stroke="#2563EB" stroke-width="6" marker-end="url(#arrowHead)" fill="none"/>')
    return ''.join(parts)


def _render_layout(plan: LayoutPlan) -> str:
    renderers = {
        "process": _render_process_layout,
        "four_step": _render_process_layout,
        "flow": _render_flow_layout,
        "timeline": _render_timeline_layout,
        "comparison": _render_process_layout,
        "before_after": _render_before_after_layout,
        "problem_solution": _render_problem_solution_layout,
        "document_pipeline": _render_document_pipeline_layout,
        "pyramid": _render_pyramid_layout,
        "cycle": _render_cycle_layout,
    }
    renderer = renderers.get(plan.layout, _render_process_layout)
    return renderer(plan)


def build_html(visual_spec: VisualSpec, bg_bytes: bytes) -> str:
    """Build a deterministic educational infographic using SVG rather than AI image panels."""
    plan = build_layout_plan(visual_spec)
    width, height = ASPECT_RATIO_DIMS.get(visual_spec.aspect_ratio, (1600, 900))

    title = html_lib.escape(plan.title)
    subtitle = html_lib.escape(plan.subtitle)
    category = html_lib.escape(plan.category)
    day_text = f"DAY {plan.day:02d}"
    background = "#F7FAFC"
    blue = "#2563EB"
    navy = "#17365D"
    text = "#0F172A"
    muted = "#475569"
    layout_svg = _render_layout(plan)

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <style>
    html, body {{ margin: 0; padding: 0; background: {background}; font-family: 'Segoe UI', Arial, sans-serif; }}
    body {{ width: {width}px; height: {height}px; overflow: hidden; }}
    svg {{ display: block; background: {background}; }}
    .title {{ font-size: 42px; font-weight: 800; letter-spacing: -0.05em; fill: {text}; }}
    .subtitle {{ font-size: 20px; fill: {muted}; }}
    .day {{ font-size: 18px; font-weight: 700; letter-spacing: 0.12em; fill: {navy}; }}
    .category {{ font-size: 14px; font-weight: 800; letter-spacing: 0.1em; fill: {blue}; }}
    .small {{ font-size: 13px; fill: {muted}; }}
    .comparison-grid {{ display: block; }}
    .key-points {{ list-style: none; display: flex; gap: 12px; padding: 0; margin: 0; position: absolute; top: 760px; left: 48px; right: 48px; }}
    .key-points li {{ flex: 1; border-radius: 14px; background: #FFFFFF; border: 1px solid #DCEEFF; padding: 12px 16px; font-size: 14px; font-weight: 700; color: {text}; }}
  </style>
</head>
<body>
  <svg width="{width}" height="{height}" viewBox="0 0 {width} {height}" xmlns="http://www.w3.org/2000/svg">
    {_arrow_marker()}
    <rect width="{width}" height="{height}" fill="{background}"/>
    <rect x="48" y="52" width="172" height="46" rx="23" fill="#FFFFFF" stroke="#DCEEFF" stroke-width="2"/>
    <text x="134" y="81" text-anchor="middle" class="day">{day_text}</text>
    <text x="{width - 210}" y="78" text-anchor="middle" class="category">{category}</text>
    <text x="48" y="158" class="title">{title}</text>
    {f'<text x="48" y="202" class="subtitle">{subtitle}</text>' if subtitle else ''}
    <g class="comparison-grid">{layout_svg}</g>
    <text x="{width/2}" y="860" text-anchor="middle" font-size="14" font-weight="700" letter-spacing="0.14em" fill="#475569">#LEARNWITHAI</text>
  </svg>
  <ul class="key-points">{''.join(f'<li>{html_lib.escape(point)}</li>' for point in visual_spec.key_points)}</ul>
</body>
</html>"""
