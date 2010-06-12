#!/usr/bin/env python
# display.py 
#
"""to do list
reorder thumbnails3
change album name2
hover display annotation
function on build 802--4.5
proprietary jobject_id for journal thumbnails5
gtk-idle-add for thumbnail processing6
pygame scrolling1
start slide show roughing out4
"""
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
from sugar.graphics.alert import *
import sys, os
import gtk
import shutil
import sqlite3
from sqlite3 import dbapi2 as sqlite
import math
import hashlib
import time
from threading import Timer
import datetime
import gobject

#application imports
from dbphoto import *
from sources import *
import ezscroll
from ezscroll.ezscroll import  ScrollBar


#pick up activity globals
from xophotoactivity import *

#Display Module globals
mouse_timer = time.time()
in_click_delay = False
in_db_wait = False
in_drag = False
screen_h = 0
screen_w = 0

#thickness of scroll bar
thick = 15
sb_padding = 6
background_color = (210,210,210)
album_background_color = (170,170,170)
album_selected_color = (210,210,210)
selected_color = (0,230,0)
text_color = (0,0,200)
album_font_size = 30
album_column_width = 200
album_height = 190
album_size = (180,165)
album_location = (25,25)
album_aperature = (150,125)

journal_id =  '20100521T10:42'
trash_id = '20100521T11:40'


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
        
class OneThumbnail():
    def __init__(self,rows,db,target,index=0,save_to_db=True):
        self.rows = rows
        self.db = db
        self.target = target
        self.row_index = index
        self.save_to_db = save_to_db
        self.border = 5
        self.x = 200
        self.y = 200
        self.size_x = 800
        self.size_y = 800
        self.surf = None
        self.background = (200,200,200)
        self.scaled = None
        self.from_database = False
        
    def paint_thumbnail(self):
        """
        Put an image on pygame screen.
        Inputs: 1. cursor pointing to picture records of xophoto.sqlite
                2. Index into cursor
        """
        if not self.scaled:
            i = self.db.row_index('jobject_id','picture')
            id = self.rows[self.row_index]['jobject_id']
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
        self.target.blit(self.surface,[self.x,self.y])
        
    def scale_image(self,id, x_size, y_size):
        """
        First check to see if this thumbnail is already in the database, if so, return it
        If not, generate the thumbnail, write it to the database, and return it
        """
        #_logger.debug('scale_image id:%s.x:%s. y:%s'%(id,x_size,y_size,))
        max_dim = max(x_size,y_size) - 2*self.border
        sql = 'select * from data_cache.transforms where jobject_id = "%s"'%id
        rows, cur = self.db.dbdo(sql)
        for row in rows:
            w = row['scaled_x']
            h = row['scaled_y']
            transform_max = max(w,h)            
            #_logger.debug('transform rec max: %s request max: %s'%(transform_max,max_dim,))
            if max_dim == transform_max:
                self.x_thumb = w
                self.y_thumb = h
                self.aspect = float(w)/h
                blob =row['thumb']
                surf = pygame.image.frombuffer(blob,(w,h),'RGB')
                #_logger.debug('retrieved thumbnail from database')
                self.from_database = True
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
            try:
                self.db.create_picture_record(ds_obj.object_id,fn)
            except PhotoException,e:
                _logger.debug('create_picture_record returned exception %s'%e)
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
        if self.save_to_db:
            #write the transform to the database for speedup next time
            thumbstr = pygame.image.tostring(ret,'RGB')
            conn = self.db.get_connection()
            cursor = conn.cursor()
            thumb_binary = sqlite3.Binary(thumbstr)
            try:
                cursor.execute("insert into data_cache.transforms (jobject_id,original_x,original_y,scaled_x,scaled_y,thumb) values (?,?,?,?,?,?)",\
                           (id,w,h,self.x_thumb,self.y_thumb,thumb_binary,))
            except sqlite3.Error,e:
                _logger.debug('write thumbnail error %s'%e)
                return None
            self.db.commit()
            self.from_database = False
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
        self.target.blit(self.surface,[self.x,self.y])
        return self
        
    def unselect(self):
        self.surface.fill(background_color)
        self.thumbnail.blit(self.scaled,[0,0])
        self.target.blit(self.surface,[self.x,self.y])
        return self
        
        
