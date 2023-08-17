from typing import Optional, List, NoReturn

from deckbuilder.ast import ExprConcat, ExprLit, Expr, ExprField, ExprID, ExprCall
from deckbuilder.utils import ValidateError

SpecialChars = frozenset("$")
Whitespaces = frozenset(" \n\r\t")
IdStartChar = frozenset("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ_")
IdChar = frozenset("0123456789") | IdStartChar
Digits = frozenset("0123456789")


CompareOps = frozenset(["=", "!=", "LT", "GT", "LE", "GE"])


PrecedenceUnary = 40
PrecedenceMul = 50
PrecedenceAdd = 60
PrecedenceAnd = 70
PrecedenceOr = 80
PrecedenceCompare = 90
PrecedenceMax = 100


EscapeDecode = {
	"n": "\n",
	"r": "\r",
	"t": "\t",
	"0": "\0",
}

SelfEscapeDecode = frozenset(",.~!@#$%^&*()_|-=\\/<>\"[]{}?;:'`")

HexDigits = {
	'0': 0,
	'1': 1,
	'2': 2,
	'3': 3,
	'4': 4,
	'5': 5,
	'6': 6,
	'7': 7,
	'8': 8,
	'9': 9,
	'a': 10,
	'b': 11,
	'c': 12,
	'd': 13,
	'e': 14,
	'f': 15,
	'A': 10,
	'B': 11,
	'C': 12,
	'D': 13,
	'E': 14,
	'F': 15,
}


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

	def parse_all_fstring(self) -> Expr:
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

	def parse_all_expr(self) -> Expr:
		expr = self.parse_expr()
		self.skip_ws()
		if self.peek() is not None:
			self.error("unexpceted character")
		return expr

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
		return self.parse_expr_at(PrecedenceMax)

	def parse_expr_at(self, prec: int) -> Expr:
		expr = self.try_parse_expr_at(prec)
		if expr is None:
			self.error("expected expression")
		return expr

	def try_parse_expr(self) -> Optional[Expr]:
		return self.try_parse_expr_at(PrecedenceMax)

	def peek_compare_op(self) -> Optional[str]:
		restart = self.pos
		ch = self.peek()
		if ch in IdStartChar:
			id = self.parse_id()
			if id in CompareOps:
				return id
			else:
				self.pos = restart
				return None
		else:
			candidate = ""
			found_pos = None
			found = None
			while True:
				ch = self.peek()
				if ch is None:
					break
				candidate = candidate + ch
				for op in CompareOps:
					if op == candidate:
						found_pos = self.pos
						found = candidate
					if op.startswith(candidate):
						break
				else:
					break
				self.advance()

			if found_pos is not None:
				self.pos = found_pos
				self.advance()
				return found
			else:
				self.pos = restart
				return None

	def try_parse_expr_at(self, prec: int) -> Optional[Expr]:
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
			elif prec >= PrecedenceAdd and (ch == '+' or ch == '-'):
				self.advance()
				rhs = self.parse_expr_at(PrecedenceAdd - 1)
				expr = ExprCall(ch, [expr, rhs])
			elif prec >= PrecedenceMul and (ch == '*' or ch == '/' or ch == '%'):
				self.advance()
				rhs = self.parse_expr_at(PrecedenceMul - 1)
				expr = ExprCall(ch, [expr, rhs])
			elif prec >= PrecedenceCompare and (op := self.peek_compare_op()):
				self.advance()
				rhs = self.parse_expr_at(PrecedenceCompare - 1)
				expr = ExprCall(op, [expr, rhs])
			elif ch in IdStartChar:
				tok = self.peek_token()
				if prec >= PrecedenceOr and tok == "or":
					self.parse_id()
					rhs = self.parse_expr_at(PrecedenceOr - 1)
					expr = ExprCall(tok, [expr, rhs])
				elif prec >= PrecedenceAnd and tok == "and":
					self.parse_id()
					rhs = self.parse_expr_at(PrecedenceOr - 1)
					expr = ExprCall(tok, [expr, rhs])
				elif prec >= PrecedenceCompare and tok in CompareOps:
					self.parse_id()
					rhs = self.parse_expr_at(PrecedenceCompare - 1)
					expr = ExprCall(tok, [expr, rhs])
				else:
					break
			else:
				break
		return expr

	def peek_token(self) -> str:
		pos = self.pos
		name = self.parse_id()
		self.pos = pos
		return name

	def try_parse_prim(self) -> Optional[Expr]:
		self.skip_ws()
		ch = self.peek()
		if ch is None:
			return None
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
		elif ch in Digits:
			return self.parse_number()
		elif ch == '-':
			self.advance()
			r = self.parse_expr_at(PrecedenceUnary)
			return ExprCall("negate", [r])
		elif ch == '#':
			self.advance()
			r = self.parse_expr_at(PrecedenceUnary)
			return ExprCall("len", [r])
		elif ch == "'":
			self.advance()
			begin = self.pos
			contents = []
			while True:
				ch = self.peek()
				if ch == "'":
					self.advance()
					break
				elif ch == '\\':
					self.advance()
					contents.append(self.parse_esc())
				elif ch is None:
					self.error("unterminated string literal")
				contents.append(ch)
				self.advance()
			return ExprLit(''.join(contents))
		return None

	def parse_esc(self) -> str:
		ch = self.peek()
		if ch is None:
			self.error("expected character after \\")
		if ch in SelfEscapeDecode:
			self.advance()
			return ch
		elif ch in EscapeDecode:
			self.advance()
			return EscapeDecode[ch]
		elif ch == 'x':
			self.advance()
			return self.parse_esc_hex(2)
		elif ch == 'u':
			self.advance()
			return self.parse_esc_hex(4)
		elif ch == 'U':
			self.advance()
			return self.parse_esc_hex(8)
		else:
			self.error("invalid escape sequence")

	def parse_esc_hex(self, n: int) -> str:
		acc: int = 0
		for _ in range(n):
			ch = self.peek()
			if ch not in HexDigits:
				self.error("expected more hexidecimal digits")
			acc = acc * 16 + HexDigits[ch]
		return chr(acc)

	def parse_number(self) -> Expr:
		begin = self.pos
		ch = self.peek()
		if ch == '0':
			self.advance()
		else:
			while True:
				ch = self.peek()
				if ch not in Digits:
					break
				self.advance()
		if self.peek() == '.':
			self.advance()
			while True:
				ch = self.peek()
				if ch not in Digits:
					break
				self.advance()
			return ExprLit(float(self.s[begin: self.pos]))
		return ExprLit(int(self.s[begin: self.pos]))

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
