.PHONY: clean, build, upload, install

clean:
	-rm -rf dist/
build: clean lib
	python -m build
upload:
	twine upload dist/*
install:
	pip install dist/*.whl --force-reinstall