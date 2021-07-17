include make.d/makefilet-download-ondemand.mk

DEBIAN_UPLOAD_TARGET = silicann

BLACK_TARGETS = kien tests setup.py
BLACK_ARGS = --target-version py35
BLACK_BIN = $(PYTHON_BIN) -m black
COVERAGE_BIN ?= $(PYTHON_BIN) -m coverage

PYPI_BUILD_DIR ?= dist

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

.PHONY: clean-pypi
clean-pypi:
	$(RM) -r "$(PYPI_BUILD_DIR)"

.PHONY: distribute-pypi
distribute-pypi: clean-pypi
	python3 setup.py sdist
	twine upload "$(PYPI_BUILD_DIR)"/*
