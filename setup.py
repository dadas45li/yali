#!/usr/bin/env python
#
# Copyright (C) 2005, TUBITAK/UEKAE
#
# This program is free software; you can redistribute it and/or modify it under
# the terms of the GNU General Public License as published by the Free
# Software Foundation; either version 2 of the License, or (at your option)
# any later version.
#
# Please read the COPYING file.

import os
import pyqtconfig
from distutils.core import setup
from distutils.command.build import build
from distutils.spawn import find_executable, spawn

YALI_VERSION = "0.1"

ui_files = ["yali/gui/installwidget.ui",
            "yali/gui/parteditwidget.ui",
            "yali/gui/partlistwidget.ui"]

pyqt_configuration = pyqtconfig.Configuration()


def getRevision():
    import os
    try:
        p = os.popen("svn info 2> /dev/null")
        for line in p.readlines():
            line = line.strip()
            if line.startswith("Revision:"):
                return line.split(":")[1].strip()
    except:
        return None

def getVersion():
    rev = getRevision()
    if rev:
        return "-r".join([YALI_VERSION, rev])
    else:
        return YALI_VERSION

class YaliBuild(build):

    def compile_ui(self, ui_file):
        pyuic_exe = find_executable('pyuic', pyqt_configuration.default_bin_dir)
        if not pyuic_exe:
            # Search on the $Path.
            pyuic_exe = find_executable('pyuic')
    
        py_file = os.path.splitext(ui_file)[0] + ".py"

        cmd = [pyuic_exe, ui_file, "-o", py_file]
        spawn(cmd)

    def run(self):
        for f in ui_files:
            self.compile_ui(f)

        build.run(self)



setup(name="yali",
    version= getVersion(),
    description="YALI (Yet Another Linux Installer)",
    long_description="Pardus System Installer.",
    license="GNU GPL2",
    author="Pardus Developers",
    author_email="yali@uludag.org.tr",
    url="http://www.uludag.org.tr/eng/yali/",
    package_dir = {'': ''},
    packages = ['yali', 'yali.gui'],
    scripts = ['yali-bin'],
    cmdclass = {
        'build' : YaliBuild
        }
    )
