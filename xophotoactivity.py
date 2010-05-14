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

import display
import photo_toolbar

#Application Globals
album_column_width = 200

import logging
_logger = logging.getLogger('xophoto')
_logger.setLevel(logging.DEBUG)
console_handler = logging.StreamHandler()
console_formatter = logging.Formatter('%(name)s %(levelname)s %(funcName)s: %(lineno)d||| %(message)s')
console_handler.setFormatter(console_formatter)
#_logger.addHandler(console_handler)


class XoPhotoActivity(activity.Activity):
    def __init__(self, handle):
        if handle and handle.object_id != '':
            make_jobject = False
        else:
            make_jobject = True
        activity.Activity.__init__(self, handle, create_jobject = make_jobject)
        """
        #for development purposes, copy the sqlite database to the data directory
        source = os.path.join(os.getcwd(),'xophoto.sqlite')
        dest = os.path.join(os.environ['SUGAR_ACTIVITY_ROOT'],'data','xophoto.sqlite')
        if handle.object_id == None and source != dest:
            shutil.copy('./xophoto.sqlite',dest)
        """
        # Build the activity toolbar.
        self.build_toolbar()

        # Create the game instance.
        self.game = display.Application()

        # Build the Pygame canvas.
        self._pygamecanvas = sugargame.canvas.PygameCanvas(self)
        # Note that set_canvas implicitly calls read_file when resuming from the Journal.
        self.set_canvas(self._pygamecanvas)
        
        # Start the game running.
        self._pygamecanvas.run_pygame(self.game.run)
        
    def build_toolbar(self):
        toolbox = photo_toolbar.ActivityToolbox(self)
        activity_toolbar = toolbox.get_activity_toolbar()
        label = gtk.Label(_('New Album Name:'))
        tool_item = gtk.ToolItem()
        tool_item.set_expand(False)
        tool_item.add(label)
        label.show()
        activity_toolbar.insert(tool_item, 0)
        tool_item.show()

        activity_toolbar._add_widget(label)
        activity_toolbar.keep.props.visible = False
        #activity_toolbar.share.props.visible = False
        
        self.edit_toolbar = EditToolbar()
        toolbox.add_toolbar(_('Edit'), self.edit_toolbar)
        self.edit_toolbar.connect('do-import',
                self.edit_toolbar_doimport_cb)
        self.edit_toolbar.show()

        self.use_toolbar = UseToolbar()
        toolbox.add_toolbar(_('Use'), self.use_toolbar)
        self.use_toolbar.connect('do-export',
                self.use_toolbar_doexport_cb)
        self.use_toolbar.connect('do-upload',
                self.use_toolbar_doupload_cb)
        self.use_toolbar.connect('do-slideshow',
                self.use_toolbar_doslideshow_cb)
        self.use_toolbar.show()

        toolbox.show()
        self.set_toolbox(toolbox)

    def edit_toolbar_doimport_cb(self, view_toolbar):
        pass
    
    def use_toolbar_doexport_cb(self,use_toolbar):
        pass
    
    def use_toolbar_doupload_cb(self,use_toolbar):
        pass
    
    def use_toolbar_doslideshow_cb(self,use_toolbar):
        pass
    
    def read_file(self, file_path):
        sql_file = open(file_path, "rb")
        local_path = os.path.join(os.environ['SUGAR_ACTIVITY_ROOT'],'data','xophoto.sqlite')
        f = open(local_path, 'wb')
        _logger.debug('reading from %s and writeing to %s'%(file_path,local_path,))
        try:
            while sql_file:
                block = sql_file.read(4096)
                f.write(block)
        except IOError, e:
            _logger.debug('read sqlite file to local error %s'%e)
        finally:
            f.close
            sql_file.close()
        
    def write_file(self, file_path):
        try:
            local_path = os.path.join(os.environ['SUGAR_ACTIVITY_ROOT'],'data','xophoto.sqlite')
            self.metadata['filename'] = local_path
            self.metadata['mime_type'] = mtype
            #dest = os.path.join(os.environ['SUGAR_ACTIVITY_ROOT'],'instance',f)
            _logger.debug('write_file %s to %s'%(local_path,file_path,))
            shutil.copyfile(local_path,file_path)
            self.set_file_path(dest)
        except Exception,e:
            _logger.debug('write_file exception %s'%e)
            raise e

class EditToolbar(gtk.Toolbar):
    __gtype_name__ = 'EditToolbar'

    __gsignals__ = {
        'needs-update-size': (gobject.SIGNAL_RUN_FIRST,
                              gobject.TYPE_NONE,
                              ([])),
        'do-import': (gobject.SIGNAL_RUN_FIRST,
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
        self.delete_comment.set_stock_id('gtk_stock_delete')
        self.delete_comment.set_tooltip(_("Remove Picture"))
        self.delete_comment.show()
        self.insert(self.delete_comment,-1)
        
        separator = gtk.SeparatorToolItem()
        separator.props.draw = False
        separator.set_expand(True)
        self.insert(separator, -1)
        separator.show()

        self.entry = gtk.Entry()        
        self.entry.set_width_chars(50)
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

        self.stop = ToolButton('activity-stop', tooltip=_('Stop'))
        self.stop.props.accelerator = '<Ctrl>Q'
        #self.stop.connect('clicked', self.__stop_clicked_cb)
        self.insert(self.stop, -1)
        self.stop.show()


    def doimport_cb(self, button):
        self.emit('do-import')

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
                          ([]))
    }

    def __init__(self):
        gtk.Toolbar.__init__(self)
        self.doexport = ToolButton('view-fullscreen')
        self.doexport.set_tooltip(_('Export to USB/SD/FileSystem'))
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
        #self.stop.connect('clicked', self.__stop_clicked_cb)
        self.insert(self.stop, -1)
        self.stop.show()

    def doexport_cb(self, button):
        self.emit('do-import')

    def doupload_cb(self, button):
        self.emit('do-upload')

    def doslideshow_cb(self, button):
        self.emit('do-slideshow')

