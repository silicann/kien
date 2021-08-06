include make.d/makefilet-download-ondemand.mk

DEBIAN_UPLOAD_TARGET = silicann

BLACK_TARGETS = kien tests setup.py
BLACK_ARGS = --target-version py35
BLACK_BIN = $(PYTHON_BIN) -m black
COVERAGE_BIN ?= $(PYTHON_BIN) -m coverage

default-target: build

.PHONY: lint-python-black
lint-python-black:
	$(BLACK_BIN) $(BLACK_ARGS) --check $(BLACK_TARGETS)

lint-python: lint-python-black

.PHONY: test-report
test-report:
	$(COVERAGE_BIN) report

.PHONY: test-report-short
test-report-short:
	$(MAKE) test-report | grep TOTAL | grep -oP '(\d+)%$$' | sed 's/^/Code Coverage: /'

.PHONY: style
style:
	$(BLACK_BIN) $(BLACK_ARGS) $(BLACK_TARGETS)

distribute-pypi:
	@if ! which twine >/dev/null 2>&1 || [ "$$(printf "1.11.0\n$$(twine --version | head -1 | cut -d" " -f3)" | sort -V | head -1)" != "1.11.0" ]; then \
		echo "you need twine >v1.11.0" >&2; \
		exit 1; \
	fi
	rm -rf dist/
	python3 setup.py sdist
	twine upload dist/*
