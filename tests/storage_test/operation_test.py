#!/usr/bin/python

import unittest
from mock import Mock
from mock import TestCase

from storagetestcase import StorageTestCase
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

# operation classes
from yali.storage.operations import OperationCreateDevice
from yali.storage.operations import OperationResizeDevice
from yali.storage.operations import OperationDestroyDevice
from yali.storage.operations import OperationCreateFormat
from yali.storage.operations import OperationResizeFormat
from yali.storage.operations import OperationMigrateFormat
from yali.storage.operations import OperationDestroyFormat

""" DeviceOperationTestSuite """

class DeviceOperationTestCase(StorageTestCase):
    def setUp(self):
        """ Create something like a preexisting autopart on two disks (sda,sdb).

            The other two disks (sdc,sdd) are left for individual tests to use.
        """
        for name in ["sda", "sdb", "sdc", "sdd"]:
            disk = self.newDevice(device_class=Disk,
                                  device=name,
                                  size=100000)
            disk.format = self.newFormat("disklabel", path=disk.path, exists=True)
            self.storage.devicetree._addDevice(disk)

        # create a layout similar to autopart as a starting point
        sda = self.storage.devicetree.getDeviceByName("sda")
        sdb = self.storage.devicetree.getDeviceByName("sdb")

        sda1 = self.newDevice(device_class=Partition,
                              exists=True,
                              name="sda1",
                              parents=[sda],
                              size=500)
        sda1.format = self.newFormat("ext4", mountpoint="/boot",
                                     device_instance=sda1,
                                     device=sda1.path,
                                     exists=True)
        self.storage.devicetree._addDevice(sda1)

        sda2 = self.newDevice(device_class=Partition,
                              size=99500, name="sda2",
                              parents=[sda],
                              exists=True)
        sda2.format = self.newFormat("lvmpv",
                                     device=sda2.path,
                                     exists=True)
        self.storage.devicetree._addDevice(sda2)

        sdb1 = self.newDevice(device_class=Partition,
                              size=99999,
                              name="sdb1",
                              parents=[sdb],
                              exists=True)
        sdb1.format = self.newFormat("lvmpv",
                                     device=sdb1.path,
                                     exists=True)
        self.storage.devicetree._addDevice(sdb1)

        vg = self.newDevice(device_class=VolumeGroup,
                            name="VolGroup", parents=[sda2, sdb1],
                            exists=True)
        self.storage.devicetree._addDevice(vg)

        lv_root = self.newDevice(device_class=LogicalVolume,
                                 name="lv_root",
                                 vgdev=vg,
                                 size=160000,
                                 exists=True)
        lv_root.format = self.newFormat("ext4",
                                        mountpoint="/",
                                        device_instance=lv_root,
                                        device=lv_root.path,
                                        exists=True)
        self.storage.devicetree._addDevice(lv_root)

        lv_swap = self.newDevice(device_class=LogicalVolume,
                                 name="lv_swap",
                                 vgdev=vg,
                                 size=4000,
                                 exists=True)
        lv_swap.format = self.newFormat("swap",
                                        device=lv_swap.path,
                                        device_instance=lv_swap,
                                        exists=True)
        self.storage.devicetree._addDevice(lv_swap)

    def testOperations(self, *args, **kwargs):
        """ Verify correct management of operations.

            - operation creation/registration/cancellation
                - OperationCreateDevice adds device to tree
                - OperationDestroyDevice removes device from tree
                - OperationCreateFormat sets device.format in tree
                - OperationDestroyFormat unsets device.format in tree
                - cancelled operation's registration side-effects reversed
                - failure to register destruction of non-leaf device
                - failure to register creation of device already in tree?
                - failure to register destruction of device not in tree?

            - operation pruning
                - non-existent-device create..destroy cycles removed
                    - all operations on this device should get removed
                - all operations pruned from to-be-destroyed devices
                    - resize, format, migrate, &c
                - redundant resize/migrate/format operations pruned
                    - last one registered stays

            - operation sorting
                - destroy..resize..migrate..create
                - creation
                    - leaves-last, including formatting
                - destruction
                    - leaves-first
        """
        devicetree = self.storage.devicetree

        # clear the disks
        self.destroyAllDevices()
        self.assertEqual(devicetree.getDevicesByType("lvmlv"), [])
        self.assertEqual(devicetree.getDevicesByType("lvmvg"), [])
        self.assertEqual(devicetree.getDevicesByType("partition"), [])

        sda = devicetree.getDeviceByName("sda")
        self.assertNotEqual(sda, None, "failed to find disk 'sda'")

        sda1 = self.newDevice(device_class=Partition,
                              name="sda1",
                              size=500,
                              parents=[sda])
        self.scheduleCreateDevice(device=sda1)

        sda2 = self.newDevice(device_class=Partition,
                              name="sda2",
                              size=100000,
                              parents=[sda])
        self.scheduleCreateDevice(device=sda2)
        format = self.newFormat("lvmpv", device=sda2.path)
        self.scheduleCreateFormat(device=sda2, format=format)

        vg = self.newDevice(device_class=VolumeGroup,
                            name="vg",
                            parents=[sda2])
        self.scheduleCreateDevice(device=vg)

        lv_root = self.newDevice(device_class=LogicalVolume,
                                 name="lv_root",
                                 vgdev=vg,
                                 size=60000)
        self.scheduleCreateDevice(device=lv_root)
        format = self.newFormat("ext4", device=lv_root.path, mountpoint="/")
        self.scheduleCreateFormat(device=lv_root, format=format)

        lv_swap = self.newDevice(device_class=LogicalVolume,
                                 name="lv_swap",
                                 vgdev=vg,
                                 size=4000)
        self.scheduleCreateDevice(device=lv_swap)
        format = self.newFormat("swap", device=lv_swap.path)
        self.scheduleCreateFormat(device=lv_swap, format=format)

        sda3 = self.newDevice(device_class=Partition,
                              name="sda3",
                              parents=[sda],
                              size=40000)
        self.scheduleCreateDevice(device=sda3)
        format = self.newFormat("mdmember", device=sda3.path)
        self.scheduleCreateFormat(device=sda3, format=format)

        sdb = devicetree.getDeviceByName("sdb")
        self.assertNotEqual(sdb, None, "failed to find disk 'sdb'")

        sdb1 = self.newDevice(device_class=Partition,
                              name="sdb1",
                              parents=[sdb],
                              size=40000)
        self.scheduleCreateDevice(device=sdb1)
        format = self.newFormat("mdmember", device=sdb1.path,)
        self.scheduleCreateFormat(device=sdb1, format=format)

        md0 = self.newDevice(device_class=RaidArray,
                             name="md0", level="raid0", minor=0, size=80000,
                             memberDevices=2, totalDevices=2,
                             parents=[sdb1, sda3])
        self.scheduleCreateDevice(device=md0)

        format = self.newFormat("ext4", device=md0.path, mountpoint="/home")
        self.scheduleCreateFormat(device=md0, format=format)

        format = self.newFormat("ext4", mountpoint="/boot", device=sda1.path)
        self.scheduleCreateFormat(device=sda1, format=format)

    def testOperationCreation(self, *args, **kwargs):
        """ Verify correct operation of operation class constructors. """
        # instantiation of device resize operation for non-existent device should
        # fail
        # XXX resizable depends on existence, so this is covered implicitly
        sdd = self.storage.devicetree.getDeviceByName("sdd")
        p = self.newDevice(device_class=Partition,
                           name="sdd1", size=32768, parents=[sdd])
        self.failUnlessRaises(ValueError,
                              storage.operations.OperationResizeDevice,
                              p,
                              p.size + 7232)

        # instantiation of device resize operation for non-resizable device
        # should fail
        vg = self.storage.devicetree.getDeviceByName("VolGroup")
        self.assertNotEqual(vg, None)
        self.failUnlessRaises(ValueError,
                              storage.operations.OperationResizeDevice,
                              vg,
                              vg.size + 32)

        # instantiation of format resize operation for non-resizable format type
        # should fail
        lv_swap = self.storage.devicetree.getDeviceByName("VolGroup-lv_swap")
        self.assertNotEqual(lv_swap, None)
        self.failUnlessRaises(ValueError,
                              storage.operations.OperationResizeFormat,
                              lv_swap,
                              lv_swap.size + 32)

        # instantiation of format resize operation for non-existent format
        # should fail
        lv_root = self.storage.devicetree.getDeviceByName("VolGroup-lv_root")
        self.assertNotEqual(lv_root, None)
        lv_root.format.exists = False
        self.failUnlessRaises(ValueError,
                              storage.operations.OperationResizeFormat,
                              lv_root,
                              lv_root.size - 1000)
        lv_root.format.exists = True

        # instantiation of format migrate operation for non-migratable format
        # type should fail
        lv_swap = self.storage.devicetree.getDeviceByName("VolGroup-lv_swap")
        self.assertNotEqual(lv_swap, None)
        self.assertEqual(lv_swap.exists, True)
        self.failUnlessRaises(ValueError,
                              storage.operations.OperationMigrateFormat,
                              lv_swap)

        # instantiation of format migrate for non-existent format should fail
        lv_root = self.storage.devicetree.getDeviceByName("VolGroup-lv_root")
        self.assertNotEqual(lv_root, None)
        orig_format = lv_root.format
        lv_root.format = getFormat("ext3", device=lv_root.path)
        self.failUnlessRaises(ValueError,
                              storage.operations.OperationMigrateFormat,
                              lv_root)
        lv_root.format = orig_format

        # instantiation of device create operation for existing device should
        # fail
        lv_swap = self.storage.devicetree.getDeviceByName("VolGroup-lv_swap")
        self.assertNotEqual(lv_swap, None)
        self.assertEqual(lv_swap.exists, True)
        self.failUnlessRaises(ValueError,
                              storage.operations.OperationCreateDevice,
                              lv_swap)

        # instantiation of format destroy operation for device causes device's
        # format attribute to be a DeviceFormat instance
        lv_swap = self.storage.devicetree.getDeviceByName("VolGroup-lv_swap")
        self.assertNotEqual(lv_swap, None)
        orig_format = lv_swap.format
        self.assertEqual(lv_swap.format.type, "swap")
        a = storage.operations.OperationDestroyFormat(lv_swap)
        self.assertEqual(lv_swap.format.type, None)

        # instantiation of format create operation for device causes new format
        # to be accessible via device's format attribute
        new_format = getFormat("vfat", device=lv_swap.path)
        a = storage.operations.OperationCreateFormat(lv_swap, new_format)
        self.assertEqual(lv_swap.format, new_format)
        lv_swap.format = orig_format

    def testOperationRegistration(self, *args, **kwargs):
        """ Verify correct operation of operation registration and cancelling. """
        # self.setUp has just been run, so we should have something like
        # a preexisting autopart config in the devicetree.

        # registering a destroy operation for a non-leaf device should fail
        vg = self.storage.devicetree.getDeviceByName("VolGroup")
        self.assertNotEqual(vg, None)
        self.assertEqual(vg.isleaf, False)
        a = storage.operations.OperationDestroyDevice(vg)
        self.failUnlessRaises(ValueError,
                              self.storage.devicetree.addOperation, a)

        # registering any operation other than create for a device that's not in
        # the devicetree should fail
        sdc = self.storage.devicetree.getDeviceByName("sdc")
        self.assertNotEqual(sdc, None)
        sdc1 = self.newDevice(device_class=Partition,
                              name="sdc1",
                              size=100000,
                              parents=[sdc],
                              exists=True)

        sdc1_format = self.newFormat("ext2", device=sdc1.path, mountpoint="/")
        create_sdc1_format = OperationCreateFormat(sdc1, sdc1_format)
        self.failUnlessRaises(storage.devicetree.DeviceTreeError,
                              self.storage.devicetree.addOperation,
                              create_sdc1_format)

        sdc1_format.exists = True

        migrate_sdc1 = OperationMigrateFormat(sdc1)
        self.failUnlessRaises(storage.devicetree.DeviceTreeError,
                              self.storage.devicetree.addOperation,
                              migrate_sdc1)
        migrate_sdc1.cancel()

        resize_sdc1_format = OperationResizeFormat(sdc1, sdc1.size - 10000)
        self.failUnlessRaises(storage.devicetree.DeviceTreeError,
                              self.storage.devicetree.addOperation,
                              resize_sdc1_format)

        resize_sdc1 = OperationResizeDevice(sdc1, sdc1.size - 10000)
        self.failUnlessRaises(storage.devicetree.DeviceTreeError,
                              self.storage.devicetree.addOperation,
                              resize_sdc1)

        resize_sdc1.cancel()
        resize_sdc1_format.cancel()

        destroy_sdc1_format = OperationDestroyFormat(sdc1)
        self.failUnlessRaises(storage.devicetree.DeviceTreeError,
                              self.storage.devicetree.addOperation,
                              destroy_sdc1_format)


        destroy_sdc1 = OperationDestroyDevice(sdc1)
        self.failUnlessRaises(storage.devicetree.DeviceTreeError,
                              self.storage.devicetree.addOperation,
                              resize_sdc1)

        # registering a device destroy operation should cause the device to be
        # removed from the devicetree
        lv_root = self.storage.devicetree.getDeviceByName("VolGroup-lv_root")
        self.assertNotEqual(lv_root, None)
        a = OperationDestroyDevice(lv_root)
        self.storage.devicetree.addOperation(a)
        lv_root = self.storage.devicetree.getDeviceByName("VolGroup-lv_root")
        self.assertEqual(lv_root, None)
        self.storage.devicetree.removeOperation(a)

        # registering a device create operation should cause the device to be
        # added to the devicetree
        sdd = self.storage.devicetree.getDeviceByName("sdd")
        self.assertNotEqual(sdd, None)
        sdd1 = self.storage.devicetree.getDeviceByName("sdd1")
        self.assertEqual(sdd1, None)
        sdd1 = self.newDevice(device_class=Partition,
                              name="sdd1",
                              size=100000,
                              parents=[sdd])
        a = OperationCreateDevice(sdd1)
        self.storage.devicetree.addOperation(a)
        sdd1 = self.storage.devicetree.getDeviceByName("sdd1")
        self.assertNotEqual(sdd1, None)

    def testOperationObsoletes(self, *args, **kwargs):
        """ Verify correct operation of DeviceOperation.obsoletes. """
        self.destroyAllDevices(disks=["sdc"])
        sdc = self.storage.devicetree.getDeviceByName("sdc")
        self.assertNotEqual(sdc, None)

        sdc1 = self.newDevice(device_class=Partition,
                              name="sdc1",
                              parents=[sdc],
                              size=40000)

        # OperationCreateDevice
        #
        # - obsoletes other OperationCreateDevice instances w/ lower id and same
        #   device
        create_device_1 = OperationCreateDevice(sdc1)
        create_device_2 = OperationCreateDevice(sdc1)
        self.assertEqual(create_device_2.obsoletes(create_device_1), True)
        self.assertEqual(create_device_1.obsoletes(create_device_2), False)

        # OperationCreateFormat
        #
        # - obsoletes other OperationCreateFormat instances w/ lower id and same
        #   device
        format_1 = self.newFormat("ext3", mountpoint="/home", device=sdc1.path)
        format_2 = self.newFormat("ext3", mountpoint="/opt", device=sdc1.path)
        create_format_1 = OperationCreateFormat(sdc1, format_1)
        create_format_2 = OperationCreateFormat(sdc1, format_2)
        self.assertEqual(create_format_2.obsoletes(create_format_1), True)
        self.assertEqual(create_format_1.obsoletes(create_format_2), False)

        # OperationMigrateFormat
        #
        # - obsoletes other OperationMigrateFormat instances w/ lower id and same
        #   device
        sdc1.format = self.newFormat("ext2", mountpoint="/", device=sdc1.path,
                                     device_instance=sdc1,
                                     exists=True)
        migrate_1 = OperationMigrateFormat(sdc1)
        migrate_2 = OperationMigrateFormat(sdc1)
        self.assertEqual(migrate_2.obsoletes(migrate_1), True)
        self.assertEqual(migrate_1.obsoletes(migrate_2), False)

        # OperationResizeFormat
        #
        # - obsoletes other OperationResizeFormat instances w/ lower id and same
        #   device
        resize_format_1 = OperationResizeFormat(sdc1, sdc1.size - 1000)
        resize_format_2 = OperationResizeFormat(sdc1, sdc1.size - 5000)
        self.assertEqual(resize_format_2.obsoletes(resize_format_1), True)
        self.assertEqual(resize_format_1.obsoletes(resize_format_2), False)

        # OperationCreateFormat
        #
        # - obsoletes migrate, resize format operations w/ lower id on same device
        new_format = self.newFormat("ext4", mountpoint="/foo", device=sdc1.path)
        create_format_3 = OperationCreateFormat(sdc1, new_format)
        self.assertEqual(create_format_3.obsoletes(resize_format_1), True)
        self.assertEqual(create_format_3.obsoletes(resize_format_2), True)
        self.assertEqual(create_format_3.obsoletes(migrate_1), True)
        self.assertEqual(create_format_3.obsoletes(migrate_2), True)

        # OperationResizeDevice
        #
        # - obsoletes other OperationResizeDevice instances w/ lower id and same
        #   device
        sdc1.exists = True
        sdc1.format.exists = True
        resize_device_1 = OperationResizeDevice(sdc1, sdc1.size + 10000)
        resize_device_2 = OperationResizeDevice(sdc1, sdc1.size - 10000)
        self.assertEqual(resize_device_2.obsoletes(resize_device_1), True)
        self.assertEqual(resize_device_1.obsoletes(resize_device_2), False)
        sdc1.exists = False
        sdc1.format.exists = False

        # OperationDestroyFormat
        #
        # - obsoletes all format operations w/ lower id on same device (including
        #   self if format does not exist)
        destroy_format_1 = OperationDestroyFormat(sdc1)
        self.assertEqual(destroy_format_1.obsoletes(create_format_1), True)
        self.assertEqual(destroy_format_1.obsoletes(migrate_2), True)
        self.assertEqual(destroy_format_1.obsoletes(resize_format_1), True)
        self.assertEqual(destroy_format_1.obsoletes(destroy_format_1), True)

        # OperationDestroyDevice
        #
        # - obsoletes all operations w/ lower id that act on the same non-existent
        #   device (including self)
        # sdc1 does not exist
        destroy_sdc1 = OperationDestroyDevice(sdc1)
        self.assertEqual(destroy_sdc1.obsoletes(create_format_2), True)
        self.assertEqual(destroy_sdc1.obsoletes(migrate_1), True)
        self.assertEqual(destroy_sdc1.obsoletes(resize_format_2), True)
        self.assertEqual(destroy_sdc1.obsoletes(create_device_1), True)
        self.assertEqual(destroy_sdc1.obsoletes(resize_device_1), True)
        self.assertEqual(destroy_sdc1.obsoletes(destroy_sdc1), True)

        # OperationDestroyDevice
        #
        # - obsoletes all but OperationDestroyFormat operations w/ lower id on the
        #   same existing device
        # sda1 exists
        sda1 = self.storage.devicetree.getDeviceByName("sda1")
        self.assertNotEqual(sda1, None)
        resize_sda1_format = OperationResizeFormat(sda1, sda1.size - 50)
        resize_sda1 = OperationResizeDevice(sda1, sda1.size - 50)
        destroy_sda1_format = OperationDestroyFormat(sda1)
        destroy_sda1 = OperationDestroyDevice(sda1)
        self.assertEqual(destroy_sda1.obsoletes(resize_sda1_format), True)
        self.assertEqual(destroy_sda1.obsoletes(resize_sda1), True)
        self.assertEqual(destroy_sda1.obsoletes(destroy_sda1), False)
        self.assertEqual(destroy_sda1.obsoletes(destroy_sda1_format), False)

    def testOperationPruning(self, *args, **kwargs):
        """ Verify correct functioning of operation pruning. """
        self.destroyAllDevices()

        sda = self.storage.devicetree.getDeviceByName("sda")
        self.assertNotEqual(sda, None, "failed to find disk 'sda'")

        sda1 = self.newDevice(device_class=Partition,
                              name="sda1",
                              size=500,
                              parents=[sda])
        self.scheduleCreateDevice(device=sda1)

        sda2 = self.newDevice(device_class=Partition,
                              name="sda2",
                              size=100000,
                              parents=[sda])
        self.scheduleCreateDevice(device=sda2)
        format = self.newFormat("lvmpv", device=sda2.path)
        self.scheduleCreateFormat(device=sda2, format=format)

        vg = self.newDevice(device_class=VolumeGroup,
                            name="vg",
                            parents=[sda2])
        self.scheduleCreateDevice(device=vg)

        lv_root = self.newDevice(device_class=LogicalVolume,
                                 name="lv_root",
                                 vgdev=vg, size=60000)
        self.scheduleCreateDevice(device=lv_root)
        format = self.newFormat("ext4", device=lv_root.path, mountpoint="/")
        self.scheduleCreateFormat(device=lv_root, format=format)

        lv_swap = self.newDevice(device_class=LogicalVolume,
                                 name="lv_swap",
                                 vgdev=vg,
                                 size=4000)
        self.scheduleCreateDevice(device=lv_swap)
        format = self.newFormat("swap", device=lv_swap.path)
        self.scheduleCreateFormat(device=lv_swap, format=format)

        # we'll soon schedule destroy operations for these members and the array,
        # which will test pruning. the whole mess should reduce to nothing
        sda3 = self.newDevice(device_class=Partition,
                              name="sda3",
                              parents=[sda],
                              size=40000)
        self.scheduleCreateDevice(device=sda3)
        format = self.newFormat("mdmember", device=sda3.path)
        self.scheduleCreateFormat(device=sda3, format=format)

        sdb = self.storage.devicetree.getDeviceByName("sdb")
        self.assertNotEqual(sdb, None, "failed to find disk 'sdb'")

        sdb1 = self.newDevice(device_class=Partition,
                              name="sdb1",
                              parents=[sdb],
                              size=40000)
        self.scheduleCreateDevice(device=sdb1)
        format = self.newFormat("mdmember", device=sdb1.path,)
        self.scheduleCreateFormat(device=sdb1, format=format)

        md0 = self.newDevice(device_class=RaidArray,
                             name="md0", level="raid0", minor=0, size=80000,
                             memberDevices=2, totalDevices=2,
                             parents=[sdb1, sda3])
        self.scheduleCreateDevice(device=md0)

        format = self.newFormat("ext4", device=md0.path, mountpoint="/home")
        self.scheduleCreateFormat(device=md0, format=format)

        # now destroy the md and its components
        self.scheduleDestroyFormat(device=md0)
        self.scheduleDestroyDevice(device=md0)
        self.scheduleDestroyDevice(device=sdb1)
        self.scheduleDestroyDevice(device=sda3)

        format = self.newFormat("ext4", mountpoint="/boot", device=sda1.path)
        self.scheduleCreateFormat(device=sda1, format=format)

        # verify the md operations are present prior to pruning
        md0_operations = self.storage.devicetree.findOperations(devid=md0.id)
        self.assertNotEqual(len(md0_operations), 0)

        sdb1_operations = self.storage.devicetree.findOperations(devid=sdb1.id)
        self.assertNotEqual(len(sdb1_operations), 0)

        sda3_operations = self.storage.devicetree.findOperations(devid=sda3.id)
        self.assertNotEqual(len(sda3_operations), 0)

        self.storage.devicetree.pruneOperations()

        # verify the md operations are gone after pruning
        md0_operations = self.storage.devicetree.findOperations(devid=md0.id)
        self.assertEqual(len(md0_operations), 0)

        sdb1_operations = self.storage.devicetree.findOperations(devid=sdb1.id)
        self.assertEqual(len(sdb1_operations), 0)

        sda3_operations = self.storage.devicetree.findOperations(sda3.id)
        self.assertEqual(len(sda3_operations), 0)

    def testOperationDependencies(self, *args, **kwargs):
        """ Verify correct functioning of operation dependencies. """
        # OperationResizeDevice
        # an operation that shrinks a device should require the operation that
        # shrinks the device's format
        lv_root = self.storage.devicetree.getDeviceByName("VolGroup-lv_root")
        self.assertNotEqual(lv_root, None)
        shrink_format = OperationResizeFormat(lv_root, lv_root.size - 5000)
        shrink_device = OperationResizeDevice(lv_root, lv_root.size - 5000)
        self.assertEqual(shrink_device.requires(shrink_format), True)
        self.assertEqual(shrink_format.requires(shrink_device), False)
        shrink_format.cancel()
        shrink_device.cancel()

        # OperationResizeDevice
        # an operation that grows a format should require the operation that
        # grows the device
        orig_size = lv_root.currentSize
        grow_device = OperationResizeDevice(lv_root, orig_size + 100)
        grow_format = OperationResizeFormat(lv_root, orig_size + 100)
        self.assertEqual(grow_format.requires(grow_device), True)
        self.assertEqual(grow_device.requires(grow_format), False)

        # create something like uncommitted autopart
        self.destroyAllDevices()
        sda = self.storage.devicetree.getDeviceByName("sda")
        sdb = self.storage.devicetree.getDeviceByName("sdb")
        sda1 = self.newDevice(device_class=Partition,
                              name="sda1",
                              size=500,
                              parents=[sda])
        sda1_format = self.newFormat("ext4", mountpoint="/boot",
                                     device=sda1.path)
        self.scheduleCreateDevice(device=sda1)
        self.scheduleCreateFormat(device=sda1, format=sda1_format)

        sda2 = self.newDevice(device_class=Partition,
                              name="sda2",
                              size=99500,
                              parents=[sda])
        sda2_format = self.newFormat("lvmpv", device=sda1.path)
        self.scheduleCreateDevice(device=sda2)
        self.scheduleCreateFormat(device=sda2, format=sda2_format)

        sdb1 = self.newDevice(device_class=Partition,
                              name="sdb1",
                              size=100000,
                              parents=[sdb])
        sdb1_format = self.newFormat("lvmpv", device=sdb1.path)
        self.scheduleCreateDevice(device=sdb1)
        self.scheduleCreateFormat(device=sdb1, format=sdb1_format)

        vg = self.newDevice(device_class=VolumeGroup,
                            name="VolGroup",
                            parents=[sda2, sdb1])
        self.scheduleCreateDevice(device=vg)

        lv_root = self.newDevice(device_class=LogicalVolume,
                                 name="lv_root",
                                 vgdev=vg,
                                 size=160000)
        self.scheduleCreateDevice(device=lv_root)
        format = self.newFormat("ext4", device=lv_root.path, mountpoint="/")
        self.scheduleCreateFormat(device=lv_root, format=format)

        lv_swap = self.newDevice(device_class=LogicalVolume,
                                 name="lv_swap",
                                 vgdev=vg,
                                 size=4000)
        self.scheduleCreateDevice(device=lv_swap)
        format = self.newFormat("swap", device=lv_swap.path)
        self.scheduleCreateFormat(device=lv_swap, format=format)

        # OperationCreateDevice
        # creation of an LV should require the operations that create the VG,
        # its PVs, and the devices that contain the PVs
        lv_root = self.storage.devicetree.getDeviceByName("VolGroup-lv_root")
        self.assertNotEqual(lv_root, None)
        operations = self.storage.devicetree.findOperations(type="create",
                                                            object="device",
                                                            device=lv_root)
        self.assertEqual(len(operations), 1,
                         "wrong number of device create operations for lv_root: "
                         "%d" % len(operations))
        create_lv_operation = operations[0]

        vgs = [d for d in self.storage.vgs if d.name == "VolGroup"]
        self.assertNotEqual(vgs, [])
        vg = vgs[0]
        operations = self.storage.devicetree.findOperations(type="create",
                                                            object="device",
                                                            device=vg)
        self.assertEqual(len(operations), 1,
                         "wrong number of device create operations for VolGroup")
        create_vg_operation = operations[0]

        self.assertEqual(create_lv_operation.requires(create_vg_operation), True)

        create_pv_operations = []
        pvs = [d for d in self.storage.pvs if d in vg.pvs]
        self.assertNotEqual(pvs, [])
        for pv in pvs:
            # include device and format create operations for each pv
            operations = self.storage.devicetree.findOperations(type="create",
                                                                device=pv)
            self.assertEqual(len(operations), 2,
                             "wrong number of device create operations for "
                             "pv %s" % pv.name)
            create_pv_operations.append(operations[0])

        for pv_operation in create_pv_operations:
            self.assertEqual(create_lv_operation.requires(pv_operation), True)
            # also check that the vg create operation requires the pv operations
            self.assertEqual(create_vg_operation.requires(pv_operation), True)

        # OperationCreateDevice
        # the higher numbered partition of two that are scheduled to be
        # created on a single disk should require the operation that creates the
        # lower numbered of the two, eg: create sda2 before creating sda3
        sdc = self.storage.devicetree.getDeviceByName("sdc")
        self.assertNotEqual(sdc, None)

        sdc1 = self.newDevice(device_class=Partition,
                              name="sdc1",
                              parents=[sdc],
                              size=50000)
        create_sdc1 = self.scheduleCreateDevice(device=sdc1)
        self.assertEqual(isinstance(create_sdc1, OperationCreateDevice), True)

        sdc2 = self.newDevice(device_class=Partition,
                              name="sdc2",
                              parents=[sdc],
                              size=50000)
        create_sdc2 = self.scheduleCreateDevice(device=sdc2)
        self.assertEqual(isinstance(create_sdc2, OperationCreateDevice), True)

        self.assertEqual(create_sdc2.requires(create_sdc1), True)
        self.assertEqual(create_sdc1.requires(create_sdc2), False)

        # OperationCreateDevice
        # operations that create partitions on two separate disks should not
        # require each other, regardless of the partitions' numbers
        sda1 = self.storage.devicetree.getDeviceByName("sda1")
        self.assertNotEqual(sda1, None)
        operations = self.storage.devicetree.findOperations(type="create",
                                                            object="device",
                                                            device=sda1)
        self.assertEqual(len(operations), 1,
                         "wrong number of create operations found for sda1")
        create_sda1 = operations[0]
        self.assertEqual(create_sdc2.requires(create_sda1), False)
        self.assertEqual(create_sda1.requires(create_sdc1), False)

        # OperationDestroyDevice
        # an operation that destroys a device containing an mdmember format
        # should require the operation that destroys the md array it is a
        # member of if an array is defined
        self.destroyAllDevices(disks=["sdc", "sdd"])
        sdc = self.storage.devicetree.getDeviceByName("sdc")
        self.assertNotEqual(sdc, None)
        sdd = self.storage.devicetree.getDeviceByName("sdd")
        self.assertNotEqual(sdd, None)

        sdc1 = self.newDevice(device_class=Partition,
                              name="sdc1", parents=[sdc], size=40000)
        self.scheduleCreateDevice(device=sdc1)
        format = self.newFormat("mdmember", device=sdc1.path)
        self.scheduleCreateFormat(device=sdc1, format=format)

        sdd1 = self.newDevice(device_class=Partition,
                              name="sdd1",
                              parents=[sdd],
                              size=40000)
        self.scheduleCreateDevice(device=sdd1)
        format = self.newFormat("mdmember", device=sdd1.path,)
        self.scheduleCreateFormat(device=sdd1, format=format)

        md0 = self.newDevice(device_class=RaidArray,
                             name="md0", level="raid0", minor=0, size=80000,
                             memberDevices=2, totalDevices=2,
                             parents=[sdc1, sdd1])
        self.scheduleCreateDevice(device=md0)
        format = self.newFormat("ext4", device=md0.path, mountpoint="/home")
        self.scheduleCreateFormat(device=md0, format=format)

        destroy_md0_format = self.scheduleDestroyFormat(device=md0)
        destroy_md0 = self.scheduleDestroyDevice(device=md0)
        destroy_members = [self.scheduleDestroyDevice(device=sdc1)]
        destroy_members.append(self.scheduleDestroyDevice(device=sdd1))

        for member in destroy_members:
            # device and format destroy operations for md members should require
            # both device and format destroy operations for the md array
            for array in [destroy_md0_format, destroy_md0]:
                self.assertEqual(member.requires(array), True)

        # OperationDestroyDevice
        # when there are two operations that will each destroy a partition on the
        # same disk, the operation that will destroy the lower-numbered
        # partition should require the operation that will destroy the higher-
        # numbered partition, eg: destroy sda2 before destroying sda1
        self.destroyAllDevices(disks=["sdc", "sdd"])
        sdc1 = self.newDevice(device_class=Partition,
                              name="sdc1", parents=[sdc], size=50000)
        self.scheduleCreateDevice(device=sdc1)

        sdc2 = self.newDevice(device_class=Partition,
                              name="sdc2", parents=[sdc], size=40000)
        self.scheduleCreateDevice(device=sdc2)

        destroy_sdc1 = self.scheduleDestroyDevice(device=sdc1)
        destroy_sdc2 = self.scheduleDestroyDevice(device=sdc2)
        self.assertEqual(destroy_sdc1.requires(destroy_sdc2), True)
        self.assertEqual(destroy_sdc2.requires(destroy_sdc1), False)

        self.destroyAllDevices(disks=["sdc", "sdd"])
        sdc = self.storage.devicetree.getDeviceByName("sdc")
        self.assertNotEqual(sdc, None)
        sdd = self.storage.devicetree.getDeviceByName("sdd")
        self.assertNotEqual(sdd, None)

        sdc1 = self.newDevice(device_class=Partition,
                              name="sdc1", parents=[sdc], size=50000)
        create_pv = self.scheduleCreateDevice(device=sdc1)
        format = self.newFormat("lvmpv", device=sdc1.path)
        create_pv_format = self.scheduleCreateFormat(device=sdc1, format=format)

        testvg = self.newDevice(device_class=VolumeGroup,
                                name="testvg",
                                parents=[sdc1], size=50000)
        create_vg = self.scheduleCreateDevice(device=testvg)
        testlv = self.newDevice(device_class=LogicalVolume,
                                name="testlv",
                                vgdev=testvg,
                                size=30000)
        create_lv = self.scheduleCreateDevice(device=testlv)
        format = self.newFormat("ext4", device=testlv.path)
        create_lv_format = self.scheduleCreateFormat(device=testlv, format=format)

        # OperationCreateFormat
        # creation of a format on a non-existent device should require the
        # operation that creates the device
        self.assertEqual(create_lv_format.requires(create_lv), True)

        # OperationCreateFormat
        # an operation that creates a format on a device should require an operation
        # that creates a device that the format's device depends on
        self.assertEqual(create_lv_format.requires(create_pv), True)
        self.assertEqual(create_lv_format.requires(create_vg), True)

        # OperationCreateFormat
        # an operation that creates a format on a device should require an operation
        # that creates a format on a device that the format's device depends on
        self.assertEqual(create_lv_format.requires(create_pv_format), True)

        # XXX from here on, the devices are existing but not in the tree, so
        #     we instantiate and use operations directly
        self.destroyAllDevices(disks=["sdc", "sdd"])
        sdc1 = self.newDevice(device_class=Partition,
                              exists=True,
                              name="sdc1",
                              parents=[sdc],
                              size=50000)
        sdc1.format = self.newFormat("lvmpv", device=sdc1.path, exists=True,
                                     device_instance=sdc1)
        testvg = self.newDevice(device_class=VolumeGroup,
                                exists=True,
                                name="testvg",
                                parents=[sdc1],
                                size=50000)
        testlv = self.newDevice(device_class=LogicalVolume,
                                exists=True,
                                name="testlv",
                                vgdev=testvg,
                                size=30000)
        testlv.format = self.newFormat("ext4", device=testlv.path,
                                       exists=True, device_instance=testlv)

        # OperationResizeDevice
        # an operation that resizes a device should require an operation that grows
        # a device that the first operation's device depends on, eg: grow
        # device containing PV before resize of VG or LVs
        tmp = sdc1.format
        sdc1.format = None      # since lvmpv format is not resizable
        grow_pv = OperationResizeDevice(sdc1, sdc1.size + 10000)
        grow_lv = OperationResizeDevice(testlv, testlv.size + 5000)
        grow_lv_format = OperationResizeFormat(testlv, testlv.size + 5000)

        self.assertEqual(grow_lv.requires(grow_pv), True)
        self.assertEqual(grow_pv.requires(grow_lv), False)

        # OperationResizeFormat
        # an operation that grows a format should require the operation that grows
        # the format's device
        self.assertEqual(grow_lv_format.requires(grow_lv), True)
        self.assertEqual(grow_lv.requires(grow_lv_format), False)

        # OperationResizeFormat
        # an operation that resizes a device's format should depend on an operation
        # that grows a device the first device depends on
        self.assertEqual(grow_lv_format.requires(grow_pv), True)
        self.assertEqual(grow_pv.requires(grow_lv_format), False)

        # OperationResizeFormat
        # an operation that resizes a device's format should depend on an operation
        # that grows a format on a device the first device depends on
        # XXX resize of PV format is not allowed, so there's no real-life
        #     example of this to test

        grow_lv_format.cancel()
        grow_lv.cancel()
        grow_pv.cancel()

        # OperationResizeDevice
        # an operation that resizes a device should require an operation that grows
        # a format on a device that the first operation's device depends on, eg:
        # grow PV format before resize of VG or LVs
        # XXX resize of PV format is not allowed, so there's no real-life
        #     example of this to test

        # OperationResizeDevice
        # an operation that resizes a device should require an operation that
        # shrinks a device that depends on the first operation's device, eg:
        # shrink LV before resizing VG or PV devices
        shrink_lv = OperationResizeDevice(testlv, testlv.size - 10000)
        shrink_pv = OperationResizeDevice(sdc1, sdc1.size - 5000)

        self.assertEqual(shrink_pv.requires(shrink_lv), True)
        self.assertEqual(shrink_lv.requires(shrink_pv), False)

        # OperationResizeDevice
        # an operation that resizes a device should require an operation that
        # shrinks a format on a device that depends on the first operation's
        # device, eg: shrink LV format before resizing VG or PV devices
        shrink_lv_format = OperationResizeFormat(testlv, testlv.size)
        self.assertEqual(shrink_pv.requires(shrink_lv_format), True)
        self.assertEqual(shrink_lv_format.requires(shrink_pv), False)

        # OperationResizeFormat
        # an operation that resizes a device's format should depend on an operation
        # that shrinks a device that depends on the first device
        # XXX can't think of a real-world example of this since PVs and MD
        #     member devices are not resizable in anaconda

        # OperationResizeFormat
        # an operation that resizes a device's format should depend on an operation
        # that shrinks a format on a device that depends on the first device
        # XXX can't think of a real-world example of this since PVs and MD
        #     member devices are not resizable in anaconda

        shrink_lv_format.cancel()
        shrink_lv.cancel()
        shrink_pv.cancel()
        sdc1.format = tmp   # restore pv's lvmpv format

        # OperationCreateFormat
        # an operation that creates a format on a device should require an operation
        # that resizes a device that the format's device depends on
        # XXX Really? Is this always so?

        # OperationCreateFormat
        # an operation that creates a format on a device should require an operation
        # that resizes a format on a device that the format's device depends on
        # XXX Same as above.

        # OperationCreateFormat
        # an operation that creates a format on a device should require an operation
        # that resizes the device that will contain the format
        grow_lv = OperationResizeDevice(testlv, testlv.size + 1000)
        format = self.newFormat("msdos", device=testlv.path)
        format_lv = OperationCreateFormat(testlv, format)
        self.assertEqual(format_lv.requires(grow_lv), True)
        self.assertEqual(grow_lv.requires(format_lv), False)

        # OperationDestroyFormat
        # an operation that destroys a format should require an operation that
        # destroys a device that depends on the format's device
        destroy_pv_format = OperationDestroyFormat(sdc1)
        destroy_lv_format = OperationDestroyFormat(testlv)
        destroy_lv = OperationDestroyDevice(testlv)
        self.assertEqual(destroy_pv_format.requires(destroy_lv), True)
        self.assertEqual(destroy_lv.requires(destroy_pv_format), False)

        # OperationDestroyFormat
        # an operation that destroys a format should require an operation that
        # destroys a format on a device that depends on the first format's
        # device
        self.assertEqual(destroy_pv_format.requires(destroy_lv_format), True)
        self.assertEqual(destroy_lv_format.requires(destroy_pv_format), False)

    def testOperationSorting(self, *args, **kwargs):
        """ Verify correct functioning of operation sorting. """
        pass


def suite():
    return unittest.TestLoader().loadTestsFromTestCase(DeviceOperationTestCase)


if __name__ == "__main__":
    unittest.main()

