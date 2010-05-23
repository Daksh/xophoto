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
import datetime

#application imports
from dbphoto import *
from sources import *


#pick up activity globals
from xophotoactivity import *

#Display Module globals
background_color = (210,210,210)
album_background_color = (170,170,170)
album_selected_color = (210,210,210)
selected_color = (0,230,0)
mouse_timer = time.time()
in_click_delay = False
in_drag = False
screen_h = 0
screen_w = 0
album_display_start = 0
album_column_width = 200

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
        self.target.blit(self.surface,[self.x,self.y])
        
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
        if self.save_to_db:
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
        self.target.blit(self.surface,[self.x,self.y])
        return self
        
    def unselect(self):
        self.surface.fill(background_color)
        self.thumbnail.blit(self.scaled,[0,0])
        self.target.blit(self.surface,[self.x,self.y])
        return self
        
        
class DisplayMany():
    """
    Receives  an open database object refering to
        database:'xophoto.sqlite' which is stored in the journal
    """
    def __init__(self,dbaccess,index=0):
        global background_color
        self.db = dbaccess
        self.pict_dict = {}
        self.large_displayed = False
        self.screen_width = screen_w - album_column_width
        self.screen_height = screen_h
        self.picture_surface = pygame.Surface((self.screen_width,self.screen_height))
        self.picture_surface.fill(background_color)
        self.screen_origin_x = 000
        self.screen_origin_y = 000
        self.pict_per_row = 5
        self.num_rows = 4
        self.display_start_index = index
        self.origin_row = 0
        self.last_selected = None
        
    def paint(self,rows,index=0):
        """
        Put multiple images on pygame screen.
        Inputs: 1. cursor pointing to picture records of xophoto.sqlite
                2. Index into cursor
        """
        self.rows = rows
        if index < 0:
            self.display_start_index = 0
            self.origin_row = 0
        elif index >= len(rows):
            self.display_start_index = len(rows) - self.pict_per_row
            self.origin_row = index // self.pict_per_row
        self.selected_index = index
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
        self.xy_size = x_size
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
        self.display_end_index = num_pict + self.display_start_index
        for i in range(self.display_start_index, self.display_end_index):
            if not self.pict_dict.has_key(i):
                self.pict_dict[i] = DisplayOne(self.rows,self.db,self.picture_surface,i)
            row = i // self.pict_per_row
            pos_x = (i % self.pict_per_row) * x_size
            pos_y = (row  - self.origin_row) * y_size
            self.pict_dict[i].position(pos_x,pos_y)
            #_logger.debug('calling paint with size(%s,%s) and position(%s,%s)'%(x_size,y_size,pos_x,pos_y,))
            self.pict_dict[i].size(x_size,y_size)
            self.pict_dict[i].paint()
        screen.blit(self.picture_surface,(album_column_width,0))
        self.select_pict(self.selected_index)
        
    def clear(self):
        #self.picture_surface = pygame.Surface((self.screen_width,self.screen_height))
        self.pict_dict = {}
        self.picture_surface.fill(background_color)
        
    def click(self,x,y):
        #first determine if the x,y pair are within the displayed thumbnails
        thumb_index = int((y // self.xy_size) * self.pict_per_row + (x - album_column_width) // self.xy_size)
        if thumb_index <= self.display_end_index:
            self.selected_index = thumb_index
            self.select_pict(self.selected_index)
            
    def get_jobject_id_at_xy(self,x,y):
        #first determine if the x,y pair are within the displayed thumbnails
        thumb_index = int((y // self.xy_size) * self.pict_per_row + (x - album_column_width) // self.xy_size)
        if thumb_index <= self.display_end_index:
             return self.rows[thumb_index]['jobject_id']
        return None
               
    def toggle(self,x,y):
        if not self.large_displayed:
            self.large_displayed = True
            #restore the number of rows
            self.num_rows_save = self.num_rows 
            self.num_rows = 1
            self.origin_row = self.selected_index // self.pict_per_row
            self.picture_surface.fill(background_color)
            self.one_large()
        else:
            self.large_displayed = False
            self.num_rows = self.num_rows_save
            self.picture_surface.fill(background_color)
        #following call paints the thumnails
        self.paint(self.rows)


    def one_large(self):
        #clear the pictures
        #self.picture_surface.fill(background_color)
        #figure out what size to paint
        y_size = screen_h - self.xy_size
        x_pos =  (screen_w - album_column_width - y_size) / 2
        disp_one = DisplayOne(self.rows,self.db,self.picture_surface,self.selected_index)
        disp_one.position(x_pos,self.xy_size)
        disp_one.size(y_size,y_size)
        disp_one.paint()           
 
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
        if self.large_displayed:
            self.one_large()
        screen.blit(self.picture_surface,(album_column_width,0))

    def next(self):
        if self.selected_index < len(self.rows)-1:
            self.selected_index += 1
            #self.display_start_index = self.selected_index
            if self.selected_index  >= (self.origin_row + self.num_rows) * self.pict_per_row:
                self.origin_row += 1
                self.paint(self.rows,self.selected_index)
            self.select_pict(self.selected_index)
            
    def next_row(self):
        if self.selected_index // self.pict_per_row < len(self.rows) // self.pict_per_row:
            self.selected_index += self.pict_per_row
            if self.selected_index > len(self.rows)-1:
                self.selected_index = len(self.rows)-1
            if self.selected_index  >= (self.origin_row + self.num_rows) * self.pict_per_row:
                self.origin_row += 1
                self.paint(self.rows,self.selected_index)
                self.last_selected = None
            self.select_pict(self.selected_index)
        
        
    def prev(self):
        if self.selected_index > 0:
            self.selected_index -= 1
            if self.selected_index  < (self.origin_row) * self.pict_per_row:
                self.origin_row -= 1
                self.paint(self.rows, self.selected_index)
            self.select_pict(self.selected_index)
        
    def prev_row(self):
        if self.selected_index // self.pict_per_row > 0:
            self.selected_index -= self.pict_per_row        
        if self.selected_index // self.pict_per_row < self.origin_row:
            self.origin_row -= 1
            self.paint(self.rows,self.selected_index)
        self.select_pict(self.selected_index)
        
        
class DisplayAlbums():
    """Shows the photo albums on left side of main screen, responds to clicks, drag/drop events"""
       
    predefined_albums = [('20100521T10:42',_('Journal')),('20100521T11:40',_('Trash')),] #_('Duplicates'),_('Last Year'),_('Last Month'),]
    journal_name = _('Journal')
    def __init__(self,db):
        global album_column_width
        global background_color
        global album_background_color
        global album_selected_color
        self.album_rows = None
        self.album_column_width = album_column_width
        self.db = db  #pointer to the open database
        self.accumulation_target,id = self.db.get_last_album()
        self.disp_many = DisplayMany(self.db)
        self.num_of_last_rolls = 5
        self.text_color = (0,0,200)
        self.selected_color = album_selected_color
        self.background_color = album_background_color
        self.album_height = 190
        self.album_font_size = 30
        self.up_down_jump = 5
        self.selected_index = 0
        #figure out how many albums can be displayed
        if screen_h == 0:
            _logger.debug('screen height not initialized')
            return        
        self.max_albums_displayed = screen_h // self.album_height
        #prepare a surface to clear the albums
        self.album_surface = pygame.Surface((album_column_width,screen_h))
        self.album_surface.fill(background_color)
        
        #if the albums table is empty, populate it from the journal, and initialize
        self.conn = self.db.get_connection()
        sql = "select * from groups"
        rows,cur = self.db.dbdo(sql)        
        i = 0    
        if len(rows) == 0: #it is not initialized
            #first put the predefined names in the list of albums
            for album_tup in self.predefined_albums:
                sql = """insert into groups (category,subcategory,jobject_id,seq) \
                                  values ('%s','%s','%s',%s)"""%('albums',album_tup[0],album_tup[1],i,)
                self.db.dbtry(sql)
                i += 1
            self.db.commit()
            """
            #following block is just to debug the situation where there are more albums than fit in one column
            #this wont be necessary if I use scroll bar
            if len(rows) < 15: #it is not long enough            
                conn = self.db.get_connection()
                cursor = conn.cursor()
                for j in range(15):
                    album = 'Camera Roll %s'%j
                    sql = "insert into groups (category,subcategory,jobject_id,seq) values ('%s','%s','%s',%s)"%('albums',album,'',i,)
                    cursor.execute(sql)
                self.db.commit()
            """
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
                    i += 1
            conn.commit()
            
        #the initial screen will show the contents of the journal
        self.display_journal()
        
    def display_thumbnails(self,album):
        """uses the album as value for category in table groups to display thumbnails on the right side of screen"""
        sql = """select pict.*, grp.* from picture as pict, groups as grp \
              where grp.category = ? and grp.jobject_id = pict.jobject_id order by create_date desc"""
        cursor = self.conn.cursor()
        cursor.execute(sql,(str(album),))
        rows = cursor.fetchall()
        _logger.debug('album to display: %s. Number of pictures found: %s'%(album,len(rows),))
        self.disp_many.clear()
        self.disp_many.last_selected = None
        self.disp_many.paint(rows)
     
    def display_journal(self):   
        self.display_thumbnails('20100521T10:42')
                
    def clear_albums(self):
        global album_background_color
        self.album_surface.fill(album_background_color)
        
    def can_go_up(self):
        if album_display_start > 0:
            return True
        return False
    
    def can_go_down(self):
        if album_display_start < self.number_of_albums - self.up_down_jump:
            return True
        return False
    
    def one_album(self,album,selected=False):
        surf = pygame.Surface((self.album_column_width,self.album_height))
        
        if selected:
            surf.fill(self.selected_color)
        else:
            surf.fill(self.background_color)
        
        fn = os.path.join('startup_images','stack_background.png')
        stack = pygame.image.load(fn)
        frame = pygame.transform.scale(stack,(190,164))
        surf.blit(frame,(0,0))
        font = pygame.font.Font(None,self.album_font_size)
        text = font.render(album,0,self.text_color)
        text_rect = text.get_rect()
        text_rect.midbottom =  surf.get_rect().midbottom
        surf.blit(text,text_rect)
        _logger.debug('one album %s'%album)
        return surf
    
    def paint_albums(self, start=0):
        global album_display_start
        global album_column_width
        screen_row = 0
        if not self.album_rows:
            self.refresh_album_rows()            
        if len(self.album_rows) > 0:
            self.clear_albums()
            if start > 0:
                album_display_start = start
            #the logic for albums is very similar to the paint many thumbnails above
            num_albums = len(self.album_rows)
            if num_albums > album_display_start + self.max_albums_displayed:
                num_albums = num_albums - album_display_start
            if num_albums > self.max_albums_displayed:
                num_albums = self.max_albums_displayed - 2
                #display the up and down arrows at top of album column
                self.album_surface.blit(self.one_album('UP'),(0,0))
                self.album_surface.blit(self.one_album('DOWN'),(0,(self.max_albums_displayed-1)*self.album_height))
                screen_row = 1
            #check for upper bound on rows
            if num_albums + album_display_start > len(self.album_rows):
                num_albums = len(self.album_rows)-album_display_start
            _logger.debug('paint_albums in range %s,%s'%(album_display_start, num_albums + album_display_start,))
            for row_index in range(album_display_start, num_albums + album_display_start):
                selected = (row_index == self.selected_index)
                self.album_surface.blit(self.one_album(self.album_rows[row_index]['jobject_id'],selected),(0,screen_row * self.album_height))
                screen_row += 1
            screen.blit(self.album_surface,(0,0))

    def refresh_album_rows(self):
        sql = "select * from groups where category = 'albums'"
        rows,cur = self.db.dbdo(sql)
        self.number_of_albums = len(rows)
        #keep a permanent reference to the list of albums            
        self.album_rows = rows

    def click(self,x,y):
        """select the pointed to item"""
        global album_display_start
        #get the y index
        y_index = y // self.album_height
        self.selected_index = y_index + album_display_start
        if self.number_of_albums > self.max_albums_displayed:
            self.selected_index -= 1
            if self.selected_index < album_display_start and self.can_go_up():
                album_display_start -= self.up_down_jump
            elif y_index == self.max_albums_displayed-1 and self.can_go_down():
                self.selected_index = album_display_start + self.max_albums_displayed
                album_display_start += self.up_down_jump        
        self.paint_albums()
        #now change the thumbnail side of the screen
        try:
            album_name = self.album_rows[self.selected_index]['subcategory']
        except:
            album_name = '20100521T10:42' #the journal
        _logger.debug('now display the thumbnails with the album identifier %s'%album_name)
        self.display_thumbnails(album_name)
        
    def add_to_current_album(self,jobject_id,name=None):
        """if no current album create one. if name supplied use it
        if there is a current album,and name but no jobject_id, change name
        """
        if not name: name = _("Unnamed Stack")
        conn = self.db.get_connection()
        cursor = conn.cursor()
        if not self.accumulation_target:
            self.accumulation_target = str(datetime.datetime.today())
            _logger.debug('new album is:%s'%self.accumulation_target)
            sql = """insert into groups (category,subcategory,jobject_id,seq) \
                  values ('%s','%s','%s',%s)"""% ('albums',self.accumulation_target,name,0,)
            cursor.execute(sql)
            
            #save off the unique id(timestamp)as a continuing target
            self.db.set_last_album(self.accumulation_target)
        else:    #see if this is a request to change name
            if jobject_id == None:
                sql = 'select * from groups where category = ? and subcategory = ?'
                cursor.execute(sql,('albums',self.accumulation_target))
                rows = cursor.fetchmany()
                if len(rows)>0  : #pick up the name
                    id = rows[0]['id']
                    sql = "update groups set jobject_id = ? where id = ?"
                    cursor.execute(sql,(name,id,))
                    return    
        #we will try to add the same picture only once
        sql = "select * from groups where category = ? and jobject_id = ?"
        cursor.execute(sql,(self.accumulation_target,jobject_id,))
        rows = cursor.fetchmany()
        if len(rows)>0: return
            
        sql = """insert into groups (category,subcategory,jobject_id,seq) \
              values (?,?,?,?)""" 
        cursor.execute(sql,(self.accumulation_target,name,jobject_id,0,))
        self.db.commit()
        #self.display_thumbnails(self.accumulation_target)
        self.refresh_album_rows()
        self.paint_albums()
        
    def change_name_of_current_album(self,name):
        """create a 'current' album (if necessary) and name it"""
        self.add_to_current_album('',name)
            
    def add_album_at_xy(self,x,y):
        jobject_id = self.disp_many.get_jobject_id_at_xy(x,y)
        if jobject_id:
            self.add_to_current_album(jobject_id)
            
    def toggle(self,x,y):
        """change the number of albums displayed"""
        pass
        
    
    def roll_over(self,x,y, in_drag=False):
        """indicate willingness to be selected"""
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
    def __init__(self):    
        self.db = DbAccess('xophoto.sqlite')
        if not self.db.is_open():
            _logger.debug('failed to open "xophoto.sqlite" database')
            exit()
        self.ds_sql = Datastore_SQLite(self.db)
        ds_count, added = self.ds_sql.check_for_recent_images()
        #if the picture table is empty, populate it from the journal, and initialize
        if ds_count < 10: 
            self.first_run_setup()
        
    def first_run_setup(self):
        
        #scan the datastore and add new images as required
        #the following call takes too long during startup, just do it during import
        number_of_pictures = self.ds_sql.scan_images()
        if number_of_pictures < 10: #put 11 images for learning and demo
            source = os.path.join(os.environ['SUGAR_BUNDLE_PATH'],'startup_images')
            self.ds_sql.copy_tree_to_ds(source)
            number_of_pictures = self.ds_sql.scan_images()
            if number_of_pictures < 10:
                _logger.debug('failed to initalize the datastore with at least 10 pictures')
    
    def run(self):
        global screen
        global in_click_delay
        global screen_w
        global screen_h
        
        if True:
            running = True
            do_display = True
            screen = pygame.display.get_surface()
            info = pygame.display.Info()
            screen_w = info.current_w
            screen_h = info.current_h
            _logger.debug('startup screen sizes w:%s h:%s '%(screen_w,screen_h,))
            if screen_h < 400:
                screen_h = 780
                screen_w = 1200               
                #there is a startup bug which causes this intermittentl
                #return

            # Clear Display
            screen.fill((255,255,255)) #255 for white
            pygame.display.flip()  
            """#fetch the album (array of album records)
            sql = 'select * from picture'
            rows,cur = self.db.dbdo(sql)
            self.dm = DisplayMany(rows,self.db)
            self.dm.num_per_row(8)
            self.dm.number_of_rows(6)
            """
            self.albums = DisplayAlbums(self.db)
            self.albums.paint_albums()
            #self.dm.paint()
            #self.dm.display_album('journal')

            # Flip Display
            pygame.display.flip()  

    
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
                            self.albums.disp_many.prev()
                            pygame.display.flip()  
                        elif event.key == K_RIGHT:
                            self.albums.disp_many.next()
                            pygame.display.flip()  
                        elif event.key == K_UP:
                            self.albums.disp_many.prev_row()
                            pygame.display.flip()  
                        elif event.key == K_DOWN:
                            self.albums.disp_many.next_row()
                            pygame.display.flip()
                    
                    #mouse events
                    elif event.type == MOUSEBUTTONDOWN:
                        if self.mouse_timer_running(): #this is a double click
                            self.process_mouse_double_click(x, y)
                            in_click_delay = False
                        else: #just a single click
                            self.process_mouse_click(x, y)
                            pygame.display.flip()
                    elif event.type == MOUSEMOTION:
                        self.drag(x, y)
                    elif event.type == MOUSEBUTTONUP:
                        if in_drag:
                            self.drop(x, y)
                    if event.type == pygame.QUIT:
                        return
                    
                    elif event.type == pygame.VIDEORESIZE:
                        pygame.display.set_mode(event.size, pygame.RESIZABLE)
                        
                
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
        pygame.display.flip()
    
    def process_mouse_click(self,x,y):
        print('mouse single click')
        if x < album_column_width:
            self.albums.click(x,y)
        else:
            self.albums.disp_many.click(x,y)
        pygame.display.flip()
                
    def process_mouse_double_click(self,x,y):
        print('double click')
        if x > album_column_width:
            self.albums.add_album_at_xy(x,y)
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
        

def main():
    pygame.init()
    pygame.display.set_mode((0, 0), pygame.RESIZABLE)
    ap = Application()
    ap.run()

if __name__ == '__main__':
    main()
            
