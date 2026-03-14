"""Template library for creative preview.

Upload ad template images (PNG/JPG from Figma/Canva), define text
slot regions, and render previews with generated copy composited on.
"""
from __future__ import annotations

import io
import json
import zipfile
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import BinaryIO

from PIL import Image, ImageDraw, ImageFont


# ── Data Model ──────────────────────────────────────────

@dataclass
class TextSlot:
    """A text region on a template image."""
    slot_id: str          # maps to platform copy key: "headline", "primary_text", etc.
    label: str            # display name
    x: int = 0
    y: int = 0
    width: int = 400
    height: int = 80
    font_size: int = 32
    font_color: str = "#FFFFFF"
    font_weight: str = "normal"  # "normal" or "bold"
    align: str = "left"          # "left", "center", "right"


@dataclass
class AdTemplate:
    """A template image with defined text slot regions."""
    template_id: str
    name: str
    platform: str = ""
    image_filename: str = ""
    width: int = 0
    height: int = 0
    slots: list[TextSlot] = field(default_factory=list)


def _templates_dir(client_id: str) -> Path:
    """Return templates directory for a client."""
    d = Path(__file__).parent / "clients" / client_id / "templates"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _slugify(name: str) -> str:
    import re
    s = name.lower().strip()
    s = re.sub(r"[^a-z0-9]+", "-", s)
    return s.strip("-") or "template"


# ── CRUD ────────────────────────────────────────────────

def list_templates(client_id: str) -> list[AdTemplate]:
    """List all templates for a client."""
    d = _templates_dir(client_id)
    templates = []
    for f in sorted(d.glob("*.json")):
        try:
            data = json.loads(f.read_text())
            slots = [TextSlot(**s) for s in data.pop("slots", [])]
            templates.append(AdTemplate(**data, slots=slots))
        except Exception:
            continue
    return templates


def load_template(client_id: str, template_id: str) -> AdTemplate | None:
    path = _templates_dir(client_id) / f"{template_id}.json"
    if not path.exists():
        return None
    data = json.loads(path.read_text())
    slots = [TextSlot(**s) for s in data.pop("slots", [])]
    return AdTemplate(**data, slots=slots)


def save_template(client_id: str, template: AdTemplate):
    d = _templates_dir(client_id)
    data = asdict(template)
    with open(d / f"{template.template_id}.json", "w") as f:
        json.dump(data, f, indent=2)


def save_template_image(client_id: str, template_id: str, image_bytes: bytes, filename: str):
    """Save the uploaded template image."""
    d = _templates_dir(client_id)
    ext = Path(filename).suffix or ".png"
    dest = d / f"{template_id}{ext}"
    dest.write_bytes(image_bytes)
    return dest.name


def delete_template(client_id: str, template_id: str):
    d = _templates_dir(client_id)
    for f in d.glob(f"{template_id}.*"):
        f.unlink()


def get_template_image_path(client_id: str, template: AdTemplate) -> Path | None:
    """Get the full path to a template's image file."""
    if not template.image_filename:
        return None
    p = _templates_dir(client_id) / template.image_filename
    return p if p.exists() else None


def create_template(client_id: str, name: str, image_file: BinaryIO, filename: str,
                    platform: str = "") -> AdTemplate:
    """Create a new template from an uploaded image."""
    tid = _slugify(name)
    # Ensure unique
    existing = {t.template_id for t in list_templates(client_id)}
    final_id = tid
    counter = 2
    while final_id in existing:
        final_id = f"{tid}-{counter}"
        counter += 1

    # Read image to get dimensions
    img_bytes = image_file.read()
    img = Image.open(io.BytesIO(img_bytes))
    w, h = img.size

    # Save image
    img_name = save_template_image(client_id, final_id, img_bytes, filename)

    template = AdTemplate(
        template_id=final_id,
        name=name,
        platform=platform,
        image_filename=img_name,
        width=w,
        height=h,
        slots=[],
    )
    save_template(client_id, template)
    return template


# ── Rendering ───────────────────────────────────────────

