# -*- coding: utf-8 -*-
#
# Copyright (C) 2005-2010 TUBITAK/UEKAE
#
# This program is free software; you can redistribute it and/or modify it under
# the terms of the GNU General Public License as published by the Free
# Software Foundation; either version 2 of the License, or (at your option)
# any later version.
#
# Please read the COPYING file.
#
import sys
import math
import gettext

__trans = gettext.translation('yali', fallback=True)
_ = __trans.ugettext

from PyQt4 import QtGui
from PyQt4.QtCore import *

import yali.context as ctx
from yali.gui.ScreenWidget import ScreenWidget, GUIError
from yali.gui.Ui.autopartwidget import Ui_AutoPartWidget
from yali.gui.Ui.partitionshrinkwidget import Ui_PartShrinkWidget
from yali.storage.partitioning import CLEARPART_TYPE_ALL, CLEARPART_TYPE_LINUX, CLEARPART_TYPE_NONE, doAutoPartition, defaultPartitioning
from yali.storage.operations import OperationResizeDevice, OperationResizeFormat


class ShrinkWidget(QtGui.QWidget):
    def __init__(self, parent):
        QtGui.QWidget.__init__(self, ctx.mainScreen)
        self.parent = parent
        self.ui = Ui_PartShrinkWidget()
        self.ui.setupUi(self)
        self.setStyleSheet("""
                     QSlider::groove:horizontal {
                         border: 1px solid #999999;
                         height: 12px;
                         background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #B1B1B1, stop:1 #c4c4c4);
                         margin: 2px 0;
                     }

                     QSlider::handle:horizontal {
                         background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #b4b4b4, stop:1 #8f8f8f);
                         border: 1px solid #5c5c5c;
                         width: 18px;
                         margin: 0 0;
                         border-radius: 2px;
                     }

                    QFrame#mainFrame {
                        background-image: url(:/gui/pics/transBlack.png);
                        border: 1px solid #BBB;
                        border-radius:8px;
                    }

                    QWidget#Ui_PartShrinkWidget {
                        background-image: url(:/gui/pics/trans.png);
                    }
        """)
        self.operations = []
        QObject.connect(self.ui.partitions, SIGNAL("currentRowChanged(int)"), self.updateSpin)
        self.connect(self.ui.shrinkButton, SIGNAL("clicked()"), self.slotShrink)
        self.connect(self.ui.cancelButton, SIGNAL("clicked()"), self.hide)
        self.fillPartitions()

    def check(self):
        return self.ui.partitions.count() == 0

    def fillPartitions(self):
        biggest = -1
        i = -1
        for partition in self.parent.storage.partitions:
            if not partition.exists:
                continue

            if partition.resizable and partition.format.resizable:
                entry = PartitionItem(self.ui.partitions, partition)

                i += 1
                if biggest == -1:
                    biggest = i
                else:
                    current = self.ui.partitions.item(biggest).partition
                    if partition.format.targetSize > current.format.targetSize:
                        biggest = i

        if biggest > -1:
            self.ui.partitions.setCurrentRow(biggest)

    def updateSpin(self, index):
        request = self.ui.partitions.item(index).partition
        try:
            reqlower = long(math.ceil(request.format.minSize))
        except FilesystemError, msg:
            raise GUIError, msg
        else:
            requpper = long(math.floor(request.format.currentSize))

        self.ui.shrinkMB.setMinimum(max(1, reqlower))
        self.ui.shrinkMB.setMaximum(requpper)
        self.ui.shrinkMB.setValue(reqlower)
        self.ui.shrinkMBSlider.setMinimum(max(1, reqlower))
        self.ui.shrinkMBSlider.setMaximum(requpper)
        self.ui.shrinkMBSlider.setValue(reqlower)

    def slotShrink(self):
        self.hide()
        runResize = True
        while runResize:
           index = self.ui.partitions.currentRow()
           request = self.ui.partitions.item(index).partition
           newsize = self.ui.shrinkMB.value()
           try:
               self.operations.append(OperationResizeFormat(request, newsize))
           except ValueError as e:
               self.parent.intf.messageWindow(_("Resize FileSystem Error"),
                                              _("%(device)s: %(msg)s") %
                                              {'device': request.format.device, 'msg': e.message},
                                              type="warning", customIcon="error")
               continue

           try:
               self.operations.append(OperationResizeDevice(request, newsize))
           except ValueError as e:
               self.parent.intf.messageWindow(_("Resize Device Error"),
                                              _("%(name)s: %(msg)s") %
                                               {'name': request.name, 'msg': e.message},
                                               type="warning", customIcon="error")
               continue

           runResize = False

        self.hide()

