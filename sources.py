#!/usr/bin/env python
# sources.py 
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

from sugar.datastore import datastore
import sys, os
import gtk
import shutil
import sqlite3

from dbphoto import *

#pick up activity globals
from xophotoactivity import *


import logging
_logger = logging.getLogger('xophoto')
_logger.setLevel(logging.DEBUG)
console_handler = logging.StreamHandler()
console_formatter = logging.Formatter('%(name)s %(levelname)s %(funcName)s: %(lineno)d||| %(message)s')
console_handler.setFormatter(console_formatter)
#_logger.addHandler(console_handler)

class Datastore_SQLite():
    """class for interfacing between the Journal and an SQLite database"""
    def __init__(self,database_access_object):
        """receives an open dbaccess object (defined in dbphoto) """
        #self.db = dbaccess(fn)
        self.db = database_access_object
    
    def ok(self):
        if self.db.is_open():return True
        return False
    
    def scan_images(self):
        """
        returns a list of journal object ids that have mime_type equal to one
        of the entries in mimetype table of xophoto database. 
        """
        rtn = []
        mime_list = self.db.get_mime_list()
        (results,count) = datastore.find({})
        for f in results:
            dict = f.get_metadata().get_dictionary()
            if dict["mime_type"].find('jpg')>-1:
                _logger.debug('found jpg: %s in mime_list %r'%(dict["mime_type"],mime_list,))
            if dict["mime_type"] in mime_list:
                #record the id, file size, file date, in_ds
                self.db.create_picture_record(f.object_id, f.get_file_path())
                rtn.append(f.object_id)
            f.destroy()
        self.db.commit()
        _logger.debug('%s found in journal'%count)
        return rtn


    def get_filename_from_jobject_id(self, id):
        try:
            ds_obj = datastore.get(id)
        except Exception,e:
            _logger.debug('get filename from id error: %s'%e)
            return None
        if ds_obj:
            fn = ds_obj.get_file_path()
            ds_obj.destroy()
            return(fn)
        return None
    
class filetree():
    def __init__(self,fn):
        self.db = dbaccess(fn)
        self.dialog = None

    def get_path(self):
        _logger.debug('dialog to get user path for importing into journal')
        if not self.dialog:
            self.dialog = gtk.FileChooserDialog("Select Folder..",
                                       None,
                                       gtk.FILE_CHOOSER_ACTION_SELECT_FOLDER,
                                       (gtk.STOCK_CANCEL, gtk.RESPONSE_CANCEL,
                                        gtk.STOCK_OPEN, gtk.RESPONSE_OK))
        else:
            self.dialog.show_all()
        self.dialog.set_default_response(gtk.RESPONSE_OK)
        #self.dialog.set_current_folder(os.path.dirname(self.last_filename))       
        
        filter = gtk.FileFilter()
        filter.set_name("All files")
        filter.add_pattern("*")
        self.dialog.add_filter(filter)
        
        filter = gtk.FileFilter()
        filter.set_name("Pictures")
        filter.add_pattern("*.png,*.jpg,*jpeg,*.gif")
        self.dialog.add_filter(filter)
               
        response = self.dialog.run()
        if response == gtk.RESPONSE_OK:
            _logger.debug('%s selected'%self.dialog.get_filename() )
            fname = self.dialog.get_filename()
            self.last_filename = fname
        elif response == gtk.RESPONSE_CANCEL:
            fname = None
            _logger.debug( 'File chooseer closed, no files selected')
        self.dialog.hide_all()
        self.dialog.destroy()
        self.dialog = None
        return fname

    def copy_tree_to_ds(self,path):
        added = 0
        if os.path.isdir(path):
            files = os.listdir(path)
            for f in files:
                mtype = ''
                chunks = f.split('.')
                if len(chunks)>1:
                    ext = chunks[-1]
                    if ext == 'jpg' or ext == 'jpeg':
                        mtype = 'image/jpg'
                    elif ext == 'gif':
                        mtype = 'image/gif'
                    elif ext == 'png':
                        mtype = 'image/png'
                if mtype == '': continue        
                fullname = os.path.join(path,f)
                info = os.stat(fullname)
                size = info.st_size
                if self.db.check_in_ds(fullname,size): continue
                ds = datastore.create()
                ds.metadata['filename'] = fullname
                ds.metadata['title'] = f
                ds.metadata['mime_type'] = mtype
                dest = os.path.join(os.environ['SUGAR_ACTIVITY_ROOT'],'instance',f)
                shutil.copyfile(fullname,dest)
                ds.set_file_path(dest)
                datastore.write(ds,transfer_ownership=True)
                self.db.update_picture(ds.object_id,fullname)
                ds.destroy()
                added += 1
            return added
        return 0
        
    def fill_ds(self):
        path = self.get_path()
        if path:
            return self.copy_tree_to_ds(path)
        
                    
                
if __name__ == '__main__':
    db = DbAccess('xophoto.sqlite')
    if db.is_open():
        ds_sql = Datastore_SQLite(db)
        imagelist = ds_sql.scan_images()
        exit()
        for i in imagelist:
            print('\n%s'%ds.get_filename_from_jobject_id(i))
        ft = filetree('xophoto.sqlite')
        #new = ft.fill_ds()
        print('%s datastore records added'%new)
    else:
        print('xophoto sqlite database failed to open')
