import hashlib
import html


class ValidateError(RuntimeError):
	pass


def encode(s):
	return html.escape(s)


def sha1file(path):
	with open(path, 'rb') as fp:
		return hashlib.sha1(fp.read()).hexdigest()