import os
import sys

from deckbuilder.ast import StmtForEach, StmtSetName, StmtSetDescription, StmtWhile, StmtFor, StmtCase, StmtIf, \
	StmtSetVar, WhenBlock
from deckbuilder.context import DeckTemplate, DeckContext, CardBlock, CardData, FaceTemplate, InlineSymbol
from deckbuilder.datasource import download_google_sheet_as_dictionary
from deckbuilder.executor import StmtSequence, StmtFace, StmtDrawText, StmtDrawRect, StmtDrawImage
from deckbuilder.process import run_threaded, TaskProcess
from deckbuilder.promise import Promise, asyncify
from deckbuilder.utils import ValidateError, encode
from deckbuilder.validators import parse_expr, parse_int, parse_name, parse_font_name, \
	parse_color, parse_bool, parse_halign, parse_valign, parse_float, parse_string, parse_fstring

sys.modules['_elementtree'] = None
import xml.etree.ElementTree as ElementTree
from typing import Dict, Optional, List, Callable, Any, TypeVar, Tuple, NoReturn
from xml.etree.ElementTree import Element
from deckbuilder.core import TextStyle

T = TypeVar("T")


class LineNumberingParser(ElementTree.XMLParser):
	def _start(self, *args, **kwargs):
		element = getattr(super(self.__class__, self), '_start')(*args, **kwargs)
		element.start_line_number = self.parser.CurrentLineNumber
		element.start_column_number = self.parser.CurrentColumnNumber
		element.start_byte_index = self.parser.CurrentByteIndex
		return element

	def _end(self, *args, **kwargs):
		element = getattr(super(self.__class__, self), '_end')(*args, **kwargs)
		element.end_line_number = self.parser.CurrentLineNumber
		element.end_column_number = self.parser.CurrentColumnNumber
		element.end_byte_index = self.parser.CurrentByteIndex
		element.location = (
			(element.start_line_number, element.start_column_number),
			(element.end_line_number, element.end_column_number)
		)
		return element


class ElementScheme:
	def __init__(self, attrs: Dict[str, Callable[[str], Any]], required: List[str]):
		self.attrs: Dict[str, Callable[[str], Any]] = attrs
		self.required: List[str] = required

style_scheme = ElementScheme({
	"name": parse_name,
	"parent": parse_name,
	"font": parse_font_name,
	"size": parse_int,
	"color": parse_color,
	"bold": parse_bool,
	"italic": parse_bool,
	"underline": parse_bool,
	"halign": parse_halign,
	"valign": parse_valign,
	"padding": parse_int,
	"paragraph-spacing": parse_int
}, ["name"])

inline_scheme = ElementScheme({
	"name": parse_name,
	"src": parse_string,
	"offset-y": parse_float
}, ["name", "src"])

foreach_scheme = ElementScheme({
	"var": parse_name,
	"in": parse_expr
}, ["var", "in"])

setname_scheme = ElementScheme({
	"value": parse_fstring,
}, ["value"])

setdescription_scheme = ElementScheme({
	"value": parse_fstring,
}, ["value"])

deck_scheme = ElementScheme({
	"name": parse_name,
	"width": parse_int,
	"height": parse_int,
	"scale": parse_float
}, ["name", "width", "height"])

google_scheme = ElementScheme({
	"key": parse_string,
	"sheet": parse_string,
}, ["key", "sheet"])

draw_text_scheme = ElementScheme({
	"x": parse_expr,
	"y": parse_expr,
	"width": parse_expr,
	"height": parse_expr,
	"style": parse_fstring,
	"text": parse_fstring
}, ["x", "y", "width", "height", "style", "text"])

draw_image_scheme = ElementScheme({
	"x": parse_expr,
	"y": parse_expr,
	"src": parse_fstring,
	"align-x": parse_expr,
	"align-y": parse_expr,
}, ["x", "y", "src"])

draw_rect_scheme = ElementScheme({
	"x": parse_expr,
	"y": parse_expr,
	"width": parse_expr,
	"height": parse_expr,
	"color": parse_fstring,
	"line-color": parse_fstring,
	"line-width": parse_expr
}, ["x", "y", "width", "height"])

