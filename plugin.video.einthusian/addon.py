import re
import sys
import json
import base64
import urllib
import requests
import xbmc
import xbmcgui
import xbmcplugin
from pprint import pprint, pformat
from urlparse import parse_qs
from bs4 import BeautifulSoup as bs
from lib.simpleplugin3 import MemStorage


PLUGIN_BASE_URL = sys.argv[0]
addon_handle = int(sys.argv[1])
args = parse_qs(sys.argv[2][1:])

storage = MemStorage(PLUGIN_BASE_URL)

xbmc.log('base_url: {}'.format(PLUGIN_BASE_URL), level=xbmc.LOGNOTICE)
xbmc.log('args: {}'.format(sys.argv[2]), level=xbmc.LOGNOTICE)

xbmcplugin.setContent(addon_handle, 'movies')

mode = args.get('mode', None)
if mode is not None:
    mode = mode[0]
lang = args.get('lang', None)
if lang is not None:
    lang = lang[0]
category = args.get('category', None)
if category is not None:
    category = category[0]
sub_category = args.get('sub_category', None)
if sub_category is not None:
    sub_category = sub_category[0]
page = args.get('page', None)
if page is not None:
    page = int(page[0])
else:
    page = 1

# kodi defaults
DEFAULT_VIDEO_IMG = 'DefaultVideo.png'
DEFAULT_FOLDER_IMG = 'DefaultFolder.png'

# website parameters
WEBSITE_BASE_URL = 'https://einthusan.tv'
WEBSITE_DEFAULT_LANG = 'Hindi'
WEBSITE_USER_AGENT = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/81.0.4044.122 Safari/537.36 Edg/81.0.416.64'


# utility functions
def enum(**enums):
    return type('Enum', (), enums)


def decode_base64(data):
    return base64.b64decode(data[0:10] + data[-1] + data[12:-1])


def build_plugin_url(query_params):
    return '{}?{}'.format(PLUGIN_BASE_URL, urllib.urlencode(query_params))


def build_site_url(url=None):
    if url is None:
        return WEBSITE_BASE_URL
    else:
        return '{}{}'.format(WEBSITE_BASE_URL, url)


def fetch_page(url):
    headers = {
        'Origin': WEBSITE_BASE_URL,
        'User-Agent': WEBSITE_USER_AGENT
    }
    soup = None
    resp = requests.get(url, headers=headers)
    if resp.status_code != requests.codes.ok:
        xbmc.log('url={}, resp={}'.format(
            url, resp.status_code), xbmc.LOGERROR)
        return soup

    soup = bs(resp.text, 'html.parser')
    return soup


def site_language_categories_get(url):
    options = list()
    soup = fetch_page(url)
    if soup is None:
        return options

    keyword = 'launcher'

    for a in soup.find_all('a'):
        try:
            if keyword not in a['href']:
                continue
            p = a.find('p')
            lang = p.string
            href = a['href']
            options.append(dict(lang=lang, url=href))
        except KeyError:
            continue

    return options


def site_main_categories_get(url):
    options = list()
    soup = fetch_page(url)
    if soup is None:
        return options

    section = soup.find(id='UILaunchPad')
    for a in section.find_all('a'):
        try:
            if a['href'] != '#':
                for p in a.find_all('p'):
                    options.append({'name': p.string, 'url': a['href']})
        except KeyError:
            continue

    return options


def site_movies_list_get(url, section_id):
    movies = list()
    soup = fetch_page(url)
    if soup is None:
        return movies

    section = soup.find(id=section_id)
    # block #1 will give url and img
    for a in section.select('.block1 a'):
        movie = dict()
        try:
            img = a.find('img')
            movie['url'] = a['href']
            movie['id'] = a['href'].split('/')[3]
            movie['img'] = img['src']
        except:
            continue
        else:
            movies.append(movie)

    # block #2 will name and other information
    for a in section.select('.block2 .title'):
        for movie in movies:
            try:
                if movie['url'] != a['href']:
                    continue
            except KeyError:
                continue

            movie['name'] = a.contents[0].string

    return movies


def site_movies_featured_list_get(url):
    return site_movies_list_get(url, 'UIFeaturedFilms')

def site_movies_search_result_get(url):
    return site_movies_list_get(url, 'UIMovieSummary')


