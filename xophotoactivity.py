#!/usr/bin/env python
# xophotoactivity.py 
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
"""
Top level description of the components of XoPhoto Activity
xophotoactivity.py  --this file, subclasses Activity, Sets up Menus, canvas,
                    fetches the display module.Application class in display.py,
                    passes application object to sugargame.<canvas application runner>
display.py          --contains the xophoto main loop this analyzes keystokes and
                    manipulates the display
sources.py          --obtains images from datastore, folders, cameras and puts relevant
                    information into the sqlite database
sinks.py            --combines information from the sqlite database and the Journal and
                    pumps it to various destinations, folders, email messages, slideshows
dbphoto.py          --interfaces with the sqlite database, provides low level db access
sugarpygame         --pygame platform developed sugarlabs.org see:
                    http://wiki.sugarlabs.org/go/Development_Team/sugargame
"""
from gettext import gettext as _

import gtk
import pygame
from sugar.activity import activity
from sugar.graphics.toolbutton import ToolButton
import gobject
import sugargame.canvas
import os
import shutil
from threading import Timer
from subprocess import Popen, PIPE

import display
import photo_toolbar
from sources import *
from sinks import *
import dbphoto

#Application Globals
album_column_width = 200
#db can be resumed, new instance, or recovering from db error

import logging
_logger = logging.getLogger('xophoto')
_logger.setLevel(logging.DEBUG)
console_handler = logging.StreamHandler()
console_formatter = logging.Formatter('%(name)s %(levelname)s %(funcName)s: %(lineno)d||| %(message)s')
#console_handler.setFormatter(console_formatter)
#_logger.addHandler(console_handler)


