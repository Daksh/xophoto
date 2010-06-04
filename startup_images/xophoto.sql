DROP TABLE IF EXISTS "config";
CREATE TABLE "config" ("id" INTEGER PRIMARY KEY  AUTOINCREMENT  NOT NULL , "name" TEXT NOT NULL , "value" TEXT, "int" INTEGER, "real" FLOAT, "blob" BLOB, "date" DATETIME);
INSERT INTO "config" VALUES(1,'mime_type','image/png',NULL,NULL,NULL,NULL);
INSERT INTO "config" VALUES(2,'mime_type','image/jpg',NULL,NULL,NULL,NULL);
INSERT INTO "config" VALUES(3,'mime_type','image/gif',NULL,NULL,NULL,NULL);
DROP TABLE IF EXISTS "groups";
CREATE TABLE "groups" ("id" INTEGER PRIMARY KEY  NOT NULL ,"category" TEXT,"subcategory" TEXT,"jobject_id" TEXT,"seq" INTEGER,"newseq" INTEGER);
DROP TABLE IF EXISTS "picture";
CREATE TABLE "picture" ("jobject_id" TEXT NOT NULL ,"mount_point" TEXT,"orig_width" INTEGER,"orig_height" INTEGER,"mime_type" TEXT,"create_date" DATETIME,"title" TEXT,"comment" TEXT,"id" INTEGER PRIMARY KEY  NOT NULL ,"seq" INTEGER,"orig_size" DOUBLE,"album" TEXT,"in_ds" INTEGER, "md5_sum" TEXT, "longitude" FLOAT, "latitude" FLOAT, "duplicate" INTEGER DEFAULT 0);
DROP TABLE IF EXISTS "sqlite_sequence";
CREATE TABLE sqlite_sequence(name,seq);
INSERT INTO "sqlite_sequence" VALUES('config',3);
DROP TABLE IF EXISTS "transforms";
CREATE TABLE "transforms" ("id" INTEGER PRIMARY KEY  NOT NULL ,"jobject_id" TEXT,"original_x" INTEGER,"original_y" INTEGER,"scaled_x" INTEGER,"scaled_y" INTEGER,"thumb" blob);
CREATE INDEX "grp_order" ON "groups" ("category" ASC, "subcategory" ASC, "seq" ASC);
CREATE UNIQUE INDEX "jobject_id" ON "picture" ("jobject_id" ASC);
CREATE INDEX "name" ON "config" ("name" ASC, "int" ASC);
CREATE UNIQUE INDEX "path" ON "picture" ("mount_point" ASC, "orig_size" ASC);