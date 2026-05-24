.PHONY: install test run scenarios clean

install:
	pip install -e ".[dev]"

test:
	pytest

run:
	streamlit run app/streamlit_app.py

scenarios:
	python -m gacct.scenarios.runner --all --out examples/traces

clean:
	rm -rf __pycache__ .pytest_cache *.egg-info traces/runtime
