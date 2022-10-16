#!/usr/bin/env python3
################################################################################
#region #*      docstring and metadata
################################################################################
__doc__ = """

Title - One line blurb

Paragraph describing

Usage:
    ./projectmain.py arg1 [optionalarg2]

Parameters
    param1          Thing 1 (required). 6 chars starting with Thing
    param2          Thing 2 (optional)

Output:
    string_output   Thing 3.  6 chars starting with Thing

Examples:
    ./projectmain.py                    Will prompt for all arguments
    ./projectmain.py Thing1             Will prompt for 1 argument
    ./projectmain.py Thing1 Thing2      Will execute and return Thing 3
    ./projectmain.py help               Will output this help doc

"""
__author__ = "epopisces"
__date__ = "2020.12.06"
__version__ = 0.1

#endregion

################################################################################
#region #*      working notes
################################################################################

# main(db,
#          output_dir,
#          music_folder=None,
#          overwrite=False,
#          prepend_parent=False,
#          folders=False):

# Pertinent database queries
# SELECT ID, SongTitle, Artist, Album, Custom1, Custom2, Custom3, Custom4 FROM Songs
# SELECT * FROM Playlists

# Flow, generally speaking
#* Get media & playlists, building the library object
# - get music
# - get playlists
#? if the DB weren't multiple 100s of MB, could just load it all into memory.  It is effectively the library object anyway
#? https://stackoverflow.com/questions/3850022/how-to-load-existing-db-file-to-memory-in-python-sqlite3

#* construct autoplaylists (ideally matching m3u format)
#* load playlists into plex
# - for playlist name
# - - if doesn't exist, create
# - - if exists, for each song in playlist list library object
# - - - get song id in plex library
# - - - if song id doesn't exist in plex playlist, add to plex playlist (and to tracking list)
# - - - if song id exists, add to tracking list
# - get plex song ids in playlist
# - - for each song id, if not in tracking list, remove from plex playlist

#! ALTERNATELY
#* for each autoplaylist, create a collection in Plex with corresponding logic (association = country, playlist = mood, etc)
#* update tags in plex songs with the matching custom metadata from MediaMonkey

# TODO 
# - modify the m3u code to work for library object/autoplaylists
# - Aggression playlist (and any others with an 'or' match condition instead of an 'and') will need to be handled differently

#endregion
from mm_extract_playlist.__main__ import main
from mm_extract_playlist import database, utils
from mm_extract_playlist.track import Track
from plexapi import playlist
from plexapi.server import PlexServer

# main(r"C:\Users\epopisces\AppData\Roaming\MediaMonkey5\MM5.DB", "./output")

import logging, json #, os, time, requests
# from requests.exceptions import RequestException
# import toml # used to parse config file

class MediaLibraryException(Exception):
    pass

class MediaLibraryNotFoundException(Exception):
    pass

class MediaLibraryGeneralException(Exception):
    pass

class MediaLibraryInvalidInputException(Exception):
    pass