class OneAlbum():
    """
    Receives  an open database object refering to
        database:'xophoto.sqlite' which is stored in the journal
    Displays one album and the associated thumbnails
    """
    def __init__(self,dbaccess,album_id):
        self.db = dbaccess
        self.album_id = album_id
        self.pict_dict = {}
        self.large_displayed = False
        self.screen_width = screen_w - album_column_width - thick
        self.screen_height = screen_h
        self.screen_origin_x = 000
        self.screen_origin_y = 000
        self.pict_per_row = 5
        self.num_rows = 4
        self.origin_row = 0
        self.display_end_index = 0
        self.jobject_id = None
        self.thumbnail_world = None
        self.thumbnail_surface = pygame.Surface((screen_w-album_column_width-thick,screen_h)).convert()
        self.thumbnail_surface.fill(background_color)
        
        #variable for remembering the state of the thumbnail display
        self.display_start_index = 0
        self.thumb_index = 0
        self.last_selected = None
        
        #figure out what size to paint, assuming square aspect ratio
        screen_max = max(self.screen_height,self.screen_width)
        self.xy_size = screen_max // self.pict_per_row

        
    def paint(self):
        """
        Put multiple images on pygame screen.
        """
        #make sure we have the most recent list
        self.rows = self.db.get_album_thumbnails(self.album_id)
        
        #as we fetch the thumbnails record the number for the left column display
        self.db.set_album_count(self.album_id,len(self.rows))
        
        #protect from an empty database
        if len(self.rows) == 0: return
        num_rows = int(len(self.rows) // self.pict_per_row) + 1
        self.thumbnail_world = pygame.Surface((screen_w-album_column_width-thick,self.xy_size*num_rows))
        self.thumbnail_world.fill(background_color)
        y_size = self.xy_size
        x_size = self.xy_size

        num_pict = len(self.rows)
        _logger.debug('display many thumbnails in range %s,%s'%(self.display_start_index, num_pict + self.display_start_index,))
        for i in range(num_pict):
            if not self.pict_dict.has_key(i):
                self.pict_dict[i] = OneThumbnail(self.rows,self.db,self.thumbnail_world,i)
            row = i // self.pict_per_row
            pos_x = (i % self.pict_per_row) * x_size
            pos_y = (row  - self.origin_row) * y_size
            self.pict_dict[i].position(pos_x,pos_y)
            #_logger.debug('calling paint with size(%s,%s) and position(%s,%s)'%(x_size,y_size,pos_x,pos_y,))
            self.pict_dict[i].size(x_size,y_size)
            self.pict_dict[i].paint_thumbnail()
            if not self.pict_dict[i].from_database:
                surf = self.thumbnail_panel(self.thumbnail_world)
                screen.blit(surf,(album_column_width,0))
                pygame.display.flip()
        surf = self.thumbnail_panel(self.thumbnail_world)
        screen.blit(surf,(album_column_width,0))
        screen.blit(self.thumbnail_world,(album_column_width,0))
        self.select_pict(self.thumb_index)
       
    def thumbnail_panel(self,world):
        #modeled after ezscrollbar example
        scrollRect = pygame.Rect(screen_w - album_column_width - thick, 0, screen_w-album_column_width-sb_padding, screen_h)
        excludes = ((0, 0), (screen_w-album_column_width-thick,screen_h)) # rect where sb update is a pass
        group = pygame.sprite.RenderPlain()    
        self.sb = ScrollBar(
            group,
            world.get_height(),
            scrollRect,
            self.thumbnail_surface,
            1,
            excludes,
            4,
            False,
            thick,
            #(170,220,180),
            (255,255,255),
            (200,210,225),
            (240,240,250),
            (0,55,100))    
        self.sb.draw(self.thumbnail_surface)
        self.thumbnail_surface.blit(world, (album_column_width,0),(self.sb.get_scrolled(),(screen_w-album_column_width-thick,screen_h)))  
        return self.thumbnail_surface
    
    def clear(self):
        #self.thumbnail_world = pygame.Surface((self.screen_width,self.screen_height))
        self.pict_dict = {}
        if not self.thumbnail_world: return
        self.thumbnail_world.fill(background_color)
        screen.blit(self.thumbnail_world,(album_column_width,0))

    def one_album_image(self,rows,index,selected=False,image_id=None):
        """album name is title stored in groups.jobject_id where category='albums'
        This should be called after display thumbnails  because the thumbnail routine
        counts the number of images  which this routine displays to the user
        """
        surf = pygame.Surface((album_column_width,album_height))
        
        if image_id:
            self.jobject_id = image_id

        if selected:
            surf.fill(album_selected_color)
        else:
            surf.fill(album_background_color)
        album_id = rows[index]['subcategory']
        count = rows[index]['seq']
        album = rows[index]['jobject_id']

        if album_id == trash_id:
            if count > 0:
                fn = os.path.join('assets','trash_full.png')
            else:
                fn = os.path.join('assets','trash_empty.png')
        else:
            fn = os.path.join('assets','stack_background.png')
        stack = pygame.image.load(fn)
        frame = pygame.transform.scale(stack,album_size)
        stack_image = self.put_image_on_stack(album_id)
        if stack_image:
            frame.blit(stack_image,album_location)
        surf.blit(frame,(0,0))
        font = pygame.font.Font(None,album_font_size)
        text = font.render('%s %s'%(album,count),0,text_color)
        text_rect = text.get_rect()
        text_rect.midbottom =  surf.get_rect().midbottom
        surf.blit(text,text_rect)
        _logger.debug('one album %s'%album)
        return surf
        
    def put_image_on_stack(self,album_id):
        if album_id == journal_id:
            sql = "select * from groups where category = '%s' order by seq asc"%(album_id)
        else:
            sql = "select * from groups where category = '%s' order by seq desc"%(album_id)
        (rows,cur) = self.db.dbdo(sql)
        if len(rows)>0:
            jobject_id = str(rows[0]['jobject_id'])
        else:
            jobject_id = None
            _logger.debug('failed to get jobject_id:%s for display on album side (stack).sql:%s'%(jobject_id,sql,))
            return None
        
        conn = self.db.get_connection()
        cursor = conn.cursor()
        cursor.execute('select * from data_cache.transforms where jobject_id = ?',(jobject_id,))
        rows = cursor.fetchall()
        if len(rows) > 0:
            row = rows[0]
            w = row['scaled_x']
            h = row['scaled_y']
            blob =row['thumb']
            surf = pygame.image.frombuffer(blob,(w,h),'RGB')
            transform_max = max(w,h)            
            #_logger.debug('transform rec max: %s request max: %s'%(transform_max,max_dim,))
            ret = pygame.transform.scale(surf,album_aperature)
            return ret
        
    def set_top_image(self,jobject_id):
        self.jobject_id = jobject_id

    def click(self,x,y):
        #first determine if the x,y pair are within the displayed thumbnails
        thumb_index = int((y // self.xy_size) * self.pict_per_row + \
            (x - album_column_width) // self.xy_size) + self.display_start_index
        if thumb_index <= self.display_end_index:
            self.thumb_index = thumb_index
            self.select_pict(self.thumb_index)
            
    def get_jobject_id_at_xy(self,x,y):
        #first determine if the x,y pair are within the displayed thumbnails
        thumb_index = int((y // self.xy_size) * self.pict_per_row + (x - album_column_width) // self.xy_size)
        if thumb_index <= self.display_end_index:
             return self.rows[thumb_index]['jobject_id']
        return 

    def toggle(self,x,y):
        if not self.large_displayed:
            self.large_displayed = True
            #restore the number of rows
            self.num_rows_save = self.num_rows 
            self.num_rows = 1
            self.origin_row = self.thumb_index // self.pict_per_row
            self.thumbnail_world.fill(background_color)
            self.one_large()
        else:
            self.large_displayed = False
            self.num_rows = self.num_rows_save
            self.thumbnail_world.fill(background_color)
        #following call paints the thumnails
        self.paint()


    def one_large(self):
        #clear the pictures
        #self.thumbnail_world.fill(background_color)
        #figure out what size to paint
        y_size = screen_h - self.xy_size
        x_pos =  (screen_w - album_column_width - y_size) / 2
        disp_one = OneThumbnail(self.rows,self.db,self.thumbnail_world,self.thumb_index)
        disp_one.position(x_pos,self.xy_size)
        disp_one.size(y_size,y_size)
        disp_one.paint_thumbnail() #this one will be larger than a thumbnail           
 
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
        if not self.pict_dict.has_key(num): return
        self.last_selected = self.pict_dict[num].select()
        if self.large_displayed:
            self.one_large()
        screen.blit(self.thumbnail_world,(album_column_width,0))

    def next(self):
        if self.thumb_index < len(self.rows)-1:
            self.thumb_index += 1
            #self.display_start_index = self.thumb_index
            if self.thumb_index  >= (self.origin_row + self.num_rows) * self.pict_per_row:
                self.origin_row += 1
                self.paint()
            self.select_pict(self.thumb_index)
            
    def next_row(self):
        if self.thumb_index // self.pict_per_row < len(self.rows) // self.pict_per_row:
            self.thumb_index += self.pict_per_row
            if self.thumb_index > len(self.rows)-1:
                self.thumb_index = len(self.rows)-1
            if self.thumb_index  >= (self.origin_row + self.num_rows) * self.pict_per_row:
                self.origin_row += 1
                self.paint()
                self.last_selected = None
            self.select_pict(self.thumb_index)
        
        
    def prev(self):
        if self.thumb_index > 0:
            self.thumb_index -= 1
            if self.thumb_index  < (self.origin_row) * self.pict_per_row:
                self.origin_row -= 1
                self.paint()
            self.select_pict(self.thumb_index)
        
    def prev_row(self):
        if self.thumb_index // self.pict_per_row > 0:
            self.thumb_index -= self.pict_per_row        
        if self.thumb_index // self.pict_per_row < self.origin_row:
            self.origin_row -= 1
            self.paint()
        self.select_pict(self.thumb_index)
        
        
class DisplayAlbums():
    """Shows the photo albums on left side of main screen, responds to clicks, drag/drop events"""
    journal_id =  '20100521T10:42'
    trash_id = '20100521T11:40'
    predefined_albums = [(journal_id,_('Journal')),(trash_id,_('Trash')),] #_('Duplicates'),_('Last Year'),_('Last Month'),]
    def __init__(self,db,activity):
        """
        global album_column_width
        global thick
        global background_color
        global album_background_color
        global album_selected_color
        """
        
        #why both _rows and _objects?
        # rows is returned from a select in seq order
        # objects is storage for local context and paint yourself functionality
        # objects dictionary is accessed via album_id datetime stamp
        self.album_rows = []
        self.album_objects = {}
        self.album_column_width = album_column_width
        self.db = db  #pointer to the open database
        self._activity = activity #pointer to the top level activity
        self.accumulation_target,id = self.db.get_last_album()
        #self.disp_many = DisplayMany(self.db)
        self.default_name = _("Unnamed Photos")
        self.num_of_last_rolls = 5
        self.selected_color = album_selected_color
        self.background_color = album_background_color
        self.album_height = album_height
        self.album_index = 0
        self.selected_album_id = journal_id
        #figure out how many albums can be displayed
        if screen_h == 0:
            _logger.debug('screen height not initialized')
            return        
        self.max_albums_displayed = screen_h // self.album_height
        #prepare a surface to clear the albums
        self.album_surface = pygame.Surface((album_column_width,screen_h)).convert()
        self.album_surface.fill(background_color)
        
        #if the albums table is empty, populate it from the journal, and initialize
        sql = "select * from groups"
        rows,cur = self.db.dbdo(sql)        
        i = 0    
        if len(rows) == 0: #it is not initialized
            #first put the predefined names in the list of albums
            for album_tup in self.predefined_albums:
                sql = """insert into groups (category,subcategory,jobject_id,seq) \
                                  values ('%s','%s','%s',%s)"""%('albums',album_tup[0],album_tup[1],i,)
                self.db.dbtry(sql)
                i += 20
            self.db.commit()
            #then put the journal picutres into the journal album
            rows, cur = self.db.dbdo('select * from picture')
            i = 0
            conn = self.db.get_connection()
            cursor = conn.cursor()
            if len(rows)>0:
                for row in rows:
                    sql = """insert into groups (category,subcategory,jobject_id,seq) \
                          values ('%s','%s','%s',%s)"""% (self.predefined_albums[0][0],self.predefined_albums[0][1],row['jobject_id'],i,)
                    cursor.execute(sql)
                    i += 20
            conn.commit()
            
        #initialize the list of album objects from the database
        album_rows = self.db.get_albums()
        _logger.debug('initializing albums. %s found'%len(album_rows))
        for row in album_rows:
            id = str(row['subcategory'])
            self.album_objects[id] = OneAlbum(self.db,id)
        #the initial screen will show the contents of the journal
        self.display_journal()
        
    def display_thumbnails(self,album_id):
        """uses the album (a datetime str) as value for category in table groups
        to display thumbnails on the right side of screen"""
        self.album_objects[self.selected_album_id].clear()
        self.album_objects[self.selected_album_id].last_selected = None        
        alb_object = self.album_objects.get(self.selected_album_id)
        if alb_object:
            alb_object.paint()
        else:
            _logger.debug('display_thumbnails did not find %s'%album_id)
     
    def display_journal(self):   
        self.display_thumbnails(self.journal_id)
                
    def clear_albums(self):
        global album_background_color
        self.album_surface.fill(album_background_color)
        
    

    def album_panel(self,world):
        """modeled after ezscrollbar example"""
        global album_column_width
        global screen_h
        global background_color
        global album_background_color
        global album_selected_color
        global thick
        global sb_padding
        #thick = 15
        scrollRect = pygame.Rect(album_column_width - thick, 0, album_column_width-sb_padding, screen_h)
        excludes = ((0, 0), (album_column_width-thick,screen_h)) # rect where sb update is a pass
        group = pygame.sprite.RenderPlain()    
        self.sb = ScrollBar(
            group,
            world.get_height(),
            scrollRect,
            self.album_surface,
            1,
            excludes,
            4,
            False,
            thick,
            #(170,220,180),
            (255,255,255),
            (200,210,225),
            (240,240,250),
            (0,55,100))    
        self.sb.draw(self.album_surface)
        self.album_surface.blit(world, (0,0),(self.sb.get_scrolled(),(album_column_width-thick,screen_h)))  
        return self.album_surface    
    
    def paint_albums(self):
        global album_column_width
        screen_row = 0
        self.refresh_album_rows()            
        if len(self.album_rows) > 0:
            self.clear_albums()
            self.world = pygame.Surface((album_column_width, 8 * self.album_height)) #len(self.album_rows) * self.album_height))
            self.world.fill(album_background_color)

            num_albums = len(self.album_rows)
            for row_index in range(num_albums ):
                selected = (row_index == self.album_index)
                album_id = self.album_rows[row_index]['subcategory']
                album_object = self.album_objects[album_id]
                album_image = album_object.one_album_image(self.album_rows, row_index, selected)
                self.world.blit(album_image,(0,screen_row * self.album_height))
                screen_row += 1
            surf = self.album_panel(self.world)
            screen.blit(surf, (0,0))
            pygame.display.flip()
            
    def refresh_album_rows(self):
        sql = "select * from groups where category = 'albums' order by id"
        rows,cur = self.db.dbdo(sql)
        self.number_of_albums = len(rows)
        #keep a permanent reference to the list of albums            
        self.album_rows = rows

    def click(self,x,y):
        """select the pointed to item"""
        #get the y index
        sb_x,sb_y = self.sb.get_scrolled()
        y_index = (y + sb_y) // self.album_height 
        self.album_index = int(y_index)
        self.accumulation_target = self.album_index
        self.refresh_album_rows()
        if  self.album_index >= len(self.album_rows) :
            return None
            
        #now change the thumbnail side of the screen
        try:
            album_name = self.album_rows[int(self.album_index)]['subcategory']
            album_title = self.album_rows[int(self.album_index)]['jobject_id']
        except Exception,e:
            album_name = journal_id #the journal
            _logger.debug('exception fetching thumbnails %s'%e)
            return
        self.selected_album_id = album_name
        _logger.debug('now display the thumbnails with the album identifier %s'%album_name)
        self._activity.activity_toolbar.title.set_text(album_title)
        self.display_thumbnails(album_name)
        
    def add_to_current_album(self,jobject_id,name=None):
        """if no current album create one. if name supplied use it
        if there is a current album,and name but no jobject_id, change name
        NOTE: Albums are stored in the table - 'groups' as follows:
           --category = 'albums'
           --subcategory = <unique string based upon date-time album was created
              (This is then used as a value for category to get all pictures in album)
           --Album name = Stored in the jobject_id field (when category = 'albums')
           --seq = modified as the order of the pictures is modified
                    (seq = count of albums when category='albums')
        """
        if not name: name = self.default_name
        self.accumulation_target,id = self.db.get_last_album()
        if not self.album_objects.has_key(self.accumulation_target):
            self.accumulation_target = None
        _logger.debug('last album id was %s and id was %s'%(self.accumulation_target,id))
        if not self.accumulation_target:
            self.create_new_album(name)
        else:    #see if this is a request to change name
            if jobject_id == '':
                jobject_id = self.accumulation_target
        self.db.add_image_to_album(self.accumulation_target, jobject_id)
        self.album_objects[self.accumulation_target].set_top_image(self.accumulation_target)
            
        #self.display_thumbnails(self.accumulation_target)
        self.paint_albums()
        
    def set_name(self,name):
        self.db.create_update_album(self.album_rows[self.album_index]['subcategory'],name)
        self.paint_albums()
        pygame.display.flip()
        
        
    def create_new_album(self,name):
        if not name: name = self.default_name
        self.accumulation_target = str(datetime.datetime.today())
        _logger.debug('new album is:%s'%self.accumulation_target)
        self.db.create_update_album(self.accumulation_target,name)
        self.album_objects[self.accumulation_target] = (OneAlbum(self.db,self.accumulation_target))
        #save off the unique id(timestamp)as a continuing target
        self.db.set_last_album(self.accumulation_target)
        self.paint_albums()

    def delete_album(self,album_id):
        _logger.debug('delete album action routine. deleting id(timestamp):%s'%album_id)
        """ need to delete the album pointer, the album records, and album object"""
        if self.album_objects.has_key(album_id):
            del self.album_objects[album_id]
        conn = self.db.get_connection()
        cursor = conn.cursor()
        cursor.execute('delete from groups where subcategory = ?',(str(album_id),))
        cursor.execute('delete from groups where category = ?',(str(album_id),))
        conn.commit()
        self.album_index = 0
        self.selected_album_id = self.journal_id
        self.display_thumbnails(self.selected_album_id)
        self.paint_albums()
        

    def change_name_of_current_album(self,name):
        """create a 'current' album (if necessary) and name it"""
        self.add_to_current_album('',name)
            
    def get_current_album_identifier(self):
        return   str(self.album_rows[self.album_index]['subcategory'])

    def get_current_album_name(self):
        return   str(self.album_rows[self.album_index]['jobject_id'])
    
    def get_album_index_at_xy(self,x,y):
        if x > album_column_width - thick: return None
        index = y // self.album_height
        return int(index)
            
    def add_to_album_at_xy(self,x,y):
        jobject_id = self.album_objects[self.selected_album_id].get_jobject_id_at_xy(x,y)
        if jobject_id:
            self.add_to_current_album(jobject_id)
        else:
            _logger.debug('could not find jobject_id in add_to_aqlbum_at_xy')
            
    def start_grab(self,x,y):
        self.start_grab_x = x
        self.start_grab_y = y
        #change the cursor some way
        self._activity.window.set_cursor(gtk.gdk.Cursor(gtk.gdk.TOP_LEFT_CORNER))
            
    def drop_image(self, img_x,img_y,album_x, album_y):
        self._activity.window.set_cursor(None)
        index = self.get_album_index_at_xy(album_x, album_y)
        jobject_id = self.album_objects[self.selected_album_id].get_jobject_id_at_xy(img_x,img_y)
        if not index or not jobject_id: return
        #if index is larger than max, we want a new album
        _logger.debug('index:%s length of rows:%s  jobject_id %s'%(index,len(self.album_rows),jobject_id,))
        if index > len(self.album_rows)-1:
            self.create_new_album(self.default_name)
            self.album_objects[self.accumulation_target].set_top_image(jobject_id)
        else:
            self.db.add_image_to_album(self.album_rows[index]['subcategory'], jobject_id)
        #self.display_thumbnails(self.accumulation_target)
        self.refresh_album_rows()
        self.paint_albums()

    def toggle(self,x,y):
        """change the number of albums displayed"""
        pass
        
    
    def roll_over(self,x,y, in_drag=False):
        """indicate willingness to be selected"""
        pass
    
    def do_drag_up(self,x,y):
        """add the dragged item to the selected album"""
        pass
    
    
        
    #####################            ALERT ROUTINES   ##################################
class Utilities():
    def __init__(self,activity):
        self._activity = activity
    
    def alert(self,msg,title=None):
        alert = NotifyAlert(0)
        if title != None:
            alert.props.title = title
        alert.props.msg = msg
        alert.connect('response',self.no_file_cb)
        self._activity.add_alert(alert)
        return alert
        
    def no_file_cb(self,alert,response_id):
        self._activity.remove_alert(alert)
        pygame.display.flip
        
    from sugar.graphics.alert import ConfirmationAlert
  
    def confirmation_alert(self,msg,title=None,confirmation_cb = None):
        alert = ConfirmationAlert()
        alert.props.title=title
        alert.props.msg = msg
        alert.callback_function = confirmation_cb
        alert.connect('response', self._alert_response_cb)
        self._activity.add_alert(alert)
        return alert

    #### Method: _alert_response_cb, called when an alert object throws a
                 #response event.
    def _alert_response_cb(self, alert, response_id):
        #remove the alert from the screen, since either a response button
        #was clicked or there was a timeout
        this_alert = alert  #keep a reference to it
        self._activity.remove_alert(alert)
        pygame.display.flip()
        #Do any work that is specific to the type of button clicked.
        if response_id is gtk.RESPONSE_OK and this_alert.callback_function != None:
            this_alert.callback_function (this_alert, response_id)
            
    
class Application():
    #how far does a drag need to be not to be ignored?
    drag_threshold = 10
    db = None
    def __init__(self, activity):
        self._activity = activity
        self.in_grab = False
        self.file_tree = None
    
    def first_run_setup(self):        
        #scan the datastore and add new images as required
        #the following call takes too long during startup, just do it during import
        number_of_pictures = self.ds_sql.scan_images()
        if number_of_pictures < 10: #put 11 images for learning and demo
            source = os.path.join(os.environ['SUGAR_BUNDLE_PATH'],'startup_images')
            self.file_tree = FileTree(self.db)
            self.file_tree.copy_tree_to_ds(source)
            number_of_pictures = self.ds_sql.scan_images()
            if number_of_pictures < 10:
                    _logger.debug('failed to initalize the datastore with at least 10 pictures')
        
    def change_album_name(self,name):
        if self.album_collection:
            self.album_collection.set_name(name)
            
    def pygame_display(self):
        pygame.display.flip()
            
    def run(self):
        global screen
        global in_click_delay
        global screen_w
        global screen_h
        global in_db_wait
        global in_drag
        if True:
            #moved the database functionality here because of sync problems with journal
            if not self._activity.DbAccess_object:  #we need to wait for the read-file to finish
                Timer(5.0, self.end_db_delay, ()).start()
                in_db_wait = True
                while not self._activity.DbAccess_object and in_db_wait:
                    gtk.main_iteration()
                if not self._activity.DbAccess_object:
                    _logger.error('db object not open after timeout in Appplication.run')
                    exit()
                    
            self.db = self._activity.DbAccess_object
            if not self.db.is_open():
                _logger.debug('failed to open "xophoto.sqlite" database')
                exit()
            self.ds_sql = Datastore_SQLite(self.db)
            try:
                ds_count, added = self.ds_sql.check_for_recent_images()
            except PhotoException,e:
                #This is a corrupted copy the sqlite database, start over
                self.db.close()
                source = os.path.join(os.getcwd(),'xophoto.sqlite.template')
                dest = os.path.join(os.environ['SUGAR_ACTIVITY_ROOT'],'data','xophoto.sqlite')
                try:
                    shutil.copy(source,dest)
                except Exception,e:
                    _logger.debug('database template failed to copy error:%s'%e)
                    exit()
                try:
                    self.DbAccess_object = DbAccess(dest)
                except Exception,e:
                    _logger.debug('database failed to open in read file. error:%s'%e)
                    exit()
                self.db = self.DbAccess_object
                
        
            running = True
            do_display = True
            screen = pygame.display.get_surface()
            info = pygame.display.Info()
            screen_w = info.current_w
            screen_h = info.current_h
            _logger.debug('startup screen sizes w:%s h:%s '%(screen_w,screen_h,))

            # Clear Display
            screen.fill((255,255,255)) #255 for white
            x = 0
            pygame.display.flip()
            self.util = Utilities(self._activity)
            #self.util.alert("this is a test")
            #if the picture table is empty, populate it from the journal, and initialize
            if ds_count < 10:
                
                self.first_run_setup()
                
            self.album_collection = DisplayAlbums(self.db, self._activity)
            self.album_collection.paint_albums()

            # Flip Display
            pygame.display.flip()
            
            # start processing any datastore images that don't have thumbnails
            #gobject.idle_add(self.ds_sql.make_one_thumbnail)

    
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
                            self.album_collection.album_objects[self.album_collection.selected_album_id].prev()
                            pygame.display.flip()  
                        elif event.key == K_RIGHT:
                            self.album_collection.album_objects[self.album_collection.selected_album_id].next()
                            pygame.display.flip()  
                        elif event.key == K_UP:
                            self.album_collection.album_objects[self.album_collection.selected_album_id].prev_row()
                            pygame.display.flip()  
                        elif event.key == K_DOWN:
                            self.album_collection.album_objects[self.album_collection.selected_album_id].next_row()
                            pygame.display.flip()
                    
                    #mouse events
                    elif event.type == MOUSEBUTTONDOWN:
                        if self.mouse_timer_running(): #this is a double click
                            self.process_mouse_double_click( event)
                            in_click_delay = False
                        else: #just a single click
                            self.process_mouse_click(event)
                            pygame.display.flip()
                    elif event.type == MOUSEMOTION:
                        self.drag(event)
                    elif event.type == MOUSEBUTTONUP:
                        if in_drag:
                            self.drop(event)
                    if event.type == pygame.QUIT:
                        return
                    
                    elif event.type == pygame.VIDEORESIZE:
                        pygame.display.set_mode(event.size, pygame.RESIZABLE)

                    if x < album_column_width:
                        self.album_collection.sb.update(event)
                    changes = self.album_collection.sb.draw(self.album_collection.album_surface)
                    if len(changes) > 0:
                        changes.append(self.album_collection.album_surface.blit(self.album_collection.world, (0,0),
                              (self.album_collection.sb.get_scrolled(),(album_column_width-thick,screen_h))))
                    screen.blit(self.album_collection.album_surface,(0,0))
                    pygame.display.update(changes)
                        
                
    def drag(self,event):
        global in_drag
        x,y = event.pos
        l,m,r = pygame.mouse.get_pressed()
        self.last_l = l
        self.last_r = r
        if not l: return
        if not in_drag:
            print('drag started at %s,%s'%(x,y,))
            in_drag = True
            #record the initial position
            self.drag_start_x,self.drag_start_y = x,y
        elif x < album_column_width -thick:
            self._activity.window.set_cursor(gtk.gdk.Cursor(gtk.gdk.PLUS))
            
    
    def drop(self,event):
        global in_drag
        x,y = event.pos
        #if the drag is less than threshold, ignore
        if max(abs(self.drag_start_x - x), abs(self.drag_start_y - y)) < self.drag_threshold:
            in_drag = False
            return
        print('drop at %s,%s'%(x,y,))
        if in_drag and self.last_l:
            self.album_collection.drop_image(self.drag_start_x,self.drag_start_y,x,y)
        pygame.display.flip()
    
    def process_mouse_click(self,event):
        x,y = event.pos
        l,m,r = pygame.mouse.get_pressed()
        print('mouse single click')
        if x < album_column_width -thick:
            scroll_x,scroll_y = self.album_collection.sb.get_scrolled()
            rtn_val = self.album_collection.click(x,y + scroll_y)
            if not rtn_val:
                #create a new album
                pass
        elif x > album_column_width:
            if l:
                self.album_collection.album_objects[self.album_collection.selected_album_id].click(x,y)
            elif r: 
                self.in_grab = True 
                self.album_collection.start_grab(x,y)
        pygame.display.flip()
                
    def process_mouse_double_click(self,event):
        x,y = event.pos
        print('double click')
        if x > album_column_width:
            self.album_collection.add_to_album_at_xy(x,y)
        pygame.display.flip()
                
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
    
    def end_db_delay(self):    
        global in_db_wait
        in_db_wait = False
        
class shim():
    def __init__(self):
        self.DbAccess_object = DbAccess('/home/olpc/.sugar/default/org.laptop.PyDebug/data/pydebug/playpen/XoPhoto.activity/xophoto.sqlite')
    

def main():
    pygame.init()
    pygame.display.set_mode((0, 0), pygame.RESIZABLE)
    dummy = shim()
    ap = Application(dummy)
    ap.run()

if __name__ == '__main__':
    local_path = os.path.join(os.environ['SUGAR_ACTIVITY_ROOT'],'data','xophoto.sqlite')
    source = 'xophoto.sqlite'
    shutil.copy(source,local_path)
    #DbAccess_object = DbAccess(local_path)

    main()
            