class XoPhotoActivity(activity.Activity):
    DbAccess_object = None
    def __init__(self, handle):
        #initialize variables
        self.file_tree = None
        self.use_db_template = False
        self._activity = self
        self.interactive_close = False
        self.timed_out = False
        self.window_realized = False
        self.game = None
        self.kept_once = False
       
        if handle and handle.object_id and handle.object_id != '' and not self.use_db_template:
            _logger.debug('At activity startup, handle.object_id is %s'%handle.object_id)
            self.make_jobject = False
        else:
            self.make_jobject = True
            self.read_file(None)
            _logger.debug('At activity startup, handle.object_id is None. Making a new datastore entry')
        
        activity.Activity.__init__(self, handle, create_jobject = self.make_jobject)
        self.make_jobject = False

        # Build the activity toolbar.
        self.build_toolbar()
        
        """
        #wait for the gtk window to realize
        self.connect('realize',self.realized_cb)
        Timer(5.0, self.end_realize_delay, ()).start()
        
        while not self.timed_out and not self.realized:
            gtk.main_iteration()
        
        if self.timed_out:
            _logger.debug('gtk window not realized')
            exit()
    def realized_cb(self):
        self.realized = True

        """
        
        # Build the Pygame canvas.
        self._pygamecanvas = sugargame.canvas.PygameCanvas(self)

        # Note that set_canvas implicitly calls read_file when resuming from the Journal.
        self.set_canvas(self._pygamecanvas)
        
        # Create the game instance.
        self.game = display.Application(self)

        # Start the game running.
        self._pygamecanvas.run_pygame(self.game.run)
    """
    def __realize_cb(self,window):
        super(activity.Activity,self).__realize_cb()
        self.window.realized = True
    """   
    def is_realized(self):
        return self.window_realized

    def end_realize_delay(self):
        self.timed_out = True
        
        
    def build_toolbar(self):
        toolbox = photo_toolbar.ActivityToolbox(self)
        activity_toolbar = toolbox.get_activity_toolbar()
        """
        label = gtk.Label(_('New Album Name:'))
        tool_item = gtk.ToolItem()
        tool_item.set_expand(False)
        tool_item.add(label)
        label.show()
        activity_toolbar.insert(tool_item, 0)
        tool_item.show()

        activity_toolbar._add_widget(label)
        """
        activity_toolbar.keep.props.visible = True
        #activity_toolbar.share.props.visible = False
        
        self.edit_toolbar = EditToolbar()
        toolbox.add_toolbar(_('Edit'), self.edit_toolbar)
        self.edit_toolbar.connect('do-import',
                self.edit_toolbar_doimport_cb)
        self.edit_toolbar.connect('do-stop',
                self.__stop_clicked_cb)
        self.edit_toolbar.show()

        self.use_toolbar = UseToolbar()
        toolbox.add_toolbar(_('Use'), self.use_toolbar)
        self.use_toolbar.connect('do-export',
                self.use_toolbar_doexport_cb)
        self.use_toolbar.connect('do-upload',
                self.use_toolbar_doupload_cb)
        self.use_toolbar.connect('do-slideshow',
                self.use_toolbar_doslideshow_cb)
        self.use_toolbar.connect('do-stop',
                self.__stop_clicked_cb)
        self.use_toolbar.show()

        toolbox.show()
        self.set_toolbox(toolbox)
    
 
    def activity_toolbar_add_album_cb(self,album_name):
        self.game.albums.change_name_of_current_album(album_name )
    
    def activity_toolbar_delete_album_cb(self):
        album = self.game.albums.get_current_album_name()
        self.game.albums.alert('Are you sure you want to delete %s?'%album)
        
    def confirm_delete_album_cb(self,response):
        album = self.game.albums.get_current_album_identifier()

        if not response in (gtk.RESPONSE_OK):return
        sql = 'delete from groups where subcategory = ?'
        cursor = self.game.db.conn.cursor()
        cursor.execute(sql,())

    def command_line(self,cmd, alert_error=False):
        _logger.debug('command_line cmd:%s'%cmd)
        p1 = Popen(cmd,stdout=PIPE, shell=True)
        output = p1.communicate()
        if p1.returncode != 0 :
            _logger.debug('error returned from shell command: %s was %s'%(cmd,output[0]))
            if alert_error: self.alert(_('%s Command returned non zero\n'%cmd+output[0]))
        return output[0],p1.returncode
        
    
    def copy(self):
        _logger.debug('entered copy which will save and re-init sql database')
        dict = self.get_metadata()
        #set a flag to copy the template
        self.interactive_close = True
        self.save()
        
        db_path = os.path.join(os.environ['SUGAR_ACTIVITY_ROOT'],'data','xophoto.sqlite')
        try:
            self.DbAccess_object = dbphoto.DbAccess(db_path)
        except Exception,e:
            _logger.debug('database template failed to open error:%s'%e)
            exit()
        source = db_path
        ds = datastore.create()
        ds.metadata['title'] = _('Empty Photo Stack')
        ds.metadata['activity_id'] = dict.get('activity_id')
        ds.metadata['activity'] = 'org.laptop.XoPhoto'
        ds.metadata['mime_type'] = 'application/binary'
        dest = os.path.join(os.environ['SUGAR_ACTIVITY_ROOT'],'instance','xophoto.sqlite')
        shutil.copyfile(source,dest)
        ds.set_file_path(dest)
        datastore.write(ds,transfer_ownership=True)
        ds.destroy()
        if dict.get('dbcorrupted','False') == 'False' and not self.kept_once:
            #try to save all the time/computation involved in making thumbnails
            backup_db = os.path.join(os.environ['SUGAR_ACTIVITY_ROOT'],'data','xophoto_back.sqlite')
            if os.path.isfile(backup_db):
                try:
                    conn = self.DbAccess_object.get_connection()
                    cursor = conn.cursor()
                    cursor.execute("attach '%s' as thumbs"%backup_db)
                    sql = 'insert into picture select * from thumbs.picture'
                    cursor.execute(sql)
                    sql = 'insert into transforms select * from thumbs.transforms'
                    cursor.execute(sql)
                    conn.commit()
                except Exception,e:
                    _logger.debug('database exception %s'%e)
                    raise e
                self.kept_once = True
                self.game.albums.alert(_('Click KEEP again for a completely new Database.'),_('New Database initialized from the Current Database.'))
        
    def edit_toolbar_doimport_cb(self, view_toolbar):
        if not self.file_tree:
            self.file_tree = FileTree(self.game.db)
        path = self.file_tree.get_path()
        pygame.display.flip()
        if path:
            self.file_tree.copy_tree_to_ds(path)
            Datastore_SQLite().scan_images()
    
    def use_toolbar_doexport_cb(self,use_toolbar):
        if not self.file_tree:
            self.file_tree = FileTree(self.game.db)
        path = self.file_tree.get_path()
        
        #think about writing the whole journal, and the trash (would need to add these to the selectable paths)
        pygame.display.flip
        if path:
            _logger.debug("write selected album to %s"%path)
                        
            #figure out how to access correct object model:album_name = self.album_rows[self.selected_index]['subcategory']
            #generate a list of dictionary rows which contain the info about images to write
            album_object = self.game.albums
            album_name = album_object.album_rows[int(album_object.selected_index)]['subcategory']
            sql = """select pict.*, grp.* from picture as pict, groups as grp \
                  where grp.category = ? and grp.jobject_id = pict.jobject_id"""
            cursor = album_object.db.con.cursor()
            cursor.execute(sql,(album_name,))
            rows = cursor.fetchall()
            
            _logger.debug('album to export: %s. Number of pictures found: %s'%(album_name,len(rows),))
            #def __init__(self,rows,db,sources,path):
            exporter = ExportAlbum(rows,self.game.db,path)
            exporter.do_export()
            
    
    def use_toolbar_doupload_cb(self,use_toolbar):
        pass
    
    def use_toolbar_doslideshow_cb(self,use_toolbar):
        pass
    
    def read_file(self, file_path):
        _logger.debug('started read_file %s. make_file flag %s'%(file_path,self.make_jobject))
        if self.make_jobject:  #make jobject is flag signifying that we are not resuming activity
            _logger.debug(' copied template  rather than resuming')
            #This is a new invocation, copy the sqlite database to the data directory
            source = os.path.join(os.getcwd(),'xophoto.sqlite.template')
            dest = os.path.join(os.environ['SUGAR_ACTIVITY_ROOT'],'data','xophoto.sqlite')
            try:
                shutil.copy(source,dest)
            except Exception,e:
                _logger.debug('database template failed to copy error:%s'%e)
                exit()
        else:
            if self.DbAccess_object:  #if the database is open don't overwrite and confuse it
                _logger.debug('in read-file, db was already open')
                return
            dict = self.get_metadata()
            _logger.debug('title was %s'%dict.get('title','no title given'))
            dest = os.path.join(os.environ['SUGAR_ACTIVITY_ROOT'],'data','xophoto.sqlite')
            _logger.debug('reading from %s and writeing to %s'%(file_path,dest,))
            try:
                shutil.copy(file_path, dest)
                _logger.debug('completed writing the sqlite file')
                    
            except Exception, e:
                _logger.debug('read sqlite file to local error %s'%e)
                return
        try:
            self.DbAccess_object = DbAccess(dest)
        except Exception,e:
            _logger.debug('database failed to open in read file. error:%s'%e)
            exit()
        _logger.debug('completed read_file. DbAccess_jobject is created')
                
        
    def write_file(self, file_path):
        
        try:
            if self.DbAccess_object:
                if self.DbAccess_object.get_error(): return  #dont save a corrupted database
                self.DbAccess_object.closedb()
            if self.game and self.game.db:    
                self.game.db = None
            self.DbAccess_object = None
            local_path = os.path.join(os.environ['SUGAR_ACTIVITY_ROOT'],'data','xophoto.sqlite')
            #local_path = os.path.join(os.environ['SUGAR_BUNDLE_PATH'],'xophoto.sqlite')
            self.metadata['filename'] = local_path
            self.metadata['mime_type'] = 'application/binary'
            _logger.debug('write_file %s to %s'%(local_path,file_path,))
            shutil.copyfile(local_path,file_path)
        except Exception,e:
            _logger.debug('write_file exception %s'%e)
            raise e
        if self.interactive_close:
            self.interactive_close = None
            #set the currently active dbase aside as a backup
            backup_path = os.path.join(os.environ['SUGAR_ACTIVITY_ROOT'],'data','xophoto_back.sqlite')
            if os.path.isfile(backup_path):
                os.unlink(backup_path)
            cmd = 'mv %s %s'%(local_path,backup_path)
            rsp,err = self.command_line(cmd)
            
            try: #putting in an empty template makes it easier to make a distributable activity
                source = os.path.join(os.getcwd(),'xophoto.sqlite.template')
                shutil.copy(source,local_path)
            except Exception,e:
                _logger.debug('database template failed to copy error:%s'%e)
                exit()
        else: #re-open the database
            dest = os.path.join(os.environ['SUGAR_ACTIVITY_ROOT'],'data','xophoto.sqlite')
            try:
                self.DbAccess_object = DbAccess(dest)
            except Exception,e:
                _logger.debug('database failed to re-open in write file. error:%s'%e)
                exit()
            _logger.debug('sqlite datbase re-opened successfully')
        
    def __stop_clicked_cb(self, button):
        self.interactive_close = True
        self._activity.close()



