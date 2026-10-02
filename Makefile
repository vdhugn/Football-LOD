PY=.venv/bin/python

.PHONY: test scope build vocab links load checks web all
test:   ; .venv/bin/pytest -q
scope:  ; $(PY) src/select_scope.py
build:  ; $(PY) src/build_rdf.py
vocab:  ; $(PY) src/validate.py vocab
links:  ; $(PY) src/link_wikidata.py
load:   ; scripts/load.sh
checks: ; scripts/run_checks.sh
web:    ; PYTHONPATH=src $(PY) -m flask --app footballweb run --port 8000
all: test scope build vocab links load checks