class MediaLibrary():
    """A quick description of the class

    Attributes:
        var1 (bool):          used for this thing
        var2 (str, optional): used for that thing
    """

    # TODO: Update methods_supported to be accurate according to what is supported by this API
    methods_supported = ["POST","GET"] 
    # TODO: Update base_url
    base_url = ""
    playlists_of_interest = [
        '2006',
        '2007',
        '2008',
        '2009',
        '2010',
        '2011',
        '2012',
        '2013',
        '2014',
        '2015',
        '2016',
        '2017',
        '2018',
        '2019',
        '2020',
        '2021',
        '2022',
        'Workalong',
        'Maudlin',
        'My Top Rated',
        'Breakup',
        'Pacific',
        'Energizing',
        'Adrienne',
        'Aggression',
        'Ambient',
        'Christus Rex',
        'Instrumental',
        'Singalong',
        'Slumber',
        'Sarah',
        'Grayson',
        'RPG Char'
    ]

    def __init__(self, db):
        self.db_path = db
        self.playlists = {}
        # maybe call another function here to help setup things

        return

    def connect_database(self):
        self.db = database.connect(self.db_path)
        return

    def get_playlists(self):
        playlists = database.get_all_playlists(self.db)
        for pl in playlists.values():
            self.playlists[pl.name] = pl
        return

    def get_static_playlist_from_autoplaylist(self, playlist_name):
        "Get dict of tracks grouped by playlist id"
        drive_map = database.get_drive_letters(self.db)
        playlist_id = self.playlists[playlist_name].id
        # tracks = self.playlists[playlist_name].tracks
        query = self.get_query_from_autoplaylist(playlist_name)
        cur = self.db.cursor()
        cur.execute(query)
        pl_tracks = []
        for idx, row in enumerate(cur):
            # resolve drive letter and pre-pend to path
            path, media = row[1], row[-1]
            drive = drive_map[media]
            path = drive + path
            row = list(row[:-1])
            row[1] = path
            row.insert(2, playlist_id)
            row.append(idx)
            pl_tracks.append(Track(*row))
        self.playlists[playlist_name].tracks = pl_tracks
        return

    def get_query_from_autoplaylist(self, playlist_name):
        query_orig = json.loads(self.playlists[playlist_name].query)
        query_sql = 'SELECT SongTitle, SongPath, Custom1, Custom2, Custom3, Custom4, IDMedia FROM Songs WHERE '
        for field_filter in query_orig['conditions']['data']:
            if field_filter['field'] == 'extension':
                continue
            elif field_filter['operator'] == 'contains':
                q_operator = 'LIKE'
                q_operand = field_filter['value']
                query_sql += f"{field_filter['field']} {q_operator} '%{q_operand}%' AND "
            elif field_filter['operator'] == '!=' or field_filter['operator'] == '>=':
                q_operator = field_filter['operator'] 
                q_operand = field_filter['value'].split(',')[0]
                query_sql += f"{field_filter['field']} {q_operator} {q_operand} AND "
            elif field_filter['operator'] == 'does not contain':
                q_operator = 'NOT LIKE'
                q_operand = field_filter['value']
                query_sql += f"{field_filter['field']} {q_operator} '%{q_operand}%' AND "
            else:
                print()

        return query_sql[:-5] #? strip off the last AND

    def close_database(self):
        self.db.close()
        return

    def _request(self, api_path, method, params=None, headers=None, body=None, post_param=None):
        """ unpaged request template, abstracts much of the error handling.  
        May require modification for specific API to account for idiosyncrasies 
        """
    
        method = method.upper() # just in case (puns!)
        
        if method not in self.methods_supported:
            raise MediaLibraryException(f"{method} is not a HTTP method supported by this API")

        #* Make any method-dependent alterations here, eg add Content-type to headers for POST

        try:
            session = requests.Session() # using a session persists params, cookies across reqs

            session.mount(self.base_url, requests.adapters.HTTPAdapter(max_retries=3)) #? override default session retries
            if body:
                #* add auth= to below if needed for API auth
                request = requests.Request(method, self.base_url + api_path, params=params, headers=headers, json=body)
            else:
                request = requests.Request(method, self.base_url + api_path, params=params, headers=headers)

            # https://docs.python-requests.org/en/latest/user/advanced/#prepared-requests
            prepared_request = session.prepare_request(request)

            #* Here is the spot where the prepp'd content can be modified, if need be

            r = session.send(prepared_request)
        
        except requests.exceptions.RequestException as e:
            logging.exception("Connection error")
            raise MediaLibraryException(e)

        # handle status codes in response        
        if not (r.status_code == requests.codes.ok):
            if r.status_code == 204:
                return r.status_code
            else:
                print("Error retrieving data.  HTTP status code: {}".format(r.status_code))
            if r.status_code == 401:
                print("Check that your API credentials are correct.")
            else:
                logging.exception(f"Error: {r.text} for request {r.request_url}")
            raise requests.exceptions.RequestException()
        else:
            try:
                return r.json()
            except json.JSONDecodeError:
                return r.text

    def _paged_request(self, api_path, method, hal_element, params=None, headers=None, body=None, post_param=None):
        """ paged request template, still a work in progress.
        A given APIs may implement pagination very differently from another API
        May require modification for specific API to account for idiosyncrasies 
        """
        all_data = []
        page = 0
        more_pages = True

        method = method.upper() # just in case (puns!)
        
        if method not in self.methods_supported:
            raise MediaLibraryException(f"{method} is not a HTTP method supported by this API")

        #* Make any method-dependent alterations here, eg add Content-type to headers for POST

        while more_pages:
            params['page'] = page
            page_data = self._request(api_path, method, params, headers, body, post_param)
            #! assumes req returns total_pages field, mod as needed
            total_pages = page_data.get('page', {}).get('total_pages', 0)
            #! assumes API is using HAL _embedded format
            this_page_data = page_data.get('_embedded', {}).get(hal_element, [])
            all_data += this_page_data

            page += 1
            more_pages = page < total_pages

        return all_data      

def entrypoint():
    import argparse
    #? Remove this section if not accepting arguments from CLI
    #region #####-   Argparse                                                ##########
    example = (r'Example usage: '
               r'manageLibrary -db %APPDATA%\MediaMonkey\MM.DB5')
    parser = argparse.ArgumentParser(
        'manageLibrary',
        usage='',
        description=__doc__,
        epilog=example)
    parser.add_argument('db',
                        metavar='database',
                        help="MediaMonkey database to extract playlists from.",
                        default=False,
                        type=str)
    # parser.add_argument('--var1', action='store_true', help='describe arg for when man or help is used')

    # args = parser.parse_args()
    #endregion

    get_from_mediamonkey = True
    submit_to_plex = False

    # Uncomment for testing setup   
    if get_from_mediamonkey == True:
        mlib = MediaLibrary(db=r'C:\Users\epopisces\AppData\Roaming\MediaMonkey5\MM5.DB')

        mlib.connect_database()
        mlib.get_playlists()
        playlists_to_sync = [playlist for playlist in mlib.playlists.keys() if playlist in mlib.playlists_of_interest]
        for playlist in playlists_to_sync:
            if mlib.playlists[playlist].auto:
                mlib.get_static_playlist_from_autoplaylist(playlist)
        
        mlib.close_database()

    # TODO Submit to plex
    plex = PlexServer(baseurl='http://10.1.10.11:32400', token='duEp3jG_26z95GZVMdaq') # server/token in config file
    
    for playlist in playlists_to_sync:
        for track in mlib.playlists[playlist].tracks:
            print(track)
            
    if submit_to_plex == True:
        plex = PlexServer(baseurl='http://10.1.10.11:32400', token='duEp3jG_26z95GZVMdaq') # server/token in config file
        
        for playlist in playlists_to_sync:
            for track in mlib.playlists[playlist].tracks:
                print(track)

        # TODO develop once method of populating items for a given playlist is determined
        for playlist in playlists_to_sync:
            if playlist in plex.playlist():
                continue
            else:
                playlist_items = mlib.playlists[playlist].tracks
                plex.createPlaylist(playlist, items=playlist_items)
        for playlist in plex.playlists():
            print(playlist.title)

if __name__ == "__main__":
    entrypoint()