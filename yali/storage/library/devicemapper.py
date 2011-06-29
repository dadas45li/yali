#!/usr/bin/python
# -*- coding: utf-8 -*-
import os
import block
import yali.context as ctx
from yali.storage.library import  LibraryError

class DeviceMapperError(LibraryError):
    pass

def name_from_dm_node(dm_node):
    # first, try sysfs
    name_file = "/sys/class/block/%s/dm/name" % dm_node
    try:
        name = open(name_file).read().strip()
    except IOError:
        # next, try pyblock
        name = block.getNameFromDmNode(dm_node)

    return name

def dm_node_from_name(name):
    named_path = "/dev/mapper/%s" % map_name
    try:
        # /dev/mapper/ nodes are usually symlinks to /dev/dm-N
        node = os.path.basename(os.readlink(named_path))
    except OSError:
        try:
            # dm devices' names are based on the block device minor
            st = os.stat(named_path)
            minor = os.minor(st.st_rdev)
            node = "dm-%d" % minor
        except OSError:
            # try pyblock
            node = block.getDmNodeFromName(map_name)

    if not node:
        raise DeviceMapperError("dm_node_from_name(%s) has failed." % node)

    return node
