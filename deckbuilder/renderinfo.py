from typing import List, Optional


class CardInfo:
	def __init__(self, index: int, name: Optional[str], description: Optional[str]):
		self.index: int = index
		self.name: Optional[str] = name
		self.description: Optional[str] = description


class DeckSheetInfo:
	def __init__(
			self,
			face: str,
			back: str,
			unique_backs: bool,
			width: int,
			height: int,
			count: int,
			has_face_hidden: bool
	):
		self.face: str = face
		self.back: str = back
		self.unique_backs: bool = unique_backs
		self.width: int = width
		self.height: int = height
		self.count: int = count
		self.has_face_hidden: bool = has_face_hidden
		self.cards_info: List[CardInfo] = []

class DeckInfo:
	def __init__(self, name: str, width: int, height: int):
		self.name: str = name
		self.width: int = width
		self.height: int = height
		self.sheets: List[DeckSheetInfo] = []
		self.stack: List[int] = []
		self.scale: float = 1

class DecksInfo:
	def __init__(self):
		self.decks: List[DeckInfo] = []
