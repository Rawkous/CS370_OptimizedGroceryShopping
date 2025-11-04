venv:
	python -m venv .venv

install: venv
	.\.venv\Scripts\pip install -r requirements.txt

run:
	.\.venv\Scripts\python app.py

freeze:
	.\.venv\Scripts\pip freeze > requirements.txt
