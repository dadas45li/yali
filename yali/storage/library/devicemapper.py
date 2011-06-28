#!/usr/bin/python
# -*- coding: utf-8 -*-
import os
import block
import yali.util
import yali.context as ctx
from yali.storage.library import  LibraryError

class DeviceMapperError(LibraryError):
    pass

def name_from_dm_node(dm_node):
    name = block.getNameFromDmNode(dm_node)
    if name is not None:
        return name

    st = os.stat("/dev/%s" % dm_node)
    major = os.major(st.st_rdev)
    minor = os.minor(st.st_rdev)
    name = yali.util.run_batch("dmsetup", ["info", "--columns",
                               "--noheadings", "-o", "name",
                               "-j", str(major), "-m", str(minor)])[1]
    ctx.logger.debug("name_from_dm(%s) returning '%s'" % (dm_node, name.strip()))
    return name.strip()

def dm_node_from_name(name):
    dm_node = block.getDmNodeFromName(name)
    if dm_node is not None:
        return dm_node

    devnum = yali.util.run_batch("dmsetup", ["info", "--columns",
                        "--noheadings", "-o", "devno",name])[1]
    (major, sep, minor) = devnum.strip().partition(":")
    if not sep:
        raise DeviceMapperError("dm device does not exist")

    dm_node = "dm-%d" % int(minor)
    ctx.logger.debug("dm_node_from_name(%s) returning '%s'" % (name, dm_node))
    return dm_node