def _get_font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    """Get a font, falling back to default if system fonts aren't available."""
    font_paths = [
        "/System/Library/Fonts/Helvetica.ttc",        # macOS
        "/System/Library/Fonts/SFNSText.ttf",          # macOS SF
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",  # Linux
        "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
    ]
    if bold:
        font_paths = [
            "/System/Library/Fonts/Helvetica.ttc",
            "/System/Library/Fonts/SFNSText-Bold.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
            "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
        ] + font_paths

    for fp in font_paths:
        try:
            return ImageFont.truetype(fp, size)
        except (IOError, OSError):
            continue
    return ImageFont.load_default()


def _wrap_text(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.FreeTypeFont,
               max_width: int) -> list[str]:
    """Word-wrap text to fit within a max pixel width."""
    words = text.split()
    lines: list[str] = []
    current = ""
    for word in words:
        test = f"{current} {word}".strip()
        bbox = draw.textbbox((0, 0), test, font=font)
        if bbox[2] - bbox[0] <= max_width:
            current = test
        else:
            if current:
                lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines or [""]


def render_preview(client_id: str, template: AdTemplate,
                   copy_data: dict) -> Image.Image | None:
    """Render an ad preview: template image + copy text overlaid.

    Args:
        copy_data: dict mapping slot_id → text string
            e.g. {"headline": "Try it free", "primary_text": "..."}

    Returns:
        PIL Image with text composited, or None if image not found.
    """
    img_path = get_template_image_path(client_id, template)
    if not img_path:
        return None

    img = Image.open(img_path).convert("RGBA")
    # Create overlay for text with semi-transparent background
    overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)

    for slot in template.slots:
        text = copy_data.get(slot.slot_id, "")
        if not text:
            continue

        font = _get_font(slot.font_size, bold=(slot.font_weight == "bold"))
        color = slot.font_color

        # Add subtle text background for readability
        draw.rectangle(
            [slot.x - 4, slot.y - 2, slot.x + slot.width + 4, slot.y + slot.height + 2],
            fill=(0, 0, 0, 90),
        )

        # Word-wrap and draw
        lines = _wrap_text(draw, text, font, slot.width)
        line_height = slot.font_size + 4
        y_offset = slot.y

        for line in lines:
            if y_offset + line_height > slot.y + slot.height:
                break  # Don't overflow the slot region

            if slot.align == "center":
                bbox = draw.textbbox((0, 0), line, font=font)
                lw = bbox[2] - bbox[0]
                x = slot.x + (slot.width - lw) // 2
            elif slot.align == "right":
                bbox = draw.textbbox((0, 0), line, font=font)
                lw = bbox[2] - bbox[0]
                x = slot.x + slot.width - lw
            else:
                x = slot.x

            draw.text((x, y_offset), line, fill=color, font=font)
            y_offset += line_height

    return Image.alpha_composite(img, overlay).convert("RGB")


def render_all_previews(client_id: str, template: AdTemplate,
                        ad_sets: list[dict]) -> list[tuple[str, Image.Image]]:
    """Render previews for all ad sets on a template.

    Returns list of (label, image) tuples.
    """
    results = []
    for i, ad_set in enumerate(ad_sets):
        copy_data = {slot.slot_id: ad_set.get(slot.slot_id, "") for slot in template.slots}
        img = render_preview(client_id, template, copy_data)
        if img:
            label = f"{ad_set.get('original_ad', 'Ad')} — {ad_set.get('angle', f'v{i+1}')}"
            results.append((label, img))
    return results


def export_previews_zip(previews: list[tuple[str, Image.Image]],
                        template_name: str = "template") -> bytes:
    """Export rendered previews as a ZIP of PNGs."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for i, (label, img) in enumerate(previews):
            img_buf = io.BytesIO()
            img.save(img_buf, format="PNG", optimize=True)
            safe_label = _slugify(label)[:40]
            zf.writestr(f"{template_name}_{i+1}_{safe_label}.png", img_buf.getvalue())
    return buf.getvalue()
