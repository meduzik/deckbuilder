import json
import re
from typing import Optional, Dict, Any, Callable, TypeVar

from deckbuilder import textparser
from deckbuilder.ast import Stmt, StmtSequence, StmtDrawRect, StmtDrawText, StmtDrawImage, StmtFace, Expr, ExprLit, \
	ExprConcat, ExprField, ExprID, StmtForEach, ExprCall, StmtSetName, StmtSetDescription
from deckbuilder.context import DeckContext, DeckTemplate, FaceTemplate, CardData, CardBlock
from deckbuilder.core import CardTemplate, CardFaceTemplate, Deckbuilder, Deck
import deckbuilder.validators as validators
from deckbuilder.utils import ValidateError, encode


T = TypeVar("T")


def to_string(val):
	return str(val)

def to_int(val):
	try:
		return int(val)
	except ValueError:
		raise ValidateError("expected integer")


re_split = re.compile("(?:\".*?\"|\S)+")

funcs = {
	"words": {
		"args": [to_string],
		"call": lambda s: re_split.findall(s)
	},
	"repeat": {
		"args": [to_string, to_int],
		"call": lambda s, i: s * i
	}
}


class Executor:
	def __init__(self, ctx: DeckContext, card: Optional[CardTemplate], face: Optional[CardFaceTemplate]):
		self.ctx: DeckContext = ctx
		self.card: Optional[CardTemplate] = card
		self.face: Optional[CardFaceTemplate] = face
		self.env: Dict[str, Any] = dict()

	def execute(self, stmt: Stmt):
		try:
			if isinstance(stmt, StmtSequence):
				for child in stmt.stmts:
					self.execute(child)
			elif isinstance(stmt, StmtDrawRect):
				self.get_face().draw_rect(
					(
						validators.parse_int(self.eval(stmt.x)),
						validators.parse_int(self.eval(stmt.y)),
						validators.parse_int(self.eval(stmt.width)),
						validators.parse_int(self.eval(stmt.height)),
					),
					self.eval_nullable(validators.parse_color, stmt.color, None),
					self.eval_nullable(validators.parse_color, stmt.line_color, None),
					self.eval_nullable(validators.parse_int, stmt.line_width, 1)
				)
			elif isinstance(stmt, StmtDrawText):
				self.get_face().draw_text(
					(
						validators.parse_int(self.eval(stmt.x)),
						validators.parse_int(self.eval(stmt.y)),
						validators.parse_int(self.eval(stmt.width)),
						validators.parse_int(self.eval(stmt.height)),
					),
					self.ctx.resolve_style(self.eval(stmt.style)),
					textparser.TextParser(self.ctx, self.eval(stmt.text)).parse()
				)
			elif isinstance(stmt, StmtDrawImage):
				self.get_face().draw_image(
					(
						validators.parse_int(self.eval(stmt.x)),
						validators.parse_int(self.eval(stmt.y))
					),
					self.ctx.resolve_path(self.eval(stmt.src)),
					(
						self.eval_nullable(validators.parse_float, stmt.align_x, 0),
						self.eval_nullable(validators.parse_float, stmt.align_y, 0)
					)
				)
			elif isinstance(stmt, StmtFace):
				if self.face is not None:
					raise ValidateError("face already selected")
				if not self.card:
					raise ValidateError("no active card")
				self.face = self.card.front
				if not self.face:
					self.face = self.card.deck.make_face()
					self.card.set_front(self.face)
				self.execute(stmt.stmt)
				self.face = None
			elif isinstance(stmt, StmtForEach):
				var = stmt.var
				old_val = self.env.get(var, None)
				container = self.compute(stmt.in_expr)
				if isinstance(container, list):
					for elt in container:
						self.env[var] = elt
						self.execute(stmt.body)
				else:
					raise ValidateError(f"attempt to iterate over {type(container).__class__.__name__}")
				self.env[var] = old_val
			elif isinstance(stmt, StmtSetName):
				card = self.get_card()
				card.name = self.eval(stmt.value)
			elif isinstance(stmt, StmtSetDescription):
				card = self.get_card()
				card.description = self.eval(stmt.value)
			else:
				raise ValidateError("invalid statement")
		except ValidateError as ve:
			raise ValidateError(f"in line {stmt.location[0]}, col {stmt.location[1]}:\n{ve}") from ve

	def get_face(self) -> CardFaceTemplate:
		if self.face is None:
			raise ValidateError("no card face selected")
		return self.face

	def get_card(self) -> CardTemplate:
		if self.card is None:
			raise ValidateError("no card selected")
		return self.card

	def eval_nullable(self, fn: Callable[..., T], expr: Optional[Expr], default: T) -> T:
		if expr is None:
			return default
		r = self.compute(expr)
		if r is None:
			return default
		return fn(str(r))

	def eval(self, expr: Expr) -> str:
		r = self.compute(expr)
		if isinstance(r, str):
			return r
		return str(r)

	def compute(self, expr: Expr) -> Any:
		if expr is None:
			return None
		if isinstance(expr, ExprLit):
			return expr.s
		elif isinstance(expr, ExprConcat):
			return ''.join(map(self.eval, expr.pieces))
		elif isinstance(expr, ExprField):
			lhs = self.compute(expr.obj)
			if isinstance(lhs, dict):
				return lhs.get(expr.field, None)
			else:
				raise ValidateError(f"cannot read property '{encode(expr.field)}' of non-object")
		elif isinstance(expr, ExprID):
			if expr.s in self.env:
				return self.env[expr.s]
			else:
				raise ValidateError(f"variable '{encode(expr.s)}' doesn't exist")
		elif isinstance(expr, ExprCall):
			func = expr.func
			if func not in funcs:
				raise ValidateError(f"unknown function '{func}'")
			func_data = funcs[func]
			args = []
			for arg in expr.args:
				args.append(self.compute(arg))
			params = func_data['args']
			if len(args) != len(params):
				raise ValidateError(f"invalid number of arguments for function '{func}'")
			converted_args = []
			for param, arg in zip(params, args):
				converted_args.append(param(arg))
			return func_data['call'](*converted_args)
		else:
			raise ValidateError("invalid expression")