class EditToolbar(gtk.Toolbar):
    __gtype_name__ = 'EditToolbar'

    __gsignals__ = {
        'needs-update-size': (gobject.SIGNAL_RUN_FIRST,
                              gobject.TYPE_NONE,
                              ([])),
        'do-import': (gobject.SIGNAL_RUN_FIRST,
                          gobject.TYPE_NONE,
                          ([])),
        'do-stop': (gobject.SIGNAL_RUN_FIRST,
                          gobject.TYPE_NONE,
                          ([]))
    }

    def __init__(self):
        gtk.Toolbar.__init__(self)
        self.doimport = ToolButton()
        self.doimport.set_stock_id('gtk-open')
        self.doimport.set_icon_widget(None)
        self.doimport.set_tooltip(_('Import from SD or USB'))
        self.doimport.connect('clicked', self.doimport_cb)
        self.insert(self.doimport, -1)
        self.doimport.show()
        
        self.delete_comment = ToolButton()
        self.delete_comment.set_stock_id('gtk-stock-delete')
        self.delete_comment.set_tooltip(_("Remove Picture"))
        self.delete_comment.show()
        self.insert(self.delete_comment,-1)
        
        separator = gtk.SeparatorToolItem()
        separator.props.draw = False
        separator.set_expand(True)
        self.insert(separator, -1)
        separator.show()

        self.entry = gtk.Entry()        
        self.entry.set_width_chars(45)
        tool_item = gtk.ToolItem()
        tool_item.set_expand(False)
        tool_item.add(self.entry)
        self.entry.show()
        self.insert(tool_item, -1)
        tool_item.show()

        self.add_comment = ToolButton('list-add')
        self.add_comment.set_tooltip(_("Add Annotation"))
        self.add_comment.show()
        self.insert(self.add_comment,-1)

        separator = gtk.SeparatorToolItem()
        separator.props.draw = False
        separator.set_expand(True)
        self.insert(separator, -1)
        separator.show()

        self.stop = ToolButton('activity-stop', tooltip=_('Stop'))
        self.stop.props.accelerator = '<Ctrl>Q'
        self.stop.connect('clicked', self.dostop_cb)
        self.insert(self.stop, -1)
        self.stop.show()

    def doimport_cb(self, button):
        self.emit('do-import')

    def dostop_cb(self, button):
        self.emit('do-stop')

