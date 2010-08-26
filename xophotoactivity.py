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
import time
import shutil
from threading import Timer
from subprocess import Popen, PIPE

from help.help import Help,Toolbar
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
startup_clock = time.clock()
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
        gobject.GObject.__init__(self)
        self.jobject_id = None
        
        #there appears to be an initial save yourself, asynchronous, which
        #  in my write_file closes the database and causes sporatic failures
        self.initial_save_yourself = False
        
       
        if handle and handle.object_id and handle.object_id != '' and not self.use_db_template:
            _logger.debug('At activity startup, handle.object_id is %s'%handle.object_id)
            self.make_jobject = False
        else:
            self.make_jobject = True
        
        activity.Activity.__init__(self, handle, create_jobject = self.make_jobject)

        if self.make_jobject:
            self.read_file(None)
            self.save()
            _logger.debug('At activity startup, handle.object_id is None. Making a new datastore entry')

        #does activity init execute the read? check if dbobject is reliably open
        if self.DbAccess_object:
            _logger.debug('database object is_open:%s'%self.DbAccess_object.is_open())
        else:
            _logger.debug('after activity init, read has not been called')
        self.make_jobject = False

        """
        self.toolbox = activity.ActivityToolbox(self)
        self.toolbox.connect_after('current_toolbar_changed',self._toolbar_changed_cb)
        self.toolbox.show()
        """
        # Build the activity toolbar.
        self.build_toolbar()

        #following are essential for interface to Help
        self.help_x11 = None
        self.handle = handle
        self.help = Help(self)

        #repaint the screen after a frame event
        self.toolbox.connect_after('expose-event',self.pygame_repaint_cb)
        
        # Build the Pygame canvas.
        _logger.debug('Initializing Pygame Canvas. Startup Clock:%f'%(time.clock()-startup_clock,))
        self._pygamecanvas = sugargame.canvas.PygameCanvas(self)

        # Note that set_canvas implicitly calls read_file when resuming from the Journal.
        _logger.debug('Setting Activity Canvas. Startup Clock:%f'%(time.clock()-startup_clock,))
        self.set_canvas(self._pygamecanvas)
        
        # Create the game instance.
        _logger.debug('Initializing Game. Startup Clock:%f'%(time.clock()-startup_clock,))
        self.game = display.Application(self)

        # Start the game running.
        _logger.debug('Running the Game. Startup Clock:%f'%(time.clock()-startup_clock,))
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
        
        self.edit_toolbar = EditToolbar(self)
        self.toolbox.add_toolbar(_('Edit'), self.edit_toolbar)
        self.edit_toolbar.connect('do-import',
                self.edit_toolbar_doimport_cb)
        self.edit_toolbar.connect('do-initialize',
                self.edit_toolbar_doinitialize_cb)
        self.edit_toolbar.connect('do-rotate',
                self.edit_toolbar_do_rotate_cb)
        self.edit_toolbar.connect('do-stop',
                self.__stop_clicked_cb)
        self.edit_toolbar.show()

        self.use_toolbar = UseToolbar()
        self.toolbox.add_toolbar(_('Output'), self.use_toolbar)
        self.use_toolbar.connect('do-export',
                self.use_toolbar_doexport_cb)
        self.use_toolbar.connect('do-upload',
                self.use_toolbar_do_fullscreen_cb)
        self.use_toolbar.connect('do-slideshow',
                self.use_toolbar_doslideshow_cb)
        self.use_toolbar.connect('do-rewind',
                self.use_toolbar_do_rewind_cb)
        self.use_toolbar.connect('do-pause',
                self.use_toolbar_do_pause_cb)
        self.use_toolbar.connect('do-play',
                self.use_toolbar_do_play_cb)
        self.use_toolbar.connect('do-forward',
                self.use_toolbar_do_forward_cb)
        self.use_toolbar.connect('do-media-stop',
                self.use_toolbar_do_slideshow_stop_cb)
        self.use_toolbar.connect('do-stop',
                self.__stop_clicked_cb)
        self.use_toolbar.show()

        toolbar = gtk.Toolbar()
        self.toolbox.add_toolbar(_('Help'), toolbar)
        toolbar.show()

        self.toolbox.show()
        self.set_toolbox(self.toolbox)
    
    def pygame_repaint_cb(self,widget,event):
        _logger.debug('pygame_repaint_cb')
        gobject.idle_add(self.game.pygame_repaint)

    ################  Help routines
    def _toolbar_changed_cb(self,widget,tab_no):
        if tab_no == HELP_TAB:
            self.help_selected()
            
    def set_toolbar(self,tab):
        self.toolbox.set_current_toolbar(tab)
        #gobject.idle_add(self.game.pygame_repaint)
        self.game.pygame_repaint()
        
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
        rows = self.DbAccess_object.get_album_thumbnails(trash_id)
        number_of_references = 0
        for row in rows:
            jobject_id = str(row['jobject_id'])
            album_rows = self.DbAccess_object.get_albums_containing(jobject_id)
            _logger.debug('album count:%s for jobject_id %s'%(len(album_rows),jobject_id,))
            for album_row in album_rows:
                if album_row['category'] == journal_id: continue
                if album_row['category'] == trash_id: continue
                number_of_references += 1
        if number_of_references > 0:
            number = str(number_of_references)
            detail = _('These images are used in ') + number + _(' other stacks and will be deleted from them also.')
        else:
            detail = _('Are you sure you want to proceed?') 
        self.util.confirmation_alert(detail,\
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
        
        #compact the database
        conn = self.DbAccess_object.connection()
        cursor = conn.cursor()
        cursor.execute('vacuum')
        self.DbAccess_object.closedb()
        self.DbAccess_object = None
        source = os.path.join(os.environ['SUGAR_ACTIVITY_ROOT'],'data','xophoto.sqlite')

        ds = datastore.create()
        default_title = _('No Stacks')
        #ds.metadata['title'] = default_title
        ds.metadata['title'] = dict.get('title',default_title)
        ds.metadata['activity_id'] = dict.get('activity_id')
        ds.metadata['activity'] = 'org.laptop.XoPhoto'
        ds.metadata['mime_type'] = 'application/binary'
        ds.metadata['icon-color'] = dict.get('icon-color')
        dest = os.path.join(os.environ['SUGAR_ACTIVITY_ROOT'],'instance','xophoto.sqlite')
        
        shutil.copyfile(source,dest)
        ds.set_file_path(dest)
        datastore.write(ds,transfer_ownership=True)
        ds.destroy()
        
        #sanity check forces check of integrity of thumbnails and picture data, causes
        #   reload of template if sanity check fails
        self.db_sanity_check = False
        self.read_file(None,initialize=True)
        self.metadata['title'] = default_title
        self.activity_toolbar.title.set_text(default_title)
        #save the newly initialized state
        self.save()
        
        # Start the game running  again.
        self.game.do_startup()
        
    def edit_toolbar_doimport_cb(self, view_toolbar):
        if not self.file_tree:
            self.file_tree = FileTree(self.game.db,self)
        path = self.file_tree.get_path()
        pygame.display.flip()
        if path:
            self.file_tree.copy_tree_to_ds(path)
            Datastore_SQLite(self.game.db).check_for_recent_images()
   
    def edit_toolbar_doinitialize_cb(self, view_toolbar):
        #self.empty_trash_cb(None,gtk.RESPONSE_OK,journal_id) this deletes all images in the journal
        self.read_file(None,initialize=True)

    def edit_toolbar_do_rotate_cb(self, view_toolbar):
        self.game.album_collection.rotate_selected_album_thumbnail_left_90()
        
        
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
            sql = """select pict.*, grp.* from data_cache.picture as pict, groups as grp \
                  where grp.category = ? and grp.jobject_id = pict.jobject_id"""
            cursor = album_object.db.con.cursor()
            cursor.execute(sql,(album_id,))
            rows = cursor.fetchall()
            
            _logger.debug('album to export: %s. Number of pictures found: %s'%(album_name,len(rows),))
            #def __init__(self,rows,db,sources,path):
            exporter = ExportAlbum(self,rows,self.game.db,base_path,new_path)
            exporter.do_export()

    def use_toolbar_do_fullscreen_cb(self,use_toolbar):
        self.fullscreen()
    
    def use_toolbar_doslideshow_cb(self,use_toolbar):
        #self.use_toolbar.slideshow_expose(True)        
        self.use_toolbar.set_running(True)
        self.game.view_slides()
    
    def use_toolbar_do_rewind_cb(self,use_toolbar):
        self.game.set_album_for_viewslides()
        self.game.vs.prev_slide()

    def use_toolbar_do_pause_cb(self,use_toolbar):
        self.use_toolbar.set_running(False)
        self.game.vs.pause()
    
    def use_toolbar_do_play_cb(self,use_toolbar):
        self.use_toolbar.set_running(True)
        self.game.vs.play()
    
    def use_toolbar_do_forward_cb(self,use_toolbar):
        self.game.set_album_for_viewslides()
        self.game.vs.next_slide()
    
    def use_toolbar_do_slideshow_stop_cb(self,use_toolbar):
        self.use_toolbar.set_running(False)
        self.game.vs.stop()
    
    def __stop_clicked_cb(self, button):
        self.interactive_close = True
        self._activity.close()
    
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
    
            
    
    def read_file(self, file_path, initialize=False):
        _logger.debug('started read_file: %s. make_file flag %s. initialize:%s'%(file_path,self.make_jobject,initialize))
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
            if file_path:
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
                
        _logger.debug('completed read_file. DbAccess_jobject is created. Since startup:%f'%(time.clock()-startup_clock,))        
        
    def write_file(self, file_path):
        
        try:
            if self.DbAccess_object and  self.interactive_close:
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
                if self.game:
                    self.game.db = self.DbAccess_object
            except Exception,e:
                _logger.debug('database failed to re-open in write file. error:%s'%e)
                exit()
            _logger.debug('sqlite datbase re-opened successfully')
        

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
        'do-rotate': (gobject.SIGNAL_RUN_FIRST,
                          gobject.TYPE_NONE,
                          ([])),
        'do-stop': (gobject.SIGNAL_RUN_FIRST,
                          gobject.TYPE_NONE,
                          ([]))
    }

    def __init__(self,parent):
        self._parent = parent
        self.jobject_id = None
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
        self.delete_comment.set_tooltip(_("Re-Initialize the Databases -- for startup testing"))
        self.delete_comment.connect('clicked',self.do_initialize)
        self.delete_comment.show()
        self.insert(self.delete_comment,-1)
        
        separator = gtk.SeparatorToolItem()
        separator.props.draw = False
        separator.set_expand(True)
        self.insert(separator, -1)
        separator.show()

        self.title_entry = gtk.Entry()        
        self.title_entry.set_width_chars(15)
        self.title_entry.connect('changed',self._title_changed_cb)
        tool_item = gtk.ToolItem()
        tool_item.set_expand(False)
        tool_item.add(self.title_entry)
        self.title_entry.show()
        self.insert(tool_item, -1)
        tool_item.show()

        self.comment_entry = gtk.Entry()        
        self.comment_entry.set_width_chars(30)
        self.comment_entry.connect('changed',self._comment_changed_cb)
        tool_item = gtk.ToolItem()
        tool_item.set_expand(False)
        tool_item.add(self.comment_entry)
        self.comment_entry.show()
        self.insert(tool_item, -1)
        tool_item.show()

        separator = gtk.SeparatorToolItem()
        separator.props.draw = False
        separator.set_expand(True)
        self.insert(separator, -1)
        separator.show()

        self.add_comment = ToolButton()
        self.add_comment.set_stock_id('gtk-refresh')
        self.add_comment.set_tooltip(_("Rotate 90 degrees left"))
        self.add_comment.connect('clicked', self.do_rotate_cb)
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
        
        self._update_comment_sid = None
        self._update_title_sid = None

    def _title_changed_cb(self,button):
        if not self._update_title_sid:
            self._update_title_sid = gobject.timeout_add_seconds(
                                                1, self.__update_title_cb)
    def __update_title_cb(self):
        self._parent.DbAccess_object.set_title_in_picture(self.jobject_id,self.title_entry.get_text())
        #the following calls to the Datastore introduce too much latency -- do at time of export
        #Datastore_SQLite(self._parent.game.db).update_metadata(\
            #self.jobject_id,title=self.title_entry.get_text())
        self._update_title_sid = None
        return False
        
    def _comment_changed_cb(self,button):
        if not self._update_comment_sid:
            self._update_comment_sid = gobject.timeout_add_seconds(
                                                1, self.__update_comment_cb)
    def __update_comment_cb(self):
        self._parent.DbAccess_object.set_comment_in_picture(self.jobject_id,self.comment_entry.get_text())
        #Datastore_SQLite(self._parent.game.db).update_metadata(\
            #self.jobject_id,description=self.comment_entry.get_text())
        self._update_comment_sid = None
        return False
        
    def set_jobject_id(self,jobject_id):
        self.jobject_id = jobject_id
        title = self._parent.DbAccess_object.get_title_in_picture(self.jobject_id)
        if title:
            self.title_entry.set_text(title)
        else:
            self.title_entry.set_text("")            
        comment = self._parent.DbAccess_object.get_comment_in_picture(self.jobject_id)
        if comment:
            self.comment_entry.set_text(comment)
        else:
            self.comment_entry.set_text("")            
                    
    def doimport_cb(self, button):
        self.emit('do-import')
        
    def do_initialize(self, button):
        self.emit('do-initialize')
    
    def do_rotate_cb(self,button):
        self.emit('do-rotate')
        
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
        'do-rewind': (gobject.SIGNAL_RUN_FIRST,
                          gobject.TYPE_NONE,
                          ([])),
        'do-pause': (gobject.SIGNAL_RUN_FIRST,
                          gobject.TYPE_NONE,
                          ([])),
        'do-play': (gobject.SIGNAL_RUN_FIRST,
                          gobject.TYPE_NONE,
                          ([])),
        'do-media-stop': (gobject.SIGNAL_RUN_FIRST,
                          gobject.TYPE_NONE,
                          ([])),
        'do-forward': (gobject.SIGNAL_RUN_FIRST,
                          gobject.TYPE_NONE,
                          ([])),
        'do-stop': (gobject.SIGNAL_RUN_FIRST,
                          gobject.TYPE_NONE,
                          ([]))
    }

    def __init__(self):
        gtk.Toolbar.__init__(self)
        self.doexport = photo_toolbar.ImageButton()
        fn = os.path.join(os.getcwd(),'assets','stack_export.png')
        tooltip = _('Export to USB/SD/DISK')
        self.doexport.set_image(fn,tip=tooltip)
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
        self.doslideshow.set_stock_id('gtk-media-play')
        self.doslideshow.set_tooltip(_('SlideShow'))
        self.doslideshow.connect('clicked', self.doslideshow_cb)
        self.insert(self.doslideshow, -1)
        self.doslideshow.show()

        self.do_rewind = ToolButton()
        self.do_rewind.set_stock_id('gtk-media-rewind')
        self.do_rewind.set_tooltip(_('Previous Slide'))
        self.do_rewind.connect('clicked', self.do_rewind_cb)
        self.insert(self.do_rewind, -1)
        self.do_rewind.show()
        
        self.do_pause = ToolButton()
        self.do_pause.set_stock_id('gtk-media-pause')
        self.do_pause.set_tooltip(_('Pause'))
        self.do_pause.connect('clicked', self.do_pause_cb)
        self.insert(self.do_pause, -1)
        self.do_pause.set_sensitive(False)
        self.do_pause.show()
        """
        self.do_run = ToolButton()
        self.do_run.set_stock_id('gtk-media-play')
        self.do_run.set_tooltip(_('Play Automatically'))
        self.do_run.connect('clicked', self.do_run_cb)
        self.insert(self.do_run, -1)
        self.do_run.hide()
        """
        self.do_forward = ToolButton()
        self.do_forward.set_stock_id('gtk-media-forward')
        self.do_forward.set_tooltip(_('Next Slide'))
        self.do_forward.connect('clicked', self.do_forward_cb)
        self.insert(self.do_forward, -1)
        self.do_forward.show()

        self.do_slideshow_stop = ToolButton()
        self.do_slideshow_stop.set_stock_id('gtk-media-stop')
        self.do_slideshow_stop.set_tooltip(_('Stop Slide Show '))
        self.do_slideshow_stop.connect('clicked', self.do_slideshow_stop_cb)
        self.insert(self.do_slideshow_stop, -1)
        self.do_slideshow_stop.set_sensitive(False)
        self.do_slideshow_stop.show()

        self.dwell_entry = gtk.Entry()        
        self.dwell_entry.set_width_chars(2)
        tool_item = gtk.ToolItem()
        tool_item.set_expand(False)
        tool_item.add(self.dwell_entry)
        self.dwell_entry.show()
        self.insert(tool_item, -1)
        tool_item.hide()

        separator = gtk.SeparatorToolItem()
        separator.props.draw = True
        separator.set_expand(True)
        self.insert(separator, -1)
        separator.show()

        self.stop = ToolButton('activity-stop', tooltip=_('Stop'))
        self.stop.props.accelerator = '<Ctrl>Q'
        self.stop.connect('clicked', self.dostop_cb)
        self.insert(self.stop, -1)
        self.stop.show()
        
        self.set_running(False)
        
    def slideshow_expose(self,expose):
        if expose:
            self.do_rewind.show()
            self.do_pause.show()
            #self.do_run.show()
            self.do_forward.show()
            self.do_slideshow_stop.show()
        else:
            self.do_rewind.show()
            #self.do_pause.hide()
            #self.do_run.hide()
            self.do_forward.show()
            self.do_slideshow_stop.hide()
            
    def slideshow_set_break(self,show_break):
        if show_break:
            self.doslideshow.set_stock_id('gtk-media-break')
        else:
            self.doslideshow.set_stock_id('gtk-media-play')
    
    def set_running(self,running):
        if running:
            self.doslideshow.set_sensitive(False)
            self.do_forward.set_sensitive(False)
            self.do_pause.set_sensitive(True)
            self.do_rewind.set_sensitive(False)
            self.do_slideshow_stop.set_sensitive(True)
        else:
            self.doslideshow.set_sensitive(True)
            self.do_forward.set_sensitive(True)
            self.do_pause.set_sensitive(False)
            self.do_rewind.set_sensitive(True)
            self.do_slideshow_stop.set_sensitive(True)
            
        

    def doexport_cb(self, button):
        self.emit('do-export')

    def doupload_cb(self, button):
        self.emit('do-upload')

    def doslideshow_cb(self, button):
        self.emit('do-slideshow')

    def do_rewind_cb(self, button):
        self.emit('do-rewind')

    def do_pause_cb(self, button):
        self.emit('do-pause')

    def do_run_cb(self, button):
        self.emit('do-play')

    def do_forward_cb(self, button):
        self.emit('do-forward')

    def do_slideshow_stop_cb(self, button):
        self.emit('do-media-stop')

    def dostop_cb(self, button):
        self.emit('do-stop')


