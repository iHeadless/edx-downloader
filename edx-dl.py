#!/usr/bin/env python
# -*- coding: utf-8 -*-

# python 2/3 compatibility imports
from __future__ import print_function
from __future__ import unicode_literals

try:
    from http.cookiejar import CookieJar
except ImportError:
    from cookielib import CookieJar

try:
    from urllib.parse import urlencode
except ImportError:
    from urllib import urlencode

try:
    from urllib.request import urlopen
    from urllib.request import build_opener
    from urllib.request import install_opener
    from urllib.request import HTTPCookieProcessor
    from urllib.request import Request
    from urllib.request import URLError
except ImportError:
    from urllib2 import urlopen
    from urllib2 import build_opener
    from urllib2 import install_opener
    from urllib2 import HTTPCookieProcessor
    from urllib2 import Request
    from urllib2 import URLError

# we alias the raw_input function for python 3 compatibility
try:
    input = raw_input
except:
    pass

import argparse
import getpass
import json
import os
import os.path
import re
import sys
import unicodedata
import string
import logging
import re
import youtube_dl
import glob

from subprocess import Popen, PIPE
from datetime import timedelta, datetime

from bs4 import BeautifulSoup

OPENEDX_SITES = {
    'edx': {
        'url': 'https://courses.edx.org', 
        'courseware-selector': ('nav', {'aria-label':'Course Navigation'}),
    }, 
    'stanford': {
        'url': 'https://class.stanford.edu',
        'courseware-selector': ('section', {'aria-label':'Course Navigation'}),
    },
}
BASE_URL = OPENEDX_SITES['edx']['url']
EDX_HOMEPAGE = BASE_URL + '/login_ajax'
LOGIN_API = BASE_URL + '/login_ajax'
DASHBOARD = BASE_URL + '/dashboard'
COURSEWARE_SEL = OPENEDX_SITES['edx']['courseware-selector']

YOUTUBE_VIDEO_ID_LENGTH = 11

## If nothing else is chosen, we chose the default user agent:

DEFAULT_USER_AGENTS = {"chrome": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.31 (KHTML, like Gecko) Chrome/26.0.1410.63 Safari/537.31",
                       "firefox": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.8; rv:24.0) Gecko/20100101 Firefox/24.0",
                       "edx": 'edX-downloader/0.01'}

USER_AGENT = DEFAULT_USER_AGENTS["edx"]

PY3 = ( sys.version_info >= (3,0) )

def bprint(data):
    if not isinstance(data, str):
        data = data.decode()
    print(data.strip())

def youtube_get_filename(url, formatstr = None):
    logging.debug('[debug] youtube_get_filename:%s, %s', url, formatstr )
    ydl_options = {'outtmpl': '%(title)s.%(ext)s', 'nocheckcertificate': True}
    if formatstr:
        ydl_options['format'] = formatstr
    ydl = youtube_dl.YoutubeDL(ydl_options)
    # Add all the available extractors
    ydl.add_default_info_extractors()

    result = ydl.extract_info(url, download=False)

    if 'entries' in result:
        # Can be a playlist or a list of videos
        video = result['entries'][0]
    else:
        # Just a video
        video = result
    return ydl.prepare_filename(video).encode("utf-8")

def validate_filename(filename, default_name=""):
    """
    >>> bprint(validate_filename("&?foo*bar"))
    foobar
    >>> bprint(validate_filename("#$?*@"))
    <BLANKLINE>
    >>> bprint(validate_filename("#$?*@","course_dir"))
    course_dir
    """
    validFilenameChars = "-_.() %s%s" % (string.ascii_letters, string.digits)
    cleanedFilename = unicodedata.normalize('NFKD', filename).encode('ASCII', 'ignore')
    fn = ''.join(c for c in cleanedFilename.decode("utf-8") if c in validFilenameChars)
    return fn if fn != "" else default_name

