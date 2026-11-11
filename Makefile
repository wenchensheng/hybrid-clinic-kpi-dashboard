PY ?= python

.PHONY: all install data test serve screenshots clean
all:            ## run the full pipeline (data -> SQL -> dashboard JSON -> notebook)
	$(PY) run_all.py

install:
	$(PY) -m pip install -r requirements.txt

data:           ## pipeline without executing the notebook
	$(PY) run_all.py --skip-notebook

test:           ## run tests (requires data from `make data`/`make all`)
	$(PY) -m unittest discover -s tests -v

serve:          ## preview the dashboard at http://localhost:8000
	$(PY) -m http.server 8000 --directory docs

screenshots:    ## headless-browser check + screenshots (needs requirements-dev.txt)
	$(PY) scripts/screenshot.py $(if $(CHROME),--chrome $(CHROME),)

clean:
	rm -f data/raw/*.csv data/processed/*.csv data/processed/*.db