def site_movies_playable_link_get(url, ajax_url):
    headers = {
        'Origin': WEBSITE_BASE_URL,
        'User-Agent': WEBSITE_USER_AGENT
    }

    xbmc.log('url: {}, ajax_url: {}'.format(url, ajax_url), xbmc.LOGNOTICE)

    session = requests.Session()
    resp = session.get(url, headers=headers)
    if resp.status_code != requests.codes.ok:
        xbmc.log('url={}, resp={}'.format(
            url, resp.status_code), xbmc.LOGERROR)
        return None

    soup = bs(resp.text, 'html.parser')

    html = soup.find('html')
    section = soup.find(id='UIVideoPlayer')
    page_id = html['data-pageid']
    data_id = section['data-content-id']
    pingable = section['data-ejpingables']
    hls_link = section['data-hls-link']
    mp4_link = section['data-mp4-link']

    json_data = json.dumps({"EJOutcomes": pingable, "NativeHLS": False})
    post_data = {
        'xEvent': 'UIVideoPlayer.PingOutcome',
        'xJson': json_data,
        'arcVersion': 10,
        'appVersion': 255,
        'gorilla.csrf.Token': page_id
    }

    json_resp = session.post(
        ajax_url,
        data=post_data,
        cookies=session.cookies
    ).text

    resp = json.loads(json_resp)
    base64_links = resp["Data"]["EJLinks"]
    json_links = decode_base64(base64_links)
    links = json.loads(json_links)

    session.close()

    xbmc.log(pformat(links), xbmc.LOGNOTICE)

    return links['HLSLink']


# processing functions for different modes
def mode_index():
    query_params = dict(mode=Mode.Main_Categories)

    for option in site_language_categories_get(WEBSITE_BASE_URL):
        lang = option['lang']
        query_params.update(dict(lang=lang))
        plugin_url = build_plugin_url(query_params)

        storage['LANG_{}'.format(lang)] = option['url']

        li = xbmcgui.ListItem(lang, iconImage=DEFAULT_FOLDER_IMG)
        xbmcplugin.addDirectoryItem(
            handle=addon_handle, url=plugin_url, listitem=li, isFolder=True)

    xbmcplugin.endOfDirectory(addon_handle)


def mode_main_categories():
    query_params = dict(mode=Mode.Sub_Categories, lang=lang)
    url = build_site_url(storage['LANG_{}'.format(lang)])
    xbmc.log('lang:{}, url:{}'.format(lang, url), xbmc.LOGNOTICE)
    options = site_main_categories_get(url)

    for category, meta in main_category_map.items():
        query_params.update(category=category)
        plugin_url = build_plugin_url(query_params)

        for option in options:
            if meta['name'] in option['name']:
                storage['CATEGORY_{}_{}'.format(
                    lang, category)] = option['url']

        li = xbmcgui.ListItem(meta['name'], iconImage=DEFAULT_FOLDER_IMG)
        xbmcplugin.addDirectoryItem(
            handle=addon_handle, url=plugin_url, listitem=li, isFolder=True)

    xbmcplugin.endOfDirectory(addon_handle)


def mode_sub_categories():
    query_params = dict(lang=lang, category=category)
    sub_categories = main_category_map[category]['subcategories']
    for sub_category in sub_categories:
        if sub_category == SubCategory.Search:
            query_params.update(mode=Mode.Search)
        else:
            query_params.update(mode=Mode.Browse)
        query_params.update(sub_category=sub_category)
        plugin_url = build_plugin_url(query_params)

        li = xbmcgui.ListItem(
            sub_category_map[sub_category]['name'], iconImage=DEFAULT_FOLDER_IMG)
        xbmcplugin.addDirectoryItem(
            handle=addon_handle, url=plugin_url, listitem=li, isFolder=True)

    xbmcplugin.endOfDirectory(addon_handle)


def browse():
    sub_category_map[sub_category]['action']()


def browse_featured():
    if category == Category.Movies:
        browse_movies_featured()


def ui_build_movie_list(movies, query_params):
    for movie in movies:
        movie_id = movie['id']
        movie_name = movie['name']
        movie_url = build_site_url(movie['url'])
        movie_img = 'https:{}'.format(movie['img'])

        xbmc.log('id: {}, name: {}, url: {}'.format(movie_id, movie_name,
                                                    movie_url), xbmc.LOGNOTICE)

        storage['MOVIE_{}_{}'.format(lang, movie_id)] = movie['url']

        query_params.update({'id': movie_id})
        plugin_url = build_plugin_url(query_params)

        li = xbmcgui.ListItem(label=movie_name, iconImage=DEFAULT_VIDEO_IMG)
        info = {
            'title': movie_name,
        }
        li.setInfo('video', info)
        li.setArt({'thumb': movie_img, 'poster': movie_img})
        li.setProperties({'isPlayable': False, 'isFolder': False})
        xbmcplugin.addDirectoryItem(
            handle=addon_handle, url=plugin_url, listitem=li)


def ui_build_movie_list_single_page(movies, query_params):
    ui_build_movie_list(movies, query_params)

    xbmcplugin.endOfDirectory(addon_handle)