class UseToolbar(gtk.Toolbar):
    __gtype_name__ = 'UseToolbar'

    __gsignals__ = {
        'do-export': (gobject.SIGNAL_RUN_FIRST,
                              gobject.TYPE_NONE,
                              ([])),
        'do-upload': (gobject.SIGNAL_RUN_FIRST,
                          gobject.TYPE_NONE,
                          ([])),
        'do-slideshow': (gobject.SIGNAL_RUN_FIRST,
                          gobject.TYPE_NONE,
                          ([])),
        'do-stop': (gobject.SIGNAL_RUN_FIRST,
                          gobject.TYPE_NONE,
                          ([]))
    }

    def __init__(self):
        gtk.Toolbar.__init__(self)
        self.doexport = ToolButton('view-fullscreen')
        self.doexport.set_tooltip(_('Export to USB/SD/DISK'))
        self.doexport.connect('clicked', self.doexport_cb)
        self.insert(self.doexport, -1)
        self.doexport.show()
        
        separator = gtk.SeparatorToolItem()
        separator.props.draw = False
        separator.set_expand(True)
        self.insert(separator, -1)
        separator.show()

        self.doupload = ToolButton('view-fullscreen')
        self.doupload.set_tooltip(_('Fullscreen'))
        self.doupload.connect('clicked', self.doupload_cb)
        self.insert(self.doupload, -1)
        self.doupload.show()
        
        separator = gtk.SeparatorToolItem()
        separator.props.draw = False
        separator.set_expand(True)
        self.insert(separator, -1)
        separator.show()

        self.doslideshow = ToolButton()
        self.doslideshow.set_stock_id('gtk-fullscreen')
        self.doslideshow.set_tooltip(_('SlideShow'))
        self.doslideshow.connect('clicked', self.doslideshow_cb)
        self.insert(self.doslideshow, -1)
        self.doslideshow.show()

        separator = gtk.SeparatorToolItem()
        separator.props.draw = False
        separator.set_expand(True)
        self.insert(separator, -1)
        separator.show()

        self.stop = ToolButton('activity-stop', tooltip=_('Stop'))
        self.stop.props.accelerator = '<Ctrl>Q'
        self.stop.connect('clicked', self.dostop_cb)
        self.insert(self.stop, -1)
        self.stop.show()

    def doexport_cb(self, button):
        self.emit('do-export')

    def doupload_cb(self, button):
        self.emit('do-upload')

    def doslideshow_cb(self, button):
        self.emit('do-slideshow')

    def dostop_cb(self, button):
        self.emit('do-stop')


