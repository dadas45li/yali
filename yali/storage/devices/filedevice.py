#!/usr/bin/python
# -*- coding: utf-8 -*-
import os
import gettext
__trans = gettext.translation('yali', fallback=True)
_ = __trans.ugettext

import yali.context as ctx
from device import Device, DeviceError

class FileDeviceError(DeviceError):
    pass

class FileDevice(Device):
    """ A file on a filesystem.

        This exists because of swap files.
    """
    _type = "file"
    _devDir = ""

    def __init__(self, path, format=None, size=None,
                 exists=None, parents=None):
        """ Create a FileDevice instance.

            Arguments:

                path -- full path to the file

            Keyword Arguments:

                format -- a DeviceFormat instance
                size -- the file size (units TBD)
                parents -- a list of required devices (Device instances)
                exists -- indicates whether this is an existing device
        """
        if not path.startswith("/"):
            raise ValueError("FileDevice requires an absolute path")

        Device.__init__(self, path, format=format, size=size,
                        exists=exists, parents=parents)

    @property
    def fstabSpec(self):
        return self.name

    @property
    def path(self):
        root = ""
        try:
            status = self.parents[0].format.status
        except (AttributeError, IndexError):
            # either this device has no parents or something is wrong with
            # the first one
            status = (os.access(self.name, os.R_OK) and
                      self.parents in ([], None))
        else:
            # this is the actual active mountpoint
            root = self.parents[0].format._mountpoint
            # trim the mountpoint down to the chroot since we already have
            # the otherwise fully-qualified path
            mountpoint = self.parents[0].format.mountpoint
            while mountpoint.endswith("/"):
                mountpoint = mountpoint[:-1]
            if mountpoint:
                root = root[:-len(mountpoint)]

        return os.path.normpath("%s%s" % (root, self.name))

    def _preSetup(self, orig=False):
        if self.format and self.format.exists and not self.format.status:
            self.format.device = self.path

        return Device._preSetup(self, orig=orig)

    def _preTeardown(self, recursive=None):
        if self.format and self.format.exists and not self.format.status:
            self.format.device = self.path

        return Device._preTeardown(self, recursive=recursive)

    def _create(self, w):
        """ Create the device. """
        fd = os.open(self.path, os.O_WRONLY|os.O_CREAT|os.O_TRUNC)
        buf = "\0" * 1024 * 1024
        for n in range(self.size):
            os.write(fd, buf)
        os.close(fd)

    def _destroy(self):
        """ Destroy the device. """
        os.unlink(self.path)
