import os

from setuptools import find_packages, setup

__dir = os.path.abspath(os.path.dirname(__file__))
# don’t import the __version__ attr from the kien module
# so that our convenience imports won’t trigger an ImportError
# during pip install if our dependencies are not available on the system yet.
__version__ = "0.16.2"

try:
    with open(os.path.join(__dir, "README.md"), encoding="utf-8") as f:
        long_description = "\n" + f.read()
except FileNotFoundError:
    long_description = ""


setup(
    name="kien",
    version=__version__,
    description="kien is a line-based command parser for creating shell-like interfaces",
    long_description=long_description,
    long_description_content_type="text/markdown",
    author="Konrad Mohrfeldt",
    author_email="mohrfeldt@silicann.com",
    url="https://github.com/silicann/kien",
    packages=find_packages(exclude=("examples",)),
    install_requires=[
        "blessings",
        "blinker",
    ],
    extras_require={},
    include_package_data=True,
    package_data={
        "": ["README.md", "LICENSE", "CHANGELOG.md"],
    },
    license="GPLv3+",
    classifiers=[
        "Development Status :: 4 - Beta",
        "License :: OSI Approved :: GNU General Public License v3 or later (GPLv3+)",
        "Programming Language :: Python",
        "Programming Language :: Python :: 3",
    ],
)
