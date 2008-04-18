# -*- coding: utf-8 -*-
#
# Copyright (C) 2005-2007, TUBITAK/UEKAE
#
# This program is free software; you can redistribute it and/or modify it under
# the terms of the GNU General Public License as published by the Free
# Software Foundation; either version 2 of the License, or (at your option)
# any later version.
#
# Please read the COPYING file.
#


import gettext
__trans = gettext.translation('yali4', fallback=True)
_ = __trans.ugettext

from PyQt4 import QtGui
from PyQt4.QtCore import *

import time
import thread
from os.path import basename

import yali4.storage
import yali4.bootloader
import yali4.partitionrequest as request
import yali4.partitiontype as parttype
from yali4.parteddata import *

from yali4.gui.ScreenWidget import ScreenWidget
from yali4.gui.Ui.bootloaderwidget import Ui_BootLoaderWidget
from yali4.gui.YaliDialog import WarningDialog, WarningWidget, InformationWindow
from yali4.gui.GUIException import *
import yali4.gui.context as ctx

# Auto Partition Methods
methodUseAvail, methodEraseAll = range(2)

##
# BootLoader screen.
class Widget(QtGui.QWidget, ScreenWidget):
    title = _('Bootloader Choice')
    desc = _('Configure the system boot..')
    help = _('''
<font size="+2">Boot loader setup</font>

<font size="+1">
<p>
Linux makes use of GRUB boot loader, which
can boot the operating system of your taste
during the start up. 
</p>
<p>
If you have more than one operating system,
you can choose which operating system to 
boot also.
</p>

<p>
Please refer to Pardus Installing and Using 
Guide for more information about GRUB boot 
loader.
</p>
</font>
''')

    def __init__(self, *args):
        QtGui.QWidget.__init__(self,None)
        self.ui = Ui_BootLoaderWidget()
        self.ui.setupUi(self)

        self.ui.installFirstMBR.setChecked(True)

        # initialize all storage devices
        if not yali4.storage.init_devices():
            raise GUIException, _("Can't find a storage device!")

        if len(yali4.storage.devices) > 1:
            self.device_list_state = True
            # fill device list
            for dev in yali4.storage.devices:
                DeviceItem(self.ui.device_list, dev)
            # select the first disk by default
            self.ui.device_list.setCurrentRow(0)
            # be sure first is selected device
            self.device = self.ui.device_list.item(0).getDevice()
        else:
            # don't show device list if we have just one disk
            self.ui.installMBR.hide()
            self.device_list_state = False
            self.ui.device_list.hide()
            self.ui.select_disk_label.hide()

            self.device = yali4.storage.devices[0]

        self.connect(self.ui.buttonGroup, SIGNAL("clicked(int)"),
                     self.slotInstallLoader)
        self.connect(self.ui.device_list, SIGNAL("selectionChanged(QListBoxItem*)"),
                     self.slotDeviceChanged)
        self.connect(self.ui.device_list, SIGNAL("clicked()"),
                     self.slotSelect)

    def shown(self):
        ctx.installData.orderedDiskList = yali4.storage.getOrderedDiskList()
        ctx.debugger.log("Disks BIOS Boot order : %s " % ','.join(ctx.installData.orderedDiskList))

    def backCheck(self):
        if ctx.autoInstall:
            # we need to go partition auto screen, not manual ;)
            ctx.mainScreen.moveInc = 2
        return True

    def slotSelect(self):
        self.ui.installMBR.setChecked(True)

    def slotInstallLoader(self, b):
        if self.ui.installMBR.isChecked():
            self.ui.device_list.setEnabled(True)
            self.ui.device_list.setSelected(0,True)
        else:
            self.ui.device_list.setEnabled(False)
            self.ui.device_list.setSelected(self.ui.device_list.selectedItem(),False)

    def slotDeviceChanged(self, i):
        self.device = i.getDevice()

    def autopartDevice(self):
        dev = ctx.installData.autoPartDev

        # first delete partitions on device
        dev.deleteAllPartitions()
        dev.commit()

        ctx.mainScreen.processEvents()

        p = dev.addPartition(None,
                             parttype.root.parted_type,
                             parttype.root.filesystem,
                             dev.getFreeMB(),
                             parttype.root.parted_flags)
        p = dev.getPartition(p.num) # get partition.Partition

        # create the partition
        dev.commit()
        ctx.mainScreen.processEvents()

        # make partition requests
        ctx.partrequests.append(request.MountRequest(p, parttype.root))
        ctx.partrequests.append(request.FormatRequest(p, parttype.root))
        ctx.partrequests.append(request.LabelRequest(p, parttype.root))
        ctx.partrequests.append(request.SwapFileRequest(p, parttype.root))

    def useAvail(self):
        dev = ctx.installData.autoPartDev
        _part = ctx.installData.autoPartPartition
        part = _part["partition"]

        newPartSize = int(_part["newSize"]/2)
        ctx.debugger.log("UA: newPartSize : %s " % newPartSize)
        ctx.debugger.log("UA: resizing to : %s " % (int(part.getMB()) - newPartSize))
        _np = dev.resizePartition(part._fsname, part.getMB() - newPartSize, part)
        ctx.debugger.log("UA: Resize finished.")
        time.sleep(2)
        np = dev.getPartition(_np.num)

        if np.isLogical():
            ptype = PARTITION_LOGICAL
        else:
            ptype = PARTITION_PRIMARY

        newStart = _np.geom.end
        ctx.debugger.log("UA: newStart : %s " % newStart)
        _newPart = dev.addPartitionFromStart(ptype,
                                             "ext3",
                                             newStart,
                                             newPartSize,
                                             parttype.root.parted_flags)
        dev.commit()
        newPart = dev.getPartition(_newPart.num)
        ctx.mainScreen.processEvents()

        # make partition requests
        ctx.partrequests.append(request.MountRequest(newPart, parttype.root))
        ctx.partrequests.append(request.FormatRequest(newPart, parttype.root))
        ctx.partrequests.append(request.LabelRequest(newPart, parttype.root))
        ctx.partrequests.append(request.SwapFileRequest(newPart, parttype.root))

    def checkSwap(self):
        # check swap partition, if not present use swap file
        rt = request.mountRequestType
        pt = parttype.swap
        swap_part_req = ctx.partrequests.searchPartTypeAndReqType(pt, rt)

        if not swap_part_req:
            # No swap partition defined using swap as file in root
            # partition
            rt = request.mountRequestType
            pt = parttype.root
            root_part_req = ctx.partrequests.searchPartTypeAndReqType(pt, rt)
            ctx.partrequests.append(request.SwapFileRequest(root_part_req.partition(),
                                    root_part_req.partitionType()))

    def execute(self):

        w = WarningWidget(self)
        # We need different warning messages for Auto and Manual Partitioning
        if ctx.installData.autoPartDev:
            # show confirmation dialog
            w.warning.setText(_('''<b>
<p>This action will use your entire disk for Pardus installation and <br>
all your present data on the selected disk will be lost.</p>
</b>
'''))
        self.dialog = WarningDialog(w, self)
        if not self.dialog.exec_():
            # disabled by weaver
            ctx.mainScreen.enableBack()
            return False

        ctx.mainScreen.processEvents()
        info = InformationWindow(_("Writing disk tables ..."))

        # We should do partitioning operations in here.
        if ctx.options.dryRun == True:
            ctx.debugger.log("dryRun activated Yali stopped")
            return

        # Auto Partitioning
        if ctx.installData.autoPartDev:
            ctx.use_autopart = True
            if ctx.installData.autoPartMethod == methodEraseAll:
                info.show()
                ctx.mainScreen.processEvents()
                ctx.partrequests.remove_all()
                self.autopartDevice()
                time.sleep(2)
                info.updateMessage(_("Formatting ..."))
                ctx.mainScreen.processEvents()
                self.checkSwap()
                ctx.partrequests.applyAll()
            elif ctx.installData.autoPartMethod == methodUseAvail:
                info.show()
                info.updateMessage(_("Resizing ..."))
                ctx.mainScreen.processEvents()
                self.useAvail()
                time.sleep(2)
                info.updateMessage(_("Formatting ..."))
                ctx.mainScreen.processEvents()
                self.checkSwap()
                ctx.partrequests.applyAll()

        # Manual Partitioning
        else:
            ctx.debugger.log("Format Operation Started")
            info.show()
            for dev in yali4.storage.devices:
                ctx.mainScreen.processEvents()
                dev.commit()
            # wait for udev to create device nodes
            time.sleep(2)
            info.updateMessage(_("Formatting ..."))
            ctx.mainScreen.processEvents()
            self.checkSwap()
            ctx.partrequests.applyAll()
            ctx.debugger.log("Format Operation Finished")
            ctx.mainScreen.processEvents()

        info.close()

        root_part_req = ctx.partrequests.searchPartTypeAndReqType(parttype.root,
                                                                  request.mountRequestType)

        # install_dev
        if self.ui.noInstall.isChecked():
            ctx.installData.bootLoaderDev = None
        elif self.ui.installPart.isChecked():
            ctx.installData.bootLoaderDev = basename(root_part_req.partition().getPath())
        elif self.ui.installMBR.isChecked():
            ctx.installData.bootLoaderDev = basename(self.device.getPath())
        else:
            if len(yali4.storage.devices) > 1:
                ctx.installData.bootLoaderDev = basename(ctx.installData.orderedDiskList[0])
            else:
                ctx.installData.bootLoaderDev = str(filter(lambda u: not u.isdigit(),
                                                    basename(root_part_req.partition().getPath())))

        _ins_part = root_part_req.partition().getPath()

        ctx.debugger.log("Pardus installed to : %s" % _ins_part)
        ctx.debugger.log("GRUB will be installed to : %s" % ctx.installData.bootLoaderDev)

        return True

class DeviceItem(QtGui.QListWidgetItem):
    def __init__(self, parent, dev):
        text = u"%s - %s (%s)" %(dev.getModel(),
                                dev.getName(),
                                dev.getSizeStr())
        QtGui.QListWidgetItem.__init__(self,text,parent)
        self._dev = dev

    def getDevice(self):
        return self._dev

