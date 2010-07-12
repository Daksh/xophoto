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
import gobject

#application imports
from dbphoto import *
from sources import *
from display import *
import display

#pick up activity globals
from xophotoactivity import *

import logging
_logger = logging.getLogger('xophoto')
_logger.setLevel(logging.DEBUG)

class ViewSlides():

    def __init__(self,parent,album_object,db):
        self._parent = parent
        self.album_object = album_object
        self.rows = album_object.rows
        self.db = db
        #self.album_id = ablum_id
        self.index = album_object.thumb_index
        self.paused = False
        self.loop = True
        self.dwell_time = 3
        kwargs = {}
        gobject.timeout_add(1000, self.__timeout)
        self.time_end = 10
        self.current_time = 1 #set so the first call of timeout will initiate action
        self.running = False
        display.screen.fill((0,0,0))
        pygame.display.flip()

    def __timeout(self):
        _logger.debug('timer tick %s'%self.current_time)
        if self.paused or not self.running:
            return True       
        self.current_time -= 1
        if self.current_time == 0:
            self.current_time = self.dwell_time
            self.display_next()
        return True
            
    def display_next(self):
        self.current_time = self.dwell_time
        jobject_id = self.rows[self.index]['jobject_id']
        try:
            ds_obj = datastore.get(jobject_id)
        except Exception,e:
            print('get filename from id error: %s'%e)
            return None
        if ds_obj:
            fn = ds_obj.get_file_path()
            try:
                self.surf = pygame.image.load(fn)
            except Exception,e:
                print('scale_image failed to load %s'%fn)
                return None
            finally:
                ds_obj.destroy()
        self.surf.convert
        display.screen.fill((0,0,0))
        screen = display.screen
        
        #center and scale image in available space
        screen_aspect = float(display.screen_w)/display.screen_h
        screen_rect = display.screen.get_rect()
        image_rect = self.surf.get_rect()
        w,h = self.surf.get_size()
        aspect = float(w)/h
        if screen_aspect < aspect: #sceen is wider than image
            x = display.screen_w
            y = int(x / aspect)
        else:
            y = display.screen_h
            x = int(y * aspect)
        _logger.debug('screen_x:%s screen_y:%s image_x:%s image_y:%s x:%s y:%s'%\
                      (display.screen_w,display.screen_h,w,h,x,y,))
        paint = pygame.transform.scale(self.surf,(x,y))
        image_rect = paint.get_rect()
        if screen_aspect < aspect: #sceen is wider than image
            image_rect.midleft = screen_rect.midleft
        else:
            image_rect.midtop = screen_rect.midtop                    
        display.screen.blit(paint,image_rect)
        pygame.display.flip()
        self.index += 1
        if self.index == len(self.rows):
            if self.loop:
                self.index = 0
       
    def run(self):
        self.running = True
        _logger.debug('started the run loop')
        while self.running:
            # Pump GTK messages.
            while gtk.events_pending():
                gtk.main_iteration()

            # Pump PyGame messages.
            for event in pygame.event.get():
                if event.type in (MOUSEBUTTONDOWN,MOUSEBUTTONUP,MOUSEMOTION):
                    x,y = event.pos
                if  event.type == KEYUP:
                    print event
                    if event.key == K_ESCAPE:
                        self.running = False
                    elif event.key == K_LEFT:
                        if self.index > 1:
                            self.index -= 2
                        self.display_next()
                    elif event.key == K_RIGHT:
                        self.display_next()

    def pause(self):
        self.pause = True
        
    def prev_slide(self):
        if self.index > 1:
            self.index -= 2
        self.display_next()
        
    def next_slide(self):
        self.display_next()
        
    def play(self):
        self.pause = False
        
    def stop(self):
        self.running = False
        'gtk.STOCK_MEDIA_STOP'
        

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
            ds_object = datastore.get(jobject_id)
            if not ds_object:
                _logger.debug('failed to fetch ds object %s'%jobject_id)
                return
            fn = ds_object.get_file_path()
            mime_type = self.db.get_mime_type(jobject_id)
            lookup = {'image/png':'.png','image/jpg':'.jpg','image/jpeg':'.jpg','image/gif':'.gif','image/tif':'.tif'}
            base = os.path.basename(fn).split('.')
            #don't override a suffix that exists
            if len(base) == 1:
                base = base[0] + lookup.get(mime_type,'')
            else:
                base = os.path.basename(fn)
            _logger.debug('exporting %s to %s'%(fn,os.path.join(self.path,base),))
            shutil.copy(fn,os.path.join(self.path,base))
            ds_object.destroy()

                        