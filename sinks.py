#!/usr/bin/env python
# sinks.py 
#
# Copyright (C) 2010  George Hunt
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License along
# with this program; if not, write to the Free Software Foundation, Inc.,
# 51 Franklin St, Fifth Floor, Boston, MA  02110-1301  USA
#
from gettext import gettext as _

import pygame
from pygame.locals import *

from sugar.datastore import datastore
import sys, os
import gtk
import shutil

#application imports
from dbphoto import *
from sources import *

#pick up activity globals
from xophotoactivity import *

class ExportAlbum():
    
    def __init__(self,rows,db,path):
        """inputs =rows is an array or records from table xophoto.sqlite.groups
                  =db is a class object which has functions for reading database
                  =sources is a class object which has functions for getting data
                  =path is writeable path indicating location for new exported images
        """
        self.rows = rows
        self.db = db
        self.sources = Datastore_SQLite(db)
        self.path = path
        
    def do_export(self):
        if not os.path.isdir(self.path):
            try:
                os.makedirs(self.path)
            except:
                raise PhotoException('cannot create directory(s) at %s'%self.target)
        for row in self.rows:
            jobject_id = row['jobject_id']
            fn = self.sources.get_filename_from_jobject_id(jobject_id)
            mime_type = self.db.get_mime_type(jobject_id)
            lookup = {'image/png':'.png','image/jpg':'.jpg','image/gif':'.gif','image/tif':'.tif'}
            base = os.path.basename(fn).split('.')
            #don't override a suffix that exists
            if len(base) == 1:
                base = base[0] + lookup.get(mime_type,'')
            else:
                base = os.path.basename(fn)
            _logger.debug('exporting %s to %s'%(fn,os.path.join(self.path,base),))
            shutil.copy(fn,os.path.join(self.path,base))

                        