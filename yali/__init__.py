# -*- coding: utf-8 -*-
#
# Copyright (C) 2005, TUBITAK/UEKAE
#
# This program is free software; you can redistribute it and/or modify it under
# the terms of the GNU General Public License as published by the Free
# Software Foundation; either version 2 of the License, or (at your option)
# any later version.
#
# Please read the COPYING file.
#

__version__ = "1.0_beta2"

import sys
import exceptions
import traceback
import cStringIO

import gettext
__trans = gettext.translation('yali', fallback=True)
_ = __trans.ugettext


from yali.exception import *


def default_runner():
    import yali.gui.runner

    sys.excepthook = exception_handler

    return yali.gui.runner.Runner()



exception_normal, exception_fatal, exception_unknown = range(3)

def exception_handler(exception, value, tb):

#    sys.excepthook = sys.__excepthook__

    sio = cStringIO.StringIO()

    v = ''
    for e in value.args:
        v += str(e) + '\n'
    sio.write(v)

    sio.write('\n\n')
    sio.write(_("Backtrace:"))
    sio.write('\n')
    traceback.print_tb(tb, None, sio)


    exception_type = exception_unknown

    if isinstance(value, YaliError):
        # show Error dialog
        exception_type = exception_fatal

    elif isinstance(value, YaliException):
        # show Exception dialog
        exception_type = exception_normal


    sio.seek(0)

    import yali.gui.runner
    yali.gui.runner.showException(exception_type, unicode(sio.read()))