def parseNumList(numlist):
    """
    >>> parseNumList("1")
    [1]
    >>> parseNumList("5-9")
    [5, 6, 7, 8, 9]
    >>> parseNumList("1,8,16")
    [1, 8, 16]
    >>> parseNumList("1,3,5-7,8-10")
    [1, 3, 5, 6, 7, 8, 9, 10]
    >>> parseNumList("all")
    [0]
    >>> parseNumList("string,list")
    []
    >>> parseNumList("7-3")
    []
    """
    if (numlist == "all"): return [0]
    numlist_out = []
    for numlist_item in re.split(r'[ ,]+',numlist):
        if len(numlist_item.split('-')) == 2:
            m = re.match(r'(\d+)(?:-(\d+))?$', numlist_item)
            if not m:
                raise argparse.ArgumentTypeError("'" + numlist_item + "' is not a range of number. Expected forms like '1-5'.")
            start = m.group(1)
            end = m.group(2) or start
            if int(start) <= int(end):
                numlist_out.extend(range(int(start,10), int(end,10)+1))
        if numlist_item.isdigit():
            numlist_out.append(int(numlist_item))
    return numlist_out

def change_openedx_site(site_name):
    global BASE_URL
    global EDX_HOMEPAGE
    global LOGIN_API
    global DASHBOARD
    global COURSEWARE_SEL

    if site_name not in OPENEDX_SITES.keys():
        logging.error("[error] OpenEdX platform should be one of: %s" % ', '.join(OPENEDX_SITES.keys()))
        sys.exit(2)
    
    BASE_URL = OPENEDX_SITES[site_name]['url']
    EDX_HOMEPAGE = BASE_URL + '/login_ajax'
    LOGIN_API = BASE_URL + '/login_ajax'
    DASHBOARD = BASE_URL + '/dashboard'
    COURSEWARE_SEL = OPENEDX_SITES[site_name]['courseware-selector']

def get_initial_token():
    """
    Create initial connection to get authentication token for future requests.

    Returns a string to be used in subsequent connections with the
    X-CSRFToken header or the empty string if we didn't find any token in
    the cookies.
    """
    cj = CookieJar()
    opener = build_opener(HTTPCookieProcessor(cj))
    install_opener(opener)
    opener.open(EDX_HOMEPAGE)

    for cookie in cj:
        if cookie.name == 'csrftoken':
            return cookie.value

    return ''


def get_page_contents(url, headers):
    """
    Get the contents of the page at the URL given by url. While making the
    request, we use the headers given in the dictionary in headers.
    """
    logging.debug("[debug] url = " + url)
    result = urlopen(Request(url, None, headers))
    try:
        charset = result.headers.get_content_charset(failobj="utf-8")  # for python3
    except:
        charset = result.info().getparam('charset') or 'utf-8'
    return result.read().decode(charset)


def edx_json2srt(o):
    i = 1
    output = ''
    for (s, e, t) in zip(o['start'], o['end'], o['text']):
        if t == "":
            continue
        output += str(i) + '\n'
        s = datetime(1, 1, 1) + timedelta(seconds=s/1000.)
        e = datetime(1, 1, 1) + timedelta(seconds=e/1000.)
        output += "%02d:%02d:%02d,%03d --> %02d:%02d:%02d,%03d" % \
            (s.hour, s.minute, s.second, s.microsecond/1000,
             e.hour, e.minute, e.second, e.microsecond/1000) + '\n'
        output += t + "\n\n"
        i += 1
    return output


def edx_get_subtitle(url, headers):
    """ returns a string with the subtitles content from the url """
    """ or None if no subtitles are available """
    try:
        jsonString = get_page_contents(url, headers)
        jsonObject = json.loads(jsonString)
        return edx_json2srt(jsonObject)
    except URLError as e:
        logging.warning('[warning] edX subtitles (error:%s)' % e.reason)
        return None


