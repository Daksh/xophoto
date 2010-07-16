#!/usr/bin/env python
# sources.py 
#
# Copyright (C) 2010  George Hunt
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Frjur option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License along
# with this program; if not, write to the Free Software Foundation, Inc.,
# 51 Franklin St, Fifth Floor, Boston, MA  02110-1301  USA
"""
Notes to myself:
the problem I'm trying to address is latency during start up.
If there is database corruption, we need to start over with empty databases
(similar to the first download of the application)
What's the best I can do?
If there are very many images in the Journal, the best I can do is a directed find
of all the appropriate mime_types in Journal, then bring up the UI, and paint the
thumbnail as each is generated.

"""
from gettext import gettext as _

from sugar.datastore import datastore
import sys, os
import gtk
import shutil
import sqlite3
import time

from dbphoto import *
import display
#pick up activity globals
from xophotoactivity import *


import logging
_logger = logging.getLogger('xophoto')
_logger.setLevel(logging.DEBUG)
console_handler = logging.StreamHandler()
console_formatter = logging.Formatter('%(name)s %(levelname)s %(funcName)s: %(lineno)d||| %(message)s')
#console_handler.setFormatter(console_formatter)
#_logger.addHandler(console_handler)
"""
Notes to myself:
need a new structure which records the ds object_ids quickly
then a routine which creates at least n thumbnails, and
another routine which will create a single thumbnail and store it- called from gtk idle loop
"""

class Datastore_SQLite():
    """class for interfacing between the Journal and an SQLite database"""
    def __init__(self,database_access_object):
        """receives an open dbaccess object (defined in dbphoto) """
        #self.db = dbaccess(fn)
        self.db = database_access_object
        self.datastore_to_process = None
        self.datastore_process_index = -1
    
    def ok(self):
        if self.db.is_open():return True
        return False
    
    def scan_images(self):
        """
        returns a list of journal object ids that have mime_type equal to one
        of the entries in mimetype table of xophoto database. 
        """
        rtn = 0
        mime_list = self.db.get_mime_list()
        (results,count) = datastore.find({})
        for f in results:
            dict = f.get_metadata().get_dictionary()
            if dict["mime_type"] in mime_list:
                #record the id, file size, file date, in_ds
                self.db.create_picture_record(f.object_id, f.get_file_path())
                rtn += 1
            f.destroy()
        self.db.commit()
        _logger.debug('%s entries found in journal. Number of pictures %s'%(count,rtn,))
        return rtn

    def check_for_recent_images(self):
        """scans the journal for pictures that are not in database, records jobject_id if found in
        table groups with the journal id in category. Can be faster because we don't have to fetch file itself.
        """
        mime_list = ['image/jpg','image/png','image/jpeg','image/gif',]
        (results,count) = datastore.find({'mime_type':mime_list})
        _logger.debug('Journal/datastore entries found:%s'%count)
        added = 0
        a_row_found = False
        cursor = self.db.connection().cursor()
        for ds in results:
            #at least for now assume that the newest images are returned first
            if not a_row_found:
                dict = ds.get_metadata().get_dictionary()
                if dict["mime_type"] in mime_list:
                    cursor.execute('select * from groups where category = ? and jobject_id = ?',\
                                   (display.journal_id,str(ds.object_id),))
                    rows = cursor.fetchall()
                    if len(rows) == 0:
                        #may need to add date entered into ds (create date could be confusing)
                        #self.db.put_ds_into_picture(ds.object_id)
                        self.db.add_image_to_album(display.journal_id,ds.object_id)
                        added += 1
                    else: #assume that pictures are returned in last in first out order
                        #a_row_found = True
                        pass
            ds.destroy()
        _logger.debug('scan found %s. Added %s datastore object ids from datastore to picture'%(count,added,))
        return (count,added,)
    
    def make_one_thumbnail(self):
        if not self.db.is_open(): return
        if not self.datastore_to_process:
            cursor = self.db.get_connection().cursor()
            cursor.execute('select * from picture where md5_sum = null')
            self.datastore_to_process = cursor.fetchall()
            self.datastore_process_index = 0
        if self.datastore_to_process and self.datastore_process_index > -1:
            jobject_id = self.datastore_to_process[self.datastore_process_index]['jobject_id']
            fn =get_filename_from_jobject_id(jobject_id)
            if fn:
                self.db.create_picture_record(f.object_id, fn)
                self.datastore_process_index += 1
                if self.datastore_process_index > len(self.datastore_to_process):
                    self.datastore_process_index = -1
        return True #we want to continue to process in gtk_idle_loop
        
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

    def delete_jobject_id_from_datastore(self,jobject_id):
        try:
            datastore.delete(jobject_id)
        except Exception,e:
            _logger.debug('delete_jobject_id_from_datastore error: %s'%e)
    
    def update_metadata(self,jobject_id,**kwargs):
        try:
            ds_obj = datastore.get(jobject_id)
        except Exception,e:
            _logger.debug('update metadata error: %s'%e)
            return None
        if ds_obj:
            md = ds_obj.get_metadata()
            if md:
                for key in kwargs.keys():
                    md[key] = kwargs[key]
                try:
                    datastore.write(ds_obj)
                except Exception, e:
                    _logger.debug('datastore write exception %s'%e)
            else:
                _logger.error('no metadata recovered from journal')
        else:
            _logger.error('no jobject returned from datastore.get()')
            
