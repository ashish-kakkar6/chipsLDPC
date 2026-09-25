PYTHON ?= python3
SPHINXBUILD ?= $(PYTHON) -m sphinx
SOURCEDIR := source
BUILDDIR := _build

.PHONY: help html linkcheck clean

help:
	@printf "Targets:\n"
	@printf "  make html  - build the HTML documentation\n"
	@printf "  make linkcheck - check documentation links\n"
	@printf "  make clean - remove generated documentation\n"

html:
	$(SPHINXBUILD) -n -b html -W --keep-going $(SOURCEDIR) $(BUILDDIR)/html

linkcheck:
	$(SPHINXBUILD) -n -b linkcheck -W --keep-going $(SOURCEDIR) $(BUILDDIR)/linkcheck

clean:
	rm -rf $(BUILDDIR)