class DeckInstantiator:
	def __init__(self, ctx: DeckContext):
		self.ctx: DeckContext = ctx
		self.unique_faces: Dict[str, CardFaceTemplate] = dict()

	def run(self) -> Deckbuilder:
		db = Deckbuilder()
		for deck in self.ctx.decks:
			self.instantiate_deck(db, deck)
		return db

	def instantiate_deck(self, db: Deckbuilder, template: DeckTemplate):
		try:
			deck = db.make_deck(template.name, (template.width, template.height))
			deck.scale = template.scale
			if template.back_default:
				deck.set_default_back(self.build_face(deck, template.back_default))
			if template.face_hidden:
				deck.set_hidden_face(self.build_face(deck, template.face_hidden))
			for card_block in template.card_blocks:
				for card in card_block.cards:
					self.build_card(deck, card, card_block)
		except ValidateError as ve:
			raise ValidateError(f"while building deck '{encode(template.name)}': {ve}") from ve

	def build_face(self, deck: Deck, template: FaceTemplate) -> CardFaceTemplate:
		face = deck.make_face()
		exec = Executor(self.ctx, None, face)
		exec.execute(template.block)
		face_unique = face.render()
		if face_unique in self.unique_faces:
			return self.unique_faces[face_unique]
		self.unique_faces[face_unique] = face
		return face

	def build_card(self, deck: Deck, card_data: CardData, block: CardBlock) -> None:
		card = deck.make_card()
		card.set_count(card_data.count)
		if 'name' in card_data.data:
			card.name = card_data.data['name']
		if 'description' in card_data.data:
			card.name = card_data.data['description']
		exec = Executor(self.ctx, card, None)
		exec.env['card'] = card_data.data
		try:
			for renderer in block.renderers:
				exec.execute(renderer)
		except ValidateError as ve:
			raise ValidateError(f"while rendering card {json.dumps(card_data.data, ensure_ascii=False)}:\n{ve}") from ve
		if not card.get_front():
			raise ValidateError(f"no front face for card {json.dumps(card_data.data, ensure_ascii=False)}")
		if not card.get_back():
			raise ValidateError(f"no back face for card {json.dumps(card_data.data, ensure_ascii=False)}")
