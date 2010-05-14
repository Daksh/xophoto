#!/usr/bin/env python
# display.py 
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
import sqlite3
from sqlite3 import dbapi2 as sqlite
import math
import hashlib
import time
from threading import Timer

#application imports
from dbphoto import *
from sources import *


#pick up activity globals
from xophotoactivity import *

#Display Module globals
background_color = (255,255,255)
selected_color = (0,0,255)
mouse_timer = time.time()
in_click_delay = False
in_drag = False

import logging
_logger = logging.getLogger('xophoto.display')

_logger.setLevel(logging.DEBUG)
console_handler = logging.StreamHandler()
console_formatter = logging.Formatter('%(name)s %(levelname)s %(funcName)s: %(lineno)d||| %(message)s')
console_handler.setFormatter(console_formatter)
_logger.addHandler(console_handler)

class PhotoException(Exception):
    def __init__(self,value):
        self.value = value
    def __str__():
        return repr(self.value)
        
class DisplayOne():
    def __init__(self,rows,db,index=0):
        self.rows = rows
        self.db = db
        self.row_index = index
        self.border = 5
        self.x = 200
        self.y = 200
        self.size_x = 800
        self.size_y = 800
        self.surf = None
        self.background = (200,200,200)
        self.scaled = None
        
    def paint(self):
        """
        Put an image on pygame screen.
        Inputs: 1. cursor pointing to picture records of xophoto.sqlite
                2. Index into cursor
        """
        if not self.scaled:
            i = self.db.row_index('jobject_id','picture')
            id = self.rows[self.row_index][i]
            self.surface = pygame.Surface((self.size_x,self.size_y,))
            self.surface.fill(background_color)
            self.scaled = self.scale_image(id,self.size_x,self.size_y)
            if not self.scaled: return
            if self.aspect >= 1.0:
                self.subsurface_x = self.border
                self.subsurface_y = (self.size_y - self.y_thumb) // 2
            else:
                self.subsurface_y = self.border
                self.subsurface_x = (self.size_x - self.x_thumb) // 2
        self.thumbnail = self.surface.subsurface([self.subsurface_x,self.subsurface_y,self.x_thumb,self.y_thumb])
        self.thumbnail.blit(self.scaled,[0,0])
        screen.blit(self.surface,[self.x,self.y])
        
    def scale_image(self,id, x_size, y_size):
        """
        First check to see if this thumbnail is already in the database, if so, return it
        If not, generate the thumbnail, write it to the database, and return it
        """
        max_dim = max(x_size,y_size) - 2*self.border
        sql = 'select * from transforms where jobject_id = "%s"'%id
        rows, cur = self.db.dbdo(sql)
        for row in rows:
            w = row['scaled_x']
            h = row['scaled_y']
            transform_max = max(w,h)            
            _logger.debug('transform rec max: %s request max: %s'%(transform_max,max_dim,))
            if max_dim == transform_max:
                self.x_thumb = w
                self.y_thumb = h
                self.aspect = float(w)/h
                blob =row['thumb']
                surf = pygame.image.frombuffer(blob,(w,h),'RGB')
                _logger.debug('retrieved thumbnail from database')
                return surf
        try:
            ds_obj = datastore.get(id)
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
        w,h = self.surf.get_size()
        self.aspect = float(w)/h
        if self.aspect > 1.0:
            self.x_thumb = int(x_size - 2 * self.border)
            self.y_thumb = int((y_size - 2 * self.border) / self.aspect)
        else:
            self.x_thumb = int((x_size - 2 * self.border) * self.aspect)
            self.y_thumb = int((y_size - 2 * self.border))
        thumb_size = (self.x_thumb,self.y_thumb)
        ret = pygame.transform.scale(self.surf,thumb_size)
        #write the transform to the database for speedup next time
        thumbstr = pygame.image.tostring(ret,'RGB')
        conn = self.db.get_connection()
        cursor = conn.cursor()
        thumb_binary = sqlite3.Binary(thumbstr)
        try:
            cursor.execute("insert into transforms (jobject_id,original_x,original_y,scaled_x,scaled_y,thumb) values (?,?,?,?,?,?)",\
                       (id,w,h,self.x_thumb,self.y_thumb,thumb_binary,))
        except sqlite3.Error,e:
            _logger.debug('write thumbnail error %s'%e)
            return None
        self.db.commit()
        return ret
    
    def position(self,x,y):
        self.x = x
        self.y = y
        
    def size(self, x_size, y_size):
        self.size_x = x_size
        self.size_y = y_size
    
    def set_border(self,b):
        self.border = b

    def select(self):
        self.surface.fill(selected_color)
        self.thumbnail.blit(self.scaled,[0,0])
        screen.blit(self.surface,[self.x,self.y])
        return self
        
    def unselect(self):
        self.surface.fill(background_color)
        self.thumbnail.blit(self.scaled,[0,0])
        screen.blit(self.surface,[self.x,self.y])
        return self
        
        
