import unittest
from mock import Mock
from mock import TestCase

import parted
import yali
import yali.storage as storage
from yali.storage.formats import getFormat

# device classes for brevity's sake -- later on, that is
from yali.storage.devices.device import Device
from yali.storage.devices.disk import Disk
from yali.storage.devices.partition import Partition
from yali.storage.devices.raidarray import RaidArray
from yali.storage.devices.devicemapper import DeviceMapper
from yali.storage.devices.volumegroup import VolumeGroup
from yali.storage.devices.logicalvolume import LogicalVolume
from yali.storage.devices.filedevice import FileDevice


class StorageTestCase(TestCase):
    """ StorageTestCase

        This is a base class for storage test cases. It sets up imports of
        the storage package, along with an YALI instance and a Storage
        instance. There are lots of little patches to prevent various pieces
        of code from trying to access filesystems and/or devices on the host
        system, along with a couple of convenience methods.

    """
    def __init__(self, *args, **kwargs):
        TestCase.__init__(self, *args, **kwargs)

        self.setUpStorage()

    def setUpStorage(self):
        self.setUpDeviceLibrary()
        self.storage = storage.Storage()

        # device status
        yali.storage.devices.device.Device.status = False
        yali.storage.devices.devicemapper.DeviceMapper.status = False
        yali.storage.devices.volumegroup.VolumeGroup.status = False
        yali.storage.devices.raidarray.RaidArray.status = False
        yali.storage.devices.filedevice.FileDevice.status = False

        # prevent Partition from trying to dig around in the partition's
        # geometry
        yali.storage.devices.partition.Partition._setTargetSize = Device._setTargetSize

        # prevent Ext2FS from trying to run resize2fs to get a filesystem's
        # minimum size
        storage.formats.filesystem.Ext2Filesystem.minSize = storage.formats.Format.minSize
        storage.formats.filesystem.Filesystem.migratable = storage.formats.Format.migratable

    def setUpDeviceLibrary(self):
        # storage library shouldn't be touching or looking at the host system
        # lvm is easy because all calls to /sbin/lvm are via lvm()
        storage.library.lvm.lvm = Mock()

        # raid is easy because all calls to /sbin/mdadm are via mdadm()
        storage.library.raid.mdadm = Mock()

        # swap
        storage.library.swap.swapstatus = Mock(return_value=False)
        storage.library.swap.swapon = Mock()
        storage.library.swap.swapoff = Mock()

        # dm
        storage.library.devicemapper = Mock()


        # this list would normally be obtained by parsing /proc/mdstat
        storage.library.raid.raid_levels = [storage.library.raid.RAID10,
                                            storage.library.raid.RAID0,
                                            storage.library.raid.RAID1,
                                            storage.library.raid.RAID4,
                                            storage.library.raid.RAID5,
                                            storage.library.raid.RAID6]

    def newDevice(*args, **kwargs):
        """ Return a new Device instance suitable for testing. """
        args = args[1:] # drop self arg
        device_class = kwargs.pop("device_class")
        exists = kwargs.pop("exists", False)
        part_type = kwargs.pop("part_type", parted.PARTITION_NORMAL)
        device = device_class(*args, **kwargs)

        if exists:
            # set up mock parted.Device w/ correct size
            device._partedDevice = Mock()
            device._partedDevice.getSize = Mock(return_value=float(device.size))
            device._partedDevice.sectorSize = 512

        if isinstance(device, yali.storage.devices.partition.Partition):
            #if exists:
            #    device.parents = device.req_disks
            device.parents = device.req_disks

            partedPartition = Mock()

            if device.disk:
                part_num = device.name[len(device.disk.name):].split("p")[-1]
                partedPartition.number = int(part_num)

            partedPartition.type = part_type
            partedPartition.path = device.path
            partedPartition.getDeviceNodeName = Mock(return_value=device.name)
            partedPartition.getSize = Mock(return_value=float(device.size))
            device._partedPartition = partedPartition

        device.exists = exists
        device.format.exists = exists

        if isinstance(device, yali.storage.devices.partition.Partition):
            # Partition.probe sets up data needed for resize operations
            device.probe()

        return device

    def newFormat(*args, **kwargs):
        """ Return a new DeviceFormat instance suitable for testing.

            Keyword Arguments:

                device_instance - Device instance this format will be
                                  created on. This is needed for setup of
                                  resizable formats.

            All other arguments are passed directly to
            yali.storage.formats.getFormat.
        """
        args = args[1:] # drop self arg
        exists = kwargs.pop("exists", False)
        device_instance = kwargs.pop("device_instance", None)
        format = getFormat(*args, **kwargs)
        if isinstance(format, storage.formats.disklabel.DiskLabel):
            format._partedDevice = Mock()
            format._partedDisk = Mock()

        format.exists = exists

        if format.resizable and device_instance:
            format._size = device_instance.currentSize

        return format

    def destroyAllDevices(self, disks=None):
        """ Remove all devices from the devicetree.

            Keyword Arguments:

                disks - a list of names of disks to remove partitions from

            Note: this is largely ripped off from partitioning.clearPartitions.

        """
        partitions = self.storage.partitions

        # Sort partitions by descending partition number to minimize confusing
        # things like multiple "destroy sda5" operations due to parted renumbering
        # partitions. This can still happen through the UI but it makes sense to
        # avoid it where possible.
        partitions.sort(key=lambda p: p.partedPartition.number, reverse=True)
        for part in partitions:
            if disks and part.disk.name not in disks:
                continue

            devices = self.storage.deviceDeps(part)
            while devices:
                leaves = [d for d in devices if d.isleaf]
                for leaf in leaves:
                    self.storage.destroyDevice(leaf)
                    devices.remove(leaf)

            self.storage.destroyDevice(part)

    def scheduleCreateDevice(self, *args, **kwargs):
        """ Schedule an operation to create the specified device.

            Verify that the device is not already in the tree and that the
            act of scheduling/adding the operation also adds the device to
            the tree.

            Return the DeviceOperation instance.
        """
        device = kwargs.pop("device")
        if hasattr(device, "req_disks") and \
           len(device.req_disks) == 1 and \
           not device.parents:
            device.parents = device.req_disks

            devicetree = self.storage.devicetree

            self.assertEqual(devicetree.getDeviceByName(device.name), None)
            operation = storage.deviceoperation.OperationCreateDevice(device)
            devicetree.addOperation(operation)
            self.assertEqual(devicetree.getDeviceByName(device.name), device)
            return operation

    def scheduleDestroyDevice(self, *args, **kwargs):
        """ Schedule an operation to destroy the specified device.

            Verify that the device exists initially and that the act of
            scheduling/adding the operation also removes the device from
            the tree.

            Return the DeviceOperation instance.
        """
        device = kwargs.pop("device")
        devicetree = self.storage.devicetree

        self.assertEqual(devicetree.getDeviceByName(device.name), device)
        operation = storage.deviceoperation.OperationDestroyDevice(device)
        devicetree.addOperation(operation)
        self.assertEqual(devicetree.getDeviceByName(device.name), None)
        return operation

    def scheduleCreateFormat(self, *args, **kwargs):
        """ Schedule an operation to write a new format to a device.

            Verify that the device is already in the tree, that it is not
            already set up to contain the specified format, and that the act
            of adding/scheduling the operation causes the new format to be
            reflected in the tree.

            Return the DeviceOperation instance.
        """
        device = kwargs.pop("device")
        format = kwargs.pop("format")
        devicetree = self.storage.devicetree

        self.assertNotEqual(device.format, format)
        self.assertEqual(devicetree.getDeviceByName(device.name), device)
        operation = storage.operations.OperationCreateFormat(device, format)
        devicetree.addOperation(operation)
        _device = devicetree.getDeviceByName(device.name)
        self.assertEqual(_device.format, format)
        return operation

    def scheduleDestroyFormat(self, *args, **kwargs):
        """ Schedule an operation to remove a format from a device.

            Verify that the device is already in the tree and that the act
            of adding/scheduling the operation causes the new format to be
            reflected in the tree.

            Return the DeviceOperation instance.
        """
        device = kwargs.pop("device")
        devicetree = self.storage.devicetree

        self.assertEqual(devicetree.getDeviceByName(device.name), device)
        operation = storage.operations.OperationDestroyFormat(device)
        devicetree.addOperation(operation)
        _device = devicetree.getDeviceByName(device.name)
        self.assertEqual(_device.format.type, None)
        return operation
