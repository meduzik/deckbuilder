import hashlib
import html
import json
import os
import sys
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs

from deckbuilder.executor import DeckInstantiator
from deckbuilder.renderer import RenderConfig, DeckRenderer
from deckbuilder.renderinfo import DeckSheetInfo, CardInfo, DeckInfo
from deckbuilder.xmlbuilder import XMLParser
import configparser


def sha1(s):
	return hashlib.sha1(s.encode('utf-8')).hexdigest()


def convert_card(card: CardInfo):
	return {
		"index": card.index,
		"name": card.name,
		"description": card.description
	}

def add_slash(s: str) -> str:
	if s[0] == '/':
		return s
	return '/' + s

def convert_sheet(sheet: DeckSheetInfo):
	return {
		"face": "file://" + add_slash(sheet.face),
		"back": "file://" + add_slash(sheet.back),
		"count": sheet.count,
		"width": sheet.width,
		"height": sheet.height,
		"unique_backs": sheet.unique_backs,
		"has_face_hidden": sheet.has_face_hidden,
		"cards": [convert_card(card) for card in sheet.cards_info]
	}

def convert_deck(deck: DeckInfo):
	return {
		"name": deck.name,
		"width": deck.width,
		"height": deck.height,
		"sheets": [convert_sheet(sheet) for sheet in deck.sheets],
		"stack": deck.stack,
		"scale": deck.scale
	}


config = configparser.ConfigParser()
config['general'] = {
	"chrome_bin": r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
	"cache_path": r".",
	"port": "17352"
}
config.read("config.ini")

CHROME_BIN = config['general']['chrome_bin']
CACHE_PATH = config['general']['cache_path']
PORT = config.getint('general', 'port')

render_cfg = RenderConfig(CHROME_BIN)


class RequestHandler(BaseHTTPRequestHandler):
	def serve_image(self, request):
		query = parse_qs(request.query, keep_blank_values=True)
		if 'src' not in query or len(query['src']) == 0:
			raise RuntimeError("no 'src' param")
		src = query['src'][0]
		self.send_response(200)
		self.send_header("Content-type", "image/png")
		self.end_headers()
		with open(src, 'rb') as fp:
			self.wfile.write(fp.read())

	def do_GET(self):
		try:
			request = urlparse(self.path)
			if request.path == "/img":
				return self.serve_image(request)
			query = parse_qs(request.query, keep_blank_values=True)
			if 'deck' not in query or len(query['deck']) == 0:
				raise RuntimeError("no 'deck' param")
			deck = query['deck'][0]
			print(f"REQUESTED BUILDING {json.dumps(deck)}")
			db = DeckInstantiator(XMLParser(deck).parse()).run()
			deck_info = DeckRenderer(render_cfg, os.path.join(os.path.dirname(deck), CACHE_PATH, ".cache/" + sha1(deck))).render(db)
			print(f"BUILDING {json.dumps(deck)} SUCCESSFULLY COMPLETED!")
			if 'preview' in query:
				self.send_response(200)
				self.send_header("Content-type", "text/html;encoding=UTF-8")
				self.end_headers()
				imgs = []
				for deck in deck_info.decks:
					imgs.append(f"<p>{html.escape(deck.name)}<br>")
					imgs.append(f"Faces:<br>")
					for face in set((sheet.face for sheet in deck.sheets)):
						imgs.append(f"<img src=\"img?src={html.escape(face)}\">")
					imgs.append(f"<br>Backs:<br>")
					for back in set((sheet.back for sheet in deck.sheets)):
						imgs.append(f"<img src=\"img?src={html.escape(back)}\">")
				self.wfile.write('\n'.join((
					"<html>",
					"<head>",
					'<meta charset="utf-8">',
					'<style>* {font-size: 60px;}</style>',
					"</head>"
					"<body>",
					*imgs,
					"</body>",
					"</html>"
				)).encode('utf-8'))
			else:
				decks = []
				for deck in deck_info.decks:
					decks.append(convert_deck(deck))
				self.send_response(200)
				self.send_header("Content-type", "application/json;encoding=UTF-8")
				self.end_headers()
				self.wfile.write(json.dumps({
					"response": {
						"decks": decks
					}
				}, ensure_ascii=False).encode('utf-8'))
		except:
			print(f"{sys.exc_info()[1]}")
			self.send_response(500)
			self.send_header("Content-type", "application/json;encoding=UTF-8")
			self.end_headers()
			self.wfile.write(json.dumps({
				"error": str(sys.exc_info()[1])
			}, ensure_ascii=False).encode('utf-8'))


print(f"Starting server on port {PORT}")
print(f"Open http://localhost:{PORT}/?preview&deck=example/deck.xml for an example deck")
ThreadingHTTPServer(("localhost", PORT), RequestHandler).serve_forever()