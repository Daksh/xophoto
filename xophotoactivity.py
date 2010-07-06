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
from sugar import profile

import gobject
import sugargame.canvas
import os
import shutil
from threading import Timer
from subprocess import Popen, PIPE

from help.help import Help
import display
from display import *
import photo_toolbar
from sources import *
from sinks import *
import dbphoto

#help interface
HOME = os.path.join(activity.get_bundle_path(), 'help/XO_Introduction.html')
#HOME = "http://website.com/something.html"
HELP_TAB = 3


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
        self.util = Utilities(self)
        self.db_sanity_check = False
        
        #there appears to be an initial save yourself, asynchronous, which
        #  in my write_file closes the database and causes sporatic failures
        self.initial_save_yourself = False
        
       
        if handle and handle.object_id and handle.object_id != '' and not self.use_db_template:
            _logger.debug('At activity startup, handle.object_id is %s'%handle.object_id)
            self.make_jobject = False
        else:
            self.make_jobject = True
            self.read_file(None)
            _logger.debug('At activity startup, handle.object_id is None. Making a new datastore entry')
        
        activity.Activity.__init__(self, handle, create_jobject = self.make_jobject)
        #does activity init execute the read? check if dbobject is reliably open
        if self.DbAccess_object:
            _logger.debug('database object is_open:%s'%self.DbAccess_object.is_open())
        else:
            _logger.debug('after activity init, read has not been called')
        self.make_jobject = False

        #following are essential for interface to Help
        self.help_x11 = None
        self.handle = handle
        self.help = Help(self)

        self.toolbox = activity.ActivityToolbox(self)
        self.toolbox.connect_after('current_toolbar_changed',self._toolbar_changed_cb)
        self.toolbox.show()

        toolbar = gtk.Toolbar()
        self.toolbox.add_toolbar(_('Help'), toolbar)
        toolbar.show()

        # Build the activity toolbar.
        self.build_toolbar()
        
        # Build the Pygame canvas.
        self._pygamecanvas = sugargame.canvas.PygameCanvas(self)

        # Note that set_canvas implicitly calls read_file when resuming from the Journal.
        self.set_canvas(self._pygamecanvas)
        
        # Create the game instance.
        self.game = display.Application(self)

        # Start the game running.
        self._pygamecanvas.run_pygame(self.game.run)
        
    def build_toolbar(self):
        self.toolbox = photo_toolbar.ActivityToolbox(self)
        self.toolbox.connect_after('current_toolbar_changed',self._toolbar_changed_cb)
        self.activity_toolbar = self.toolbox.get_activity_toolbar()
        """
        label = gtk.Label(_('New Album Name:'))
        tool_item = gtk.ToolItem()
        tool_item.set_expand(False)
        tool_item.add(label)
        label.show()
        self.activity_toolbar.insert(tool_item, 0)
        tool_item.show()

        self.activity_toolbar._add_widget(label)
        """
        self.activity_toolbar.keep.props.visible = True
        #self.activity_toolbar.share.props.visible = False
        
        self.edit_toolbar = EditToolbar()
        self.toolbox.add_toolbar(_('Edit'), self.edit_toolbar)
        self.edit_toolbar.connect('do-import',
                self.edit_toolbar_doimport_cb)
        self.edit_toolbar.connect('do-initialize',
                self.edit_toolbar_doinitialize_cb)
        self.edit_toolbar.connect('do-stop',
                self.__stop_clicked_cb)
        self.edit_toolbar.show()

        self.use_toolbar = UseToolbar()
        self.toolbox.add_toolbar(_('Use'), self.use_toolbar)
        self.use_toolbar.connect('do-export',
                self.use_toolbar_doexport_cb)
        self.use_toolbar.connect('do-upload',
                self.use_toolbar_doupload_cb)
        self.use_toolbar.connect('do-slideshow',
                self.use_toolbar_doslideshow_cb)
        self.use_toolbar.connect('do-stop',
                self.__stop_clicked_cb)
        self.use_toolbar.show()

        toolbar = gtk.Toolbar()
        self.toolbox.add_toolbar(_('Help'), toolbar)
        toolbar.show()

        self.toolbox.show()
        self.set_toolbox(self.toolbox)
    
    ################  Help routines
    def _toolbar_changed_cb(self,widget,tab_no):
        if tab_no == HELP_TAB:
            self.help_selected()
            
    def set_toolbar(self,tab):
        self.toolbox.set_current_toolbar(tab)

    def help_selected(self):
        """
        if help is not created in a gtk.mainwindow then create it
        else just switch to that viewport
        """
        if not self.help_x11:
            screen = gtk.gdk.screen_get_default()
            self.pdb_window = screen.get_root_window()
            _logger.debug('xid for pydebug:%s'%self.pdb_window.xid)
            self.help_x11 = self.help.realize_help()
        else:
            self.help.activate_help()
     
    def activity_toolbar_add_album_cb(self,album_name):
        self.game.album_collection.create_new_album(None)
    
    def activity_toolbar_delete_album_cb(self):
        album = self.game.album_collection.get_current_album_name()
        album_id = self.game.album_collection.get_current_album_identifier()
        if album_id in [journal_id,trash_id]:
            self.util.alert(_('Drag pictures to the Trash, and then empty the trash'),\
                              _('Warning! Journal and Trash cannot be deleted'))
            return
        self.util.confirmation_alert(_('Are you sure you want to delete %s?')%album,\
                                     _('Caution'),self.confirm_delete_album_cb)
        
    def confirm_delete_album_cb(self,alert,response):
        album_id = self.game.album_collection.get_current_album_identifier()
        _logger.debug('about to delete album with identifier:%s'%album_id)
        if not response == gtk.RESPONSE_OK:return
        self.game.album_collection.delete_album(album_id)

    def activity_toolbar_empty_trash_cb(self):
        self.util.confirmation_alert(_('Are you sure you want to proceed?'),\
                              _('Warning! you are about to completely remove these images from your XO.'),\
                                self.empty_trash_cb)
        
    def empty_trash_cb(self,alert,response,album_id=trash_id):
        if not response == gtk.RESPONSE_OK:return
        rows = self.DbAccess_object.get_album_thumbnails(album_id)
        for row in rows:
            jobject_id = str(row['jobject_id'])
            Datastore_SQLite(self.game.db).delete_jobject_id_from_datastore(jobject_id)
            self.DbAccess_object.delete_all_references_to(jobject_id)
        if self.game.album_collection:
            self.game.album_collection.display_thumbnails(trash_id,new_surface=True)
            self.game.album_collection.paint_albums()
    
    def command_line(self,cmd, alert_error=False):
        _logger.debug('command_line cmd:%s'%cmd)
        p1 = Popen(cmd,stdout=PIPE, shell=True)
        output = p1.communicate()
        if p1.returncode != 0 :
            _logger.debug('error returned from shell command: %s was %s'%(cmd,output[0]))
            if alert_error: self.util.alert(_('%s Command returned non zero\n'%cmd+output[0]))
        return output[0],p1.returncode
        
    
    def copy(self):
        """processing when the keep icon is pressed"""
        _logger.debug('entered copy which will save and re-init sql database')
        dict = self.get_metadata()
        #set a flag to copy the template
        self.interactive_close = True
        
        #compact the database
        conn = self.DbAccess_object.get_connection()
        cursor = conn.cursor()
        cursor.execute('vacuum')

        self.save()
        
        db_path = os.path.join(os.environ['SUGAR_ACTIVITY_ROOT'],'data','xophoto.sqlite')
        try:
            self.DbAccess_object = dbphoto.DbAccess(db_path)
        except Exception,e:
            _logger.debug('database template failed to open error:%s'%e)
            exit()
        source = db_path
        ds = datastore.create()
        ds.metadata['title'] = _('New Photo Stack')
        ds.metadata['activity_id'] = dict.get('activity_id')
        ds.metadata['activity'] = 'org.laptop.XoPhoto'
        ds.metadata['mime_type'] = 'application/binary'
        ds.metadata['icon-color'] = dict.get('icon-color')
        dest = os.path.join(os.environ['SUGAR_ACTIVITY_ROOT'],'instance','xophoto.sqlite')
        
        #albums are stored in the groups table, so start fresh
        conn = self.DbAccess_object.get_connection()
        cursor = conn.cursor()
        cursor.execute("delete from groups")
        conn.commit()
        
        shutil.copyfile(source,dest)
        ds.set_file_path(dest)
        datastore.write(ds,transfer_ownership=True)
        ds.destroy()
        
        
    def edit_toolbar_doimport_cb(self, view_toolbar):
        if not self.file_tree:
            self.file_tree = FileTree(self.game.db,self)
        path = self.file_tree.get_path()
        pygame.display.flip()
        if path:
            self.file_tree.copy_tree_to_ds(path)
            Datastore_SQLite(self.game.db).check_for_recent_images()
   
    def edit_toolbar_doinitialize_cb(self, view_toolbar):
        self.empty_trash_cb(None,gtk.RESPONSE_OK,journal_id)
        self.read_file(None,initialize=True)

    
    def use_toolbar_doexport_cb(self,use_toolbar):
        if not self.file_tree:
            self.file_tree = FileTree(self.game.db,self)
        base_path = self.file_tree.get_path()
        
        #think about writing the whole journal, and the trash (would need to add these to the selectable paths)
        pygame.display.flip
        if base_path:
            _logger.debug("write selected album to %s"%base_path)
                        
            #figure out how to access correct object model:album_name = self.album_rows[self.selected_index]['subcategory']
            #generate a list of dictionary rows which contain the info about images to write
            album_object = self.game.album_collection
            
            album_id = album_object.album_rows[int(album_object.album_index)]['subcategory']
            album_name = album_object.album_rows[int(album_object.album_index)]['jobject_id']
            safe_name = album_name.replace(' ','_')
            new_path = self.non_conflicting(base_path,safe_name)
            _logger.debug('album_id is %s new path:%s'%(album_id,new_path))
            sql = """select pict.*, grp.* from picture as pict, groups as grp \
                  where grp.category = ? and grp.jobject_id = pict.jobject_id"""
            cursor = album_object.db.con.cursor()
            cursor.execute(sql,(album_id,))
            rows = cursor.fetchall()
            
            _logger.debug('album to export: %s. Number of pictures found: %s'%(album_name,len(rows),))
            #def __init__(self,rows,db,sources,path):
            exporter = ExportAlbum(rows,self.game.db,new_path)
            exporter.do_export()

    def non_conflicting(self,root,basename):
        """
        create a non-conflicting filename by adding '-<number>' to a filename before extension
        """
        ext = ''
        basename = basename.split('.')
        word = basename[0]
        if len(basename) > 1:
            ext = '.' + basename[1]
        adder = ''
        index = 0
        while (os.path.isfile(os.path.join(root,word+adder+ext)) or 
                                os.path.isdir(os.path.join(root,word+adder+ext))):
            index +=1
            adder = '-%s'%index
        _logger.debug('non conflicting:%s'%os.path.join(root,word+adder+ext))
        return os.path.join(root,word+adder+ext)
    
            
    
    def use_toolbar_doupload_cb(self,use_toolbar):
        pass
    
    def use_toolbar_doslideshow_cb(self,use_toolbar):
        pass
    
    def read_file(self, file_path, initialize=False):
        _logger.debug('started read_file %s. make_file flag %s'%(file_path,self.make_jobject))
        if self.make_jobject or initialize:  #make jobject is flag signifying that we are not resuming activity
            _logger.debug(' copied template  rather than resuming')
            if self.DbAccess_object:
                self.DbAccess_object.closedb()
            
            #This is a new invocation, copy the sqlite database to the data directory
            source = os.path.join(os.getcwd(),'xophoto.sqlite.template')
            dest = os.path.join(os.environ['SUGAR_ACTIVITY_ROOT'],'data','xophoto.sqlite')
            try:
                shutil.copy(source,dest)
            except Exception,e:
                _logger.debug('database template failed to copy error:%s'%e)
                exit()
                
            #now do the same for the thumbnails if they don't already exist        
            source = os.path.join(os.getcwd(),'data_cache.sqlite.template')
            dest = os.path.join(os.environ['SUGAR_ACTIVITY_ROOT'],'data','data_cache.sqlite')
            if not os.path.isfile(dest) or initialize:
                try:
                    shutil.copy(source,dest)
                except Exception,e:
                    _logger.debug('thumbnail database template failed to copy error:%s'%e)
                    exit()
        else:
            if self.DbAccess_object:  #if the database is open don't overwrite and confuse it
                _logger.debug('in read-file, db was already open')
                return
            dict = self.get_metadata()
            _logger.debug('title was %s'%dict.get('title','no title given'))
            dest = os.path.join(os.environ['SUGAR_ACTIVITY_ROOT'],'data','xophoto.sqlite')
            _logger.debug('reading from %s and writing to %s'%(file_path,dest,))
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
            
        #if this is the first time the databases are to be used this invocation?
        #if the databases are not well formed, rebuild from a template
        if not self.db_sanity_check:
            self.db_sanity_check = True
            conn = self.DbAccess_object.connection()
            c = conn.cursor()
            c.execute('pragma quick_check')
            rows = c.fetchall()
            if len(rows) == 1 and str(rows[0][0]) == 'ok':
                #main database is ok
                _logger.debug('xophoto database passes quick_check')
            else:
                #need to start over with a new template and regenerate the thumbnails
                _logger.debug('swapping in template for xophoto.sqlite database')
                    
                try: 
                    source = os.path.join(os.getcwd(),'xophoto.sqlite.template')
                    local_path = os.path.join(os.environ['SUGAR_ACTIVITY_ROOT'],'data','xophoto.sqlite')
                    shutil.copy(source,local_path)
                except Exception,e:
                    _logger.debug('xophoto template failed to copy error:%s'%e)
                    exit()
               
            #check the thumbnails
            c.execute('pragma data_cache.quick_check')
            rows = c.fetchall()
            if len(rows) == 1 and str(rows[0][0]) == 'ok':
                #thumbnails database is ok
                _logger.debug('thumbnail database passes quick_check')
            else:
                #need to start over with a new template and regenerate the thumbnails
                _logger.debug('swapping in template for transforms (thumbnail) database')
                    
                try: 
                    source = os.path.join(os.getcwd(),'data_cache.sqlite.template')
                    local_path = os.path.join(os.environ['SUGAR_ACTIVITY_ROOT'],'data','data_cache.sqlite')
                    shutil.copy(source,local_path)
                except Exception,e:
                    _logger.debug('data_cache template failed to copy error:%s'%e)
                    exit()
                
        _logger.debug('completed read_file. DbAccess_jobject is created')        
        
    def write_file(self, file_path):
        
        try:
            if self.DbAccess_object and not self.interactive_close:
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
                self.game.db = self.DbAccess_object
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
        'do-initialize': (gobject.SIGNAL_RUN_FIRST,
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
        self.delete_comment.set_stock_id('gtk.stock-delete')
        self.delete_comment.set_tooltip(_("Re-Inialize the Databass -- for startup testing"))
        self.delete_comment.connect('clicked',self.do_initialize)
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
        tool_item.hide()

        self.add_comment = ToolButton('list-add')
        self.add_comment.set_tooltip(_("Add Annotation"))
        self.add_comment.hide()
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
        
    def do_initialize(self, button):
        self.emit('do-initialize')

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
        self.doupload.hide()
        
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
        self.doslideshow.hide()

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


