#!/usr/bin/python

import os
import gettext

__trans = gettext.translation('yali', fallback=True)
_ = __trans.ugettext

import yali.util
import yali.context as ctx
from yali.storage import StorageError
from yali.storage.library.devicemapper import DeviceMapperError, dm_node_from_name
from yali.storage.udev import udev_device_get_minor, udev_device_get_major, udev_get_device
device_formats = {}

def getFormat(type, *args, **kwargs):
    """ Return a Format instance based on fmt_type and args.

        Given a device format type and a set of constructor arguments,
        return a Format instance.

        Return None if no suitable format class is found.

        Arguments:

            type -- the name of the format type (eg: 'ext3', 'swap')

        Keyword Arguments:

            The keyword arguments may vary according to the format type,
            but here is the common set:

            device -- path to the device on which the format resides
            uuid -- the UUID of the (preexisting) formatted device
            exists -- whether or not the format exists on the device
    """
    device_format = get_device_format(type)
    format = None
    if device_format:
        format = device_format(*args, **kwargs)
    try:
        className = format.__class__.__name__
    except AttributeError:
        className = None

    ctx.logger.debug("getFormat('%s') returning %s instance" % (type, className))

    return format

def register_device_format(format):
    if not issubclass(format, Format):
        raise ValueError("arg1 must be a subclass of Format")

    device_formats[format._type] = format
    ctx.logger.debug("registered device format class %s as %s" % (format.__name__, format._type))

def collect_device_formats():
    """ Pick up all device format classes from this directory.

        Note: Modules must call register_device_format(FormatClass) in
              order for the format class to be picked up.
    """
    dir = os.path.dirname(__file__)
    for moduleFile in os.listdir(dir):
        if moduleFile.endswith(".py") and moduleFile != __file__:
            module_name = moduleFile[:-3]
            try:
                globals()[module_name] = __import__(module_name, globals(), locals(), [], -1)
            except ImportError, e:
                ctx.logger.debug("import of device format module '%s' failed" % module_name)

def get_device_format(formatType):
    """ Return an appropriate format class based on fmt_type. """
    if not device_formats:
        collect_device_formats()

    format = device_formats.get(formatType)
    if not format:
        for device_format in device_formats.values():
            if formatType in device_format._udevTypes:
                format = device_format
                break

    # default to no formatting, AKA "Unknown"
    if not format:
        format = Format

    return format

default_fstypes = ("ext4", "ext3", "ext2")
def get_default_filesystem_type(boot=None):
    for fstype in default_fstypes:
        try:
            supported = get_device_format(fstype).supported
        except AttributeError:
            supported = None

        if supported:
            return fstype

    raise FormatError("None of %s is supported by your kernel" %
            ",".join(default_fstypes))

class FormatError(yali.Error):
    pass