class FileTree():
    def __init__(self,db,activity):
        self.db = db
        self._activity = activity
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
        self.dialog.set_current_folder('/home/olpc/Pictures')               
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
    
    def _response_cb(self,alert,response):
        self._activity.remove_alert(alert)
        if response == gtk.RESPONSE_CANCEL:
            self.cancel = True


    def copy_tree_to_ds(self,path):
        added = 0
        self.cancel = False
        proc_start = time.clock()
        dirlist = os.listdir(path)
        num = len(dirlist)
        message = _('Number of images to copy to the XO Journal: ') + str(num)
        pa_title = _('Please be patient')
        alert = display.ProgressAlert(msg=message,title=pa_title)
        self._activity.add_alert(alert)
        alert.connect('response',self._response_cb)
        for filename in dirlist:            
            start = time.clock()
            abspath = os.path.join(path, filename)
            #print abs_path
            mtype = ''
            chunks = abspath.split('.')
            if len(chunks)>1:
                ext = chunks[-1]
                if ext == 'jpg' or ext == 'jpeg':
                    mtype = 'image/jpg'
                elif ext == 'gif':
                    mtype = 'image/gif'
                elif ext == 'png':
                    mtype = 'image/png'
            if mtype == '': continue        
            info = os.stat(abspath)
            size = info.st_size
            
            #if path and size are equal to image already loaded, abort
            if self.db.check_in_ds(abspath,size): continue
            ds = datastore.create()
            ds.metadata['filename'] = abspath
            ds.metadata['title'] = filename
            ds.metadata['mime_type'] = mtype
            dest = os.path.join(os.environ['SUGAR_ACTIVITY_ROOT'],'instance',filename)
            shutil.copyfile(abspath,dest)
            ds.set_file_path(dest)
            datastore.write(ds,transfer_ownership=True)
            self.db.create_picture_record(ds.object_id,abspath)
            ds.destroy()
            _logger.debug('writing one image to datastore took %f seconds'%(time.clock()-start))
            added += 1
            alert.set_fraction(float(added)/num)
            while gtk.events_pending():
                gtk.main_iteration()
            if self.cancel:
                break

        _logger.debug('writing all images to datastore took %f seconds'%(time.clock()-proc_start))
        self._activity.remove_alert(alert)
        return added
    
    def fill_ds(self):
        path = self.get_path()
        if path:
            return self.copy_tree_to_ds(path)
        
                    
                
if __name__ == '__main__':
    db = DbAccess('/home/olpc/.sugar/default/org.laptop.XoPhoto/data/xophoto.sqlite')
    if db.is_open():
        ds_sql = Datastore_SQLite(db)
        #count = ds_sql.scan_images()
        count,added = ds_sql.check_for_recent_images()
        exit()
        for i in imagelist:
            print('\n%s'%ds.get_filename_from_jobject_id(i))
        ft = FileTree('xophoto.sqlite')
        #new = ft.fill_ds()
        print('%s datastore records added'%new)
    else:
        print('xophoto sqlite database failed to open')
