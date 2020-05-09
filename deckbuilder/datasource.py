import csv
from io import StringIO
import urllib.request


def download_google_sheet_as_dictionary(key, sheet):
	response = urllib.request.urlopen(f"https://docs.google.com/spreadsheets/d/{key}/gviz/tq?tqx=out:csv&sheet={sheet}")
	text = response.read()
	reader = csv.DictReader(StringIO(text.decode("utf-8")))
	rows = []
	for row in reader:
		rows.append(row)
	return rows