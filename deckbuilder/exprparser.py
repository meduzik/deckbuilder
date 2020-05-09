from typing import Optional, List, NoReturn

from deckbuilder.ast import ExprConcat, ExprLit, Expr, ExprField, ExprID, ExprCall
from deckbuilder.utils import ValidateError

SpecialChars = frozenset("$")
Whitespaces = frozenset(" \n\r\t")
IdStartChar = frozenset("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ_")
IdChar = frozenset("0123456789") | IdStartChar


class ExprParser:
	def __init__(self, s: str):
		self.s: str = s
		self.pos: int = 0

	def peek(self) -> Optional[str]:
		if self.pos >= len(self.s):
			return None
		return self.s[self.pos]

	def advance(self):
		self.pos += 1

	def parse(self) -> Expr:
		pieces: List[Expr] = []
		while True:
			ch = self.peek()
			if ch is None:
				break
			if ch in SpecialChars:
				pieces.append(self.parse_special())
			else:
				pieces.append(ExprLit(self.parse_plain()))
		return ExprConcat(pieces)

	def parse_special(self) -> Expr:
		ch = self.peek()
		if ch == '$':
			self.advance()
			ch = self.peek()
			if ch == '$':
				self.advance()
				return ExprLit('$')
			elif ch == '{':
				self.advance()
				expr = self.parse_expr()
				self.consume('}')
				return expr
			else:
				self.error("$ is not followed by $ or {, if you want to insert the dollar sign, repeat it like '$$'")
		else:
			self.error("unexpected character")

	def consume(self, ch: str):
		ch = self.peek()
		if ch != ch:
			self.error(f"expected '{ch}'")
		self.advance()

	def parse_expr(self) -> Expr:
		expr = self.try_parse_expr()
		if expr is None:
			self.error("expected expression")
		return expr

	def try_parse_expr(self) -> Optional[Expr]:
		prim = self.try_parse_prim()
		if not prim:
			return None
		expr = prim
		while True:
			self.skip_ws()
			ch = self.peek()
			if ch == '.':
				self.advance()
				self.skip_ws()
				identifier = self.parse_id()
				if len(identifier) == 0:
					self.error("expected identifier")
				expr = ExprField(expr, identifier)
			else:
				break
		return expr

	def try_parse_prim(self) -> Optional[Expr]:
		self.skip_ws()
		ch = self.peek()
		if ch in IdStartChar:
			name = self.parse_id()
			self.skip_ws()
			if self.peek() == '(':
				self.advance()
				args: List[Expr] = []
				arg = self.try_parse_expr()
				if arg:
					args.append(arg)
					while True:
						self.skip_ws()
						if self.peek() == ',':
							self.advance()
							self.skip_ws()
							args.append(self.parse_expr())
						else:
							break
				self.consume(')')
				return ExprCall(name, args)
			else:
				return ExprID(name)
		elif ch == "'":
			self.advance()
			begin = self.pos
			while True:
				ch = self.peek()
				if ch == "'":
					self.advance()
					break
				elif ch is None:
					self.error("unterminated string literal")
				self.advance()
			contents = self.s[begin: self.pos - 1]
			return ExprLit(contents)
		return None

	def parse_id(self) -> str:
		begin: int = self.pos
		while True:
			ch = self.peek()
			if ch not in IdChar:
				break
			self.advance()
		identifier = self.s[begin:self.pos]
		return identifier

	def skip_ws(self) -> None:
		while True:
			ch = self.peek()
			if ch not in Whitespaces:
				break
			self.advance()

	def error(self, msg: str) -> NoReturn:
		raise ValidateError(f"at position {self.pos}: {msg}")

	def parse_plain(self) -> str:
		begin: int = self.pos
		while True:
			ch = self.peek()
			if ch is None or ch in SpecialChars:
				break
			self.advance()
		return self.s[begin:self.pos]

	def parse_direct(self) -> Expr:
		expr = self.parse_expr()
		self.skip_ws()
		if self.peek() is not None:
			self.error("unexpceted character")
		return expr