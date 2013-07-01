import xbmc, xbmcgui, xbmcaddon, xbmcvfs
import re
import sys, os
import unicodedata
import time
import sqlite3

import buggalo
buggalo.GMAIL_RECIPIENT = "msahadl60@gmail.com"
# buggalo.SUBMIT_URL = 'http://msahadl.ms.funpic.de/buggalo-web/submit.php'

import resources.lib.utils as utils

if utils.getSetting('dbbackup') == 'true':
    import zipfile
    import datetime
    


        
# Main class of the add-on
class WatchedList:
    def __init__(self):
        self.watchedmovielist_wl = list([]) # 0imdbnumber, 1empty, 2empty, 3lastPlayed, 4playCount, 5title, 6lastChange
        self.watchedepisodelist_wl = list([]) # 0imdbnumber, 1season, 2episode, 3lastplayed, 4playcount, 5empty, 6lastChange
        
        self.watchedmovielist_xbmc = list([]) # 0imdbnumber, 1empty, 2empty, 3lastPlayed, 4playCount, 5title, 6empty, 7movieid
        self.watchedepisodelist_xbmc = list([]) # 0imdbnumber, 1season, 2episode, 3lastplayed, 4playcount, 5name, 6empty, 7episodeid
        
        self.tvshows = {} # dict: key=xbmcid, value=[imdbnumber, showname]
        self.tvshownames = {} #dict: key=imdbnumber, value=showname
        
        self.sqlcon = 0
        self.sqlcursor = 0
        
        # flag to remember copying the databasefile if requested
        self.dbcopydone = False   
        
        self.watch_user_changes_count = 0
        
        # normal access of files or access over the xbmc virtual file system (on unix)
        self.dbfileaccess = 'normal'
                
        self.dbpath = ''
        self.dbdirectory = ''
            
    # infinite loop for periodic database update
    def runProgram(self):
        try:
            utils.buggalo_extradata_settings()
            utils.footprint()
            # workaround to disable autostart, if requested
            if utils.getSetting("autostart") == 'false':
                return 0
            if self.sqlcursor == 0 or self.sqlcon == 0: 
                if self.load_db():
                    utils.showNotification(utils.getString(32102), utils.getString(32601))
                    return 3
            if len(self.tvshownames) == 0: self.sync_tvshows()
            if len(self.watchedmovielist_wl) == 0: self.get_watched_wl(1)
            if len(self.watchedmovielist_xbmc) == 0: self.get_watched_xbmc(1)
            executioncount = 0
            idletime = 0
            if utils.getSetting("watch_user") == 'true': utils.showNotification(utils.getString(32101), utils.getString(32005))
            # handle the periodic execution
            while int(utils.getSetting("starttype")) > 0 or utils.getSetting("watch_user") == 'true':
                starttime = time.time()
                # determine sleeptime before full watched-database update
                if int(utils.getSetting("starttype")) > 0: 
                    if executioncount == 0:
                        sleeptime = int(utils.getSetting("delay")) * 60
                        utils.log('Delay time before execution: %d seconds' % sleeptime, xbmc.LOGDEBUG)
                        utils.showNotification(utils.getString(32101), utils.getString(32004)%int(utils.getSetting("delay")))
                    elif utils.getSetting("starttype") == '2':
                        sleeptime = int(utils.getSetting("interval")) * 3600 # wait interval until next startup in [seconds]
                        # wait and then update again
                        utils.log('wait %d seconds until next update' % sleeptime)
                        utils.showNotification(utils.getString(32101), utils.getString(32003)%(sleeptime/3600))
                    else:
                        sleeptime = 3600 # arbitrary time for infinite loop
                else:
                    sleeptime = 3600 # arbitrary time for infinite loop
               
                # workaround to sleep the requested time. When using the sleep-function, xbmc can not exit 
                while 1:
                    if xbmc.abortRequested: return 1
                    # check if user changes arrived
                    if utils.getSetting("watch_user") == 'true':
                        idletime_old = idletime
                        idletime = xbmc.getGlobalIdleTime() # xbmc idletime in seconds
                        # check if user could have made changes and process these changes to the wl database
                        self.watch_user_changes(idletime_old, idletime)
                    # check if time for update arrived
                    if time.time() > starttime + sleeptime:
                        break
                    xbmc.sleep(1000) # wait 1 second until next check if xbmc terminates
                if utils.getSetting("starttype") == '1' and executioncount == 0 or utils.getSetting("starttype") == '2':
                    self.runUpdate()
                    executioncount += 1
                if int(utils.getSetting("starttype")) < 2 and utils.getSetting("watch_user") == 'false':
                    return 0 # the program may exit. No purpose for background process
            # do not use the periodic update
            return 0
        except:
            buggalo.onExceptionRaised()  
            
    # entry point for manual start.
    # perform the update step by step
    def runUpdate(self):
        try:
            utils.buggalo_extradata_settings()
            # check if player is running before doing the update
            while xbmc.Player().isPlaying() == True:
               if xbmc.abortRequested: return 1
               xbmc.sleep(60*1000) # wait one minute until next check for active playback
               if xbmc.Player().isPlaying() == False:
                   xbmc.sleep(180*1000) # wait 3 minutes so the dialogue does not pop up directly after the playback ends

               

    
          
            # load the addon-database
            
            if self.load_db():
                utils.showNotification(utils.getString(32102), utils.getString(32601))
                return 3
    
            if self.sync_tvshows():
                utils.showNotification(utils.getString(32102), utils.getString(32604))
                return 5
    
            # get the watched state from the addon
            if self.get_watched_wl(0):
                utils.showNotification(utils.getString(32102), utils.getString(32602))
                return 4
            

            # get watched state from xbmc
            if self.get_watched_xbmc(0):
                utils.showNotification(utils.getString(32102), utils.getString(32603))
                return 5
            
            if self.sync_tvshows():
                utils.showNotification(utils.getString(32102), utils.getString(32604))
                return 5

    
            # import from xbmc into addon database
            res = self.write_wl_wdata()
            if res == 2: # user exit
                return 0 
            elif res == 1: # error
                utils.showNotification(utils.getString(32102), utils.getString(32604))
                return 6
            
            # close the sqlite database (addon)
            self.close_db() # should be closed by the functions directly accessing the database
            
            # export from addon database into xbmc database
            res = self.write_xbmc_wdata((utils.getSetting("progressdialog") == 'true'), 2)
            if res == 2: # user exit
                return 0 
            elif res == 1: # error
                utils.showNotification(utils.getString(32102), utils.getString(32605))
                return 7
            
            utils.showNotification(utils.getString(32101), utils.getString(32107))
            utils.log('runUpdate exited with success', xbmc.LOGDEBUG)
            
            return 0
        except:
            buggalo.onExceptionRaised()  

    def load_db(self):
        try:
            # load the db path
            if utils.getSetting("extdb") == 'false':
                # use the default file 
                self.dbdirectory = xbmc.translatePath( utils.data_dir() ).decode('utf-8')
                buggalo.addExtraData('dbdirectory', self.dbdirectory);
                self.dbpath = os.path.join( self.dbdirectory , "watchedlist.db" )
            else:
                # use a user specified file, for example to synchronize multiple clients
                self.dbdirectory = xbmc.translatePath( utils.getSetting("dbpath") ).decode('utf-8')
                self.dbfileaccess = utils.fileaccessmode(self.dbdirectory)
                self.dbdirectory = utils.translateSMB(self.dbdirectory)
                
                self.dbpath = os.path.join( self.dbdirectory , utils.getSetting("dbfilename").decode('utf-8') )
                # xbmc.validatePath(self.dbdirectory) # does not work for smb
                if not xbmcvfs.exists(self.dbdirectory): # do not use os.path.exists to access smb:// paths
                    utils.log('db path does not exist: %s' % self.dbdirectory)
                    utils.showNotification(utils.getString(32102), utils.getString(32002) % self.dbdirectory )
                    return 2     
                
            # on unix, smb-shares can not be accessed with sqlite3 --> copy the db with xbmc file system operations and work in mirror directory
            buggalo.addExtraData('dbfileaccess', self.dbfileaccess);
            buggalo.addExtraData('dbdirectory', self.dbdirectory);
            buggalo.addExtraData('dbpath', self.dbpath);
            if self.dbfileaccess == 'copy':
                self.dbdirectory_copy = self.dbdirectory
                self.dbpath_copy = self.dbpath # path to db file as in the settings (but not accessable)
                buggalo.addExtraData('dbdirectory_copy', self.dbdirectory_copy);
                buggalo.addExtraData('dbpath_copy', self.dbpath_copy);
                # work in copy directory in the xbmc profile folder
                self.dbdirectory = os.path.join( xbmc.translatePath( utils.data_dir() ).decode('utf-8'), 'dbcopy')
                if not self.dbdirectory:
                    xbmcvfs.mkdir(self.dbdirectory)
                    utils.log('created directory %s' % str(self.dbdirectory))  
                self.dbpath = os.path.join( self.dbdirectory , "watchedlist.db" )
                if xbmcvfs.exists(self.dbpath_copy):
                    xbmcvfs.copy(self.dbpath_copy, self.dbpath) # copy the external db file to local mirror directory
                    utils.log('copied db file %s -> %s' % (self.dbpath_copy, self.dbpath), xbmc.LOGDEBUG)  
            
            buggalo.addExtraData('dbdirectory', self.dbdirectory);
            buggalo.addExtraData('dbpath', self.dbpath);
            
            
            #connect to the database. create database if it does not exist
            self.sqlcon = sqlite3.connect(self.dbpath);
            self.sqlcursor = self.sqlcon.cursor()
            # create tables if they don't exist
            sql = "CREATE TABLE IF NOT EXISTS movie_watched (idMovieImdb INTEGER PRIMARY KEY,playCount INTEGER,lastChange INTEGER,lastPlayed INTEGER,title TEXT)"
            self.sqlcursor.execute(sql)

            sql = "CREATE TABLE IF NOT EXISTS episode_watched (idShow INTEGER, season INTEGER, episode INTEGER, playCount INTEGER,lastChange INTEGER,lastPlayed INTEGER, PRIMARY KEY (idShow, season, episode))"
            self.sqlcursor.execute(sql)
            
            sql = "CREATE TABLE IF NOT EXISTS tvshows (idShow INTEGER, title TEXT, PRIMARY KEY (idShow))"
            self.sqlcursor.execute(sql)
            
            buggalo.addExtraData('db_connstatus', 'connected')
        except sqlite3.Error:
            utils.log("Database error while opening %s" % self.dbpath)
            self.close_db()
            buggalo.addExtraData('db_connstatus', 'sqlite3 error, closed')
            return 1
        except:
            utils.log("Error while opening %s: %s" % (self.dbpath, sys.exc_info()[2]))
            self.close_db()
            buggalo.addExtraData('dbpath', self.dbpath)
            buggalo.addExtraData('db_connstatus', 'error, closed')
            buggalo.onExceptionRaised()
            return 1     
        # only commit the changes if no error occured to ensure database persistence
        self.sqlcon.commit()
        return 0



    def close_db(self):
        if self.sqlcon:
            self.sqlcon.close()
        self.sqlcon = 0
        
        # copy the db file back to the shared directory, if needed
        if self.dbfileaccess == 'copy':
            if xbmcvfs.exists(self.dbpath):
                xbmcvfs.copy(self.dbpath, self.dbpath_copy)
                utils.log('copied db file %s -> %s' % (self.dbpath, self.dbpath_copy), xbmc.LOGDEBUG)  
        buggalo.addExtraData('db_connstatus', 'closed')
        # cursor is not changed -> error
        

    def get_watched_xbmc(self, silent):
        try:
            
            ############################################        
            # first tv shows with TheTVDB-ID, then tv episodes
            if utils.getSetting("w_episodes") == 'true':
                ############################################
                # get imdb tv-show id from xbmc database
                utils.log('get_watched_xbmc: Get all episodes from xbmc database', xbmc.LOGDEBUG)
                json_response = utils.executeJSON({
                          "jsonrpc": "2.0", 
                          "method": "VideoLibrary.GetTVShows", 
                          "params": {
                                     "properties": ["title", "imdbnumber"],
                                     "sort": { "order": "ascending", "method": "title" }
                                     }, 
                          "id": 1}) 
                if json_response.has_key('result') and json_response['result'] != None and json_response['result'].has_key('tvshows'):
                    for item in json_response['result']['tvshows']:
                        tvshowId_xbmc = int(item['tvshowid'])
                        try:
                            tvshowId_imdb = int(item['imdbnumber'])
                        except:
                            utils.log('get_watched_xbmc: tv show "%s" has no imdb-number in database. tvshowid=%d Try rescraping.' % (item['title'], tvshowId_xbmc), xbmc.LOGDEBUG)
                            continue
                        self.tvshows[tvshowId_xbmc] = list([tvshowId_imdb, item['title']])
                        self.tvshownames[tvshowId_imdb] = item['title']
            
            # Get all watched movies and episodes by unique id from xbmc-database via JSONRPC
            self.watchedmovielist_xbmc = list([])
            self.watchedepisodelist_xbmc = list([])
            for modus in ['movie', 'episode']:
                buggalo.addExtraData('modus', modus);
                if modus == 'movie' and utils.getSetting("w_movies") != 'true':
                    continue
                if modus == 'episode' and utils.getSetting("w_episodes") != 'true':
                    continue
                utils.log('get_watched_xbmc: Get all %ss from xbmc database' % modus, xbmc.LOGDEBUG)
                if modus == 'movie':
                    # use the JSON-RPC to access the xbmc-database.
                    json_response = utils.executeJSON({
                              "jsonrpc": "2.0",
                              "method": "VideoLibrary.GetMovies", 
                              "params": {
                                         "properties": ["title", "year", "imdbnumber", "lastplayed", "playcount"],
                                         "sort": { "order": "ascending", "method": "title" }
                                         }, 
                              "id": 1
                              })
                else:
                    json_response = utils.executeJSON({
                              "jsonrpc": "2.0",
                              "method": "VideoLibrary.GetEpisodes",
                              "params": {
                                         "properties": ["tvshowid", "season", "episode", "playcount", "showtitle", "lastplayed"]
                                         },
                              "id": 1
                              }) 
                if modus == 'movie': searchkey = 'movies'
                else: searchkey = 'episodes'     
                if json_response.has_key('result') and json_response['result'] != None and json_response['result'].has_key(searchkey):
                    
                    totalcount = json_response['result']['limits']['total']
                    # go through all watched movies and save them in the class-variable self.watchedmovielist_xbmc
                    for item in json_response['result'][searchkey]:
                        if modus == 'movie':
                            name = item['title'] + ' (' + str(item['year']) + ')'
                            res = re.compile('tt(\d+)').findall(item['imdbnumber'])
                            if len(res) == 0:
                                # no imdb-number for this movie in database. Skip
                                utils.log('get_watched_xbmc: Movie %s has no imdb-number in database. movieid=%d Try rescraping' % (name, int(item['movieid'])), xbmc.LOGDEBUG)
                                continue
                            imdbId = int(res[0])
                        else:
                            tvshowId_xbmc = item['tvshowid']
                            name = '%s S%02dE%02d' % (item['showtitle'], item['season'], item['episode'])
                            try:
                                tvshowId_imdb = self.tvshows[tvshowId_xbmc][0]
                            except:
                                utils.log('get_watched_xbmc: xbmc tv showid %d is not in table xbmc-tvshows. Skipping %s' % (item['tvshowid'], name), xbmc.LOGWARNING)
                                continue

                        lastplayed = utils.sqlDateTimeToTimeStamp(item['lastplayed']) # convert to integer-timestamp
                        playcount = int(item['playcount'])
                        # add data to the class-variables
                        if modus == 'movie':
                            self.watchedmovielist_xbmc.append(list([imdbId, 0, 0, lastplayed, playcount, name, 0, int(item['movieid'])]))# 0imdbnumber, 1empty, 2empty, 3lastPlayed, 4playCount, 5title, 6empty, 7movieid
                        else:
                            self.watchedepisodelist_xbmc.append(list([tvshowId_imdb, int(item['season']), int(item['episode']), lastplayed, playcount, name, 0, int(item['episodeid'])]))
            if not silent: utils.showNotification( utils.getString(32101), utils.getString(32299)%(len(self.watchedmovielist_xbmc), len(self.watchedepisodelist_xbmc)) )
            return 0
        except:
            utils.log(u'get_watched_xbmc: error getting the xbmc database : %s' % sys.exc_info()[2], xbmc.LOGERROR)
            self.close_db()
            buggalo.onExceptionRaised()  
            return 1          
        
     
        

        
    def get_watched_wl(self, silent):
        try:
            buggalo.addExtraData('self_sqlcursor', self.sqlcursor); buggalo.addExtraData('self_sqlcon', self.sqlcon);
            if self.sqlcursor == 0 or self.sqlcon == 0:
                if self.load_db():
                    return 2
            # get watched movies from addon database
            self.watchedmovielist_wl = list([])
            if utils.getSetting("w_movies") == 'true':
                utils.log('get_watched_wl: Get watched movies from WL database', xbmc.LOGDEBUG)
                self.sqlcursor.execute("SELECT idMovieImdb, lastPlayed, playCount, title, lastChange FROM movie_watched ORDER BY title") 
                rows = self.sqlcursor.fetchall() 
                for row in rows:
                    self.watchedmovielist_wl.append(list([int(row[0]), 0, 0, int(row[1]), int(row[2]), row[3], int(row[4])])) # 0imdbnumber, 1empty, 2empty, 3lastPlayed, 4playCount, 5title, 6lastChange
            
            # get watched episodes from addon database
            self.watchedepisodelist_wl = list([])
            if utils.getSetting("w_episodes") == 'true':
                utils.log('get_watched_wl: Get watched episodes from WL database', xbmc.LOGDEBUG)
                self.sqlcursor.execute("SELECT idShow, season, episode, lastPlayed, playCount, lastChange FROM episode_watched ORDER BY idShow, season, episode") 
                rows = self.sqlcursor.fetchall() 
                for row in rows:
                    try:
                        name = '%s S%02dE%02d' % (self.tvshownames[int(row[0])], int(row[1]), int(row[2]))
                    except:
                        name = 'tvdb-id %d S%02dE%02d' % (int(row[0]), int(row[1]), int(row[2]))
                    self.watchedepisodelist_wl.append(list([int(row[0]), int(row[1]), int(row[2]), int(row[3]), int(row[4]), name, int(row[5])]))# 0imdbnumber, 1season, 2episode, 3lastplayed, 4playcount, 5name, 6lastChange
            if not silent: utils.showNotification(utils.getString(32101), utils.getString(32298)%(len(self.watchedmovielist_wl), len(self.watchedepisodelist_wl)))
            self.close_db()
            return 0
        except sqlite3.Error:
            utils.log(u'get_watched_wl: SQLite Database error getting the wl database %s' % sqlite3.Error.args[0], xbmc.LOGERROR)
            self.close_db()
            # error could be that the database is locked (for tv show strings). This is not an error to disturb the other functions
            return 3
        except:
            utils.log(u'get_watched_wl:  error getting the wl database : %s' % sys.exc_info()[2], xbmc.LOGERROR)
            self.close_db()
            buggalo.onExceptionRaised()  
            return 1     
        
        
        
        
        
    def sync_tvshows(self):
        try:
            utils.log(u'sync_tvshows: sync tvshows with wl database : %s' % sys.exc_info()[2], xbmc.LOGDEBUG)
            if self.sqlcursor == 0 or self.sqlcon == 0:
                if self.load_db():
                    return 2
            # write eventually new tv shows to wl database
            for xbmcid in self.tvshows:
                sql = 'INSERT OR IGNORE INTO tvshows (idShow,title) VALUES (?, ?)'
                values = self.tvshows[xbmcid]
                self.sqlcursor.execute(sql, values)
            self.database_copy()    
            self.sqlcon.commit()
            # get all known tv shows from wl database
            self.sqlcursor.execute("SELECT idShow, title FROM tvshows") 
            rows = self.sqlcursor.fetchall() 
            for i in range(len(rows)):
                self.tvshownames[int(rows[i][0])] = rows[i][1]
            self.close_db()
        except sqlite3.Error:
            utils.log(u'sync_tvshows: SQLite Database error accessing the wl database', xbmc.LOGERROR)
            self.close_db()
            # error could be that the database is locked (for tv show strings).
            return 1
        except:
            utils.log(u'sync_tvshows:  error getting the wl database : %s' % sys.exc_info()[2], xbmc.LOGERROR)
            self.close_db()
            buggalo.onExceptionRaised()  
            return 1   
        return 0 
        

        
    def write_wl_wdata(self):
        # Go through all watched movies from xbmc and check whether they are up to date in the addon database
        buggalo.addExtraData('self_sqlcursor', self.sqlcursor); buggalo.addExtraData('self_sqlcon', self.sqlcon);
        if self.sqlcursor == 0 or self.sqlcon == 0:
            if self.load_db():
                return 2
        for modus in ['movie', 'episode']:
            buggalo.addExtraData('modus', modus);
            if modus == 'movie' and utils.getSetting("w_movies") != 'true':
                continue
            if modus == 'episode' and utils.getSetting("w_episodes") != 'true':
                continue
            utils.log('write_wl_wdata: Write watched %ss to WL database' % modus, xbmc.LOGDEBUG)
            count_insert = 0
            count_update = 0
            if utils.getSetting("progressdialog") == 'true':
                 DIALOG_PROGRESS = xbmcgui.DialogProgress()
                 DIALOG_PROGRESS.create( utils.getString(32101) , utils.getString(32105))
            if modus == 'movie':
                list_length = len(self.watchedmovielist_xbmc)
            else:
                list_length = len(self.watchedepisodelist_xbmc)
                
            for i in range(list_length):
                if xbmc.abortRequested: break # this loop can take some time in debug mode and prevents xbmc exit
                if utils.getSetting("progressdialog") == 'true' and DIALOG_PROGRESS.iscanceled():
                    utils.showNotification(utils.getString(32202), utils.getString(32301)%(count_insert, count_update))
                    return 2
                if modus == 'movie':
                    row_xbmc = self.watchedmovielist_xbmc[i]
                else:
                    row_xbmc = self.watchedepisodelist_xbmc[i]

                if utils.getSetting("progressdialog") == 'true':
                    DIALOG_PROGRESS.update(100*i/(list_length-1), utils.getString(32105), utils.getString(32610) % (i+1, list_length, row_xbmc[5]) )  

                try:
                    count = self.wl_update_media(modus, row_xbmc, 0, 0)
                    count_insert += count[0]; count_update += count[1];

                except sqlite3.Error:
                    utils.log(u'write_wl_wdata: Database error while updating %s %s' % (modus, row_xbmc[5]))
                    self.close_db()
                    # error at this place is the result of duplicate movies, which produces a DUPLICATE PRIMARY KEY ERROR
                    continue
                except:
                    utils.log(u'write_wl_wdata: Error while updating %s %s: %s' % (modus, row_xbmc[5], sys.exc_info()[2]))
                    self.close_db()
                    if utils.getSetting("progressdialog") == 'true': DIALOG_PROGRESS.close()
                    buggalo.addExtraData('count_update', count_update); buggalo.addExtraData('count_insert', count_insert); 
                    buggalo.onExceptionRaised()  
                    return 1 
                    
            if utils.getSetting("progressdialog") == 'true': DIALOG_PROGRESS.close()
            # only commit the changes if no error occured to ensure database persistence
            if count_insert > 0 or count_update > 0:
                self.database_copy()
                self.sqlcon.commit()
            if modus == 'movie': strno = [32202, 32301]
            else: strno = [32203, 32301];
            utils.showNotification(utils.getString(strno[0]), utils.getString(strno[1])%(count_insert, count_update))
        self.close_db()
        return 0
        
        
        
        
        
    # update the xbmc database.
    # progressdialogue
    # notifications: 0= no, 1=only changed info, 2=all
    def write_xbmc_wdata(self, progressdialogue, notifications):
        # Go through all watched movies/episodes from the wl-database and check, if the xbmc-database is up to date
        for modus in ['movie', 'episode']:
            buggalo.addExtraData('modus', modus);
            if modus == 'movie' and utils.getSetting("w_movies") != 'true':
                continue
            if modus == 'episode' and utils.getSetting("w_episodes") != 'true':
                continue
                     
            utils.log('write_xbmc_wdata: Write watched %ss to xbmc database (pd=%d, noti=%d)' % (modus, progressdialogue, notifications), xbmc.LOGDEBUG)
            count_update = 0
            if progressdialogue:
                 DIALOG_PROGRESS = xbmcgui.DialogProgress()
                 DIALOG_PROGRESS.create( utils.getString(32101), utils.getString(32106))
            
            # list to iterate over
            if modus == 'movie':
                list_length = len(self.watchedmovielist_wl)
            else:
                list_length = len(self.watchedepisodelist_wl)
            # iterate over wl-list
            for j in range(list_length):
                if xbmc.abortRequested: break # this loop can take some time in debug mode and prevents xbmc exit
                if progressdialogue and DIALOG_PROGRESS.iscanceled():
                    if notifications > 0: utils.showNotification(utils.getString(32204), utils.getString(32302)%(count_update))  
                    return 2
                # get media-specific list items
                if modus == 'movie':
                    row_wl = self.watchedmovielist_wl[j]
                else:
                    row_wl = self.watchedepisodelist_wl[j]
                    season = row_wl[1]
                    episode = row_wl[2]
                imdbId = row_wl[0]
                name =  row_wl[5]

                if progressdialogue:
                    DIALOG_PROGRESS.update(100*j/(list_length-1), utils.getString(32106), utils.getString(32610) % (j+1, list_length, name) )
                try:
                    # search the unique movie/episode id in the xbmc-list
                    if modus == 'movie':
                        indices = [i for i, x in enumerate(self.watchedmovielist_xbmc) if x[0] == imdbId] # the movie can have multiple entries in xbmc
                    else:
                        indices = [i for i, x in enumerate(self.watchedepisodelist_xbmc) if x[0] == imdbId and x[1] == season and x[2] == episode]
                    lastplayed_wl = row_wl[3]
                    playcount_wl = row_wl[4]
                    lastchange_wl = row_wl[6]
                    if len(indices) > 0:
                        # the movie/episode is already in the xbmc-list
                        for i in indices:
                            if modus == 'movie':
                                row_xbmc = self.watchedmovielist_xbmc[i] 
                            else:
                                row_xbmc = self.watchedepisodelist_xbmc[i]

                            lastplayed_xbmc = row_xbmc[3]
                            playcount_xbmc = row_xbmc[4]
                                
                            change_xbmc_db = False
                            # check if movie/episode is set as unwatched in the wl database
                            if playcount_wl != playcount_xbmc and lastchange_wl > lastplayed_xbmc:
                                change_xbmc_db = True
                            # compare playcount and lastplayed (update if xbmc data is older)
                            if playcount_xbmc < playcount_wl or (lastplayed_xbmc < lastplayed_wl and playcount_wl > 0):
                                change_xbmc_db = True
                            if not change_xbmc_db:    
                                if utils.getSetting("debug") == 'true':
                                    # utils.log('write_xbmc_wdata: xbmc database up-to-date for tt%d, %s' % (imdbId, row_xbmc[2]), xbmc.LOGDEBUG)
                                    pass
                                continue
                            # check if the lastplayed-timestamp in wl is useful
                            if playcount_wl == 0:
                                lastplayed_new = 0
                            else:
                                if lastplayed_wl == 0:
                                    lastplayed_new = lastplayed_xbmc
                                else:
                                    lastplayed_new = lastplayed_wl
                            # update database
                            mediaid = row_xbmc[7]
                            if modus == 'movie': jsonmethod = "VideoLibrary.SetMovieDetails"; idfieldname = "movieid"
                            else: jsonmethod = "VideoLibrary.SetEpisodeDetails"; idfieldname = "episodeid"
                            jsondict = {
                                      "jsonrpc": "2.0", 
                                      "method": jsonmethod, 
                                      "params": {idfieldname: mediaid, "playcount": playcount_wl, "lastplayed": utils.TimeStamptosqlDateTime(lastplayed_new)}, 
                                      "id": 1
                                      }
                            json_response = utils.executeJSON(jsondict)
                            if (json_response.has_key('result') and json_response['result'] == 'OK'):
                                utils.log('write_xbmc_wdata: xbmc database updated for %s. playcount: {%d -> %d}, lastplayed: {"%s" -> "%s"} (%sid=%d)' % (name, playcount_xbmc, playcount_wl, utils.TimeStamptosqlDateTime(lastplayed_xbmc), utils.TimeStamptosqlDateTime(lastplayed_new), modus, mediaid))
                                if utils.getSetting("debug") == 'true':
                                    if playcount_wl == 0:
                                        if notifications > 0: utils.showNotification(utils.getString(32404), name)
                                    else:
                                        if notifications > 0: utils.showNotification(utils.getString(32401), name)
                                count_update += 1
                                # update the xbmc-db-mirror-variable
                                if modus == 'movie':
                                    self.watchedmovielist_xbmc[i][3] = lastplayed_new
                                    self.watchedmovielist_xbmc[i][4] = playcount_wl
                                else:
                                    self.watchedepisodelist_xbmc[i][3] = lastplayed_new
                                    self.watchedepisodelist_xbmc[i][4] = playcount_wl
                            else:
                                utils.log('write_xbmc_wdata: error updating xbmc database. %s. json_response=%s' % (name, str(json_response)))
                        
                    else:
                        # the movie is in the watched-list but not in the xbmc-list -> no action
                        # utils.log('write_xbmc_wdata: movie not in xbmc database: tt%d, %s' % (imdbId, row_xbmc[2]), xbmc.LOGDEBUG)
                        continue
                except:
                    utils.log("write_xbmc_wdata: Error while updating %s %s: %s" % (modus, name, sys.exc_info()[2]))
                    if progressdialogue: DIALOG_PROGRESS.close()
                    buggalo.addExtraData('count_update', count_update);
                    buggalo.onExceptionRaised()  
                    return 1 

            if progressdialogue: DIALOG_PROGRESS.close() 
            if notifications > 1:
                if modus == 'movie': strno = [32204, 32302]
                else: strno = [32205, 32303];
                utils.showNotification(utils.getString(strno[0]), utils.getString(strno[1])%(count_update))    
        return 0
    
    
    
    
    
    # create a copy of the database, in case something goes wrong
    def database_copy(self):
        if utils.getSetting('dbbackup') == 'true' and (not self.dbcopydone):
            if not xbmcvfs.exists(self.dbpath): 
                utils.log('database_copy: directory %s does not exist. No backup possible.' % self.dbpath)
                return 1
            now = datetime.datetime.now()
            timestr = '%04d%02d%02d_%02d%02d%02d' % (now.year, now.month, now.day, now.hour, now.minute, now.second)
            zipfilename = os.path.join(self.dbdirectory, timestr + ' - watchedlist.db.zip')
            zf = False
            try:
                zf = zipfile.ZipFile(zipfilename, 'w')
                zf.write(self.dbpath, compress_type=zipfile.ZIP_DEFLATED, arcname='watchedlist.db')
                zf.close()
                self.dbcopydone = True
                utils.log('database_copy: database backup copy created to %s' % zipfilename)
                # copy the zip file with xbmc file system, if needed
                if self.dbfileaccess == 'copy':
                    xbmcvfs.copy(zipfilename, os.path.join(self.dbdirectory_copy, timestr + ' - watchedlist.db.zip'))
                    xbmcvfs.delete(zipfilename)
                return 0
            except:
                if zf:
                    zf.close()
                buggalo.addExtraData('zipfilename', zipfilename);
                buggalo.onExceptionRaised()  
                return 2
                
            
    # check if the user made changes in the watched states. Especially setting movies as "not watched". This can not be
    # recognized by the functions above
    def watch_user_changes(self, idletime_old, idletime):
        if xbmc.Player().isPlaying() == True:
            return
        if idletime > idletime_old:
            # the idle time increased. No user interaction probably happened
            return
        utils.log('watch_user_changes: Check for user changes (no. %d)' % self.watch_user_changes_count, xbmc.LOGDEBUG)
        self.watch_user_changes_count = self.watch_user_changes_count + 1
                        
        # save previous state
        old_watchedmovielist_xbmc = self.watchedmovielist_xbmc
        old_watchedepisodelist_xbmc = self.watchedepisodelist_xbmc
        # get new state
        self.get_watched_xbmc(1)
        #save exception information
        buggalo.addExtraData('len_old_watchedmovielist_xbmc', len(old_watchedmovielist_xbmc))
        buggalo.addExtraData('len_old_watchedepisodelist_xbmc', len(old_watchedepisodelist_xbmc))
        buggalo.addExtraData('len_self_watchedmovielist_xbmc', len(self.watchedmovielist_xbmc))
        buggalo.addExtraData('len_self_watchedepisodelist_xbmc', len(self.watchedepisodelist_xbmc))
        # separate the change detection and the change in the database to prevent circle reference
        indices_changed = list([])
        # compare states of movies/episodes
        for modus in ['movie', 'episode']:
            buggalo.addExtraData('modus', modus);
            if modus == 'movie' and utils.getSetting("w_movies") != 'true':
                continue
            if modus == 'episode' and utils.getSetting("w_episodes") != 'true':
                continue
            if modus == 'movie':
                list_new = self.watchedmovielist_xbmc
                list_old = old_watchedmovielist_xbmc
            else:
                list_new = self.watchedepisodelist_xbmc
                list_old = old_watchedepisodelist_xbmc
            if len(list_old) == 0 or len(list_new) == 0:
                # one of the lists is empty: nothing to compare. No user changes noticable
                continue
            for i_n, row_xbmc in enumerate(list_new):
                if xbmc.abortRequested: return
                imdbId = row_xbmc[0]
                mediaid = row_xbmc[7]
                lastplayed_new = row_xbmc[3]
                playcount_new = row_xbmc[4]
                
                # index of this movie/episode in the old database (before the change by the user)
                if (len(list_old) >= i_n) and (list_old[7] == mediaid): i_o = i_n # db did not change
                else: # search the movieid
                    i_o = [i for i, x in enumerate(list_old) if x[7] == mediaid]
                    if len(i_o) == 0: continue #movie is not in old array
                    i_o = i_o[0] # convert list to int
                lastplayed_old = list_old[i_o][3]
                playcount_old = list_old[i_o][4]
                
                
                if playcount_new != playcount_old or lastplayed_new != lastplayed_old:
                    if playcount_new == playcount_old and playcount_new == 0:
                        continue # do not add lastplayed to database, when placount = 0
                    # The user changed the playcount or lastplayed.
                    # update wl with new watched state
                    indices_changed.append([i_n, i_o, row_xbmc])  
            
            # go through all movies changed by the user        
            for icx in indices_changed:  
                if xbmc.abortRequested: return 1
                i_o = icx[1]; row_xbmc = icx[2]
                i_n = icx[0]; imdbId = row_xbmc[0]
                if modus == 'episode':
                    season = row_xbmc[1]; episode = row_xbmc[2]
                lastplayed_old = list_old[i_o][3]; playcount_old = list_old[i_o][4];
                lastplayed_new = row_xbmc[3]; playcount_new = row_xbmc[4]; mediaid = row_xbmc[7]
                utils.log('watch_user_changes: %s "%s" changed playcount {%d -> %d} lastplayed {"%s" -> "%s"}. %sid=%d' % (modus, row_xbmc[5], playcount_old, playcount_new, utils.TimeStamptosqlDateTime(lastplayed_old), utils.TimeStamptosqlDateTime(lastplayed_new), modus, mediaid))
                self.wl_update_media(modus, row_xbmc, 1, 1)
                # update xbmc watched status, e.g. to set duplicate movies also as watched
            if len(indices_changed) > 0:    
                self.write_xbmc_wdata(0, 1) # this changes self.watchedmovielist_xbmc
                self.close_db() # keep the db closed most of the time (no access problems)
        
 
                
    # update the wl database for one movie/episode with the information in row_xbmc.
    # Use saveanyway to skip checks whether not to save the changes. With commit, the db change is committed directly (slow with many movies, but safe)    
    def wl_update_media(self, mediatype, row_xbmc, saveanyway, commit):
        buggalo.addExtraData('self_sqlcursor', self.sqlcursor); buggalo.addExtraData('self_sqlcon', self.sqlcon);
        buggalo.addExtraData('len_self_watchedmovielist_wl', len(self.watchedmovielist_wl))
        buggalo.addExtraData('len_self_watchedepisodelist_wl', len(self.watchedepisodelist_wl))
        buggalo.addExtraData('len_self_tvshownames', len(self.tvshownames))
        buggalo.addExtraData('row_xbmc', row_xbmc)
        buggalo.addExtraData('saveanyway', saveanyway)
        if self.sqlcursor == 0 or self.sqlcon == 0:
            if self.load_db():
                return 2
        for modus in [mediatype]:
            buggalo.addExtraData('modus', modus)
            # row_xbmc: 0imdbnumber, 1empty, 2empty, 3lastPlayed, 4playCount, 5title, 6empty, 7movieid
            imdbId = row_xbmc[0]
            lastplayed_xbmc = row_xbmc[3]
            playcount_xbmc = row_xbmc[4]
            name = row_xbmc[5]
            if modus == 'episode':
                season = row_xbmc[1]
                episode = row_xbmc[2]

            count_return = list([0, 0])
            self.database_copy()
            if self.sqlcursor == 0 or self.sqlcon == 0:
                if self.load_db():
                    return count_return
            if not saveanyway and playcount_xbmc == 0:
                # playcount in xbmc-list is empty. Nothing to save
                if utils.getSetting("debug") == 'true':
                    # utils.log(u'wl_update_%s: not watched in xbmc: tt%d, %s' % (modus, imdbId, name), xbmc.LOGDEBUG)
                    pass
                return count_return
            if modus == 'movie':
                j = [ii for ii, x in enumerate(self.watchedmovielist_wl) if x[0] == imdbId]
            if modus == 'episode':
                j = [ii for ii, x in enumerate(self.watchedepisodelist_wl) if x[0] == imdbId and x[1] == season and x[2] == episode]
            if len(j) > 0:
                j = j[0] # there can only be one valid index j, since only one entry in wl per imdbId
                # the movie is already in the watched-list
                if modus == 'movie':
                    row_wl = self.watchedmovielist_wl[j]
                else:
                    row_wl = self.watchedepisodelist_wl[j]
                lastplayed_wl = row_wl[3]    
                playcount_wl = row_wl[4]
                lastchange_wl = row_wl[6]
                
                if not saveanyway:
                    # compare playcount and lastplayed
                    
                    # check if an update of the wl database is necessary (xbmc watched status newer)
                    if lastchange_wl > lastplayed_xbmc:
                        return count_return
                    
                    if playcount_wl >= playcount_xbmc and lastplayed_wl >= lastplayed_xbmc:
                        if utils.getSetting("debug") == 'true':
                            # utils.log(u'wl_update_movie: wl database up-to-date for movie tt%d, %s' % (imdbId, moviename), xbmc.LOGDEBUG)
                            pass
                        return count_return
                    # check if the lastplayed-timestamp in xbmc is useful
                    if lastplayed_xbmc == 0:
                        lastplayed_new = lastplayed_wl
                    else:
                        lastplayed_new = lastplayed_xbmc
                else:
                    lastplayed_new = lastplayed_xbmc
  
                lastchange_new = int(time.time())
                if modus == 'movie':
                    sql = 'UPDATE movie_watched SET playCount = ?, lastplayed = ?, lastChange = ? WHERE idMovieImdb LIKE ?'
                    values = list([playcount_xbmc, lastplayed_new, lastchange_new, imdbId])
                else:
                    sql = 'UPDATE episode_watched SET playCount = ?, lastPlayed = ?, lastChange = ? WHERE idShow LIKE ? AND season LIKE ? AND episode LIKE ?'
                    values = list([playcount_xbmc, lastplayed_new, lastchange_new, imdbId, season, episode])
                self.sqlcursor.execute(sql, values)
                count_return[1] = 1
                # update the local mirror variable of the wl database: # 0imdbnumber, season, episode, 3lastPlayed, 4playCount, 5title, 6lastChange
                if modus == 'movie':
                    self.watchedmovielist_wl[j] = list([imdbId, 0, 0, lastplayed_new, playcount_xbmc, name, lastchange_new])
                else:
                    self.watchedepisodelist_wl[j] = list([imdbId, season, episode, lastplayed_new, playcount_xbmc, name, lastchange_new])
                if utils.getSetting("debug") == 'true':
                    utils.log(u'wl_update_%s: updated wl db for "%s" (tt%d). playcount: {%d -> %d}. lastplayed: {"%s" -> "%s"}. lastchange: "%s"' % (modus, name, imdbId, playcount_wl, playcount_xbmc, utils.TimeStamptosqlDateTime(lastplayed_wl), utils.TimeStamptosqlDateTime(lastplayed_new), utils.TimeStamptosqlDateTime(lastchange_new)))
                    if playcount_xbmc > 0:
                        utils.showNotification(utils.getString(32403), name)
                    else:
                        utils.showNotification(utils.getString(32405), name)       
            else:
                # the movie is not in the watched-list -> insert the movie
                # order: idMovieImdb,playCount,lastChange,lastPlayed,title
                lastchange_new = int(time.time())
                if modus == 'movie':
                    sql = 'INSERT INTO movie_watched (idMovieImdb,playCount,lastChange,lastPlayed,title) VALUES (?, ?, ?, ?, ?)'
                    values = list([imdbId, playcount_xbmc, lastchange_new, lastplayed_xbmc, name])
                else:
                    sql = 'INSERT INTO episode_watched (idShow,season,episode,playCount,lastChange,lastPlayed) VALUES (?, ?, ?, ?, ?, ?)'
                    values = list([imdbId, season, episode, playcount_xbmc, lastchange_new, lastplayed_xbmc])
                self.sqlcursor.execute(sql, values)
                utils.log(u'wl_update_%s: new entry for wl database: "%s", lastChange="%s", lastPlayed="%s", playCount=%d' % (modus, name, utils.TimeStamptosqlDateTime(lastchange_new), utils.TimeStamptosqlDateTime(lastplayed_xbmc), playcount_xbmc))
                count_return[0] = 1
                # update the local mirror variable of the wl database
                if modus == 'movie':
                    self.watchedmovielist_wl.append(list([imdbId, 0, 0, lastplayed_xbmc, playcount_xbmc, name, lastchange_new]))
                else:
                    self.watchedepisodelist_wl.append(list([imdbId, season, episode, lastplayed_xbmc, playcount_xbmc, name, lastchange_new]))
                if utils.getSetting("debug") == 'true':
                    if playcount_xbmc > 0:
                        utils.showNotification(utils.getString(32402), name)
                    else:
                        utils.showNotification(utils.getString(32405), name)
            if commit:
                self.sqlcon.commit()     
        return count_return