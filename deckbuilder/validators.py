from deckbuilder.core import VAlign, HAlign
import deckbuilder.exprparser as exprparser
import re

from deckbuilder.utils import ValidateError

re_style_name = re.compile("[a-zA-Z][a-zA-Z0-9_\\-]*")
re_color = re.compile("#[0-9a-fA-F]{6}([0-9a-fA-F]{2})?")


def parse_nullable(fn, value):
	if value is None:
		return None
	if len(value.strip()) == 0:
		return None
	return fn(value)

def parse_fstring(value):
	return exprparser.ExprParser(value).parse_all_fstring()

def parse_expr(value):
	return exprparser.ExprParser(value).parse_all_expr()

def parse_string(value):
	return value

def parse_name(value):
	if not re_style_name.match(value):
		raise ValidateError("expected name (allowed characters are a-z, A-Z, 0-9, and '_', starts with a letter)")
	return value

def parse_int(value):
	try:
		return int(value)
	except ValueError:
		raise ValidateError("expected integer")

def parse_float(value):
	try:
		return float(value)
	except ValueError:
		raise ValidateError("expected number")

def parse_font_name(value):
	return value

def parse_bool(value):
	if value == "true":
		return True
	elif value == "false":
		return False
	else:
		raise ValidateError("expected 'true' or 'false'")

def parse_halign(value):
	if value == "left":
		return HAlign.Left
	elif value == "center":
		return HAlign.Center
	elif value == "right":
		return HAlign.Right
	elif value == "justify":
		return HAlign.Justify
	else:
		raise ValidateError("invalid value (expected 'left', 'center', 'right' or 'justify')")


def parse_valign(value):
	if value == "top":
		return VAlign.Top
	elif value == "center":
		return VAlign.Center
	elif value == "bottom":
		return VAlign.Bottom
	else:
		raise ValidateError("invalid value (expected 'top', 'center' or 'bottom')")

def parse_color(value):
	if not re_color.match(value):
		raise ValidateError("invalid color (expected #RRGGBB or #AARRGGBB)")
	return value
