#!/usr/bin/python
import baseclass
import unittest
import time
from mock import acceptance

class RaidTestCase(baseclass.LibraryTestCase):

    def testMDRaid(self):
        _LOOP_DEV0 = self._loopMap[self._LOOP_DEVICES[0]]
        _LOOP_DEV1 = self._loopMap[self._LOOP_DEVICES[1]]

        import storage.library.raid as raid

    @acceptance
    def testRaid(self):
        ##
        ## getRaidLevels
        ##
        # pass
        self.assertEqual(raid.getRaidLevels(), raid.getRaidLevels())

        ##
        ## get_raid_min_members
        ##
        # pass
        self.assertEqual(raid.get_raid_min_members(raid.RAID0), 2)
        self.assertEqual(raid.get_raid_min_members(raid.RAID1), 2)
        self.assertEqual(raid.get_raid_min_members(raid.RAID5), 3)
        self.assertEqual(raid.get_raid_min_members(raid.RAID6), 4)
        self.assertEqual(raid.get_raid_min_members(raid.RAID10), 2)

        # fail
        # unsupported raid
        self.assertRaises(ValueError, raid.get_raid_min_members, 8)

        ##
        ## get_raid_max_spares
        ##
        # pass
        self.assertEqual(raid.get_raid_max_spares(raid.RAID0, 5), 0)
        self.assertEqual(raid.get_raid_max_spares(raid.RAID1, 5), 3)
        self.assertEqual(raid.get_raid_max_spares(raid.RAID5, 5), 2)
        self.assertEqual(raid.get_raid_max_spares(raid.RAID6, 5), 1)
        self.assertEqual(raid.get_raid_max_spares(raid.RAID10, 5), 3)

        # fail
        # unsupported raid
        self.assertRaises(ValueError, raid.get_raid_max_spares, 8, 5)

        ##
        ## mdcreate
        ##
        # pass
        self.assertEqual(raid.mdcreate("/dev/md0", 1, [_LOOP_DEV0, _LOOP_DEV1]), None)
        # wait for raid to settle
        time.sleep(2)

        # fail
        self.assertRaises(raid.RaidError, raid.mdcreate, "/dev/md1", 1, ["/not/existing/dev0", "/not/existing/dev1"])

        ##
        ## mddeactivate
        ##
        # pass
        self.assertEqual(raid.mddeactivate("/dev/md0"), None)

        # fail
        self.assertRaises(raid.RaidError, raid.mddeactivate, "/not/existing/md")

        ##
        ## mdadd
        ##
        # pass
        # TODO

        # fail
        self.assertRaises(raid.RaidError, raid.mdadd, "/not/existing/device")

        ##
        ## mdactivate
        ##
        # pass
        self.assertEqual(raid.mdactivate("/dev/md0", [_LOOP_DEV0, _LOOP_DEV1], super_minor=0), None)
        # wait for raid to settle
        time.sleep(2)

        # fail
        self.assertRaises(raid.RaidError, raid.mdactivate, "/not/existing/md", super_minor=1)
        # requires super_minor or uuid
        self.assertRaises(ValueError, raid.mdactivate, "/dev/md1")

        ##
        ## mddestroy
        ##
        # pass
        # deactivate first
        self.assertEqual(raid.mddeactivate("/dev/md0"), None)

        self.assertEqual(raid.mddestroy(_LOOP_DEV0), None)
        self.assertEqual(raid.mddestroy(_LOOP_DEV1), None)

        # fail
        # not a component
        self.assertRaises(raid.RaidError, raid.mddestroy, "/dev/md0")
        self.assertRaises(raid.RaidError, raid.mddestroy, "/not/existing/device")


def suite():
    return unittest.TestLoader().loadTestsFromTestCase(RaidTestCase)


if __name__ == "__main__":
    unittest.main()