class DisplayMany():
    """
    Receives array of rows (an album), and open database object refering to
        database:'xophoto.sqlite' which is stored in the journal
    """
    def __init__(self,rows,dbaccess,index=0):
        self.rows = rows
        self.db = dbaccess
        self.pict_dict = {}
        self.screen_width = 1000
        self.screen_height = 700
        self.screen_origin_x = 200
        self.screen_origin_y = 000
        self.pict_per_row = 6
        self.num_rows = 1
        self.display_start_index = index
        self.origin_row = 0
        if index < 0:
            self.display_start_index = 0
            self.origin_row = 0
        elif index >= len(rows):
            self.display_start_index = len(rows) - self.pict_per_row
            self.origin_row = index // self.pict_per_row
        self.selected_index = index
        self.last_selected = None
        
    def paint(self):
        """
        Put multiple images on pygame screen.
        Inputs: 1. cursor pointing to picture records of xophoto.sqlite
                2. Index into cursor
        """
        #protect from an empty database
        if len(self.rows) == 0: return
        #figure out what size to paint, assuming square aspect ratio
        if self.pict_per_row > 0:
            #x_size = math.floor(self.screen_width/self.pict_per_row)
            x_size = self.screen_width // self.pict_per_row
        else:
            raise PhotoException('pict_per_row was zero or negative')
        if x_size > self.screen_width:
            x_size = self.screen_width
        if x_size > self.screen_height:
            x_size = self.screen_height
        y_size = x_size
        num_pict = len(self.rows)
        if num_pict > self.num_rows * self.pict_per_row:
            num_pict = self.num_rows * self.pict_per_row
        self.display_start_index = self.origin_row * self.pict_per_row
        #check for upper bound on rows
        if num_pict + self.display_start_index > len(self.rows):
            num_pict = len(self.rows)-self.display_start_index
            self.last_selected.unselect()
            self.last_selected = None            
            screen.fill((255,255,255))
        _logger.debug('displaymany in range %s,%s'%(self.display_start_index, num_pict + self.display_start_index,))
        for i in range(self.display_start_index, num_pict + self.display_start_index):
            if not self.pict_dict.has_key(i):
                self.pict_dict[i] = DisplayOne(self.rows,self.db,i)
            row = i // self.pict_per_row
            pos_x = self.screen_origin_x + (i % self.pict_per_row) * x_size
            pos_y = self.screen_origin_y + (row  - self.origin_row) * y_size
            self.pict_dict[i].position(pos_x,pos_y)
            #_logger.debug('calling paint with size(%s,%s) and position(%s,%s)'%(x_size,y_size,pos_x,pos_y,))
            self.pict_dict[i].size(x_size,y_size)
            self.pict_dict[i].paint()
        self.select_pict(self.selected_index)
        
    def screen_width(self,width):
        self.screen_width = width
        
    def screen_height(self,height):
        self.screen_height = height
        
    def num_per_row(self,num):
        self.pict_per_row = num
        
    def number_of_rows(self,num):
        self.num_rows = num
        
    def select_pict(self,num):
        if self.last_selected:
            self.last_selected.unselect()
        self.last_selected = self.pict_dict[num].select()

    def next(self):
        if self.selected_index < len(self.rows)-1:
            self.selected_index += 1
            #self.display_start_index = self.selected_index
            if self.selected_index  >= (self.origin_row + self.num_rows) * self.pict_per_row:
                self.origin_row += 1
                self.paint()
            self.select_pict(self.selected_index)
            
    def next_row(self):
        if self.selected_index // self.pict_per_row < len(self.rows) // self.pict_per_row:
            self.selected_index += self.pict_per_row
            if self.selected_index > len(self.rows)-1:
                self.selected_index = len(self.rows)-1
            if self.selected_index  >= (self.origin_row + self.num_rows) * self.pict_per_row:
                self.origin_row += 1
                self.paint()            
            self.select_pict(self.selected_index)
        
        
    def prev(self):
        if self.selected_index > 0:
            self.selected_index -= 1
            if self.selected_index  < (self.origin_row) * self.pict_per_row:
                self.origin_row -= 1
                self.paint()
            self.select_pict(self.selected_index)
        
    def prev_row(self):
        if self.selected_index // self.pict_per_row > 0:
            self.selected_index -= self.pict_per_row        
        if self.selected_index // self.pict_per_row < self.origin_row:
            self.origin_row -= 1
            self.paint()
        self.select_pict(self.selected_index)
        
