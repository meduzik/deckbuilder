import os
import shutil
import time
from collections import defaultdict
from typing import List, Any, Dict, Optional, Tuple, Set
from selenium import webdriver
from selenium.webdriver.chrome.options import Options

from deckbuilder.core import Deckbuilder, Deck, CardFaceTemplate, CardTemplate, TextStyle
from deckbuilder.process import run_async_command
from deckbuilder.promise import Promise, asyncify
from deckbuilder.renderinfo import DecksInfo, DeckInfo, DeckSheetInfo, CardInfo
from deckbuilder.utils import sha1file
from threading import Lock

MaxSize = 8192
MaxCards = 70

chrome_mutex = Lock()
driver = None

class RenderConfig:
	def __init__(self, chrome_bin: str):
		self.chrome_bin: str = chrome_bin


class DeckLayout:
	def __init__(self, deck: Deck):
		self.max_per_row: int = MaxSize // int(deck.size[0])
		self.max_per_col: int = MaxSize // int(deck.size[1])
		self.need_face_card: bool = deck.hidden_face is not None
		self.max_per_page: int = min(self.max_per_row * self.max_per_col - self.need_face_card, MaxCards)
		self.width: int = int(deck.size[0])
		self.height: int = int(deck.size[1])
		self.pages: int = 0


