# xtop


[![Downloads](https://static.pepy.tech/badge/xtop)](https://pepy.tech/project/xtop)
![PyPI - Version](https://img.shields.io/pypi/v/xtop?label=version)

![Static Badge](https://img.shields.io/badge/Linux-blue)
![Static Badge](https://img.shields.io/badge/Windows-green)


xtop, a command line xpu hardware monitoring tool that supports CPU, GPU, and NPU.

![demo](https://files.catbox.moe/fb9ryz.jpg)

## 1 Install
### 1.1 Install by pipx
**pipx** is an amazing tool to help you install and run applications written in Python. It is more like **brew** or **apt**. You can find more information about it here [pipx](https://github.com/pypa/pipx). **pipx** is available on almost all major platforms and is usually provided by the corresponding package manager. If you haven't used pipx before, you can refer to this [document](https://pipx.pypa.io/stable/installation/) to install it.

You can install **xtop** by the following command:
```shell
pipx install xtop
```

### 1.2 Install by pip
In any case, pip is always available, so if you can't install this program using **pipx**, you can install **xtop** by the following command:
```shell
pip install xtop
```
To upgrade **xtop**:
```shell
pip install xtop -U
# or
pip install xtop --upgrade
```

Please note that the command line entry for **xtop** is created by pip, and depending on the user, this entry may not in the __system PATH__. If you encounter this problem, pip will give you a prompt, follow the prompts to add entry to the __system PATH__.


### 1.3 Important note about Windows
Python standard package **curses** does not support Windows, so we need **windows-curses** to run **xtop** on Windows. This package should be installed automatically when you install **xtop**. If you encounter any problems, you can install it manually by the following command:

```shell
pip install windows-curses
```


### 1.4 Important note about debian 12:
If you use system pip to install **xtop**, you will encounter this problem on debian12 and some related distributions (like Ubuntu 24.04):
```text
error: externally-managed-environment

× This environment is externally managed
╰─> To install Python packages system-wide, try apt install
    python3-xyz, where xyz is the package you are trying to
    install.
    
    If you wish to install a non-Debian-packaged Python package,
    create a virtual environment using python3 -m venv path/to/venv.
    Then use path/to/venv/bin/python and path/to/venv/bin/pip. Make
    sure you have python3-full installed.
    
    For more information visit http://rptl.io/venv

note: If you believe this is a mistake, please contact your Python installation or OS distribution provider. You can override this, at the risk of breaking your Python installation or OS, by passing --break-system-packages.
hint: See PEP 668 for the detailed specification.
```
This is due to the fact that system Python is not supposed to be managed by pip. You can simply use **pipx** to install **xtop**. Or you can use a virtual environment (venv), conda environment or force remove this restriction (not recommended).


## Usage
### Use as a command line tool
You can use this tool directly from the command line with the following command, just like other programs.
```shell
xtop [Options]
```
For example, use -n flag to open NPU, with -l flag to enable LOG:
```shell
xtop -n -l
```
Or use -g flag to open GPU:
```shell
xtop -g
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