class DisplayAlbums():
    """Shows the photo albums on left side of main screen, responds to clicks, drag/drop events"""
    
    predefined_albums = [_('Journal'),_('Trash'),_('Duplicates'),_('Last Year'),_('Last Month'),]
    def __init__(self):
        self.num_of_last_rolls = 5
        self.background = (0,0,200)
        self.album_height = 50
        
    def one_album(self,album):
        surf = pygame.Surface((self.album_height,100))
        font = pygame.font.Font(None,50)
        text = font.render(album,0,self.background)
        rect = text.get_rect()
        surf.blit(text,(0,0))
        item = surf.get_rect()
        _logger.debug('one album %s'%album)
        return text
    
    def paint_albums(self):
        for index in range(len(self.predefined_albums)):
            screen.blit(self.one_album(self.predefined_albums[index]),(0,index*self.album_height))            
    
    def do_roll_over(self,x,y, in_drag=False):
        """indicate willingness to be selected"""
        pass
    
    def do_click(self,x,y):
        """select the pointed to item"""
        pass
    
    def do_drag_up(self,x,y):
        """add the dragged item to the selected album"""
        pass
    
    def add_new_album(self,name):
        pass
    
    def delete_album(self,x,y):
        pass
    
    
class Application():
    #how far does a drag need to be not to be ignored?
    drag_threshold = 10
    
    def run(self):
        global screen
        global in_click_delay
        
        self.db = DbAccess('xophoto.sqlite')
        if not self.db.is_open():
            _logger.debug('filed to open "xophoto.sqlite" database')
            return
        """
        conn = sqlite3.connect('xophoto.sqlite')
        #rows generated thusly will have columns that are  addressable as dict of fieldnames
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        """
        if True:
            
            running = True
            do_display = True
                
            pygame.init()
            pygame.display.set_mode((0, 0), pygame.RESIZABLE)
            screen = pygame.display.get_surface()
    
            while running:
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
                            running = False
                            pygame.quit()                            
                        elif event.key == K_LEFT:
                            dm.prev()
                            pygame.display.flip()  
                        elif event.key == K_RIGHT:
                            dm.next()
                            pygame.display.flip()  
                        elif event.key == K_UP:
                            dm.prev_row()
                            pygame.display.flip()  
                        elif event.key == K_DOWN:
                            dm.next_row()
                            pygame.display.flip()
                    
                    #mouse events
                    elif event.type == MOUSEBUTTONDOWN:
                        if self.mouse_timer_running(): #this is a double click
                            self.process_mouse_double_click(x, y)
                            in_click_delay = False
                        else: #just a single click
                            self.process_mouse_click(x, y)
                    elif event.type == MOUSEMOTION:
                        self.drag(x, y)
                    elif event.type == MOUSEBUTTONUP:
                        if in_drag:
                            self.drop(x, y)
                    if event.type == pygame.QUIT:
                        return
                    
                    elif event.type == pygame.VIDEORESIZE:
                        pygame.display.set_mode(event.size, pygame.RESIZABLE)
                
                
                if do_display:
                    do_display = False
                    # Clear Display
                    screen.fill((255,255,255)) #255 for white
                    #fetch the album (array of album records)
                    sql = 'select * from picture'
                    rows,cur = self.db.dbdo(sql)
                    dm = DisplayMany(rows,self.db)
                    dm.num_per_row(10)
                    dm.number_of_rows(5)
                    dm.paint()
                    albums = DisplayAlbums()
                    albums.paint_albums()
                    #albums.paint_albums()
        
                    # Flip Display
                    pygame.display.flip()  
        else:
            print('xophoto sqlite database failed to open')
            
    def drag(self,x,y):
        global in_drag
        l,m,r = pygame.mouse.get_pressed()
        if not l: return
        if not in_drag:
            print('drag started at %s,%s'%(x,y,))
            in_drag = True
            #record the initial position
            self.drag_start_x,self.drag_start_y = x,y
    
    def drop(self,x,y):
        #if the drag is less than threshold, ignore
        if max(abs(self.drag_start_x - x), abs(self.drag_start_y - y)) < self.drag_threshold:
            in_drag = False
            return
        print('drop at %s,%s'%(x,y,))
        pass
    
    def process_mouse_click(self,x,y):
        print('mouse single click')
        pass
                
    def process_mouse_double_click(self,x,y):
        print('double click')
        pass
                
    def mouse_timer_running(self):
        global in_click_delay
        if not in_click_delay:
            Timer(0.5, self.end_delay, ()).start()
            in_click_delay = True
            return False
        return True
    
    def end_delay(self):
        global in_click_delay
        in_click_delay = False
        
        

if __name__ == '__main__':
    ap = Application()
    ap.run()
            