def ui_build_movie_list_multi_page(movies, query_params, page):
    query_params_modified = query_params
    query_params_modified.update(dict(mode=Mode.Play))

    ui_build_movie_list(movies, query_params_modified)

    query_params_modified = query_params
    query_params_modified.update(dict(mode=Mode.Browse, page=(page + 1)))
    plugin_url = build_plugin_url(query_params_modified)

    li = xbmcgui.ListItem('more..', iconImage=DEFAULT_FOLDER_IMG)
    xbmcplugin.addDirectoryItem(
        handle=addon_handle, url=plugin_url, listitem=li, isFolder=True)
    
    xbmcplugin.endOfDirectory(addon_handle)


def browse_movies_featured():
    url = build_site_url(storage['CATEGORY_{}_{}'.format(lang, category)])
    query_params = dict(mode=Mode.Play, lang=lang, category=category,
                        sub_category=sub_category)
    ui_build_movie_list_single_page(site_movies_featured_list_get(url), 
                                    query_params)


def _browse_list_common_(url):
    query_params = dict(lang=lang, category=category, sub_category=sub_category)
    ui_build_movie_list_multi_page(site_movies_search_result_get(url),
                                   query_params, page)


def browse_recent():
    url = '{}/movie/results/?find=Recent&lang={}&page={}'.format(
        WEBSITE_BASE_URL, lang.lower(), page)
    _browse_list_common_(url)
    

def browse_most_watched():
    # last 30 days
    url = '{}/movie/results/?find=Popularity&lang={}&ptype=View&tp=l30d&'\
          'page={}'.format(WEBSITE_BASE_URL, lang.lower(), page)
    _browse_list_common_(url)


def browse_staff_picked():
    url = '{}/movie/results/?find=StaffPick&lang={}&page={}'.format(
        WEBSITE_BASE_URL, lang.lower(), page)
    _browse_list_common_(url)


def search():
    sub_category_map[sub_category]['action']()


def search_subcategory():
    query = args.get('query', None)
    if query is not None:
        query = query[0]
    else:
        query = None
        input = xbmc.Keyboard('', 'Search')
        input.doModal()
        if input.isConfirmed():
            query = input.getText()
        else:
            return

    if category == Category.Movies:
        search_movies(query)


def search_movies(query):
    query_params = dict(lang=lang, category=category, sub_category=sub_category,
                        query=query)
    url = '{}/movie/results/?lang={}&query={}&page={}'.format(WEBSITE_BASE_URL,
                    lang.lower(), query, page)
    ui_build_movie_list_multi_page(site_movies_search_result_get(url), 
                                   query_params, page)


def play():
    if category == Category.Movies:
        play_movie()


def play_movie():
    movie_id = args.get('id', None)
    if movie_id is not None:
        movie_id = movie_id[0]
    movie_url = build_site_url(storage['MOVIE_{}_{}'.format(lang, movie_id)])
    ajax_url = movie_url.replace('movie', 'ajax/movie')

    movie_resolved_url = site_movies_playable_link_get(movie_url, ajax_url)

    xbmc.log('id: {}, url: {}'.format(
        movie_id, movie_resolved_url), xbmc.LOGNOTICE)

    li = xbmcgui.ListItem(label=movie_id, iconImage=DEFAULT_VIDEO_IMG)
    li.setProperties({'isPlayable': True, 'isFolder': False})
    xbmcplugin.addDirectoryItem(
        handle=addon_handle, url=movie_resolved_url, listitem=li)
    xbmcplugin.setResolvedUrl(addon_handle, True, li)
    xbmcplugin.endOfDirectory(addon_handle)


# maps
Mode = enum(
    Index='None',
    Main_Categories='0',
    Sub_Categories='1',
    Browse='2',
    Search='5',
    Play='6',
    Download='7',
)

Category = enum(
    Movies='0',
    Movie_Clips='1',
    Music_Videos='2'
)

SubCategory = enum(
    Featured='0',
    Recent='1',
    Most_Watched='2',
    Staff_Picked='3',
    Search='4'
)

mode_map = {
    Mode.Index: mode_index,
    Mode.Main_Categories: mode_main_categories,
    Mode.Sub_Categories: mode_sub_categories,
    Mode.Browse: browse,
    Mode.Search: search,
    Mode.Play: play
}

main_category_map = {
    Category.Movies: {
        'category': 'MOVIES',
        'keyword': 'movie',
        'name': 'Movies',
        'subcategories': [
            SubCategory.Featured,
            SubCategory.Recent,
            SubCategory.Most_Watched,
            SubCategory.Staff_Picked,
            SubCategory.Search
        ]
    }
}

sub_category_map = {
    SubCategory.Featured: {
        'name': 'Featured',
        'action': browse_featured
    },
    SubCategory.Recent: {
        'name': 'Recent',
        'action': browse_recent
    },
    SubCategory.Most_Watched: {
        'name': 'Most Watched',
        'action': browse_most_watched
    },
    SubCategory.Staff_Picked: {
        'name': 'Staff Picked',
        'action': browse_staff_picked
    },
    SubCategory.Search: {
        'name': 'Search',
        'action': search_subcategory
    }
}

# entry
mode_map[str(mode)]()