class CardSheetLayout:
	def __init__(self, deck_layout: DeckLayout, num_cards: int, single: bool):
		if single:
			self.rows = 1
			self.cols = 1
		else:
			candidates: List[Tuple[int, int]] = []
			for rows in range(2, deck_layout.max_per_col + 1):
				cols = max(2, (num_cards + rows - 1) // rows)
				if cols > deck_layout.max_per_row:
					continue
				candidates.append((rows, cols))
			rows, cols = min(candidates, key=lambda t: (t[0] * t[1], t[0]))
			self.rows = rows
			self.cols = cols
		self.width = deck_layout.width * self.cols
		self.height = deck_layout.height * self.rows


class CardSheet:
	def __init__(self, deck: 'Deck', cards: List[Optional[CardFaceTemplate]], layout: CardSheetLayout):
		self.deck: Deck = deck
		self.layout: layout = layout
		self.cards: List[CardFaceTemplate] = cards
		self.all_styles: Set[TextStyle] = set()
		self.contents: List[str] = []
		self.compute_contents()

	def compute_contents(self) -> None:
		contents: List[str] = self.contents
		width: int = int(self.deck.size[0])
		height: int = int(self.deck.size[1])
		for idx, card in enumerate(self.cards):
			if card is None:
				continue
			self.all_styles.update(card.styles)
			row = idx // self.layout.cols
			col = idx % self.layout.cols
			x = col * width
			y = row * height
			contents.append((
					f'<div class="card" ' +
					f'style="left:{x}px;top:{y}px;width:{width}px;height:{height}px;">'
			))
			contents.append(card.render())
			contents.append(f'</div>')


def cleardir(path: str):
	os.makedirs(path, exist_ok=True)
	for filename in os.listdir(path):
		file_path = os.path.join(path, filename)
		try:
			if os.path.isfile(file_path) or os.path.islink(file_path):
				os.unlink(file_path)
			elif os.path.isdir(file_path):
				shutil.rmtree(file_path)
		except Exception as e:
			print('Failed to delete %s. Reason: %s' % (file_path, e))


class DeckRenderer:
	def __init__(self, cfg: RenderConfig, out_dir: str):
		self.cfg: RenderConfig = cfg
		self.out_dir: str = out_dir
		self.info: DecksInfo = DecksInfo()
		self.tasks: List[Promise[Any]] = []

	def render(self, db: Deckbuilder) -> DecksInfo:
		cleardir(self.out_dir)
		for deck in db.decks:
			self.render_deck(deck)
		Promise.all(self.tasks).run_until_completion()
		return self.info

	def render_deck(self, deck: Deck) -> None:
		info: DeckInfo = DeckInfo(deck.name, int(deck.size[0]), int(deck.size[1]))
		info.scale = deck.scale
		self.info.decks.append(info)
		layout: DeckLayout = DeckLayout(deck)

		cards_by_back: Dict[CardFaceTemplate, List[CardTemplate]] = defaultdict(lambda: [])
		cards_to_layout: List[List[CardTemplate]] = []
		for card in deck.cards:
			cards_by_back[card.get_back()].append(card)
			for _ in range(card.count):
				info.stack.append(card.index)
		for back, cards in cards_by_back.items():
			card_instances = []
			for card in cards:
				card_instances.append(card)
			pos = 0
			while len(card_instances) - pos > layout.max_per_page:
				self.render_page(card_instances[pos:pos + layout.max_per_page], deck, layout, info)
				pos += layout.max_per_page
			if pos != 0:
				card_instances = card_instances[pos:]
			cards_to_layout.append(card_instances)
		current_sheet: List[CardTemplate] = []
		current_sheet_tained: bool = False

		def flush_current_sheet():
			nonlocal current_sheet_tained
			if len(current_sheet) == 0:
				return
			self.render_page(current_sheet, deck, layout, info)
			current_sheet.clear()
			current_sheet_tained = False

		for cards in sorted(cards_to_layout, key=len):
			more_cards = layout.max_per_page - len(current_sheet)
			if len(cards) <= more_cards:
				current_sheet_tained = len(current_sheet) > 0
				current_sheet.extend(cards)
			elif not current_sheet_tained and more_cards < len(cards):
				flush_current_sheet()
				current_sheet.extend(cards)
				current_sheet_tained = False
			else:
				current_sheet.extend(cards[:more_cards])
				current_sheet_tained = True
				flush_current_sheet()
				current_sheet.extend(cards[more_cards:])
		flush_current_sheet()

	def render_page(self, cards: List[CardTemplate], deck: Deck, deck_layout: DeckLayout, deck_info: DeckInfo) -> None:
		unique_backs: bool = False
		for card in cards:
			if card.get_back() != cards[0].get_back():
				unique_backs = True
				break

		faces: List[Optional[CardFaceTemplate]] = []
		backs: List[CardFaceTemplate] = []

		for card in cards:
			faces.append(card.get_front())

		face_layout = CardSheetLayout(deck_layout, len(faces) + deck_layout.need_face_card, False)
		if deck_layout.need_face_card:
			while len(faces) < face_layout.rows * face_layout.cols - 1:
				faces.append(None)
			faces.append(deck.hidden_face)

		if unique_backs:
			back_layout = CardSheetLayout(deck_layout, len(faces) + deck_layout.need_face_card, False)
			for card in cards:
				backs.append(card.get_back())
		else:
			back_layout = CardSheetLayout(deck_layout, len(faces) + deck_layout.need_face_card, True)
			backs.append(deck.default_back)

		deck_layout.pages += 1
		page_id = deck_layout.pages

		face_sheet = CardSheet(deck, faces, face_layout)
		face_file = self.render_sheet(face_sheet, f"{deck.name}.{page_id}.face")

		back_sheet = CardSheet(deck, backs, back_layout)
		back_file = self.render_sheet(back_sheet, f"{deck.name}.{page_id}.back")

		cards_info = []
		for card in cards:
			card_info = CardInfo(card.index, card.name, card.description)
			cards_info.append(card_info)

		@asyncify
		def get_info():
			face_path = yield face_file
			back_path = yield back_file
			info = DeckSheetInfo(
				face_path,
				back_path,
				unique_backs,
				face_layout.cols,
				face_layout.rows,
				len(cards_info),
				deck_layout.need_face_card
			)
			for card_info in cards_info:
				info.cards_info.append(card_info)
			deck_info.sheets.append(info)
		self.tasks.append(get_info())

	def render_sheet(self, sheet: CardSheet, path: str) -> Promise[str]:
		html_file = os.path.abspath(os.path.join(self.out_dir, path + ".html"))
		width = sheet.layout.width
		height = sheet.layout.height

		with open(html_file, 'w', encoding="utf-8") as out:
			out.write("<!DOCTYPE html>")
			out.write("<html>")
			out.write("<head>")
			out.write('<meta charset="utf-8">')
			out.write('<style>')
			with open(os.path.join(os.path.dirname(os.path.realpath(__file__)), "style.css"), 'r') as style_fp:
				out.write(style_fp.read())
			out.write("\n")
			for style in sorted(sheet.all_styles, key=lambda style: style.class_id):
				out.write(style.render_css())
			out.write('</style>')
			out.write("</head>")
			out.write("<body>")
			out.write('<div class="deck">')
			for piece in sheet.contents:
				out.write(piece)
			out.write('</div>')
			out.write("</body>")
			out.write("</html>")

		@asyncify
		def run():
			global driver

			preview_path = os.path.abspath(os.path.join(self.out_dir, path)) + ".png"

			with chrome_mutex:
				print(f"Rendering {html_file}...")
				time_begin = time.time()

				if not driver:
					print(f"Starting new Chrome process")

					options = Options()
					options.headless = True

					driver = webdriver.Chrome(options)

				driver.set_window_size(width, height)
				driver.get("file://" + html_file)
				driver.save_screenshot(preview_path)

				print(f"Rendering complete in {time.time() - time_begin}s")

			hash = sha1file(preview_path)
			target_path = os.path.abspath(os.path.join(self.out_dir, sheet.deck.name + "." + hash[:12] + ".png"))
			try:
				os.remove(target_path)
			except:
				pass
			shutil.copy(preview_path, target_path)
			return target_path

		promise = run()
		self.tasks.append(promise)
		return promise
