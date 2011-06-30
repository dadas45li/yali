#!/usr/bin/python
import os
import parted

import gettext
__trans = gettext.translation('yali', fallback=True)
_ = __trans.ugettext

from device import Device, DeviceError

class DiskError(DeviceError):
    pass

class Disk(Device):
    """ A disk """
    _type = "disk"
    _isDisk = True
    _partitionable = True

    def __init__(self, device, format=None, parents=None,
                 exists=True, size=None, major=None, minor=None,
                 sysfsPath='', serial=None, model="", vendor="", bus=""):
        """ Create a Disk instance.

            Arguments:

                device -- the device name (generally a device node's basename)

            Keyword Arguments:

                size -- the device's size (units/format TBD)
                major -- the device major
                minor -- the device minor
                sysfsPath -- sysfs device path
                format -- a DeviceFormat instance
                parents -- a list of required Device instances
                removable -- whether or not this is a removable device

            Disk always exist.
        """
        Device.__init__(self, device, format=format, size=size,
                        major=major, minor=minor, exists=exists,
                        model=model, serial=serial, vendor=vendor,bus=bus,
                        sysfsPath=sysfsPath, parents=parents)

    def __repr__(self):
        s = Device.__repr__(self)
        s += ("  removable = %(removable)s  partedDevice = %(partedDevice)r" %
              {"removable": self.removable, "partedDevice": self.partedDevice})
        return s

    @property
    def mediaPresent(self):
        if not self.partedDevice:
            return False

        # Some drivers (cpqarray <blegh>) make block device nodes for
        # controllers with no disks attached and then report a 0 size,
        # treat this as no media present
        return self.partedDevice.getSize() != 0

    @property
    def description(self):
        return self.model

    @property
    def size(self):
        """ The disk's size in MB """
        return super(Disk, self).size

    def _preDestroy(self):
        """ Destroy the device. """
        if not self.mediaPresent:
            raise DiskError("cannot destroy disk with no media", self.name)

        Device._preDestroy(self)
