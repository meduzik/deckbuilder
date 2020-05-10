import json
import math
import re
from typing import Optional, Dict, Any, Callable, TypeVar

from deckbuilder import textparser
from deckbuilder.ast import Stmt, StmtSequence, StmtDrawRect, StmtDrawText, StmtDrawImage, StmtFace, Expr, ExprLit, \
	ExprConcat, ExprField, ExprID, StmtForEach, ExprCall, StmtSetName, StmtSetDescription, StmtSetVar, StmtIf, \
	StmtWhile, StmtFor, StmtCase
from deckbuilder.context import DeckContext, DeckTemplate, FaceTemplate, CardData, CardBlock
from deckbuilder.core import CardTemplate, CardFaceTemplate, Deckbuilder, Deck
import deckbuilder.validators as validators
from deckbuilder.utils import ValidateError, encode


T = TypeVar("T")

def to_any(val):
	return val

def to_string(val):
	return str(val)

def to_list(val):
	if not isinstance(val, list):
		raise ValidateError("expected list")
	return val

def to_number(val):
	if isinstance(val, int):
		return val
	if isinstance(val, float):
		return val
	try:
		return int(val)
	except ValueError:
		try:
			return float(val)
		except ValueError:
			raise ValidateError("expected integer")

def to_int(val):
	try:
		return int(val)
	except ValueError:
		raise ValidateError("expected integer")


re_split = re.compile("(?:\".*?\"|\S)+")

funcs = {
	"words": {"args": [to_string], "call": lambda s: re_split.findall(s)},
	"split": {"args": [to_string, to_string], "call": lambda s, n: s.split(n)},
	"join": {"args": [to_list, to_string], "call": lambda lst, s: s.join(lst)},
	"repeat": {"args": [to_string, to_int], "call": lambda s, i: s * i},
	"substring": {"args": [to_string, to_int, to_int], "call": lambda s, b, e: s[b: e]},
	"contains": {"args": [to_string, to_string], "call": lambda s, n: len(re.findall(n, s)) > 0},
	"negate": {"args": [to_number], "call": lambda s: -s},
	"concat": {"args": [to_string, to_string], "call": lambda s1, s2: s1 + s2},
	"tostr": {"args": [to_string], "call": lambda s: s},
	"toint": {"args": [to_int], "call": lambda s: s},
	"tonumber": {"args": [to_number], "call": lambda s: s},

	"abs": {"args": [to_number], "call": lambda x: abs(x)},
	"floor": {"args": [to_number], "call": lambda x: math.floor(x)},
	"ceil": {"args": [to_number], "call": lambda x: math.ceil(x)},
	"round": {"args": [to_number], "call": lambda x: math.floor(x + 0.5)},
	"min": {"args": [to_number, to_number], "call": lambda x, y: min(x, y)},
	"max": {"args": [to_number, to_number], "call": lambda x, y: max(x, y)},

	"len": {"args": [to_list], "call": lambda s: len(s)},
	"+": {"args": [to_number, to_number], "call": lambda x, y: x + y},
	"-": {"args": [to_number, to_number], "call": lambda x, y: x - y},
	"*": {"args": [to_number, to_number], "call": lambda x, y: x * y},
	"/": {"args": [to_number, to_number], "call": lambda x, y: x / y},
	"%": {"args": [to_number, to_number], "call": lambda x, y: x % y},
	"=": {"args": [to_any, to_any], "call": lambda x, y: 1 if x == y else 0},
	"!=": {"args": [to_any, to_any], "call": lambda x, y: 1 if x != y else 0},
	"LT": {"args": [to_any, to_any], "call": lambda x, y: 1 if x < y else 0},
	"GT": {"args": [to_any, to_any], "call": lambda x, y: 1 if x > y else 0},
	"LE": {"args": [to_any, to_any], "call": lambda x, y: 1 if x <= y else 0},
	"GE": {"args": [to_any, to_any], "call": lambda x, y: 1 if x >= y else 0},
	"and": {"args": [to_number, to_number], "call": lambda x, y: 1 if x and y else 0},
	"or": {"args": [to_number, to_number], "call": lambda x, y: 1 if x or y else 0},
}


MaxFuel = 50000


class Executor:
	def __init__(self, ctx: DeckContext, card: Optional[CardTemplate], face: Optional[CardFaceTemplate]):
		self.ctx: DeckContext = ctx
		self.card: Optional[CardTemplate] = card
		self.face: Optional[CardFaceTemplate] = face
		self.env: Dict[str, Any] = dict()
		self.fuel: int = MaxFuel

	def execute(self, stmt: Stmt):
		self.fuel -= 1
		if self.fuel <= 0:
			raise ValidateError("evaluation took too many steps")
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
				container = to_list(self.compute(stmt.in_expr))
				for elt in container:
					self.env[var] = elt
					self.execute(stmt.body)
				self.env[var] = old_val
			elif isinstance(stmt, StmtSetName):
				card = self.get_card()
				card.name = self.eval(stmt.value)
			elif isinstance(stmt, StmtSetDescription):
				card = self.get_card()
				card.description = self.eval(stmt.value)
			elif isinstance(stmt, StmtSetVar):
				var = stmt.var
				value = self.compute(stmt.value)
				self.env[var] = value
			elif isinstance(stmt, StmtIf):
				if to_number(self.compute(stmt.condition)):
					self.execute(stmt.body)
			elif isinstance(stmt, StmtWhile):
				while to_number(self.compute(stmt.condition)):
					self.execute(stmt.body)
			elif isinstance(stmt, StmtCase):
				for when in stmt.whens:
					if to_number(self.compute(when.condition)):
						self.execute(when.body)
						break
				else:
					if stmt.kelse is not None:
						self.execute(stmt.kelse)
			elif isinstance(stmt, StmtFor):
				var = stmt.var
				old_val = self.env.get(var, None)
				kfrom = to_number(self.compute(stmt.kfrom))
				to = to_number(self.compute(stmt.kto))
				step = 1
				if stmt.step:
					step = to_number(self.compute(stmt.step))
				value = kfrom
				if step == 0:
					raise ValidateError("step is 0")
				while True:
					if step > 0:
						if value > to:
							break
					elif step < 0:
						if value < to:
							break
					self.env[var] = value
					self.execute(stmt.body)
					value += step
				self.env[var] = old_val
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
