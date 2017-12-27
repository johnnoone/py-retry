tests:
	pytest tests/* -vvv --cov --cov-report term-missing --annotate-output=./annotations.json
.PHONY: tests
