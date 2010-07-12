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
from sugar import profile

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
from sinks import *


#pick up activity globals
from xophotoactivity import *

#Display Module globals
mouse_timer = time.time()
in_click_delay = False
in_db_wait = False
in_drag = False
screen_h = 0
screen_w = 0
screen = None

#thickness of scroll bar
thick = 15
sb_padding = 2
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
_logger.debug('color %s'%profile.get_color().to_string())
profile_colors = profile.get_color().to_string()
color_list = profile_colors.split(',')
color_1 = color_list[0]
color_2 = color_list[1]

class PhotoException(Exception):
    def __init__(self,value):
        self.value = value
    def __str__():
        return repr(self.value)
        
class OneThumbnail():
    def __init__(self,rows,db,target,index=0,save_to_db=True):
        """note to myself:
        surface is the square region that is painted on the world
        thumbnail is the subsurface of surface (it's parent)
        thumbnail has its dimensions set to reflect the aspect ratio of image
        """
        self.rows = rows
        self.db = db
        self.target = target
        self.row_index = index
        self.save_to_db = save_to_db
        self.border = 10
        self.x = 200
        self.y = 200
        self.size_x = 800
        self.size_y = 800
        self.surf = None
        self.background = (200,200,200)
        self.scaled = None
        self.from_database = False
        self.thumbnail = None
        
    def paint_thumbnail(self,
                        target,
                        pos_x,
                        pos_y,
                        size_x,
                        size_y,
                        selected):
        """
        Put an image on pygame screen.
        Inputs: 1. cursor pointing to picture records of xophoto.sqlite
                2. Index into cursor
        """
        self.target = target
        self.x = pos_x
        self.y = pos_y
        self.size_x = size_x
        self.size_y = size_y
        if not self.scaled:
            id = self.rows[self.row_index]['jobject_id']
            self.surface = pygame.Surface((size_x,size_y,))
            self.surface.fill(background_color)
            self.scaled = self.scale_image(id,size_x,size_y)
            if not self.scaled: return
            self.thumbnail = self.set_thumbnail_rect_on_surface(self.scaled,self.surface)
        if selected:
            self.select()
        else:
            self.unselect()
        #_logger.debug('image painted at %s,%s'%(pos_x,pos_y,))
        
    def set_thumbnail_rect_on_surface(self,thumb_image,target_surface):
        thumb_rect = thumb_image.get_rect()
        w,h = thumb_rect.size
        _logger.debug('set_thumbnail_rec_on_surface:(%s,%s)'%(w,h,))
        size_x,size_y = target_surface.get_size()
        if h <= 0: return
        aspect = float(w)/h
        if aspect >= 1.0:
            self.subsurface_x = self.border
            self.subsurface_y = (size_y - h) // 2
        else:
            self.subsurface_y = self.border
            self.subsurface_x = (size_x - w) // 2
        thumb_subsurface = self.surface.subsurface((self.subsurface_x,self.subsurface_y,w,h))
        return thumb_subsurface
    
    def unselect(self):
        if not self.thumbnail: return self
        self.surface.fill(background_color)
        self.thumbnail.blit(self.scaled,[0,0])
        self.target.blit(self.surface,[self.x,self.y])
        return self
    
    def select(self):
        if not self.thumbnail: return self
        r,g,b = self.get_rgb(color_2)
        self.surface.fill((r,g,b))
        r,g,b = self.get_rgb(color_1)
        pygame.draw.rect(self.surface,(r,g,b),(0,0,self.size_x,self.size_y),self.border)
        self.thumbnail.blit(self.scaled,[0,0])
        self.target.blit(self.surface,[self.x,self.y])
        return self
        
    def get_rgb(self,hex_no):
        r = int('0x'+hex_no[1:3],16)
        g = int('0x'+hex_no[3:5],16)
        b = int('0x'+hex_no[5:],16)
        return (r,g,b)
        
    def scale_image(self,id, x_size, y_size):
        """
        First check to see if this thumbnail is already in the database, if so, return it
        If not, generate the thumbnail, write it to the database, and return it
        """
        #_logger.debug('scale_image id:%s.x:%s. y:%s'%(id,x_size,y_size,))
        start = time.clock()
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
                #_logger.debug('retrieved thumbnail from database in %f seconds'%(time.clock()-start))
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
        _logger.debug('%f seconds to create the thumbnail'%(time.clock()-start))
        start = time.clock()
        if self.save_to_db:
            
            #write the transform to the database for speedup next time
            self.db.write_transform(id,w,h,self.x_thumb,self.y_thumb,ret)            
            self.from_database = False
            _logger.debug(' and %f seconds to write to database'%(time.clock()-start))
        return ret
    
    def rotate_thumbnail_left_90(self,jobject_id,num=1):
        """strategy for thumbnails: keep track of all the transformations.
            let the thumbnail reflect the sum of all the transformations. But
            apply them on the fly to the full size renditions, and to the uploaded
            version  (still need to satisfy myself that the metadata is the pictures
            is preserved).
        """
        _logger.debug('entered rotate_thumbnail_left_90')
        if not jobject_id: return
        start = time.clock()
        rows = self.db.get_transforms(jobject_id)
        surf = None
        rotate_type_row_id = None
        row_id = None
        for row in rows:
            if row['transform_type'] == 'rotate':
                if row['rotate_left']:
                    num = row['rotate_left']
                num += 1
                rotate_type_row_id = row['id']
                _logger.debug('number of 90 degree rotations:%s'%num)
            elif row['transform_type'] == 'thumb':
                #need the dimensions used to blobify
                scaled_x = row['scaled_x']
                scaled_y = row['scaled_y']
                w = row['original_x']
                h = row['original_y']
                row_id = row['id']
                blob =row['thumb']
                surf = pygame.image.frombuffer(blob,(scaled_x,scaled_y),'RGB')
        if not surf:
            _logger.error('failed to find transform record')
            return None
        while num > 4: num -= 4
        orig_scaled_x = scaled_x
        orig_scaled_y = scaled_y
        rotated_surf = pygame.transform.rotate(surf,90)
        scaled_x,scaled_y = rotated_surf.get_size()
        _logger.debug('originals(:%s,%s) rotated:(%s,%s)'%(orig_scaled_x,orig_scaled_y,scaled_x,scaled_y,))
        self.db.write_transform(jobject_id,w,h,scaled_x,scaled_y,rotated_surf,rec_id=row_id)
        
        #then record the amount of rotation in a transform record of type 'rotate'
        if rotate_type_row_id:
            self.db.write_transform(jobject_id,w,h,scaled_x,scaled_y,rotated_surf,
                                    rec_id=rotate_type_row_id,transform_type='rotate',rotate_left=num)
        else:
            self.db.write_transform(jobject_id,w,h,scaled_x,scaled_y,None,transform_type='rotate',rotate_left=num)
            
        _logger.debug('%f seconds to rotate the thumbnail'%(time.clock()-start))
        self.scaled = None  #force a reload from the database
        self.paint_thumbnail(self.target,self.x,self.y,self.size_x,self.size_y,True)
        return rotated_surf
        
    def position(self,x,y):
        self.x = x
        self.y = y
        
    def size(self, x_size, y_size):
        self.size_x = x_size
        self.size_y = y_size
    
    def set_border(self,b):
        self.border = b

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
        self.origin_row = 0
        self.display_end_index = 0
        self.jobject_id = None
        self.sb = None
        
        #thumbnail_surface is the viewport into thumbnail_world, mapped to screen for each album
        self.thumbnail_world = None
        self.thumbnail_surface = pygame.Surface((screen_w-album_column_width,screen_h)).convert()
        self.thumbnail_surface.fill(background_color)
        self.num_rows = 1
        
        #variable for remembering the state of the thumbnail display
        self.display_start_index = 0
        self.thumb_index = 0
        #OneThumbnail object last_selected
        self.last_selected = None
        
        #figure out what size to paint, assuming square aspect ratio
        screen_max = max(self.screen_height,self.screen_width)
        self.xy_size = screen_max // self.pict_per_row

        
    def paint(self,new_surface=False):
        """
        Put multiple images on pygame screen.
        """
        #make sure we have the most recent list
        is_journal = self.album_id == journal_id
        self.rows = self.db.get_album_thumbnails(self.album_id,is_journal)
        
        #as we fetch the thumbnails record the number for the left column display
        self.db.set_album_count(self.album_id,len(self.rows))
        _logger.debug('number of thumbnails found for %s was %s'%(self.album_id,len(self.rows)))
        
        #protect from an empty database
        #if len(self.rows) == 0: return
        num_rows = int(len(self.rows) // self.pict_per_row) + 1
        if self.thumbnail_world and num_rows == self.num_rows and not new_surface:
            self.repaint()
            return

        self.thumbnail_world = pygame.Surface((screen_w-album_column_width-thick,self.xy_size*num_rows))
        self.thumbnail_world.fill(background_color)
        num_pict = len(self.rows)
        self.num_rows = num_rows        
        _logger.debug('display many thumbnails in range %s,world y:%s'%(num_pict, self.xy_size*num_rows,))
        start_time = time.clock()
        for i in range(num_pict):
            self.pict_dict[i] = OneThumbnail(self.rows,self.db,self.thumbnail_world,i)
            row = i // self.pict_per_row
            pos_x = (i % self.pict_per_row) * self.xy_size
            pos_y = (row  - self.origin_row) * self.xy_size
            selected = self.thumb_index == i
            if selected: self.last_selected = self.pict_dict[i]
            
            #do the heavy lifting
            self.pict_dict[i].paint_thumbnail(self.thumbnail_world,pos_x,pos_y,self.xy_size,self.xy_size,selected)
            
            if not self.pict_dict[i].from_database:
                self.repaint()
                _logger.debug('paint thumbnail %s of %s in %s seconds'%(i,num_pict,(time.clock() - start_time)))
                start_time = time.clock()
                self.release_cycles()
        self.repaint()
        
    def repaint(self):        
        #if not self.thumbnail_world: return
        self.thumbnail_surface = self.thumbnail_panel(self.thumbnail_world)
        screen.blit(self.thumbnail_surface,(album_column_width,0))
        pygame.display.flip()
       
    def release_cycles(self):
        while gtk.events_pending():
            gtk.main_iteration()
        pygame.event.pump()
        pygame.event.get()

    
    def thumbnail_panel(self,world):
        #modeled after ezscrollbar example
        #following scrollRect definition changed to be surface rather than screen relative
        # -- the added origin parameter to ScrollBar helps scrollRect become screen relative
        if not self.sb:
            scrollRect = pygame.Rect((screen_w - album_column_width - thick, 0), (thick, screen_h))
            excludes = ((0, 0), (screen_w-thick,screen_h)) # rect where sb update is a pass
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
                (0,55,100),
                #translator from surface to screen: (conceptualized as origin)
                (album_column_width,0))    
        self.sb.draw(self.thumbnail_surface)
        self.thumbnail_surface.blit(world, (0,0),(self.sb.get_scrolled(),(screen_w-album_column_width,screen_h)))  
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
        elif album_id == trash_id:
            return #let trash image alone
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

    def insert_after(self,after_index, thumbnail_index):
        #get the seq of the row[after_index]
        if after_index < 0:
            adder = -1
        else:
            adder = +1
        seq = self.rows[after_index]['seq']
        id = self.rows[thumbnail_index]['id']
        self.db.update_resequence(id,seq+adder)
        self.paint(True)
        
    def click(self,x,y):
        #map from thumbnail_surface to thumbnail_world
        if self.sb:
            (sb_x,sb_y) = self.sb.get_scrolled()
        else:
            (sb_x,sb_y) = [0,0]
        thumb_index = int(((y + sb_y) // self.xy_size) * self.pict_per_row + \
            (x - album_column_width) // self.xy_size)
        _logger.debug('click index:%s'%thumb_index)
        if thumb_index < len(self.rows):
            self.thumb_index = thumb_index
        else:
            self.thumb_index = len(self.rows) - 1
        self.select_pict(self.thumb_index)
        return self.thumb_index
            
    def get_jobject_id_at_xy(self,x,y):
        #x and y are relative to thumbnail_surface, figure out first mapping to the world
        if self.sb:
            (sb_x,sb_y) = self.sb.get_scrolled()
        else:
            (sb_x,sb_y) = [0,0]
        thumb_index = int(((y + sb_y) // self.xy_size) * self.pict_per_row + (x - album_column_width) // self.xy_size)
        if thumb_index >= len(self.rows):
            thumb_index = len(self.rows)-1
        try:
            id = self.rows[thumb_index]['jobject_id']
            return id
        except:
            return None

    def get_selected_jobject_id(self):
        if self.rows and self.thumb_index and self.thumb_index < len(self.rows):
            return self.rows[self.thumb_index]['jobject_id']
        return None
        

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
        
    def make_visible(self,num):
        if self.sb:
            x,y = self.sb.get_scrolled()
        else:
            x,y = [0,0]
        row = num // self.pict_per_row
        min_y = row * self.xy_size
        if min_y < y:
            self.sb.scroll(-self.xy_size * self.sb.ratio)
        max_y = (row + 1) * self.xy_size
        if max_y > y + screen_h:
            self.sb.scroll(self.xy_size * self.sb.ratio)
        self.repaint()
    
    def scroll_up(self,num=3):
        _logger.debug('scroll up')
        #I started doing this when it wasn't my objective -- has not really been started
        if self.sb:
            x,y = self.sb.get_scrolled()
        else:
            x,y = [0,0]
        self.sb.scroll(num)
        return

    def scroll_down(self,num=-3):
        #I started doing this when it wasn't my objective -- has not really been started
        if self.sb:
            x,y = self.sb.get_scrolled()
        else:
            x,y = [0,0]
        self.sb.scroll(num)
        return

        row = num // self.pict_per_row
        min_y = row * self.xy_size
        if min_y < y:
            self.sb.scroll(-self.xy_size * self.sb.ratio)
        max_y = (row + 1) * self.xy_size
        if max_y > y + screen_h:
            self.sb.scroll(self.xy_size * self.sb.ratio)
        self.repaint()
        
        
    def select_pict(self,num):
        if self.last_selected:
            self.last_selected.unselect()
        if not self.pict_dict.has_key(num): return
        self.make_visible(num)
        self.last_selected = self.pict_dict[num].select()
        if self.large_displayed:
            self.one_large()
        #screen.blit(self.thumbnail_world,(album_column_width,0))
        #self.thumbnail_panel(self.thumbnail_world)
        self.repaint()

    def next(self):
        if self.thumb_index < len(self.rows)-1:
            self.thumb_index += 1
            #self.display_start_index = self.thumb_index
            self.select_pict(self.thumb_index)
            #if self.thumb_index  >= (self.origin_row + self.num_rows) * self.pict_per_row:
                #self.origin_row += 1
            self.paint()
            
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
    predefined_albums = [(journal_id,_('All Pictures')),(trash_id,_('Trash')),] #_('Duplicates'),_('Last Year'),_('Last Month'),]
    def __init__(self,db,activity):
        self.db = db  #pointer to the open database
        self._activity = activity #pointer to the top level activity

        #why both _rows and _objects?
        # rows is returned from a select in seq order
        # objects is storage for local context and paint yourself functionality
        # objects dictionary is accessed via album_id datetime stamp
        self.album_rows = []
        self.album_objects = {}

        self.album_column_width = album_column_width
        self.accumulation_target,id = self.db.get_last_album()
        #self.disp_many = DisplayMany(self.db)
        self.default_name = _("New Stack")
        self.album_index = 0
        self.selected_album_id = journal_id
        self.album_height = album_height
        
        #figure out how many albums can be displayed
        self.max_albums_displayed = screen_h // self.album_height

        #prepare a surface to clear the albums
        self.album_surface = pygame.Surface((album_column_width,screen_h)).convert()
        self.album_surface.fill(background_color)
        
        #if the albums table is empty, populate it from the journal, and initialize
        sql = "select * from groups where category = 'albums'"
        rows,cur = self.db.dbdo(sql)        
        i = 0    
        if len(rows) == 0: #it is not initialized
            #first put the predefined names in the list of albums
            for album_tup in self.predefined_albums:
                sql = """insert into groups (category,subcategory,jobject_id,seq) \
                                  values ('%s','%s','%s',%s)"""%('albums',album_tup[0],album_tup[1],i,)
                self.db.dbtry(sql)
            self.db.commit()
            """this needs to be done whenever new pictures are added to journal so not now
            #then put the journal picutres into the journal album
            rows, cur = self.db.dbdo('select * from data_cache.picture')
            i = 0
            conn = self.db.get_connection()
            cursor = conn.cursor()
            if len(rows)>0:
                for row in rows:
                    sql = "insert into groups (category,subcategory,jobject_id,seq) values ('%s','%s','%s',%s)"%\
                    (self.predefined_albums[0][0],self.predefined_albums[0][1],row['jobject_id'],i,)
                    cursor.execute(sql)
                    i += 20
            conn.commit()
            """
        #initialize the list of album objects from the database
        album_rows = self.db.get_albums()
        _logger.debug('initializing albums. %s found'%len(album_rows))
        for row in album_rows:
            id = str(row['subcategory'])
            self.album_objects[id] = OneAlbum(self.db,id)
        #the initial screen will show the contents of the journal
        #self.display_journal()
        
    def display_thumbnails(self,album_id,new_surface=False):
        """uses the album (a datetime str) as value for category in table groups
        to display thumbnails on the right side of screen"""
        self.selected_album_id = album_id
        #self.album_objects[self.selected_album_id].clear()
        alb_object = self.album_objects.get(self.selected_album_id)
        if alb_object:
            last_selected = alb_object
            start = time.clock()
            alb_object.paint(new_surface)
            alb_object.make_visible(alb_object.thumb_index)
            _logger.debug('took %s to display thumbnails'%(time.clock()-start))
        else:
            _logger.debug('display_thumbnails did not find %s'%album_id)
     
    def display_journal(self):   
        self.display_thumbnails(self.journal_id)
                
    def clear_albums(self):
        global album_background_color
        self.album_surface.fill(album_background_color)
    
    def release_cycles(self):
        while gtk.events_pending():
            gtk.main_iteration()
        pygame.event.pump()
        pygame.event.get()

    

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
        scrollRect = pygame.Rect(album_column_width - thick, 0, thick, screen_h)
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
        """ rows array, will need to change if albums become reorderable"""
        sql = "select * from groups where category = 'albums' order by id"
        rows,cur = self.db.dbdo(sql)
        self.number_of_albums = len(rows)
        #keep a permanent reference to the list of albums            
        self.album_rows = rows

    def click(self,x,y):
        """select the pointed to album"""
        #get the y index
        sb_x,sb_y = self.sb.get_scrolled()
        y_index = (y + sb_y) // self.album_height 
        self.album_index = int(y_index)
        self.refresh_album_rows()
        if  self.album_index >= len(self.album_rows) :
            return None
        self.accumulation_target = self.album_index
        self.paint_albums()
        
        #now change the thumbnail side of the screen
        try:
            album_name = self.album_rows[int(self.album_index)]['subcategory']
            album_title = self.album_rows[int(self.album_index)]['jobject_id']
        except Exception,e:
            album_name = journal_id #the journal
            _logger.debug('exception fetching thumbnails %s'%e)
            return
        self.selected_album_id = album_name
        if album_name == trash_id:
            self._activity.activity_toolbar.empty_journal_button.show()
        else:
            self._activity.activity_toolbar.empty_journal_button.hide()           
        _logger.debug('now display the thumbnails with the album identifier %s'%album_name)
        change_name = True
        for id,name in  self.predefined_albums:
            if album_name == id:
                change_name = False
        if change_name:
            self._activity.activity_toolbar.title.set_text(album_title)
        self.display_thumbnails(album_name,new_surface=True)
        pygame.display.flip()
        
    def add_to_current_album(self,jobject_id,current_album_id=None,name=None):
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
        if current_album_id:
            last_album_timestamp = current_album_id
        else:
            last_album_timestamp,id = self.db.get_last_album()
        self.accumulation_target = last_album_timestamp
        _logger.debug('adding image %s to album %s'%(jobject_id,self.accumulation_target))
        if not self.accumulation_target:
            self.create_new_album(name)
        else:    #see if this is a request to change name
            if jobject_id == '':
                jobject_id = self.accumulation_target

        #insert image to album
        self.db.add_image_to_album(self.accumulation_target, jobject_id)
        
        #make the newly added image the selected image on target album
        album_object = self.album_objects.get(self.accumulation_target)
        if album_object and album_object.last_selected:
            album_object.last_selected.unselect()
            album_object.thumb_index = self.db.get_thumbnail_count(self.accumulation_target) - 1
            _logger.debug('get_thumbnail_count returned %s'%album_object.thumb_index)
            self.db.set_album_count(self.accumulation_target,album_object.thumb_index + 1)


        #ask the album object to re-create the world
        self.album_objects[self.accumulation_target].thumbnail_world = None
        self.album_objects[self.accumulation_target].set_top_image(self.accumulation_target)
            
        #self.display_thumbnails(self.accumulation_target,new_surface=True)
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
        self.album_index = self.get_index_of_album_id(self.accumulation_target)

    def delete_album(self,album_id):
        _logger.debug('delete album action routine. deleting id(timestamp):%s'%album_id)
        """ need to delete the album pointer, the album records, and album object"""
        if self.album_objects.has_key(album_id):
            del self.album_objects[album_id]
        conn = self.db.get_connection()
        cursor = conn.cursor()
        cursor.execute('delete from groups where subcategory = ?',(str(album_id),))
        cursor.execute('delete from groups where category = ?',(str(album_id),))
        cursor.execute('delete from config where name = ? and value = ?',('last_album',str(album_id),))
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
    
    def get_index_of_album_id(self,album_id):
        self.refresh_album_rows()
        for index in range(len(self.album_rows)):            
            if str(self.album_rows[index]['jobject_id']) == album_id: return index
        return -1
    def get_album_id_at_index(self,index):
        if index >= len(self.album_rows):
            return ''
        return str(self.album_rows[index]['subcategory'])

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
        """
        fn = os.path.join(os.getcwd(),'assets','closed_hand.xbm')
        patfn = fn
        fd = open(fn,'r')
        bitstring = fd.read()
        bitpattern = gtk.gdk.bitmap_create_from_data(None,bitstring,48,48)

        fn = os.path.join(os.getcwd(),'assets','closed_hand_mask.xbm')
        maskfn = fn
        fd = open(fn,'r')
        maskstring = fd.read()
        bitmask = gtk.gdk.bitmap_create_from_data(None,maskstring,48,48)
        
        a, b, c, d = pygame.cursors.load_xbm(patfn,maskfn)
        #pygame.mouse.set_cursor(a,b,c,d)
        
        #self._activity.window.set_cursor(gtk.gdk.Cursor(pattern,mask,gtk.gdk.Color(255,255,255),gtk.gdk.Color(0,0,0),24,24))
        """
        self._activity.window.set_cursor(gtk.gdk.Cursor(gtk.gdk.DOTBOX))
            
    def drop_image(self, start_x,start_y,drop_x, drop_y):
        self._activity.window.set_cursor(None)
        
        if drop_x < album_column_width: #we are dropping on album side of screen
            jobject_id = self.album_objects[self.selected_album_id].get_jobject_id_at_xy(start_x,start_y)
            index = self.get_album_index_at_xy(drop_x, drop_y)
            if not index or not jobject_id: return
            
            #if dropped on the trash icon
            if self.get_album_id_at_index(index) == trash_id: #a request to delete
                current_album_id = self.get_current_album_identifier()
                self.db.delete_image(current_album_id,jobject_id)
                self.album_objects[current_album_id].paint(True)
                if  current_album_id == journal_id:
                    self.db.add_image_to_album(self.album_rows[index]['subcategory'], jobject_id)
                self.refresh_album_rows()
                self.paint_albums()
                return
                               
            #if index is larger than max, we want a new album
            _logger.debug('index:%s length of rows:%s  jobject_id %s'%(index,len(self.album_rows),jobject_id,))
            if index > len(self.album_rows)-1:
                self.create_new_album(self.default_name)
                self.album_objects[self.accumulation_target].set_top_image(jobject_id)
            else:
                self.accumulation_target = self.album_rows[index]['subcategory']
                self.db.add_image_to_album(self.accumulation_target, jobject_id)
            self.refresh_album_rows()
            self.paint_albums()
            #guarantee that the next time the thumb nails are painted, the new one is included
            self.album_objects[self.accumulation_target].thumbnail_world = None
            
        #the drop was on thumbnail side of screen, this is a reorder request
        else:
            #map from thumbnail_surface to thumbnail_world, splitting each image vertically in middle
            start_index = self.album_objects[self.selected_album_id].click(start_x, start_y)
            if self.album_objects[self.selected_album_id].sb:
                (sb_x,sb_y) = self.album_objects[self.selected_album_id].sb.get_scrolled()
            else:
                (sb_x,sb_y) = [0,0]
            xy_size = self.album_objects[self.selected_album_id].xy_size
            pict_per_row = self.album_objects[self.selected_album_id].pict_per_row
            thumb_index = int(((drop_y + sb_y) // xy_size) * pict_per_row + \
                math.floor(drop_x - album_column_width-(xy_size//2)) // xy_size)
            if thumb_index > len(self.album_objects[self.selected_album_id].rows) - 1:
                thumb_index =len(self.album_objects[self.selected_album_id].rows) - 1
            _logger.debug('insert after %s this image at index:%s'%(thumb_index,start_index,))
            self.album_objects[self.selected_album_id].insert_after(thumb_index,start_index)
            
    def rotate_selected_album_thumbnail_left_90(self):
        album_object = self.album_objects.get(self.selected_album_id)
        if album_object:
            thumb_object = album_object.pict_dict.get(album_object.thumb_index)
        if thumb_object:
            thumb_object.rotate_thumbnail_left_90(album_object.get_selected_jobject_id())
            pygame.display.flip()
        
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
    
    def remove_alert(self,alert):
        self.no_file_cb(alert,None)
        
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
 
class ProgressAlert(ConfirmationAlert):
    def __init__(self, **kwargs):
        self._parent = kwargs.get('parent')
        ConfirmationAlert.__init__(self, **kwargs)
        self.pb = gtk.ProgressBar()
        #self.pb.set_text('test')
        self.pb.show()
        
        self._hbox.pack_start(self.pb)
        
        self._timeout = 10
        #gobject.timeout_add(1000, self.__timeout)


    def __timeout(self):
        self._timeout -= 1
        self.done_percent((10.0-self._timeout)/10.0)
        if self._timeout == 0:
            self._response(gtk.RESPONSE_OK)
            return False
        return True
        
    def set_fraction(self,fraction):
        self.pb.set_fraction(fraction)
            
    
class Application():
    #how far does a drag need to be not to be ignored?
    drag_threshold = 10
    db = None
    def __init__(self, activity):
        self._activity = activity
        self.in_grab = False
        self.file_tree = None
        self.util = Utilities(self._activity)
        self.album_collection = None
        self.vs = None
    
    def first_run_setup(self):        
        #scan the datastore and add new images as required
        source = os.path.join(os.environ['SUGAR_BUNDLE_PATH'],'startup_images')
        self.file_tree = FileTree(self.db,self._activity)
        self.file_tree.copy_tree_to_ds(source)
        ds_count, added = self.ds_sql.check_for_recent_images()
        number_of_pictures = self.db.get_thumbnail_count(journal_id)
        if number_of_pictures < 10:
            _logger.error('failed to initalize the datastore with at least 10 pictures')
            exit(0)
        
    def change_album_name(self,name):
        if self.album_collection:
            self.album_collection.set_name(name)
            
    def pygame_display(self):
        pygame.display.flip()
    """        
    def show_progress(self,button,id):
        self.pa = ProgressAlert()
        self._activity.add_alert(self.pa)
        self.pa.connect('response',self._response_cb)
       
    def _response_cb(self,alert,response):
        self._activity.remove_alert(self.pa)
    """
    def do_startup(self):
            start = time.clock()
            
            #for testing purposes, use the following to delete all pictures from the journal
            if False:
                self._activity.empty_trash_cb(None,gtk.RESPONSE_OK,journal_id)
                conn = self.db.connection()
                c = conn.cursor()
                c.execute('vacuum')
                conn.commit()
                
            #alert = self.util.alert(_('A quick check of the Journal for new images'),_('PLEASE BE PATIENT'))
            try:
                #this step took 2.5 seconds to add 195 records to picture from datastore on 1.5XO
                #and 1 second when no records were added               
                ds_count, added = self.ds_sql.check_for_recent_images()
            except PhotoException,e:
                #This is a corrupted copy the sqlite database, start over
                self.db.close()
                source = os.path.join(os.getcwd(),'xophoto.sqlite.template')
                dest = os.path.join(os.environ['SUGAR_ACTIVITY_ROOT'],'data','xophoto.sqlite')
                try:
                    shutil.copy(source,dest)
                except Exception,e:
                    _logger.error('database template failed to copy error:%s'%e)
                    exit()
                try:
                    self.DbAccess_object = DbAccess(dest)
                except Exception,e:
                    _logger.error('database failed to open in read file. error:%s'%e)
                    exit()
                self.db = self.DbAccess_object
            _logger.debug('check for recent images took %f seconds'%(time.clock()-start))
                
            #self.util.remove_alert(alert)            

            #if the picture table is empty, populate it from the journal, and initialize
            if ds_count < 10:
                self.first_run_setup()
                
            self.album_collection = DisplayAlbums(self.db, self._activity)
            self.album_collection.paint_albums()
            _logger.debug('took %s to do startup and paint albums'%(time.clock()-start))
            pygame.display.flip()
            start = time.clock()
            self.album_collection.display_journal()
            _logger.debug('took %s to display journal'%(time.clock()-start))

    def view_slides(self):
        #get the album rows for viewing
        self.pygame_focus()
        album_id = self.album_collection.selected_album_id
        album_object = self.album_collection.album_objects.get(album_id,None)
        if album_object:
            if self.vs:
                self._activity.use_toolbar.slideshow_set_break(True)
                return
            else:
                self.vs = ViewSlides(self,album_object,self.db)
                self._activity.use_toolbar.slideshow_set_break(False)
                self.vs.run()
        self.album_collection.paint_albums()
        album_id = self.album_collection.selected_album_id
        thumb_surf_obj = self.album_collection.album_objects.get(album_id,None)
        screen.blit(thumb_surf_obj.thumbnail_surface,(album_column_width,0))
        pygame.display.flip()
            
    def pygame_focus(self):
        self._activity.window.focus()

    def run(self):
        global screen
        global in_click_delay
        global screen_w
        global screen_h
        global in_db_wait
        global in_drag
        if True:
            self.db = self._activity.DbAccess_object
            if not self.db.is_open():
                _logger.debug('failed to open "xophoto.sqlite" database')
                exit()
            self.ds_sql = Datastore_SQLite(self.db)
            
            screen = pygame.display.get_surface()
            info = pygame.display.Info()
            screen_w = info.current_w
            screen_h = info.current_h
            _logger.debug('startup screen sizes w:%s h:%s '%(screen_w,screen_h,))

            # Clear Display
            screen.fill((album_background_color))
            pygame.display.flip()

            self.do_startup()
            
            # Flip Display
            pygame.display.flip()
            
            running = True
            x = 0 #initialize in case there is no mouse event
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
                        elif event.key == K_r and (pygame.key.get_mods() & KMOD_CTRL):# and (pygame.key.get_mods() & KMOD_ALT):
                            _logger.debug('restart database recognized')
                            self._activity.read(none,initialize=True)
                            self._activity.close()
                            running = False
                            pygame.quit()                            

                    #mouse events
                    elif event.type == MOUSEBUTTONDOWN:
                        if event.button < 4 and self.mouse_timer_running(): #this is a double click
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
                        screen = pygame.display.get_surface()
                        info = pygame.display.Info()
                        screen_w = info.current_w
                        screen_h = info.current_h
                        _logger.debug('resized screen sizes w:%s h:%s '%(screen_w,screen_h,))
                        self.do_startup()

                    if x < album_column_width:
                        self.album_collection.sb.update(event)
                        changes = self.album_collection.sb.draw(self.album_collection.album_surface)
                        if len(changes) > 0:
                            changes.append(self.album_collection.album_surface.blit(self.album_collection.world, (0,0),
                                  (self.album_collection.sb.get_scrolled(),(album_column_width-thick,screen_h))))
                            screen.blit(self.album_collection.album_surface,(0,0))
                            pygame.display.update(changes)
                    else:
                        album_id = self.album_collection.selected_album_id
                        thumb_surf_obj = self.album_collection.album_objects.get(album_id,None)
                        if thumb_surf_obj and thumb_surf_obj.sb:
                            thumb_surf_obj.sb.update(event)
                            thumb_changes =  thumb_surf_obj.sb.draw(thumb_surf_obj.thumbnail_surface)
                            if len(thumb_changes) > 0:
                                thumb_surf_obj.thumbnail_surface.blit(thumb_surf_obj.thumbnail_world,
                                                    (0,0),(thumb_surf_obj.sb.get_scrolled(),
                                                    (screen_w-album_column_width, screen_h)))
                                thumb_changes.append(pygame.Rect(album_column_width,0,screen_w-album_column_width,screen_h))                                                
                                screen.blit(thumb_surf_obj.thumbnail_surface,(album_column_width,0))
                                pygame.display.update(thumb_changes)
                        
                
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
            #self._activity._pygamecanvas._socket.window.set_cursor(None)
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
        in_drag = False
        pygame.display.flip()
    
    def process_mouse_click(self,event):
        x,y = event.pos
        butt = event.button
        if butt == 4:
            _logger.debug('button 4s')
            self.album_collection.album_objects[self.album_collection.selected_album_id].scroll_up()
        elif butt == 5:
            self.album_collection.album_objects[self.album_collection.selected_album_id].scroll_down()
        else:     
            l,m,r = pygame.mouse.get_pressed()
            print('mouse single click')
            if x < album_column_width -thick:
                scroll_x,scroll_y = self.album_collection.sb.get_scrolled()
                rtn_val = self.album_collection.click(x,y + scroll_y)
                if not rtn_val:
                    #create a new album
                    pass
            elif x > album_column_width and x < (screen_w - thick):
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
            
