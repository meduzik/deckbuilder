import html
import re
from typing import Optional, List

from deckbuilder.context import DeckContext

special_chars = frozenset("@*\n\r")
subst_chars = frozenset("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_")
re_int = re.compile('[0-9]+')


class TextParser:
	def __init__(self, ctx: DeckContext, s: str):
		self.ctx: DeckContext = ctx
		self.s: str = s
		self.pos: int = 0
		self.fragments: List[str] = []

	def peek(self) -> Optional[str]:
		if self.pos >= len(self.s):
			return None
		return self.s[self.pos]

	def advance(self) -> None:
		self.pos += 1

	def parse(self) -> str:
		while self.peek() is not None:
			self.parse_next()
		return ''.join(self.fragments)

	def parse_next(self) -> None:
		ch = self.peek()
		if ch not in special_chars:
			self.parse_plain()
		else:
			if ch == '\r' or ch == '\n':
				self.parse_newline()
			elif ch == '*':
				self.parse_star()
			elif ch == '@':
				self.parse_subst()
			else:
				raise RuntimeError("invalid encoding")

	def parse_subst(self):
		self.advance()
		ch = self.peek()
		if ch == '@':
			self.advance()
			self.fragments.append('@')
			return
		start = self.pos
		while True:
			ch = self.peek()
			if ch not in subst_chars:
				break
			self.advance()
		name = self.s[start: self.pos]
		inline = self.ctx.resolve_inline(name)
		style = ""
		if inline.offset_y != 0:
			style = f'style="transform: translateY({inline.offset_y}px);"'
		self.fragments.append(f'<img src="{html.escape(self.ctx.resolve_path(inline.src))}" class="icon-inline" {style}>')

	def parse_star(self):
		count = 1
		self.advance()
		if self.peek() == '*':
			self.advance()
			count += 1
		if count == 1:
			self.fragments.append('<span class="markdown-italic">')
		else:
			self.fragments.append('<span class="markdown-bold">')
		while True:
			ch = self.peek()
			if ch is None:
				raise RuntimeError("unterminated *")
			if ch == '*':
				num = self.lookahead_stars()
				if num == count:
					self.pos += num
					break
			self.parse_next()
		self.fragments.append('</span>')

	def lookahead_stars(self) -> int:
		reset = self.pos
		while self.peek() == '*':
			self.advance()
		count = self.pos - reset
		self.pos = reset
		return count

	def parse_newline(self):
		self.try_consume_newline()
		nl2 = self.try_consume_newline()
		if nl2:
			self.fragments.append('<p>')
		else:
			self.fragments.append('<br>')

	def try_consume_newline(self) -> bool:
		ch = self.peek()
		flag = False
		if ch == '\r':
			self.advance()
			ch = self.peek()
			flag = True
		if ch == '\n':
			self.advance()
			flag = True
		return flag

	def parse_plain(self) -> None:
		begin = self.pos
		while True:
			ch = self.peek()
			if ch is None or ch in special_chars:
				break
			self.advance()
		self.fragments.append(html.escape(self.s[begin:self.pos]))