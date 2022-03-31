include make.d/makefilet-download-ondemand.mk

DEBIAN_UPLOAD_TARGET = silicann

BLACK_FILES = kien/ tests/ setup.py
COVERAGE_BIN ?= $(PYTHON_BIN) -m coverage

PYPI_BUILD_DIR ?= dist

default-target: build

.PHONY: clean-pypi
clean-pypi:
	$(RM) -r "$(PYPI_BUILD_DIR)"

clean: clean-pypi

.PHONY: distribute-pypi
distribute-pypi: clean-pypi
	python3 setup.py sdist
	twine upload "$(PYPI_BUILD_DIR)"/*
