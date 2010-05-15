#!/usr/bin/env python
# dbphoto.py
# The sqlite database access functions for the XoPhoto application
#
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

import os
from  sqlite3 import dbapi2 as sqlite
from sqlite3 import *
import sqlite3
import hashlib

#pick up activity globals
from xophotoactivity import *

#define globals related to sqlite
sqlite_file_path = None

import logging
_logger = logging.getLogger('xophoto')
_logger.setLevel(logging.DEBUG)
console_handler = logging.StreamHandler()
console_formatter = logging.Formatter('%(name)s %(levelname)s %(funcName)s: %(lineno)d||| %(message)s')
console_handler.setFormatter(console_formatter)
_logger.addHandler(console_handler)


class DbAccess():
    con = None
    cursor = None
    def __init__(self,fn):
        self.opendb(fn)
        self.added = 0
    
    def opendb(self,dbfilename):
        try:
            _logger.debug('opening database cwd:%s filename %s'%(os.getcwd(),dbfilename,))
            self.con = sqlite3.connect(dbfilename)
            self.con.row_factory = sqlite3.Row
            self.con.text_factory = str
            #rows generated thusly will have columns that are  addressable as dict of fieldnames
            self.cur = self.con.cursor()
        except IOError,e:
            _logger.debug('open database failed. exception :%s '%(e,))
            return None
        return self.cur
    
    def is_open(self):
        if self.con: return True
        return False

    def closedb(self):
        if self.con:self.con.close()
        
    def get_mime_list(self):
        mime_list =[]
        self.cur.execute('select * from config where name ="mime_type"')
        rows = self.cur.fetchall()
        for m in rows:
            mime_list.append(m[2])
        return mime_list
    
    def get_album_list(self):
        sql = 'select max duplicate from picture group by album'
        album_list,cur = self.dbdo(sql)
        if len(album_list) == 0:
            _logger.debug('failed to retrieve albums')
            return None
        return album_list
    
    def create_picture_record(self,object_id, fn):
        """create a record in picture pointing to unique pictures in the journal.
           Use md5 checksum to test for uniqueness
           For non unique entries, add a copy number (fieldname:duplicate) greater than 0
        """
        _logger.debug('create_picture_record object_id:%s  file: %s'%(object_id,fn,))
        #if object_id == '': return
        
        #we'll calculate the md5, check it against any pictures, and store it away
        md5_hash = Md5Tools().md5sum(fn)
        sql = "select * from picture where md5_sum = '%s'"%(md5_hash,)
        self.cur.execute(sql)
        rows_md5 = self.cur.fetchall()
        if len(rows_md5) >0:
            pass
            #_logger.debug('duplicate picture, ojbect_id %s path: %s'%(object_id,fn,))        
        sql = "select * from picture where jobject_id = '%s'"%(object_id,)
        self.cur.execute(sql)
        rows = self.cur.fetchall()
        #_logger.debug('rowcount %s object_id %s'%(len(rows),object_id))
        #the object_id is supposed to be unique, so add only new object_id's
        if len(rows) == 0:
            info = os.stat(fn)
            sql = """insert into picture \
                  (in_ds, mount_point, orig_size, create_date,jobject_id, md5_sum, duplicate) \
                  values (%s,'%s',%s,'%s','%s','%s',%s)""" % \
                  (1, fn, info.st_size, info.st_ctime, object_id, md5_hash,len(rows_md5),)
            _logger.debug('sql: %s'%sql)
            self.con.execute(sql)                

    def clear_in_ds(self):
        self.con.execute('update picture set in_ds = 0')
    
    def delete_not_in_ds(self):
        self.con.execute('delete from picture where in_ds = 0')

    def check_in_ds(self,fullpath,size):
        sql = "select * from picture where mount_point = '%s' and orig_size = %s"%(fullpath,size,)
        self.cur.execute(sql)
        rows = self.cur.fetchall()
        if len(rows)>0: return True
        return False

    def table_exists(self,table):
        try:
            sql = 'select  * from %s'%table
            self.con.execute(sql)
            return True
        except:
            return False

    def commit(self):
        if self.con:self.con.commit()

    def set_connection(self,connection,cursor):
        self.con = connection
        self.cur = cursor

    def get_connection(self):
        """ return connection """
        return self.con

    def numberofrows(self,table):
        sql = "SELECT count(*) from %s"%table
        rows,cur = self.dbdo(sql)
        if rows:
            return rows[0][0]
        return 0

    def fieldlist(self,table):
        list=[]     #accumulator for model
        cur = self.con.cursor()
        cur.execute('select * from %s'%table)
        if cur:
            for field in cur.description:
                list.append(field[0])
        return list
    
    def row_index(self,field,table):
        field_list = self.fieldlist(table)
        return field_list.index(field)

    def tablelist(self):
        list=[]     #accumulator for
        sql =  "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        rows,cur = self.dbdo(sql)
        if rows:
            for row in rows:
                list.append(row[0])
        return list

    def dbdo(self,sql):
        """ execute a sql statement or definition, return rows and cursor """
        try:
            cur = self.con.cursor()
            cur.execute(sql)
            return cur.fetchall(), cur
            #self.con.commit()
        except sqlite.Error, e:
            print 'An sqlite error:',e.args[0]
            print sql+'\n'
            return [],str(e)

    def dbtry(self,sql):
        """ execute a sql statement return true if no error"""
        try:
            self.cur.execute(sql)
            return True,None
        except sqlite.Error, e:
            print sql+'\n'
            return False,e
"""
class osfsys():

    def havewriteaccess(self,writefile):
        try:
            fh=open(writefile,'w+')
            fh.close()
            return True
        except:
            return False

    def havereadaccess(self,readfile):
        try:
            fh=open(readfile,'r')
            fh.close()
            return True
        except:
            return False
"""
class Md5Tools():
    def md5sum_buffer(self, buffer, hash = None):
        if hash == None:
            hash = hashlib.md5()
        hash.update(buffer)
        return hash.hexdigest()

    def md5sum(self, filename, hash = None):
        h = self._md5sum(filename,hash)
        return h.hexdigest()
       
    def _md5sum(self, filename, hash = None):
        if hash == None:
            hash = hashlib.md5()
        try:
            fd = None
            fd =  open(filename, 'rb')
            while True:
                block = fd.read(128)
                if not block: break
                hash.update(block)
        finally:
            if fd != None:
                fd.close()
        return hash
    
    def md5sum_tree(self,root):
        if not os.path.isdir(root):
            return None
        h = hashlib.md5()
        for dirpath, dirnames, filenames in os.walk(root):
            for filename in filenames:
                abs_path = os.path.join(dirpath, filename)
                h = self._md5sum(abs_path,h)
                #print abs_path
        return h.hexdigest()
    
    def set_permissions(self,root, perms='664'):
        if not os.path.isdir(root):
            return None
        for dirpath, dirnames, filenames in os.walk(root):
            for filename in filenames:
                abs_path = os.path.join(dirpath, filename)
                old_perms = os.stat(abs_path).st_mode
                if os.path.isdir(abs_path):
                    new_perms = int(perms,8) | int('771',8)
                else:
                    new_perms = old_perms | int(perms,8)
                os.chmod(abs_path,new_perms)
    
if __name__ == '__main__':
    db = DbAccess('xophoto.sqlite')
    rows,cur = db.dbdo('select * from picture')
    for row in rows:
        print row['jobject_id']
    print('index of jobject_id: %s'%db.row_index('duplicate','picture'))
    print('number of records %s'%db.numberofrows('picture'))
    print('fields %r'%db.fieldlist('picture'))
    print ('tables %r'%db.tablelist())
    