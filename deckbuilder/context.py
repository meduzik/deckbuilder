import os
from typing import Dict, List, Optional, TYPE_CHECKING

from deckbuilder.utils import encode, ValidateError

if TYPE_CHECKING:
	from deckbuilder.core import TextStyle
	from deckbuilder.executor import StmtSequence, Stmt


class DeckContext:
	def __init__(self, base_path: str):
		self.base_path: str = base_path
		self.styles: Dict[str, TextStyle] = dict()
		self.decks: List[DeckTemplate] = []
		self.inlines: Dict[str, InlineSymbol] = dict()

	def resolve_inline(self, name: str) -> 'InlineSymbol':
		if name in self.inlines:
			return self.inlines[name]
		raise ValidateError(f"inline symbol '{encode(name)}' is not defined")

	def resolve_style(self, name: str) -> 'TextStyle':
		if name in self.styles:
			return self.styles[name]
		raise ValidateError(f"text style '{encode(name)}' is not defined")

	def resolve_path(self, path: str) -> str:
		return os.path.abspath(os.path.join(self.base_path, path))


class FaceTemplate:
	def __init__(self, block: 'StmtSequence'):
		self.block: StmtSequence = block


class CardData:
	def __init__(self):
		self.count = 1
		self.data: Dict[str, str] = dict()


class CardBlock:
	def __init__(self):
		self.cards: List[CardData] = []
		self.renderers: List[Stmt] = []


class DeckTemplate:
	def __init__(self, name: str, width: int, height: int):
		self.name = name
		self.width: int = width
		self.height: int = height
		self.scale: float = 1
		self.face_hidden: Optional[FaceTemplate] = None
		self.back_default: Optional[FaceTemplate] = None
		self.card_blocks: List[CardBlock] = []


class InlineSymbol:
	def __init__(self, name: str, src: str, offset_y: float):
		self.name: str = name
		self.src: str = src
		self.offset_y: float = offset_y