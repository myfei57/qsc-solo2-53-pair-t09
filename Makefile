test:
	PYTHONPATH=. python -m pytest -q

run:
	PYTHONPATH=. python -m coke --config config/coke.json serve --host 127.0.0.1 --port 8080

demo:
	PYTHONPATH=. python -m coke --config config/coke.json demo --fast --ovens 3

deadcode:
	PYTHONPATH=. python tools/deadcode.py coke
