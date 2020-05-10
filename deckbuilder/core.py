import html
from enum import Enum
from typing import Tuple, List, Optional, Dict, Any, Set

Rect = Tuple[float, float, float, float]
Point = Tuple[float, float]


class HAlign(Enum):
	Left = "left"
	Center = "center"
	Right = "right"
	Justify = "justify"


class VAlign(Enum):
	Top = "top"
	Center = "center"
	Bottom = "bottom"


class Deckbuilder:
	def __init__(self):
		self.decks: List[Deck] = []

	def make_deck(self, name: str, size: Point) -> 'Deck':
		deck = Deck(self, name, size)
		self.decks.append(deck)
		return deck


def convert_color(s: str) -> str:
	return s


class TextStyle:
	def __init__(self, name: str, parent: Optional['TextStyle'], params: Dict[str, Any]):
		self.class_id = f"text-style-{name}"
		self.font_family: str = params.get("font", parent and parent.font_family or "")
		self.font_size: str = params.get("size", parent and parent.font_size or 20)
		self.text_color: str = params.get("color", parent and parent.text_color or '#000000')
		self.bold: bool = params.get("bold", parent and parent.bold or False)
		self.italic: bool = params.get("italic", parent and parent.italic or False)
		self.underline: bool = params.get("underline", parent and parent.underline or False)
		self.halign: HAlign = params.get("halign", parent and parent.halign or HAlign.Left)
		self.valign: VAlign = params.get("valign", parent and parent.valign or VAlign.Top)
		self.padding: int = params.get("padding", parent and parent.padding or 0)
		self.paragraph_spacing: int = params.get("paragraph-spacing", parent and parent.paragraph_spacing or 0)

	def render_css(self) -> str:
		extras = []
		if self.bold:
			extras.append("  font-weight: bold;")
		if self.italic:
			extras.append("  font-style: italic;")
		if self.underline:
			extras.append("  text-decoration: underline;")
		if self.valign == VAlign.Center:
			extras.append("  top: 50%;")
			extras.append("  transform: translateY(-50%);")
		elif self.valign == VAlign.Bottom:
			extras.append("  top: 100%;")
			extras.append("  transform: translateY(-100%);")
		p_extras = []
		if self.padding != 0:
			p_extras.append(f"  margin: {self.padding}px;")
		if self.paragraph_spacing != 0:
			p_extras.append(f"  padding-bottom: {self.paragraph_spacing}px;")
		return '\n'.join((
			f".{self.class_id} {{",
			f"  color: {convert_color(self.text_color)};",
			f"  font-family: {self.font_family};",
			f"  font-size: {self.font_size}px;",
			f"  text-align: {self.halign.value};",
			*extras,
			"}",
			f".{self.class_id} p{{",
			*p_extras,
			"}"
		))

class CardTemplate:
	def __init__(self, deck: 'Deck'):
		self.deck: Deck = deck
		self.count: int = 1
		self.front: Optional[CardFaceTemplate] = None
		self.back: Optional[CardFaceTemplate] = None
		self.name: Optional[str] = None
		self.description: Optional[str] = None
		self.index: int = len(deck.cards)

	def set_count(self, count: int) -> None:
		self.count = count

	def set_back(self, face: Optional['CardFaceTemplate']):
		self.back = face
		return face

	def set_front(self, face: Optional['CardFaceTemplate']):
		self.front = face
		return face

	def get_back(self) -> Optional['CardFaceTemplate']:
		return self.back or self.deck.default_back

	def get_front(self) -> Optional['CardFaceTemplate']:
		return self.front


class CardFaceTemplate:
	def __init__(self, deck: 'Deck'):
		self.deck: Deck = deck
		self.contents: List[str] = []
		self.contents_str: Optional[str] = None
		self.styles: Set[TextStyle] = set()

	def render(self) -> str:
		if not self.contents_str:
			self.contents_str = ''.join(self.contents)
		return self.contents_str

	def draw_rect(self, rect: Rect, color: Optional[str], line_color: Optional[str] = None, line_width: int = 1):
		self.contents.extend((
			f'<div class="rect" ',
			f'style="left:{rect[0]}px;top:{rect[1]}px;width:{rect[2]}px;height:{rect[3]}px;'
		))

		if color:
			self.contents.append(f'background-color:{convert_color(color)};')
		if line_color:
			self.contents.append(f'border-color:{convert_color(line_color)};border-style:solid;border-width:{line_width}px;')

		self.contents.append('"></div>')

	def draw_image(self, pos: Point, image: str, align: Point = (0, 0)):
		tx = -100 * align[0]
		ty = -100 * align[1]
		self.contents.append(
			f'<img class="image" ' +
			f'style="left:{pos[0]}px;top:{pos[1]}px;transform:translateX({tx}%) translateY({ty}%);" ' +
			f'src="{html.escape(image)}">'
		)

	def draw_text(self, rect: Rect, style: TextStyle, text: str):
		self.styles.add(style)
		self.contents.append(
			f'<div style="position:absolute;left:{rect[0]}px;top:{rect[1]}px;width:{rect[2]}px;height:{rect[3]}px;">'
			f'<div class="text-field {style.class_id}" ' +
			'><p>' +
			text +
			"</div></div>"
		)


class Deck:
	def __init__(self, db: Deckbuilder, name: str, size: Point):
		self.db: Deckbuilder = db
		self.name: str = name
		self.size = size
		self.cards: List[CardTemplate] = []
		self.hidden_face: Optional[CardFaceTemplate] = None
		self.default_back: Optional[CardFaceTemplate] = None
		self.scale: float = 1
		self.data = {
			"name": name,
			"width": size[0],
			"height": size[1]
		}

	def set_default_back(self, face: Optional['CardFaceTemplate']):
		self.default_back = face
		return face

	def set_hidden_face(self, face: Optional['CardFaceTemplate']):
		self.hidden_face = face
		return face

	def make_card(self) -> 'CardTemplate':
		card = CardTemplate(self)
		self.cards.append(card)
		return card

	def make_face(self) -> 'CardFaceTemplate':
		return CardFaceTemplate(self)