class Format(object):
    """ Generic device format. """
    _type = None
    _name = "Unknown"
    _udevTypes = []
    partedFlag = None
    partedSystem = None
    _formattable = False                # can be formatted
    _supported = False                  # is supported
    _linuxNative = False                # for clearpart
    _resizable = False                  # can be resized
    _bootable = False                   # can be used as boot
    _migratable = False                 # can be migrated
    _maxSize = 0                        # maximum size in MB
    _minSize = 0                        # minimum size in MB
    _dump = False
    _check = False
    _hidden = False                     # hide devices with this formatting?

    def __init__(self, *args, **kwargs):
        """ Create a Format instance.

            Keyword Arguments:

                device -- path to the underlying device
                uuid -- this format's UUID
                exists -- indicates whether this is an existing format

        """
        self.device = kwargs.get("device")
        self.uuid = kwargs.get("uuid")
        self.exists = kwargs.get("exists")
        self.options = kwargs.get("options")
        self._majorminor = None
        self._migrate = False

    def __repr__(self):
        s = ("%(classname)s instance (%(id)s) --\n"
             "  type = %(type)s  name = %(name)s  status = %(status)s\n"
             "  device = %(device)s  uuid = %(uuid)s  exists = %(exists)s\n"
             "  options = %(options)s  supported = %(supported)s"
             "  formattable = %(format)s  resizable = %(resize)s mountable = %(mount)s\n"
             "  maxSize = %(maxSize)s  minSize = %(minSize)s\n" %
             {"classname": self.__class__.__name__, "id": "%#x" % id(self),
              "type": self.type, "name": self.name, "status": self.status,
              "device": self.device, "uuid": self.uuid, "exists": self.exists,
              "options": self.options, "supported": self.supported,
              "format": self.formattable, "resize": self.resizable,
              "mount": self.mountable,
              "maxSize": self.maxSize, "minSize": self.minSize})
        return s

    @property
    def _existence_str(self):
        exist = "existing"
        if not self.exists:
            exist = "non-existent"
        return exist

    @property
    def desc(self):
        return str(self.type)

    def __str__(self):
        return "%s %s" % (self._existence_str, self.desc)

    def _setOptions(self, options):
        self._options = options

    def _getOptions(self):
        return self._options

    options = property(_getOptions, _setOptions)

    def _setDevice(self, devspec):
        if devspec and not devspec.startswith("/"):
            raise ValueError("device must be a fully qualified path")
        self._device = devspec

    def _getDevice(self):
        return self._device

    device = property(lambda f: f._getDevice(),
                      lambda f,d: f._setDevice(d),
                      doc="Full path the device this format occupies")

    @property
    def name(self):
        if self._name:
            name = self._name
        else:
            name = self.type
        return name

    @property
    def type(self):
        return self._type

    def probe(self):
        pass

    def notifyKernel(self):
        if not self.device:
            return

        if self.device.startswith("/dev/mapper/"):
            try:
                name = dm_node_from_name(os.path.basename(self.device))
            except Exception, e:
                ctx.logger.warning("failed to get dm node for %s" % self.device)
                return
        else:
            name = self.device

        path = yali.util.get_sysfs_path_by_name(name)
        try:
            yali.util.notify_kernel(path, action="change")
        except Exception, e:
            ctx.logger.warning("failed to notify kernel of change: %s" % e)

    def cacheMajorminor(self):
        """ Cache the value of self.majorminor.

            Once a device node of this format's device disappears (for instance
            after a teardown), it is no longer possible to figure out the value
            of self.majorminor pseudo-unique string. Call this method before
            that happens for caching this.
        """
        self._majorminor = None
        try:
            self.majorminor # this does the caching
        except FormatError:
            # entirely possible there's no majorminor, for instance an
            # VolumeGroup has got no device node and no sysfs path.  In this
            # case obviously, calling majorminor of this object later raises an
            # exception.
            pass
        return self._majorminor

    def create(self, *args, **kwargs):
        # allow late specification of device path
        device = kwargs.get("device")
        if device:
            self.device = device

        if not os.path.exists(self.device):
            raise FormatError("invalid device specification", self.device)

    def destroy(self, *args, **kwargs):
        try:
            rc = yali.util.run_batch("wipefs", ["-a", self.device])
        except Exception as e:
            err = str(e)
        else:
            err = ""
            if rc:
                err = str(rc)

        if err:
            msg = "error wiping old signatures from %s: %s" % (self.device, err)
            raise FormatError(msg)

        self.exists = False

    def setup(self, *args, **kwargs):
        if not self.exists:
            raise FormatError("format has not been created")

        if self.status:
            return

        # allow late specification of device path
        device = kwargs.get("device")
        if device:
            self.device = device

        if not self.device or not os.path.exists(self.device):
            raise FormatError("invalid device specification")

    def teardown(self, *args, **kwargs):
        ctx.logger.debug("Format teardown method call")

    @property
    def status(self):
        return (self.exists and
                self.__class__ is not Format and
                isinstance(self.device, str) and
                self.device and 
                os.path.exists(self.device))

    @property
    def formattable(self):
        """ Can we create formats of this type? """
        return self._formattable

    @property
    def supported(self):
        """ Is this format a supported type? """
        return self._supported

    @property
    def resizable(self):
        """ Can formats of this type be resized? """
        return self._resizable and self.exists

    @property
    def bootable(self):
        """ Is this format type suitable for a boot partition? """
        return self._bootable

    @property
    def migratable(self):
        """ Can formats of this type be migrated? """
        return self._migratable

    @property
    def migrate(self):
        return self._migrate

    @property
    def linuxNative(self):
        """ Is this format type native to linux? """
        return self._linuxNative

    @property
    def mountable(self):
        """ Is this something we can mount? """
        return False

    @property
    def dump(self):
        """ Whether or not this format will be dumped by dump(8). """
        return self._dump

    @property
    def check(self):
        """ Whether or not this format is checked on boot. """
        return self._check

    @property
    def maxSize(self):
        """ Maximum size (in MB) for this format type. """
        return self._maxSize

    @property
    def minSize(self):
        """ Minimum size (in MB) for this format type. """
        return self._minSize

    @property
    def hidden(self):
        """ Whether devices with this formatting should be hidden in UIs. """
        return self._hidden

    def majorminor(self):
        """A string suitable for using as a pseudo-unique ID in kickstart."""
        if not self._majorminor:
            # If this is a device-mapper device, we have to get the DM node and
            # build the sysfs path from that.
            try:
                device = dm_node_from_name(os.path.basename(self.device))
            except DeviceMapperError:
                device = self.device

            try:
                sysfs_path = yali.util.get_sysfs_path_by_name(device)
            except RuntimeError:
                raise FormatError("DeviceFormat.majorminor: "
                                   "can not get majorminor for '%s'" % device)
            dev = udev_get_device(sysfs_path[4:])

            self._majorminor = "%03d%03d" %\
                (udev_device_get_major(dev), udev_device_get_minor(dev))
        return self._majorminor

collect_device_formats()