class DrivesListItem(QtGui.QListWidgetItem):
    def __init__(self, parent, widget):
        QtGui.QListWidgetItem.__init__(self, parent)
        self.widget = widget
        self.setSizeHint(QSize(300, 64))

class DriveItem(QtGui.QWidget):
    def __init__(self, parent, drive):
        QtGui.QWidget.__init__(self, parent)
        self.layout = QtGui.QHBoxLayout(self)
        self.checkBox = QtGui.QCheckBox(self)
        self.layout.addWidget(self.checkBox)
        self.labelDrive = QtGui.QLabel(self)
        self.labelDrive.setText("%s on %s - (%s) MB" % (drive.model, drive.name, str(int(drive.size))))
        self.layout.addWidget(self.labelDrive)
        spacerItem = QtGui.QSpacerItem(40, 20, QtGui.QSizePolicy.Expanding, QtGui.QSizePolicy.Minimum)
        self.layout.addItem(spacerItem)
        self.connect(self.checkBox, SIGNAL("stateChanged(int)"), self.stateChanged)
        self.drive = drive
        self.parent = parent

    def stateChanged(self, state):
        if state == Qt.Checked:
            ctx.mainScreen.enableNext()
        else:
            selectedDisks = []
            for index in range(self.parent.count()):
                if self.checkBox.checkState() == Qt.Checked:
                    selectedDisks.append(self.ui.drives.item(index).drive.name)

            if len(selectedDisks):
                ctx.mainScreen.enableNext()
            else:
                ctx.mainScreen.disableNext()



class PartitionItem(QtGui.QListWidgetItem):

    def __init__(self, parent, partition):
        text = u"%s (%s, %d MB)" % (partition.name, partition.format.name, math.floor(partition.format.size))
        QtGui.QListWidgetItem.__init__(self, text, parent)
        self.partition = partition

