# -*- coding: utf-8 -*-
#
# Copyright (C) 2005-2008, TUBITAK/UEKAE
#
# This program is free software; you can redistribute it and/or modify it under
# the terms of the GNU General Public License as published by the Free
# Software Foundation; either version 2 of the License, or (at your option)
# any later version.
#
# Please read the COPYING file.
#
# User management module for YALI.

import random
import shutil
import glob
import os

from string import ascii_letters, digits
from yali4.constants import consts

# a set of User instances waiting...
# we'll add these users at the last step of the installation.
pending_users = []

def reset_pending_users():
    global pending_users
    pending_users = []

def iter_head_images():
    left, right, images = [], [], []

    g = glob.glob(consts.user_faces_dir + "/*.png")

    for e in g: left.append(e)

    for n in range(0, 5):
        right = []
        for i in range(0, len(g)/2 + 1):
            right.append(left.pop(random.randrange(len(g) - i)))
        left.reverse()
        left = right + left

    for p in left:
        images.append(p)

    while True:
        for image in images:
            yield image

head_images = iter_head_images()

class User:
    """ User class for adding or editing new users 
        to the installed system """
    def __init__(self, username = ''):
        self.username = username
        self.groups = []
        self.realname = ''
        self.passwd = ''
        self.uid = -1
        self.icon = head_images.next()
        self.noPass = False

        # KDE AutoLogin Defaults
        self.autoLoginDefaults = {"AutoLoginAgain":"false",
                                  "AutoLoginDelay":"0",
                                  "AutoLoginLocked":"false"}

        self.shadow_path = os.path.join(consts.target_dir, 'etc/shadow')
        self.passwd_path = os.path.join(consts.target_dir, 'etc/passwd')
        self.group_path  = os.path.join(consts.target_dir, 'etc/group')
        self.fake_passwd_path = '/etc/passwd'

    def exists(self, byUid = False):
        """ Check if the given user exists on system """
        var = self.username
        col = 0
        if byUid:
            var = self.uid
            col = 2
        if filter(lambda x: x == var, \
              map(lambda x: x[col], [line.split(':') for line in open(self.fake_passwd_path, 'r').readlines()])):
            return True
        return False

    def usernameIsValid(self):
        """ Check if the given username is valid not """
        valid = ascii_letters + '_' + digits
        name = self.username
        if len(name) == 0 or filter(lambda x: not x in valid, name) or not name[0] in ascii_letters:
            return False
        return True

    def realnameIsValid(self):
        """ Check if the given Real Name is valid or not """
        not_allowed_chars = '\n' + ':'
        return '' == filter(lambda r: [x for x in not_allowed_chars if x == r], self.realname)

    # KDE AutoLogin
    def setAutoLogin(self,state=True):
        """ Sets the KDE's Autologin feature's state """
        confFile = os.path.join(consts.target_dir, 'etc/X11/kdm/kdmrc')

        if not os.path.exists(confFile):
            import yali4.gui.context as ctx
            ctx.debugger.log("SAL: Failed, kdmrc not found; possibly KDE is not installed !")
            return False

        import ConfigParser
        section = 'X-:0-Core'
        kdmrc = ConfigParser.ConfigParser()
        kdmrc.optionxform = str
        kdmrc.readfp(open(confFile))
        for opt in self.autoLoginDefaults.keys():
            kdmrc.set(section,opt,self.autoLoginDefaults[opt])
        # Set State
        kdmrc.set(section,'AutoLoginEnable',str(state).lower())
        # Set User
        kdmrc.set(section,'AutoLoginUser',self.username)
        kdmrc.write(open(confFile,'w'))

if __name__ == '__main__':
    pass