def parse_args():
    """
    Parse the arguments/options passed to the program on the command line.
    """
    parser = argparse.ArgumentParser(prog='edx-dl',
                                     description='Get videos from the OpenEdX platform',
                                     epilog='For further use information,'
                                     'see the file README.md',)
    # positional
    parser.add_argument('course_id',
                        action='store',
                        default=None,
                        nargs='?',
                        help='target course id '
                        '(e.g., https://courses.edx.org/courses/BerkeleyX/CS191x/2013_Spring/info/)'
                        )

    # optional
    parser.add_argument('-u',
                        '--username',
                        action='store',
                        help='your edX username (email)')
    parser.add_argument('-p',
                        '--password',
                        action='store',
                        help='your edX password')
    parser.add_argument('-f',
                        '--format',
                        dest='format',
                        action='store',
                        default=None,
                        help='format of videos to download')
    parser.add_argument('-s',
                        '--with-subtitles',
                        dest='subtitles',
                        action='store_true',
                        default=False,
                        help='download subtitles with the videos')
    parser.add_argument('-o',
                        '--output-dir',
                        action='store',
                        dest='output_dir',
                        help='store the files to the specified directory',
                        default='Downloaded')
    parser.add_argument('-x',
                        '--platform',
                        action='store',
                        dest='platform',
                        help='OpenEdX platform, currently either "edx" or "stanford"',
                        default='edx')
    parser.add_argument('-r',
                        '--rate-limit',
                        action='store',
                        dest='ratelimit',
                        help='Limit the download speed to the specified maximum L (e.g., 50k or 44.6m)',
                        default=None)
    parser.add_argument('-w',
                        '--week',
                        action='store',
                        nargs = "*",
                        type=parseNumList,
                        help='Week number (number on the list of --list or "all")',
                        default=None)
    parser.add_argument('-l',
                        '--list',
                        action='store_true',
                        default=False,
                        dest='list_weeks',
                        help='List weeks in course')
    parser.add_argument('-e',
                        '--list-enrolled',
                        action='store_true',
                        default=False,
                        dest='list_enrolled',
                        help='List enrolled courses')
    parser.add_argument('-c',
                        '--course-number',
                        action='store',
                        nargs = "*",
                        default=None,
                        type = parseNumList,
                        dest='course_number',
                        help='Course number in list of -e')
    parser.add_argument('-d',
                        '--do-not-rename',
                        action='store_true',
                        default=False,
                        dest='notrename',
                        help='Do not try to search and rename files with changed index')
    parser.add_argument('--test',
                        action='store_true',
                        default=False,
                        help=argparse.SUPPRESS)

    args = parser.parse_args()
    return args


