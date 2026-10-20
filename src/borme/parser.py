"""Parse BORME Section A XML documents into filings, acts and positions.

A document (one province, one day) is a list of filings, each two paragraphs::

    <p class="articulo">464219 - SINERGIA ENERGETICA SOCIEDAD LIMITADA.</p>
    <p class="parrafo">Ceses/Dimisiones. Adm. Unico: BENEYTO FERRE JAUME.
      Nombramientos. Adm. Unico: BENEYTO VAÑO JOSEP FRANCESC.
      Datos registrales. S 8 , H AB 18123, I/A 4 (13.10.26).</p>

The paragraph is a sequence of acts, each starting with a known heading
(``ACT_HEADINGS``). Acts about positions (appointments, removals…) list
``Role: NAME;NAME.`` pairs; a few acts carry fields this module extracts
(capital, address, new name, start of operations). The closing
"Datos registrales" give the company's registry sheet (``hoja``), its stable
identifier in the Mercantile Registry: the BORME carries no tax id.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

from lxml import etree

# Act headings as the BORME prints them; accents and case vary between years,
# so matching ignores both. The longest heading wins.
ACT_HEADINGS: tuple[str, ...] = (
    "Nombramientos",
    "Ceses/Dimisiones",
    "Revocaciones",
    "Reelecciones",
    "Cancelaciones de oficio de nombramientos",
    "Constitución",
    "Disolución",
    "Extinción",
    "Modificaciones estatutarias",
    "Cambio de objeto social",
    "Ampliación del objeto social",
    "Cambio de denominación social",
    "Cambio de domicilio social",
    "Ampliación de capital",
    "Reducción de capital",
    "Desembolso de dividendos pasivos",
    "Declaración de unipersonalidad",
    "Sociedad unipersonal",
    "Pérdida del carácter de unipersonalidad",
    "Situación concursal",
    "Fusión por absorción",
    "Fusión por unión",
    "Escisión parcial",
    "Escisión total",
    "Segregación",
    "Cesión global de activo y pasivo",
    "Transformación de sociedad",
    "Adaptación de sociedad",
    "Adaptación Ley 2/95",
    "Adaptación Ley 44/2015",
    "Adaptada segun D.T. 2 apartado 2 Ley 2/95",
    "Reapertura hoja registral",
    "Reactivación de la sociedad (Art. 242 del Reglamento del Registro Mercantil)",
    "Cierre provisional hoja registral por baja en el índice de Entidades Jurídicas",
    "Cierre provisional de la hoja registral por revocación del NIF",
    "Cierre provisional hoja registral por revocación del NIFde Entidades Jurídicas",
    "Cierre provisional hoja registral art. 137.2 Ley 43/1995 Impuesto de Sociedades",
    "Cierre de Sucursal",
    "Apertura de sucursal",
    "Primera sucursal de sociedad extranjera",
    "Sucursal",
    "Página web de la sociedad",
    "Emisión de obligaciones",
    "Modificación de poderes",
    "Modificación de duración",
    "Articulo 378.5 del Reglamento del Registro Mercantil",
    "Primera inscripcion (O.M. 10/6/1.997)",
    "Anotación preventiva. Demanda de impugnación de acuerdos sociales",
    "Anotación preventiva. Declaración de deudor fallido",
    "Acuerdo de ampliación de capital social sin ejecutar. Importe del acuerdo",
    "Crédito incobrable",
    "Suspensión de pagos",
    "Quiebra",
    "Empresario Individual",
    "Fe de erratas",
    "Otros conceptos",
    "Datos registrales",
)
OTHER = "Otros conceptos"
REGISTRY = "Datos registrales"

# Acts whose content is a list of positions ("Socio único" for sole members).
POSITION_ACTS: frozenset[str] = frozenset(
    {
        "Nombramientos",
        "Ceses/Dimisiones",
        "Revocaciones",
        "Reelecciones",
        "Cancelaciones de oficio de nombramientos",
        "Declaración de unipersonalidad",
    }
)

# A role label is cut at the nearest ". " before its colon, except after these
# abbreviations, which start two-piece labels ("Adm. Unico", "Dir. General").
_LABEL_PREFIXES = frozenset({"adm", "ent", "cons", "dir", "d"})
_MAX_LABEL = 40


def unaccented(text: str) -> str:
    """Lowercase, no accents: the comparison form of headings and labels.

    Maps each character to exactly one, so offsets found in the result are
    offsets in ``text`` (NFKD or ``lower`` alone would expand "…" or "İ").
    Compose ``text`` first (NFC) for decomposed accents to be dropped.
    """

    def one(c: str) -> str:
        base = unicodedata.normalize("NFD", c)[0]
        low = base.lower()
        return low if len(low) == 1 else base

    return "".join(one(c) for c in text)


_CANONICAL = {unaccented(h): h for h in ACT_HEADINGS}
# A heading opens the paragraph or follows "." (old years write ".-"); it is
# followed by "." / ":" or the end. Matching runs on the unaccented text, which
# keeps the offsets of the original.
_HEADING_RE = re.compile(
    r"(?:^|(?<=\.)-?\s*)("
    + "|".join(re.escape(h) for h in sorted(_CANONICAL, key=len, reverse=True))
    + r")(?=[.:]|\s*$)"
)
_FILING_RE = re.compile(r"^\s*(?P<number>\d+)\s*-\s*(?P<company>.+?)\.?\s*$", re.DOTALL)
_AMOUNT = r"(-?\d{1,3}(?:\.\d{3})+(?:,\d+)?|-?\d+(?:,\d+)?)\s*(?:euros|€)"
_SHORT_DATE_RE = re.compile(r"(\d{1,2})\.(\d{1,2})\.(\d{2,4})")
# Two-digit years: the BORME starts in 2009, but registry dates go back decades.
_CENTURY_PIVOT = 70
_TWO_DIGITS = 100


@dataclass
class Position:
    """One person or company in one role of a positions act."""

    role: str
    name: str


@dataclass
class Act:
    kind: str
    text: str
    positions: list[Position] = field(default_factory=list)
    capital: float | None = None
    resulting_capital: float | None = None
    address: str | None = None
    new_name: str | None = None
    purpose: str | None = None
    start_of_operations: date | None = None


@dataclass
class Registry:
    """The "Datos registrales" of a filing."""

    volume: str | None = None
    page: str | None = None
    section: str | None = None
    sheet: str | None = None
    entry: str | None = None
    entry_date: date | None = None


@dataclass
class Filing:
    """One filing: a company and the acts registered for it."""

    number: int
    company: str
    text: str
    acts: list[Act]
    registry: Registry


@dataclass
class Document:
    id: str
    province: str
    date: date
    filings: list[Filing]


def short_date(text: str) -> date | None:
    """'13.10.26' or '1.10.2026' → date; None if it is not a valid date."""
    m = _SHORT_DATE_RE.search(text)
    if not m:
        return None
    day, month, year = (int(x) for x in m.groups())
    if year < _TWO_DIGITS:
        year += 2000 if year < _CENTURY_PIVOT else 1900
    try:
        return date(year, month, day)
    except ValueError:
        return None


def amount(text: str, label: str) -> float | None:
    """Amount after ``label:`` ('3.000,00 Euros' → 3000.0)."""
    m = re.search(re.escape(label) + r"\s*:\s*" + _AMOUNT, text, re.IGNORECASE)
    if not m:
        return None
    return float(m.group(1).replace(".", "").replace(",", "."))


def _field(text: str, label: str) -> str | None:
    """Text after ``label:`` up to the next 'Label:' or the end."""
    m = re.search(
        re.escape(label) + r"\s*:\s*(.+?)\.?(?=\s+[A-ZÁÉÍÓÚ][\w ]{2,30}:\s|\s*$)",
        text,
        re.DOTALL,
    )
    return m.group(1).strip() if m else None


def _label_start(text: str, colon: int, floor: int) -> int:
    """Start of the role label that ends at ``colon`` (not before ``floor``)."""
    cut = text.rfind(". ", floor, colon)
    start = floor if cut < 0 else cut + 2
    if cut >= 0:
        previous = text.rfind(" ", floor, cut)
        piece = text[previous + 1 : cut] if previous >= 0 else text[floor:cut]
        if unaccented(piece) in _LABEL_PREFIXES:
            start = cut - len(piece)
    return start


def positions(text: str) -> list[Position]:
    """Role/name pairs of a positions act.

    ``'Adm. Unico: A. Consejero: B;C.'`` → (Adm. Unico, A), (Consejero, B),
    (Consejero, C).
    """
    text = text.strip()
    labels: list[tuple[int, int]] = []  # (label start, colon)
    floor = 0
    for colon in (m.start() for m in re.finditer(":", text)):
        start = _label_start(text, colon, floor)
        if 0 < colon - start <= _MAX_LABEL and ";" not in text[start:colon]:
            labels.append((start, colon))
            floor = colon + 1
    out = []
    for i, (start, colon) in enumerate(labels):
        end = labels[i + 1][0] if i + 1 < len(labels) else len(text)
        role = " ".join(text[start:colon].split())
        for name in text[colon + 1 : end].split(";"):
            clean = " ".join(name.split()).strip(" .")
            if clean:
                out.append(Position(role, clean))
    return out


def registry(text: str) -> Registry:
    """'T 21104 , F 127, S 8, H M 374639, I/A 2 (12.01.06)' → its fields."""

    def get(key: str) -> str | None:
        m = re.search(rf"(?:^|,)\s*{key}\s+([^,(]+)", text)
        return " ".join(m.group(1).split()) if m else None

    when = re.search(r"\(([^)]+)\)", text)
    return Registry(
        volume=get("T"),
        page=get("F"),
        section=get("S"),
        sheet=get("H"),
        entry=get("I/A"),
        entry_date=short_date(when.group(1)) if when else None,
    )


def _details(act: Act) -> None:
    """Fill the structured fields of the acts that carry them."""
    t = act.text
    if act.kind in POSITION_ACTS:
        act.positions = positions(t)
    elif act.kind == "Constitución":
        start = _field(t, "Comienzo de operaciones")
        act.start_of_operations = short_date(start) if start else None
        act.purpose = _field(t, "Objeto social")
        act.address = _field(t, "Domicilio")
        act.capital = amount(t, "Capital")
    elif act.kind in ("Ampliación de capital", "Reducción de capital"):
        act.capital = amount(t, "Capital")
        act.resulting_capital = amount(t, "Resultante Suscrito")
    elif act.kind == "Cambio de domicilio social":
        act.address = t.strip(" .") or None
    elif act.kind == "Cambio de denominación social":
        act.new_name = t.strip(" .") or None
    elif act.kind in ("Cambio de objeto social", "Ampliación del objeto social"):
        act.purpose = t.strip(" .") or None


def acts(paragraph: str) -> tuple[list[Act], Registry]:
    """Split a filing's paragraph into its acts and its registry data."""
    text = unicodedata.normalize("NFC", " ".join(paragraph.split()))
    marks = list(_HEADING_RE.finditer(unaccented(text)))
    found: list[Act] = []
    reg = Registry()
    # Free text before the first heading (old years) is kept as "other".
    head = text[: marks[0].start()] if marks else text
    if head.strip(" .-"):
        found.append(Act(kind=OTHER, text=head.strip(" -")))
    for i, m in enumerate(marks):
        end = marks[i + 1].start() if i + 1 < len(marks) else len(text)
        content = text[m.end() : end].lstrip(".: ").rstrip(" -").strip()
        kind = _CANONICAL[m.group(1)]
        if kind == REGISTRY:
            reg = registry(content)
            continue
        act = Act(kind=kind, text=content)
        _details(act)
        found.append(act)
    return found, reg


def document(xml: bytes) -> Document | None:
    """Parse one Section A document; None for the daily alphabetical index."""
    root = etree.fromstring(xml)
    meta = root.find("metadatos")
    if meta is None:
        return None
    doc_id = meta.findtext("identificador", "")
    province = meta.findtext("titulo", "")
    if doc_id.endswith("-99") or unaccented(province).startswith("indice"):
        return None
    when = meta.findtext("fecha_publicacion", "")
    published = date(int(when[:4]), int(when[4:6]), int(when[6:8]))

    filings: list[Filing] = []
    current: tuple[int, str] | None = None
    for p in root.iter("p"):
        kind = p.get("class")
        text = "".join(p.itertext())
        if kind == "articulo":
            m = _FILING_RE.match(text)
            current = (
                (int(m.group("number")), " ".join(m.group("company").split()))
                if m
                else None
            )
        elif kind == "parrafo" and current is not None:
            found, reg = acts(text)
            filings.append(
                Filing(
                    number=current[0],
                    company=current[1],
                    text=" ".join(text.split()),
                    acts=found,
                    registry=reg,
                )
            )
            current = None
    return Document(doc_id, province, published, filings)


def read(path: Path) -> Document | None:
    return document(path.read_bytes())
