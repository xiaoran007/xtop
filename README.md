# xtop


[![Downloads](https://static.pepy.tech/badge/pypci-ng)](https://pepy.tech/project/pypci-ng)
![PyPI - Version](https://img.shields.io/pypi/v/xtop?label=version)

![Static Badge](https://img.shields.io/badge/Linux-blue)


xtop, a command line xpu hardware monitoring tool that supports CPU, GPU, and NPU.


## Install
Just install it directly by pip.
```shell
pip install xtop
```
To upgrade xtop:
```shell
pip install xtop --upgrade
# or
pip install xtop -U
```

## Usage
### Use as a command line tool
You can use this tool directly from the command line with the following command, just like other programs.
```shell
xtop [Options]
```
For example, use -n flag to open NPU, with -l flag to enable LOG.
```shell
xtop -n -l
```
For more command line flags, see:
```shell
xtop -h
```

Please note that the command line entry for __xtop__ is created by pip, and depending on the user, this entry may not in the __system PATH__. If you encounter this problem, pip will give you a prompt, follow the prompts to add entry to the __system PATH__.

More functionalities are under development.

## Supported (Tested) OS
* Linux
* Windows (Only GPU)


## Build from source
### Build tools
Make sure the following Python build tools are already installed.
* setuptools
* build
* twine

### Build package
clone the project, and run:
```shell
python -m build
```
After the build process, the source package and the binary whl package can be found in the dist folder.

# Windows
install:
```shell
pip install nvidia-ml-py windows-curses
```


