#!/usr/bin/env python3

import re
import struct
import sys

from setuptools import setup

import versioneer

# These requirements are also declared via requirements/gridsync.in. Please
# ensure that changes made to this list are propagated there (and vice versa).
requirements = [
    "atomicwrites",
    "attrs",
    "autobahn",
    'certifi ; sys_platform == "win32"',
    'distro ; sys_platform != "darwin" and sys_platform != "win32"',
    "humanize",
    "hyperlink",
    "magic-wormhole",
    "psutil",
    "PyNaCl >= 1.2.0",  # 1.2.0 adds Argon2id KDF
    "PyQt5",
    "PyQtChart",
    "pyyaml",
    "qt5reactor",
    "treq",
    "twisted[tls] >= 21.7.0",  # 21.7.0 adds Deferred type hinting/annotations
    "txtorcon",
    "watchdog",
    "zxcvbn",
]

if sys.platform.startswith("linux") and (struct.calcsize("P") * 8) == 32:
    try:
        import PyQt5  # noqa; F401 (imported but unused)
    except ImportError:
        sys.exit(
            "PyQt5 wheels are not available for 32-bit GNU/Linux. Please "
            "manually install PyQt5 into this environment and try again."
        )
    requirements.remove("PyQt5")


module_file = open("gridsync/__init__.py").read()
metadata = dict(re.findall(r"__([a-z]+)__\s*=\s*\"([^\"]+)\"", module_file))


setup(
    name="gridsync",
    version=versioneer.get_version(),
    cmdclass=versioneer.get_cmdclass(),
    description="Synchronize local directories with Tahoe-LAFS storage grids.",
    long_description=open("README.rst").read(),
    author=metadata["author"],
    url=metadata["url"],
    license=metadata["license"],
    keywords="gridsync tahoe-lafs tahoe lafs allmydata-tahoe magic-wormhole",
    python_requires=">=3.9, <3.10",
    classifiers=[
        "Development Status :: 4 - Beta",
        "Environment :: MacOS X",
        "Environment :: Win32 (MS Windows)",
        "Environment :: X11 Applications",
        "Environment :: X11 Applications :: Gnome",
        "Environment :: X11 Applications :: GTK",
        "Environment :: X11 Applications :: KDE",
        "Environment :: X11 Applications :: Qt",
        "Intended Audience :: End Users/Desktop",
        "License :: DFSG approved",
        "License :: OSI Approved",
        "License :: OSI Approved :: GNU General Public License v3 (GPLv3)",
        "Natural Language :: English",
        "Operating System :: MacOS :: MacOS X",
        "Operating System :: Microsoft :: Windows",
        "Operating System :: Microsoft :: Windows :: Windows 7",
        "Operating System :: Microsoft :: Windows :: Windows 8",
        "Operating System :: Microsoft :: Windows :: Windows 8.1",
        "Operating System :: Microsoft :: Windows :: Windows 10",
        "Operating System :: POSIX",
        "Operating System :: POSIX :: Linux",
        "Programming Language :: Python",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3 :: Only",
        "Topic :: Communications :: File Sharing",
        "Topic :: Desktop Environment",
        "Topic :: Internet",
        "Topic :: Security",
        "Topic :: Security :: Cryptography",
        "Topic :: System :: Archiving",
        "Topic :: System :: Archiving :: Backup",
        "Topic :: System :: Archiving :: Mirroring",
        "Topic :: System :: Distributed Computing",
        "Topic :: System :: Filesystems",
        "Topic :: System :: Recovery Tools",
        "Topic :: Utilities",
    ],
    packages=["gridsync", "gridsync.gui"],
    package_data={"gridsync": ["resources/*", "resources/providers/*"]},
    entry_points={"console_scripts": ["gridsync=gridsync.cli:main"]},
    install_requires=requirements,
)