class Widget(QtGui.QWidget, ScreenWidget):
    title = _("Select Partitioning Method")
    icon = "iconPartition"
    help = _('''
<font size="+2">Partitioning Method</font>
<font size="+1">
<p>
You can install Pardus if you have an unpartitioned-unused disk space 
of 4GBs (10 GBs recommended) or an unused-unpartitioned disk. 
The disk area or partition selected for installation will automatically 
be formatted. Therefore, it is advised to backup your data to avoid future problems.
</p>
<p>Auto-partitioning will automatically format the select disk part/partition 
and install Pardus. If you like, you can do the partitioning manually or make 
Pardus create a new partition for installation.</p>
</font>
''')

    def __init__(self, *args):
        QtGui.QWidget.__init__(self,None)
        self.ui = Ui_AutoPartWidget()
        self.ui.setupUi(self)
        self.storage = ctx.storage
        self.intf = ctx.yali
        self.shrinkOperations = None
        self.clearPartDisks = None

        self.connect(self.ui.useAllSpace, SIGNAL("clicked()"), self.typeChanged)
        self.connect(self.ui.replaceExistingLinux, SIGNAL("clicked()"), self.typeChanged)
        self.connect(self.ui.shrinkCurrent, SIGNAL("clicked()"), self.typeChanged)
        self.connect(self.ui.useFreeSpace, SIGNAL("clicked()"), self.typeChanged)
        self.connect(self.ui.createCustom, SIGNAL("clicked()"), self.typeChanged)
        #self.connect(self.ui.drives,   SIGNAL("currentItemChanged(QListWidgetItem *, QListWidgetItem * )"),self.slotDeviceChanged)
        #self.ui.drives.hide()
        #self.ui.drivesLabel.hide()

    def typeChanged(self):
        if self.sender() != self.ui.createCustom:
            self.ui.review.setEnabled(True)
            if self.sender() == self.ui.shrinkCurrent:
                shrinkwidget = ShrinkWidget(self)
                if shrinkwidget.check():
                    self.intf.messageWindow(_("Error"),
                                            _("No partitions are available to resize.Only physical\n"
                                              "partitions with specific filesystems can be resized."),
                                            type="warning", customIcon="error")
                else:
                    shrinkwidget.show()
                    if shrinkwidget.operations:
                        self.shrinkOperations = shrinkwidget.operations
                    else:
                        return False
        else:
            self.ui.review.setEnabled(False)

        ctx.mainScreen.enableNext()

    def setPartitioningType(self):
        if self.storage.clearPartType is None or self.storage.clearPartType == CLEARPART_TYPE_LINUX:
            self.ui.replaceExistingLinux.toggle()
        elif self.storage.clearPartType == CLEARPART_TYPE_NONE:
            self.ui.useFreeSpace.toggle()
        elif self.storage.clearPartType == CLEARPART_TYPE_ALL:
            self.ui.useAllSpace.toggle()

    def fillDrives(self):
        disks = filter(lambda d: not d.format.hidden, self.storage.disks)
        self.ui.drives.clear()

        for disk in disks:
            if disk.size >= ctx.consts.min_root_size:
                drive = DriveItem(self.ui.drives, disk)
                listItem = DrivesListItem(self.ui.drives, drive)
                self.ui.drives.setItemWidget(listItem, drive)

        # select the first disk by default
        self.ui.drives.setCurrentRow(0)

    def shown(self):
        self.storage.reset()
        if self.storage.checkNoDisks(self.intf):
            raise GUIError, _("No storage device found.")
        else:
            self.fillDrives()
            self.setPartitioningType()

    def checkClearPartDisks(self):
        selectedDisks = []
        for index in range(self.ui.drives.count()):
            if self.ui.drives.item(index).widget.checkBox.checkState() == Qt.Checked:
                selectedDisks.append(self.ui.drives.item(index).widget.drive.name)

        if len(selectedDisks) == 0:
            self.intf.messageWindow(_("Error"),
                                    _("You must select at least one "
                                      "drive to be used for installation."), customIcon="error")
            return False
        else:
            selectedDisks.sort(self.storage.compareDisks)
            self.storage.clearPartDisks = selectedDisks
            return True

    def execute(self):
        rc = self.nextCheck()
        if rc is None:
            #FIXME:Unknown bug
            #sys.exit(0)
            return True
        else:
            return rc

    def nextCheck(self):
        if self.checkClearPartDisks():
            increment = 0
            if self.ui.createCustom.isChecked():
                increment = 1
                self.storage.clearPartType = CLEARPART_TYPE_NONE
            else:
                if self.ui.shrinkCurrent.isChecked():
                    if self.shrinkOperations:
                        for operation in self.shrinkOperations:
                            self.storage.addOperation(operation)
                        self.storage.clearPartType = CLEARPART_TYPE_NONE
                elif self.ui.useAllSpace.isChecked():
                    self.storage.clearPartType = CLEARPART_TYPE_ALL
                elif self.ui.replaceExistingLinux.isChecked():
                    self.storage.clearPartType = CLEARPART_TYPE_LINUX
                elif self.ui.useFreeSpace.isChecked():
                    self.storage.clearPartType = CLEARPART_TYPE_NONE

                self.storage.doAutoPart = True
                self.storage.autoPartitionRequests = defaultPartitioning(self.storage, quiet=0)
                if not self.storage.clearPartDisks:
                    return False

                if self.ui.review.isChecked():
                    increment = 1
                else:
                    increment = 2
                return doAutoPartition(self.storage)

            ctx.mainScreen.stepIncrement = increment
            return True

        return False