def main():
    args = parse_args()
    if args.test:
        import doctest
        doctest.testmod(verbose=True)
        sys.exit(0)
    ## clean args a bit. Maybe argparse can do it for me
    ## TODO: add exception handling
    ## TODO: clean args processing
    if type(args.course_number) is list and type(args.course_number[0]) is list: args.course_number=args.course_number[0]
    if type(args.week) is list and type(args.week[0]) is list: args.week=args.week[0]

    # if no args means we are calling the interactive version
    is_interactive = len(sys.argv) == 1
    if is_interactive:
        args.platform = input('Platform [edx/stanford]: ')
        args.username = input('Username: ')
        args.password = getpass.getpass()

    change_openedx_site(args.platform)

    if not args.username or not args.password:
        logging.error("[error] You must supply username AND password to log-in")
        sys.exit(2)

    # Prepare Headers
    headers = {
        'User-Agent': USER_AGENT,
        'Accept': 'application/json, text/javascript, */*; q=0.01',
        'Content-Type': 'application/x-www-form-urlencoded;charset=utf-8',
        'Referer': EDX_HOMEPAGE,
        'X-Requested-With': 'XMLHttpRequest',
        'X-CSRFToken': get_initial_token(),
    }

    # Login
    post_data = urlencode({'email': args.username, 'password': args.password,
                           'remember': False}).encode('utf-8')
    request = Request(LOGIN_API, post_data, headers)
    response = urlopen(request)
    resp = json.loads(response.read().decode('utf-8'))
    if not resp.get('success', False):
        logging.error(resp.get('value', "Wrong Email or Password."))
        exit(2)

    # Get user info/courses
    dash = get_page_contents(DASHBOARD, headers)
    soup = BeautifulSoup(dash)
    data = soup.find_all('ul')[1]
    USERNAME = data.find_all('span')[1].string
    COURSES = soup.find_all('article', 'course')
    courses = []
    course_loop = []
    c = 0
    for COURSE in COURSES:
        c += 1
        c_name = COURSE.h3.text.strip()
        c_link = BASE_URL + COURSE.a['href']
        if c_link.endswith('info') or c_link.endswith('info/'):
            state = 'Started'
        else:
            state = 'Not yet'
        courses.append((c_name, c_link, state))
        if args.course_id and (c_link.rstrip("/") == args.course_id.rstrip("/")):
            course_loop = [c]
    numOfCourses = len(courses)
    # Welcome and Choose Course

    logging.info('Welcome %s' % USERNAME)
    logging.info('You can access %d courses' % numOfCourses)

    c = 0
    for course in courses:
        c += 1
        logging.info('%d - %s -> %s' % (c, course[0], course[2]))
    if args.list_enrolled: sys.exit(0)

    ## url gets priority over "course number"

    if args.course_number:
        if type(args.course_number) is list:
            if args.course_number == ['all']:
                course_loop = range(1,numOfCourses+1)
                logging.info("[info] Downloading all started courses")
            else:
                course_loop = args.course_number
                logging.info("[info] Selected courses : " + str(course_loop))
        else:
            logging.error('-c need number, list or "all"')
            sys.exit(2)

    if course_loop == []:
       if args.course_number:
            course_loop = args.course_number
       else:
           course_loop = [int(input('Enter Course Number: '))]

    if course_loop == []:
        while c_number > numOfCourses or courses[c_number - 1][2] != 'Started':
            logging.error('Enter a valid Number for a Started Course ! between 1 and %d', numOfCourses)
            c_number = int(input('Enter Course Number: '))
            course_loop = [c_number]

    ## course loop

    for current_course in course_loop:
        if current_course <= numOfCourses:
            logging.info("[info] Using course " + str(current_course) + ": " + COURSES[current_course - 1].h3.text.strip())
        else:
            continue

        if courses[current_course - 1][2] != 'Started':
            logging.info("[info] Course " + str(current_course) + ": " + COURSES[current_course - 1].h3.text.strip() + " is not started yet")
            continue
        selected_course = courses[current_course - 1]
        COURSEWARE = selected_course[1].replace('info', 'courseware')

        ## Getting Available Weeks
        courseware = get_page_contents(COURSEWARE, headers)
        soup = BeautifulSoup(courseware)

        data = soup.find(*COURSEWARE_SEL)
        WEEKS = data.find_all('div')
        weeks = [(w.h3.a.string, [BASE_URL + a['href'] for a in
                 w.ul.find_all('a')]) for w in WEEKS]
        numOfWeeks = len(weeks)

        # Choose Week or choose all
        logging.info('%s has %d weeks so far' % (selected_course[0], numOfWeeks))
        w = 0
        for week in weeks:
            w += 1
            logging.info('%d - Download %s videos' % (w, week[0].strip()))
        if is_interactive:
            logging.info('%d - Download them all' % (numOfWeeks + 1))
        else:
            logging.info('"all" - Download them all')
        if args.list_weeks:
            sys.exit(1)
        if args.week:
            if type(args.week) is list:
                if args.week == [0]:
                    week_loop = range(1,numOfWeeks+1)
                    logging.info("[info] Downloading all items")
                else:
                    week_loop = args.week
                    logging.info("[info] Downloading items : " + str(week_loop))
            else:
                logging.error('-w need number, list or "all"')
                sys.exit(2)
        else:
            w_number = int(input('Enter Your Choice: '))
            week_loop = [w_number]
        ## TODO: check all list
        if not week_loop:
            while w_number > numOfWeeks + 1:
                logging.error('Enter a valid Number between 1 and %d' % (numOfWeeks + 1))
                w_number = int(input('Enter Your Choice: '))

        ## get format / subtitles info before main loop
        if is_interactive:
            # Get Available Video formats
            os.system('youtube-dl -F %s' % video_link[-1])
            logging.error('Choose a valid format or a set of valid format codes e.g. 22/17/...')
            args.format = input('Choose Format code: ')

            args.subtitles = input('Download subtitles (y/n)? ').lower() == 'y'

        logging.info("[info] Base output directory: " + args.output_dir)
        ## Week loop
        for current_week in week_loop:
            links = weeks[current_week - 1][1]
            w_name = weeks[current_week-1][0].strip()
            logging.info("[info] Processing item # %s  " % current_week)
            video_id = []
            subsUrls = []
            regexpSubs = re.compile(r'data-transcript-translation-url=(?:&#34;|")([^"&]*)(?:&#34;|")')
            splitter = re.compile(r'data-streams=(?:&#34;|").*1.0[0]*:')
            extra_youtube = re.compile(r'//w{0,3}\.youtube.com/embed/([^ \?&]*)[\?& ]')
            for link in links:
                logging.info("[info] Processing '%s'..." % link)
                page = get_page_contents(link, headers)

                id_container = splitter.split(page)[1:]
                video_id += [link[:YOUTUBE_VIDEO_ID_LENGTH] for link in
                             id_container]
                subsUrls += [BASE_URL + regexpSubs.search(container).group(1) + "?videoId=" + id + "&language=en"
                             for id, container in zip(video_id[-len(id_container):], id_container)]
                # Try to download some extra videos which is referred by iframe
                extra_ids = extra_youtube.findall(page)
                video_id += [link[:YOUTUBE_VIDEO_ID_LENGTH] for link in
                             extra_ids]
                subsUrls += ['' for link in extra_ids]

            video_link = ['http://youtube.com/watch?v=' + v_id
                          for v_id in video_id]

            if len(video_link) < 1:
                logging.warning('WARNING: No downloadable video found.')
                continue
                # sys.exit(0)

            # Download Videos
            c = 0
            for v, s in zip(video_link, subsUrls):
                c += 1
                w_folder = validate_filename(w_name,"week " + str(current_week))
                target_dir = os.path.join(args.output_dir,
                                          validate_filename(selected_course[0],"course_folder"),w_folder)
                filename_prefix = str(c).zfill(2)
                cmd = ["youtube-dl",
                       "-o", os.path.join(target_dir, filename_prefix + "-%(title)s.%(ext)s")]
                if args.format:
                    cmd.append("-f")
                    # defaults to mp4 in case the requested format isn't available
                    cmd.append(args.format + '/mp4')
                if args.subtitles:
                    cmd.append('--write-sub')
                if args.ratelimit:
                    cmd.append('--rate-limit='+args.ratelimit)
                cmd.append(str(v))

                file_renamed = False
                if args.format:
                    video_filename = youtube_get_filename(str(v), args.format + '/mp4').decode("utf-8")
                else:
                    video_filename = youtube_get_filename(str(v)).decode("utf-8", "22/mp4")
                v_fn_template = os.path.join(target_dir, ("[0-9]" * len(filename_prefix)) + "-" + video_filename)
                v_fn_exact = os.path.join(target_dir, str(filename_prefix) + "-" + video_filename)
                logging.info("[info] Filename template:" + v_fn_template)
                search_file = glob.glob(os.path.abspath(v_fn_template))

                if (len(search_file) == 1) and (search_file[0] != v_fn_exact):
                    logging.info("[info] Found with different index:" + search_file[0])
                    file_renamed = True
                    if not args.notrename:
                        logging.info("[info] Rename to:" + v_fn_exact)
                        os.rename(search_file[0], v_fn_exact)
                    else:
                        logging.info("[info] No action")

                logging.info("[info] youtube-dl: " + ' '.join(cmd))

                popen_youtube = Popen(cmd, stdout=PIPE, stderr=PIPE)

                youtube_stdout = b''
                enc = sys.getdefaultencoding()
                while True:  # Save output to youtube_stdout while this being echoed
                    tmp = popen_youtube.stdout.read(1)
                    youtube_stdout += tmp
                    print(tmp.decode(enc), end="")
                    sys.stdout.flush()
                    # do it until the process finish and there isn't output
                    if tmp == b"" and popen_youtube.poll() is not None:
                        break

                if args.subtitles:
                    filename = get_filename(target_dir, filename_prefix)
                    if file_renamed:
                        v_fn_old_sub = os.path.splitext(search_file[0])[0] + '.srt'
                        v_fn_exact_sub = os.path.splitext(v_fn_exact)[0] + '.srt'
                        if os.path.isfile(v_fn_old_sub):
                            logging.info("[info] Rename subs to:" + v_fn_exact_sub)
                            os.rename(v_fn_old_sub, v_fn_exact_sub)
                    subs_filename = os.path.join(target_dir, filename + '.srt')
                    if not os.path.exists(subs_filename):
                        subs_string = edx_get_subtitle(s, headers)
                        if subs_string:
                            logging.info('Writing edX subtitles: %s' % subs_filename)
                            open(os.path.join(os.getcwd(), subs_filename),
                                 'wb+').write(subs_string.encode('utf-8'))
                ## /week loop
        ## /course loop

def get_filename(target_dir, filename_prefix):
    """ returns the basename for the corresponding filename_prefix """
    # this whole function is not the nicest thing, but isolating it makes
    # things clearer , a good refactoring would be to get
    # the info from the video_url or the current output, to avoid the
    # iteration from the current dir
    filenames = os.listdir(target_dir)
    # subs_filename = filename_prefix
    for name in filenames:  # Find the filename of the downloaded video
        if name.startswith(filename_prefix):
            (basename, ext) = os.path.splitext(name)
            return basename

if __name__ == '__main__':
    logging.basicConfig(level = logging.DEBUG, format = '%(message)s')
    try:
        main()
    except KeyboardInterrupt:
        logging.info("[info] \n\nCTRL-C detected, shutting down....")
        sys.exit(0)