block_scheme = ElementScheme({}, [])
template_scheme = ElementScheme({}, [])
cards_scheme = ElementScheme({}, [])
face_scheme = ElementScheme({}, [])

if_scheme = ElementScheme({"condition": parse_expr}, ["condition"])
while_scheme = ElementScheme({"condition": parse_expr}, ["condition"])
when_scheme = ElementScheme({"condition": parse_expr}, ["condition"])
else_scheme = ElementScheme({}, [])
case_scheme = ElementScheme({}, [])
setvar_scheme = ElementScheme({"var": parse_name, "value": parse_expr}, ["var", "value"])
for_scheme = ElementScheme({
	"var": parse_name,
	"from": parse_expr,
	"to": parse_expr,
	"step": parse_expr
}, ["var", "from", "to"])


class XMLParser:
	def __init__(self):
		self.styles: Dict[str, Dict[str, any]] = dict()
		self.inlines: Dict[str, InlineSymbol] = dict()
		self.decks: Dict[str, DeckTemplate] = dict()
		self.pending_tasks: List[Promise[Any]] = []
		self.resolved_styles: Dict[str, Optional[TextStyle]] = dict()

	def parse_scheme(self, elt: Element, scheme: ElementScheme):
		params: Dict[str, Any] = dict()
		for key, value in elt.attrib.items():
			if key not in scheme.attrs:
				raise ValidateError(f"unexpected attribute '{encode(key)}'")
			try:
				params[key] = scheme.attrs[key](value)
			except ValidateError as ve:
				raise ValidateError(f"in attribute '{encode(key)}': {ve}") from ve
		for key in scheme.required:
			if key not in params:
				raise ValidateError(f"missing required attribute '{key}'")
		return params

	def process_element(self, elt: Element, func: Callable[..., T], *args: Any, **kwargs: Any) -> T:
		try:
			return func(elt, *args, **kwargs)
		except ValidateError as ve:
			loc = self.getloc(elt)
			raise ValidateError(f"in <{encode(elt.tag)}> at line {loc[0]}, col {loc[1]}:\n{ve}") from ve

	def unexpected_elt(self, elt: Element) -> NoReturn:
		loc = self.getloc(elt)
		raise ValidateError(f"unexpected child <{elt.tag}> at line {loc[0]}, col {loc[1]}")

	def parse(self, path: str) -> DeckContext:
		xml: Element = ElementTree.parse(path, parser=LineNumberingParser()).getroot()
		self.process_element(xml, self.parse_root)
		Promise.all(self.pending_tasks).run_until_completion()
		ctx = DeckContext(os.path.dirname(path))
		for name, inline in self.inlines.items():
			ctx.inlines[name] = inline
		for name, style in self.styles.items():
			ctx.styles[name] = self.resolve_style(name)
		for deck in sorted(self.decks.values(), key=lambda deck: deck.name):
			ctx.decks.append(deck)
		return ctx

	def resolve_style(self, name: str) -> TextStyle:
		if name in self.resolved_styles:
			return self.resolved_styles[name]
		if name not in self.styles:
			raise ValidateError(f"text style '{encode(name)}' is not defined")
		params = self.styles[name]
		self.resolved_styles[name] = None
		parent_name = params.get('parent')
		parent = None
		if parent_name is not None:
			parent = self.resolve_style(parent_name)
		style = TextStyle(name, parent, params)
		self.resolved_styles[name] = style
		return style

	def parse_root(self, root_elt: Element):
		for elt in root_elt:
			if elt.tag == "style":
				self.process_element(elt, self.parse_style)
			elif elt.tag == "inline":
				self.process_element(elt, self.parse_inline)
			elif elt.tag == "deck":
				self.process_element(elt, self.parse_deck)
			else:
				raise self.unexpected_elt(elt)

	def parse_inline(self, inline_elt: Element):
		params = self.parse_scheme(inline_elt, inline_scheme)
		name = params['name']
		if name in self.inlines:
			raise ValidateError(f"duplicate inline '{name}'")
		self.inlines[name] = InlineSymbol(params['name'], params['src'], params.get('offset-y', 0))

	def parse_style(self, style_elt: Element):
		params = self.parse_scheme(style_elt, style_scheme)
		name = params['name']
		if name in self.styles:
			raise ValidateError(f"duplicate style '{name}'")
		self.styles[name] = params
		for elt in style_elt:
			raise self.unexpected_elt(elt)

	def parse_deck(self, deck_elt: Element):
		params = self.parse_scheme(deck_elt, deck_scheme)
		name = params['name']
		if name in self.decks:
			raise ValidateError(f"duplicate deck '{name}'")
		deck = DeckTemplate(name, params['width'], params['height'])
		if 'scale' in params:
			deck.scale = params['scale']
		self.decks[name] = deck
		for elt in deck_elt:
			if elt.tag == "cards":
				self.process_element(elt, self.parse_cards, deck)
			elif elt.tag == "back-default":
				deck.back_default = self.process_element(elt, self.parse_template)
			elif elt.tag == "face-hidden":
				deck.face_hidden = self.process_element(elt, self.parse_template)
			else:
				raise self.unexpected_elt(elt)

	def parse_cards(self, cards_elt: Element, deck: DeckTemplate):
		self.parse_scheme(cards_elt, cards_scheme)
		block = CardBlock()
		deck.card_blocks.append(block)
		for elt in cards_elt:
			if elt.tag == "card":
				self.process_element(elt, self.parse_card_data, block)
			elif elt.tag == "google-sheet":
				self.process_element(elt, self.parse_google_sheet, block)
			elif elt.tag == "render":
				stmt = self.process_element(elt, self.parse_stmt_block)
				block.renderers.append(stmt)
			else:
				raise self.unexpected_elt(elt)

	def parse_google_sheet(self, google_elt: Element, block: CardBlock):
		params = self.parse_scheme(google_elt, google_scheme)
		try:
			def worker(process: TaskProcess):
				data = download_google_sheet_as_dictionary(params['key'], params['sheet'])
				return data
			@asyncify
			def run():
				data = yield run_threaded(f"Downloading {params['key']}/{params['sheet']}", worker)
				for row in data:
					self.add_card(block, row)
			self.pending_tasks.append(run())
		except BaseException as err:
			raise ValidateError(f"failed to download google spreadsheet: {err}")

	def add_card(self, block: CardBlock, data: Dict[str, str]):
		card_data = CardData()
		for key, value in data.items():
			if key == "count":
				try:
					card_data.count = int(value)
				except ValueError:
					raise ValidateError(f"invalid 'count' value of {encode(value)}")
			card_data.data[key] = value
		block.cards.append(card_data)

	def parse_card_data(self, card_elt: Element, block: CardBlock):
		self.add_card(block, card_elt.attrib)
		for elt in card_elt:
			raise self.unexpected_elt(elt)

	def parse_template(self, template_elt: Element) -> FaceTemplate:
		self.parse_scheme(template_elt, template_scheme)
		return FaceTemplate(self.parse_stmt_list(template_elt))

	def parse_stmt_list(self, list_elt: Element) -> StmtSequence:
		block = StmtSequence(self.getloc(list_elt))
		for elt in list_elt:
			if elt.tag == "block":
				block.stmts.append(self.process_element(elt, self.parse_stmt_block))
			elif elt.tag == "draw-text":
				block.stmts.append(self.process_element(elt, self.parse_draw_text))
			elif elt.tag == "draw-rect":
				block.stmts.append(self.process_element(elt, self.parse_draw_rect))
			elif elt.tag == "draw-image":
				block.stmts.append(self.process_element(elt, self.parse_draw_image))
			elif elt.tag == "face":
				block.stmts.append(self.process_element(elt, self.parse_face))
			elif elt.tag == "set-name":
				block.stmts.append(self.process_element(elt, self.parse_setname))
			elif elt.tag == "set-description":
				block.stmts.append(self.process_element(elt, self.parse_setdescription))
			elif elt.tag == "for-each":
				block.stmts.append(self.process_element(elt, self.parse_foreach))
			elif elt.tag == "for":
				block.stmts.append(self.process_element(elt, self.parse_for))
			elif elt.tag == "if":
				block.stmts.append(self.process_element(elt, self.parse_if))
			elif elt.tag == "while":
				block.stmts.append(self.process_element(elt, self.parse_while))
			elif elt.tag == "case":
				block.stmts.append(self.process_element(elt, self.parse_case))
			elif elt.tag == "set-var":
				block.stmts.append(self.process_element(elt, self.parse_set_var))
			else:
				raise self.unexpected_elt(elt)
		return block

	def parse_setname(self, elt: Element) -> StmtSetName:
		params = self.parse_scheme(elt, setname_scheme)
		return StmtSetName(self.getloc(elt), params['value'])

	def parse_setdescription(self, elt: Element) -> StmtSetDescription:
		params = self.parse_scheme(elt, setdescription_scheme)
		return StmtSetDescription(self.getloc(elt), params['value'])

	def parse_if(self, elt: Element) -> StmtIf:
		params = self.parse_scheme(elt, if_scheme)
		return StmtIf(self.getloc(elt), params['condition'], self.parse_stmt_list(elt))

	def parse_set_var(self, setvar_elt: Element) -> StmtSetVar:
		params = self.parse_scheme(setvar_elt, setvar_scheme)
		for elt in setvar_elt:
			raise self.unexpected_elt(elt)
		return StmtSetVar(self.getloc(setvar_elt), params['var'], params['value'])

	def parse_case(self, case_elt: Element) -> StmtCase:
		params = self.parse_scheme(case_elt, case_scheme)
		case = StmtCase(self.getloc(case_elt))
		for elt in case_elt:
			if elt.tag == "when":
				case.whens.append(self.process_element(elt, self.parse_when_block))
			elif elt.tag == "default":
				if case.kelse is not None:
					raise ValidateError("duplicate <else> element")
				case.kelse = (self.process_element(elt, self.parse_else_block))
			else:
				raise self.unexpected_elt(elt)
		return case

	def parse_when_block(self, elt: Element) -> WhenBlock:
		params = self.parse_scheme(elt, when_scheme)
		return WhenBlock(self.getloc(elt), params['condition'], self.parse_stmt_list(elt))

	def parse_else_block(self, else_elt: Element) -> StmtSequence:
		self.parse_scheme(else_elt, else_scheme)
		return self.parse_stmt_list(else_elt)

	def parse_while(self, elt: Element) -> StmtWhile:
		params = self.parse_scheme(elt, while_scheme)
		return StmtWhile(self.getloc(elt), params['condition'], self.parse_stmt_list(elt))

	def parse_for(self, elt: Element) -> StmtFor:
		params = self.parse_scheme(elt, for_scheme)
		return StmtFor(self.getloc(elt), params['var'], params['from'], params['to'], params.get('step'), self.parse_stmt_list(elt))

	def parse_foreach(self, elt: Element) -> StmtForEach:
		params = self.parse_scheme(elt, foreach_scheme)
		return StmtForEach(self.getloc(elt), params['var'], params['in'], self.parse_stmt_list(elt))

	def parse_face(self, elt: Element) -> StmtFace:
		params = self.parse_scheme(elt, face_scheme)
		face = StmtFace(self.getloc(elt), self.parse_stmt_list(elt))
		return face

	def parse_draw_text(self, elt: Element) -> StmtDrawText:
		params = self.parse_scheme(elt, draw_text_scheme)
		return StmtDrawText(
			self.getloc(elt),
			params['x'],
			params['y'],
			params['width'],
			params['height'],
			params['style'],
			params['text']
		)

	def parse_draw_rect(self, elt: Element) -> StmtDrawRect:
		params = self.parse_scheme(elt, draw_rect_scheme)
		return StmtDrawRect(
			self.getloc(elt),
			params['x'],
			params['y'],
			params['width'],
			params['height'],
			params.get('color', None),
			params.get('line-color', None),
			params.get('line-width', None)
		)

	def parse_draw_image(self, elt: Element) -> StmtDrawImage:
		params = self.parse_scheme(elt, draw_image_scheme)
		return StmtDrawImage(
			self.getloc(elt),
			params['x'],
			params['y'],
			params['src'],
			params.get('align-x', None),
			params.get('align-y', None)
		)

	def parse_stmt_block(self, block_elt: Element) -> StmtSequence:
		self.parse_scheme(block_elt, block_scheme)
		return self.parse_stmt_list(block_elt)

	def getloc(self, elt: Element) -> Tuple[int, int]:
		return getattr(elt, "location")[0]

