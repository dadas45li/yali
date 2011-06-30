#!/usr/bin/python
# -*- coding: utf-8 -*-
import gettext

__trans = gettext.translation('yali', fallback=True)
_ = __trans.ugettext

import yali.context as ctx
from yali.util import numeric_type
from yali.storage.devices.devicemapper import DeviceMapper
from yali.storage.devices.device import Device, DeviceError
from yali.storage.devices.volumegroup import VolumeGroup
from yali.storage.library import lvm
from yali.baseudev import udev_settle
from yali.storage.library import devicemapper

class LogicalVolumeError(DeviceError):
    pass

class SinglePhysicalVolumeError(LogicalVolumeError):
    pass

class LogicalVolume(DeviceMapper):
    """ An LVM Logical Volume """
    _type = "lvmlv"
    _resizable = True
    _packages = ["lvm2"]

    def __init__(self, name, vgdev, size=None, uuid=None,
                 stripes=1, logSize=0, snapshotSpace=0,
                 format=None, exists=None, sysfsPath='',
                 grow=None, maxsize=None, percent=None,
                 singlePV=False):
        """ Create a LogicalVolume instance.

            Arguments:

                name -- the device name (generally a device node's basename)
                vgdev -- volume group (VolumeGroup instance)

            Keyword Arguments:

                size -- the device's size (in MB)
                uuid -- the device's UUID
                stripes -- number of copies in the vg (>1 for mirrored lvs)
                logSize -- size of log volume (for mirrored lvs)
                snapshotSpace -- sum of sizes of snapshots of this lv
                sysfsPath -- sysfs device path
                format -- a DeviceFormat instance
                exists -- indicates whether this is an existing device
                singlePV -- if true, maps this lv to a single pv

                For new (non-existent) LVs only:

                    grow -- whether to grow this LV
                    maxsize -- maximum size for growable LV (in MB)
                    percent -- percent of VG space to take

        """
        if isinstance(vgdev, list):
            if len(vgdev) != 1:
                raise ValueError("constructor requires a single VolumeGroup instance")
            elif not isinstance(vgdev[0], VolumeGroup):
                raise ValueError("constructor requires a VolumeGroup instance")
        elif not isinstance(vgdev, VolumeGroup):
            raise ValueError("constructor requires a VolumeGroup instance")

        DeviceMapper.__init__(self, name, size=size, format=format,
                              sysfsPath=sysfsPath, parents=vgdev, exists=exists)
        self.singlePVerr = ("%(mountpoint)s is restricted to a single "
                            "physical volume on this platform.  No physical "
                            "volumes available in volume group %(vgname)s "
                            "with %(size)d MB of available space." %
                           {'mountpoint': getattr(self.format, "mountpoint",
                                                  "A proposed logical volume"),
                            'vgname': self.vg.name,
                            'size': self.size})

        self.uuid = uuid
        self.snapshotSpace = snapshotSpace
        self.stripes = stripes
        self.logSize = logSize
        self.singlePV = singlePV

        self.req_grow = None
        self.req_max_size = 0
        self.req_size = 0   
        self.req_percent = 0

        if not self.exists:
            self.req_grow = grow
            self.req_max_size = numeric_type(maxsize)
            # XXX should we enforce that req_size be pe-aligned?
            self.req_size = self._size
            self.req_percent = numeric_type(percent)

        if self.singlePV:
            # make sure there is at least one PV that can hold this LV
            validpvs = filter(lambda x: float(x.size) >= self.req_size,
                              self.vg.pvs)
            if not validpvs:
                raise SinglePhysicalVolumeError(self.singlePVerr)

        # here we go with the circular references
        self.vg._addLogicalVolume(self)

    def __repr__(self):
        s = DeviceMapper.__repr__(self)
        s += ("  VG device = %(vgdev)r\n"
              "  percent = %(percent)s\n"
              "  mirrored = %(mirrored)s stripes = %(stripes)d"
              "  snapshot total =  %(snapshots)dMB\n"
              "  VG space used = %(vgspace)dMB" %
              {"vgdev": self.vg, "percent": self.req_percent,
               "mirrored": self.mirrored, "stripes": self.stripes,
               "snapshots": self.snapshotSpace, "vgspace": self.vgSpaceUsed })
        return s

    @property
    def dict(self):
        d = super(LogicalVolume, self).dict
        if self.exists:
            d.update({"mirrored": self.mirrored, "stripes": self.stripes,
                      "snapshots": self.snapshotSpace,
                      "vgspace": self.vgSpaceUsed})
        else:
            d.update({"percent": self.req_percent})

        return d

    @property
    def mirrored(self):
        return self.stripes > 1

    def _setSize(self, size):
        size = self.vg.align(numeric_type(size))
        ctx.logger.debug("trying to set lv %s size to %dMB" % (self.name, size))
        if size <= self.vg.freeSpace + self.vgSpaceUsed:
            self._size = size
            self.targetSize = size
        else:
            ctx.logger.debug("failed to set size: %dMB short" % (size - (self.vg.freeSpace + self.vgSpaceUsed),))
            raise ValueError("not enough free space in volume group")

    size = property(Device._getSize, _setSize)

    @property
    def vgSpaceUsed(self):
        """ Space occupied by this LV, not including snapshots. """
        return (self.vg.align(self.size, roundup=True) * self.stripes
                + self.logSize)

    @property
    def vg(self):
        """ This Logical Volume's Volume Group. """
        return self.parents[0]

    @property
    def mapName(self):
        """ This device's device-mapper map name """
        # Thank you lvm for this lovely hack.
        return "%s-%s" % (self.vg.mapName, self._name.replace("-","--"))

    @property
    def path(self):
        """ Device node representing this device. """
        return "%s/%s" % (self._devDir, self.mapName)

    def getDMNode(self):
        """ Return the dm-X (eg: dm-0) device node for this device. """
        if not self.exists:
            raise LogicalVolumeError("device has not been created", self.name)

        return devicemapper.dm_node_from_name(self.mapName)

    @property
    def name(self):
        """ This device's name. """
        return "%s-%s" % (self.vg.name, self._name)

    @property
    def lvname(self):
        """ The LV's name (not including VG name). """
        return self._name

    @property
    def complete(self):
        """ Test if vg exits and if it has all pvs. """
        return self.vg.complete

    def setupParents(self, orig=False):
        # parent is a vg, which has no formatting (or device for that matter)
        Device.setupParents(self, orig=orig)

    def _setup(self, intf=None, orig=False):
        """ Open, or set up, a device. """
        lvm.lvactivate(self.vg.name, self._name)

    def _teardown(self, recursive=None):
        """ Close, or tear down, a device. """
        lvm.lvdeactivate(self.vg.name, self._name)

    def _postTeardown(self, recursive=False):
        try:
            # It's likely that teardown of a VG will fail due to other
            # LVs being active (filesystems mounted, &c), so don't let
            # it bring everything down.
            Device._postTeardown(self, recursive=recursive)
        except DeviceError:
            if recursive:
                ctx.logger.debug("vg %s teardown failed; continuing" % self.vg.name)
            else:
                raise

    def _create(self, w):
        """ Create the device. """
        # should we use --zero for safety's sake?
        if self.singlePV:
            lvm.lvcreate(self.vg.name, self._name, self.size, progress=w,
                         pvs=self._getSinglePV())
        else:
            lvm.lvcreate(self.vg.name, self._name, self.size, progress=w)

    def _preDestroy(self):
        Device._preDestroy(self)
        # set up the vg's pvs so lvm can remove the lv
        self.vg.setupParents(orig=True)

    def _destroy(self):
        """ Destroy the device. """
        lvm.lvremove(self.vg.name, self._name)

    def _getSinglePV(self):
        validpvs = filter(lambda x: float(x.size) >= self.size, self.vg.pvs)

        if not validpvs:
            raise SinglePhysicalVolumeError(self.singlePVerr)

        return [validpvs[0].path]

    def resize(self, intf=None):
        # XXX resize format probably, right?
        if not self.exists:
            raise LogicalVolumeError("device has not been created", self.name)

        # Setup VG parents (in case they are dmraid partitions for example)
        self.vg.setupParents(orig=True)

        if self.originalFormat.exists:
            self.originalFormat.teardown()
        if self.format.exists:
            self.format.teardown()

        udev_settle()
        lvm.lvresize(self.vg.name, self._name, self.size)

    def checkSize(self):
        """ Check to make sure the size of the device is allowed by the
            format used.

            return None is all is ok
            return large or small depending on the problem
        """
        problem = None
        if self.format.maxSize and self.size > self.format.maxSize:
            problem = _("large")
        elif (self.format.minSize and
              (not self.req_grow and
               self.size < self.format.minSize) or
              (self.req_grow and self.req_max_size and
               self.req_max_size < self.format.minSize)):
            problem = _("small")
        return problem
