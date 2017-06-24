#!/usr/bin/env python
# encoding=utf8

from __future__ import print_function, unicode_literals, absolute_import

import atexit
import base64
import functools
import json
import logging
import os
import pickle
import re
import sys
import threading
import time
from collections import namedtuple
from urllib.parse import urlparse

import arrow
import requests
from requests_oauthlib.oauth1_session import OAuth1Session, TokenRequestDenied

__version__ = '0.0.4'
__all__ = ['Fan', 'User', 'Status', 'Timeline', 'Config']

_session = None  # type: OAuth1Session
_cfg = None  # type: Config
_logger = logging.getLogger(__name__)


class AuthFailed(Exception):
    def __init__(self, msg):
        self.msg = msg


def get_input(prompt=None):
    return input(prompt).strip()


def get_photo(p):
    if p is None:
        return False
    elif hasattr(p, 'read'):
        return p
    elif os.path.isfile(p):
        f = open(p, 'rb')
        return f
    else:
        try:
            url = p.strip('\'').strip('"')
            if urlparse(url).scheme != '':
                resp = requests.get(url, stream=True)
                resp.raise_for_status()
                if not resp.headers.get('Content-Type', '').lower().startswith('image/'):
                    return False
                return resp.raw
        except requests.RequestException:
            return False
    return False


Photo = namedtuple('Photo', ['url', 'largeurl', 'imageurl', 'thumburl', 'originurl', 'type'])


def _request(method, endpoint, **data):
    # 1-tuple (not a tuple at all)
    # {fieldname: file_object}
    # 2-tuple
    # {fieldname: (filename, file_object)}
    # 3-tuple
    # {fieldname: (filename, file_object, content_type)}
    # 4-tuple
    # {fieldname: (filename, file_object, content_type, headers)}
    data.setdefault('mode', 'lite')
    data.setdefault('format', 'html')
    files = data.pop('files', None)

    url = 'http://api.fanfou.com/{}.json'.format(endpoint)
    d = {{'GET': 'params', 'POST': 'data'}[method]: data}

    timeout = _cfg.timeout
    fail_sleep_time = _cfg.fail_sleep_time
    for failure in range(3):
        try:
            result = _session.request(method, url, **d, files=files, timeout=timeout)
            j = result.json()
            if result.status_code == 200:
                return True, j
            _logger.error(j['error'])
            return False, j['error']
        except requests.RequestException as e:
            _logger.error(e)
            timeout += 2
            fail_sleep_time += 2
            if failure >= 2:
                raise
        time.sleep(fail_sleep_time)


_get = functools.partial(_request, 'GET')
_post = functools.partial(_request, 'POST')


class Base:
    """
    :class:`User` 和 :class:`Status` 的基类。
    为子类提供对象缓存和自动加载功能。
    """
    endpiont = None
    _object_buffer = {}  # 对象缓存
    _time_format = 'ddd MMM DD HH:mm:ss Z YYYY'

    def __init__(self, *, id=None, data=None, **kwargs):
        # 构造函数的三种使用方式：
        # 1. User.get(id='') 由id获取对象
        # 2. User.get(data=rv) 由API返回的字典构造对象
        # 3. Status(text='abc') 提供一些参数构造一个不完全的对象(一般是没有ID)，API调用之后用返回结果补完
        # 4. User.get(master=True) 作为主人的特殊待遇
        self.id = id

        # 对 master 特殊对待
        if (id and not data and not kwargs) or kwargs.pop('master', None):
            self.fill()
        elif data:
            self.populate(data)
        elif kwargs:
            self.populate(kwargs)
        else:
            raise ValueError('One of id and data is required')

    @classmethod
    def get(cls, *, id=None, data=None, **kwargs):
        """
        获取一个对象

        :param str id: 对象 ID
        :param dict data: 由字典构造对象
        :rtype: cls
        """
        # make sure every object only has one instance
        id = id or (data.get('id') if data else id)
        if id not in cls._object_buffer:
            o = cls(id=id, data=data, **kwargs)
            cls._object_buffer[o.id] = o
            return o
        return cls._object_buffer[id]

    def populate(self, data):
        """用API返回的字典填充此对象"""
        raise NotImplementedError

    def fill(self):
        """调用API填充此对象"""
        _, rv = _get(self.endpiont, id=self.id)
        if _:
            self.populate(rv)


class Timeline:
    """

    """

    def __init__(self, user, endpoint):
        self.user = user
        """:class:`~van.User` 时间线的主人"""
        self.endpoint = endpoint
        self._pool = []  # type: [Status]
        self._max_id = None
        self._max_rawid = -1
        self._since_id = None
        self._since_rawid = 999999999  # 什么时候饭否消息会达到这个数字呢？
        self._curr = 0

    def tell(self):
        """
        返回当前游标的位置

        :rtype: int
        """
        return self._curr

    def rewind(self):
        """
        获取最新的状态插入到时间线的头部，并将指针置为0（指向最新的状态）

        :rtype: int
        """
        self._fetch_newer()
        self._curr = 0
        return 0

    def seek(self, offset=None, whence=0):
        """
        移动游标的位置

        :param int offset: 偏移量
        :param int whence: 相对位置

            * 0 -- 相对于时间线开始位置，偏移量必须 >= 0
            * 1 -- 相对于当前游标位置，偏移量可正可负，超出范围的偏移量会被纠正为边界值
            * 2 -- 相对于时间线结尾，偏移量 <=0

        .. attention::

            此函数只能在有限范围满足索引要求，超出范围太多的偏移量会被自动纠正为合法值。

        :return: 移动后的游标位置
        :rtype: int
        """
        if not self._pool:
            self._fetch_older()

        if whence == 0:
            if offset < 0:
                raise ValueError('offset should be zero or positive')
            self._curr = min(offset, max(len(self._pool) - 1, 0))
        elif whence == 1:
            self._curr += offset
            self._curr = min(max(self._curr, 0), len(self._pool) - 1)
        else:
            if offset > 0:
                old_len = len(self._pool)
                while old_len + offset >= len(self._pool):
                    if self._fetch_older() == 0:
                        break
                self._curr = min(old_len + offset, len(self._pool) - 1)
            else:
                self._curr = max(len(self._pool) + offset, 0)
        return self._curr

    def read(self, count=10):
        """
        从当前游标位置处往后读取 `count` 条消息

        :param int count: 读取数量
        :return: :class:`Status` 数组
        :rtype: [Status]
        """
        while self._curr + count >= len(self._pool):
            if self._fetch_older() == 0:
                break
        rv = self._pool[self._curr:self._curr + count]
        self._curr += count
        return rv

    def fetch(self, since_id=None, max_id=None, count=60):
        """
        调用 API 获取数据。
        可以自己控制 `since_id`, `max_id` 和 `count` 参数，获取的结果不加入内部缓存。

        :param since_id: 开始的消息ID
        :param max_id: 结束的消息ID
        :param count: 获取数量，最大为60
        :return: :class:`Status` 数组
        :rtype: [Status]
        """
        _, rv = _get(self.endpoint, id=self.user.id,
                     since_id=since_id, max_id=max_id, count=count)
        if _:
            rv = [Status.get(data=s) for s in rv]
        return _, rv

    def _fetch_older(self):
        _, rv = self.fetch(max_id=self._since_id)
        if _ and rv:
            self._since_id = rv[-1].id
            self._since_rawid = rv[-1].rawid
            if rv[0].rawid > self._max_rawid:
                self._max_id = rv[0].id
                self._max_rawid = rv[0].rawid
            self._pool.extend(rv)
            return len(rv)
        return 0

    def _fetch_newer(self):
        _, rv = self.fetch(since_id=self._max_id)
        if _ and rv:
            self._max_id = rv[0].id
            self._max_rawid = rv[0].rawid
            if rv[0].rawid < self._since_rawid:
                self._since_id = rv[-1].id
                self._since_rawid = rv[-1].rawid
            self._pool = rv + self._pool
            self._curr += len(rv)
            return len(rv)
        return 0

    def __iter__(self):
        """
        从当前游标位置开始获取消息，可以像普通数组一样在循环中使用。
        :return: :class:`Status`
        """
        while True:
            if self._curr >= len(self._pool):
                if self._fetch_older() == 0:
                    raise StopIteration
            yield self._pool[self._curr]
            self._curr += 1

    def __len__(self):
        return len(self._pool)


class User(Base):
    # 需要 id 参数，可查看其他用户信息的 API 在此类中（也可以省略 id 表示当前用户）
    endpiont = 'users/show'
    _object_buffer = {}  # 对象缓存

    def __init__(self, *, id=None, data=None, **kwargs):
        """
        :param str id: 用户ID
        :param str name: 用户名字
        :param str screen_name: 用户昵称
        :param str location: 位置
        :param str gender: 性别
        :param str birthday: 用户生日信息
        :param str description: 用户自述
        :param str url: 用户主页
        :param bool protected: 用户是否设置隐私保护
        :param int followers_count: 用户关注用户数
        :param int friends_count: 用户好友数
        :param int favourites_count: 用户收藏消息数
        :param int statuses_count: 用户消息数
        :param bool following: 该用户是被当前登录用户关注
        :param bool notifications: 当前登录用户是否已对该用户发出关注请求
        :param str created_at: 用户注册时间
        :param int utc_offset: UTC offset
        """
        self.timeline = Timeline(self, 'statuses/home_timeline')  # 返回此用户看到的时间线
        self.statues = Timeline(self, 'statuses/user_timeline')  # 返回此用户已发送的消息
        self.photos = Timeline(self, 'photos/user_timeline')  # 浏览指定用户的图片

        super(User, self).__init__(id=id, data=data, **kwargs)

    def populate(self, data):
        self.id = data.get('id')
        self.unique_id = data.get('unique_id')
        self.name = data.get('name')
        self.screen_name = data.get('screen_name')
        self.location = data.get('location')
        self.gender = data.get('gender')
        self.birthday = data.get('birthday')
        self.description = data.get(' description')
        self.url = data.get('url')
        self.protected = data.get('protected')
        self.followers_count = data.get('followers_count')
        self.friends_count = data.get('friends_count')
        self.favourites_count = data.get('favourites_count')
        self.statuses_count = data.get('statuses_count')
        self.photo_count = data.get('photo_count')
        self.following = data.get('following')
        self.notifications = data.get('notifications')
        self.created_at = data.get('created_at')
        self.utc_offset = data.get('utc_offset')
        self.profile_image_url = data.get('profile_image_url')
        self.profile_image_url_large = data.get('profile_image_url')
        if self.created_at:
            self.created_at = arrow.get(self.created_at, self._time_format)

    @property
    def followers(self, count=100):
        """
        返回此用户的关注者(前100个)
        此用户为当前用户的关注对象或未设置隐私
        """
        # count=100
        _, rv = _get('statuses/followers', id=self.id, count=count)
        if _:
            rv = [User.get(data=f) for f in rv]
        return _, rv

    @property
    def followers_id(self, count=None):
        """返回此用户关注者的id列表"""
        # count=1..60
        return _get('followers/ids', id=self.id, count=count)

    @property
    def friends(self, count=100):
        """
        返回此用户的关注对象(前100个)
        此用户为当前用户的关注对象或未设置隐私
        """
        # count=100
        _, rv = _get('statuses/friends', id=self.id, count=count)
        if _:
            rv = [User.get(data=f) for f in rv]
        return _, rv

    @property
    def friends_id(self, count=None):
        """返回此用户关注对象的id列表"""
        # count=1..60
        return _get('friends/ids', id=self.id, count=count)

    @property
    def favorites(self, count=None):
        """浏览此用户收藏的消息"""
        _, rv = _get('favorites/id', id=self.id, count=count)
        if _:
            rv = [Status.get(data=s) for s in rv]
        return _, rv

    def relationship(self, other):
        """
        返回此用户与 other 的关系： 是否屏蔽，是否关注，是否被关注

        :param str|User other: 其他用户
        :rtype: (a_blocked_b, a_following_b, a_followed_b)
        """
        if isinstance(other, User):
            other = other.id
        _, rv = _get('friendships/show', source_id=self.id, target_id=other)
        if _:
            source = rv['relationship']['source']
            rv = (source['blocking'] == 'true', source['following'] == 'true', source['followed_by'] == 'true')
        return _, rv

    def __str__(self):
        return '<User ({}@{})>'.format(self.name, self.id)

    __repr__ = __str__


class Status(Base):
    endpiont = 'statuses/show'
    _object_buffer = {}  # 对象缓存

    _at_re = re.compile(r'@<a.*?>(.*?)</a>', re.I)
    _topic_re = re.compile(r'#<a.*?>(.*?)</a>#', re.I)
    _link_re = re.compile(r'<a.*?rel="nofollow" target="_blank">(.*)</a>', re.I)

    def __init__(self, *, id=None, data=None, **kwargs):
        """
        :param str text: 消息内容
        :param str id: status id
        :param bool fill: 是否立即发起请求，填充对象属性。默认为False，当省略该值，并且只提供了id时，fill为True
        :param dict|File photo: 图片URL字典 imageurl=图片地址 thumburl=缩略图地址 largeurl=图片原图地址
        :param Status|dict repost_status: 被转发消息的详细信息
        :param User|dict user: 消息的主人
        """
        super(Status, self).__init__(id=id, data=data, **kwargs)

    def populate(self, d):
        self.id = d.get('id')
        self.text = d.get('text')
        self.photo = d.get('photo')
        self.user = d.get('user')
        self.created_at = d.get('created_at')
        self.in_reply_to_user_id = d.get('in_reply_to_user_id')
        self.in_reply_to_status_id = d.get('in_reply_to_status_id')
        self.in_reply_to_screen_name = d.get('in_reply_to_screen_name')
        self.repost_status_id = d.get('repost_status_id')
        self.repost_status = d.get('repost_status')
        self.repost_user_id = d.get('repost_user_id')
        self.repost_screen_name = d.get('repost_screen_name')
        self.favorited = d.get('favorited')
        self.rawid = d.get('rawid')
        self.source = d.get('source')
        self.truncated = d.get('truncated')
        self.is_self = d.get('is_self')
        self.location = d.get('location')
        if self.user and isinstance(self.user, dict):
            self.user = User.get(data=self.user)
        if self.repost_status and isinstance(self.repost_status, dict):
            self.repost_status = Status.get(data=self.repost_status)
        if self.created_at:
            self.created_at = arrow.get(self.created_at, self._time_format)
        # process photo dict
        if isinstance(self.photo, dict):
            p = self.photo
            originurl = re.sub(r'@.+\..+$', '', p['largeurl'])
            type = re.match(r'^.+\.(.+)$', originurl).group(1)
            p['originurl'] = originurl
            p['type'] = type
            self.photo = Photo(**p)

        return self

    @classmethod
    def process_text(cls, text):
        text = cls._at_re.sub(r'@\1', text)
        text = cls._topic_re.sub(r'#\1#', text)
        text = cls._link_re.sub(r'\1', text)
        return text

    def send(self):
        """
        Send self
        :return 发送状态
        :rtype (bool, Status|str)
        """
        photo = get_photo(self.photo)
        text = self.process_text(self.text)
        if photo:
            _, rs = _post('photos/upload', status=text, files=dict(photo=photo),
                          in_reply_to_user_id=self.in_reply_to_user_id,
                          in_reply_to_status_id=self.in_reply_to_status_id,
                          repost_status_id=self.repost_status_id)
            # 上传文件也可以写成这样：
            # rs=_file('photos/upload',
            # status=(None,status,'text/plain'),
            # photo=('photo',p,''application/octet-stream'')
            photo.close()
        else:
            _, rs = _post('statuses/update', status=text,
                          in_reply_to_user_id=self.in_reply_to_user_id,
                          in_reply_to_status_id=self.in_reply_to_status_id,
                          repost_status_id=self.repost_status_id)
        if _:
            # 用返回的结果补全自己
            rs = self.populate(rs)
        else:
            _logger.error('Send faile, saved to draft box, you can send it later')
            _cfg.draft_box.append(self)
        return _, rs

    def delete(self):
        """删除此消息（当前用户发出的消息）"""
        _, rs = _post('statuses/destroy', id=self.id)
        if _:
            rs = self.populate(rs)
        return _, rs

    @property
    def context(self):
        """按照时间先后顺序显示消息上下文"""
        _, rv = _get('statuses/context_timeline', id=self.id)
        if _:
            rv = [Status.get(data=s) for s in rv]
        return _, rv

    def reply(self, response, photo=None):
        """回复这条消息"""
        response = '@{poster} {resp}'.format(resp=response, poster=self.user.screen_name)
        status = Status(text=response, photo=photo, in_reply_to_user_id=self.user.id,
                        in_reply_to_status_id=self.id)
        rv = status.send()
        return rv

    def repost(self, repost, photo=None):
        """转发这条消息"""
        repost = '{repost}{repost_style_left}@{name} {origin}{repost_style_right}'.format(
                repost=repost,
                repost_style_left=_cfg.repost_style_left,
                name=self.user.screen_name,
                origin=self.text,
                repost_style_right=_cfg.repost_style_right)
        status = Status(text=repost, photo=photo, repost_status_id=self.id)
        rv = status.send()
        return rv

    def favorite(self):
        """收藏此消息"""
        # fuck, 为啥就这一个API不一样…
        _, rs = _post('favorites/create/' + self.id)
        if _:
            rs = self.populate(rs)
        return _, rs

    def unfavorite(self):
        """取消收藏此消息"""
        _, rs = _post('favorites/destroy/' + self.id)
        if _:
            rs = self.populate(rs)
        return _, rs

    def __str__(self):
        return '<Status ("{}" @{})>'.format(self.text, self.user.id)

    __repr__ = __str__


class Config:
    """
    配置类
    """
    consumer_key = None  # required
    consumer_secret = None  # required
    auth_type = 'xauth'  # or 'oauth', or offer ``access_token``
    save_token = True  # default True
    save_path = os.path.abspath('van.cfg')
    # or you can offer the ``access_token`` directly
    access_token = None
    xauth_username = None
    xauth_password = None
    auto_auth = True
    redirect_url = 'http://localhost:8000/callback'
    repost_style_left = ' '
    repost_style_right = ''
    # API related urls
    request_token_url = 'http://fanfou.com/oauth/request_token'
    authorize_url = 'http://fanfou.com/oauth/authorize'
    access_token_url = 'http://fanfou.com/oauth/access_token'
    draft_box = []  # type:[Status]
    timeout = 5
    fail_sleep_time = 3

    def __init__(self):
        atexit.register(self.dump)
        if self.access_token is not None \
                and not isinstance(self.access_token, dict):
            raise ValueError('access token should be a dict')
        self.load()

    def load(self):
        if self.save_token and os.path.isfile(self.save_path):
            with open(self.save_path, encoding='utf8') as f:
                c = json.load(f)
                c['draft_box'] = self.load_draft_box(c['draft_box'])
                self.__dict__.update(c)

    def dump(self):
        if self.save_token:
            attrs = ['consumer_key',
                     'consumer_secret',
                     'auth_type',
                     'save_token',
                     'save_path',
                     'access_token',
                     'xauth_username',
                     'xauth_password',
                     'auto_auth',
                     'redirect_url',
                     'request_token_url',
                     'authorize_url',
                     'access_token_url',
                     'draft_box',
                     'timeout',
                     'fail_sleep_time']
            with open(self.save_path, 'w', encoding='utf8') as f:
                config = {x: getattr(self, x) for x in attrs}
                config['draft_box'] = self.save_draft_box()
                json.dump(config, f)

    def save_draft_box(self):
        return base64.encodebytes(pickle.dumps(self.draft_box)).decode('latin-1')

    def load_draft_box(self, b):
        return pickle.loads(base64.decodebytes(b.encode('latin-1')))

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.dump()


class Fan(User):
    """
    模拟
    """

    def __init__(self, *, cfg, **kwargs):
        """
        :param Config cfg: Config 对象
        """
        # Fan as a user with access_token, could not offer id

        self.mentions = Timeline(self, 'statuses/mentions')
        """返回提到当前用户的20条消息"""
        self.replies = Timeline(self, 'statuses/replies')
        """返回当前用户收到的回复"""
        self.public_timeline = Timeline(self, 'statuses/public_timeline')
        """返回公共时间线"""

        self.setup(cfg)

        super(Fan, self).__init__(master=True)

    @classmethod
    def setup(cls, cfg):
        """

        :param Config cfg:
        """
        global _session, _cfg

        _cfg = cfg
        _session = OAuth1Session(cfg.consumer_key, cfg.consumer_secret)
        if not cfg.access_token:
            if cfg.auth_type == 'oauth':
                cfg.access_token = cls._oauth(cfg)
            else:
                cfg.access_token = cls._xauth(cfg)
        _session._populate_attributes(cfg.access_token)

    @staticmethod
    def _oauth(cfg):
        from http.server import BaseHTTPRequestHandler, HTTPServer

        callback_request = None

        class OAuthTokenHandler(BaseHTTPRequestHandler):
            def do_GET(self):
                nonlocal callback_request
                if 'callback?oauth_token=' in self.path:
                    callback_request = self.path
                    self.send_response(200)
                    self.send_header('Content-type',
                                     'text/html; charset=utf-8')
                    self.end_headers()
                    self.wfile.write("<h1>授权成功</h1>".encode('utf8'))
                    self.wfile.write('<p>快去刷饭吧~</p>'.encode('utf8'))
                else:
                    self.send_response(403)
                    self.send_header('Content-type',
                                     'text/html; charset=utf-8')
                    self.wfile.write('<h1>参数错误！</h1>'.encode('utf8'))
                    raise AuthFailed

        def start_oauth_server(redirect_uri):
            nonlocal callback_request
            netloc = urlparse(redirect_uri).netloc
            hostname, port = netloc.split(':')
            try:
                port = int(port)
            except TypeError:
                port = 80
            except ValueError:
                print('[x] 不合法的回调地址: %s' % redirect_uri)
                sys.exit(1)
            httpd = HTTPServer((hostname, port), OAuthTokenHandler)
            sa = httpd.socket.getsockname()
            serve_message = "[-] 已在本地启动HTTP服务器，等待饭否君的到来"" \
            "" (http://{host}:{port}/) ..."
            print(serve_message.format(host=sa[0], port=sa[1]))
            try:
                httpd.handle_request()
            except KeyboardInterrupt:
                print("[-] 服务器退出中...", 'cyan')
                raise AuthFailed
            httpd.server_close()

            if not callback_request:
                print('[x] 服务器没有收到请求', 'red')
                callback = get_input('[-] 请手动粘贴跳转后的链接>')
                callback_request = callback

        try:
            _session.fetch_request_token(cfg.request_token_url)
            authorization_url = _session.authorization_url(
                    cfg.authorize_url,
                    callback_uri=cfg.redirect_url)

            print('[-] 初次使用，此工具需要你的授权才能工作/_\\', 'cyan')
            if get_input('[-] 是否自动在浏览器中打开授权链接(y/n)>') == 'y':
                import webbrowser
                webbrowser.open_new_tab(authorization_url)
            else:
                print('[-] 请在浏览器中打开此链接: ', 'cyan')
                print(authorization_url)

            if cfg.auto_auth:
                start_oauth_server(cfg.redirect_url)
            else:
                callback_request = get_input('[-] 请手动粘贴跳转后的链接>')

            if callback_request:
                try:
                    _session.parse_authorization_response(
                            cfg.redirect_url + callback_request)
                    # requests-oauthlib换取access token时verifier是必须的，
                    # 而饭否在上一步是不返回verifier的，所以必须手动设置
                    access_token = _session.fetch_access_token(
                            cfg.access_token_url, verifier='123')
                except ValueError:
                    raise AuthFailed
                return access_token
            else:
                raise AuthFailed
        except TokenRequestDenied:
            raise AuthFailed('授权失败，请检查本地时间与网络时间是否同步')

    @staticmethod
    def _xauth(cfg):
        from oauthlib.oauth1 import Client as OAuth1Client
        from oauthlib.oauth1.rfc5849 import utils
        import getpass
        # patch utils.filter_params
        utils.filter_oauth_params = lambda t: t

        username = cfg.xauth_username or get_input('[-]请输入用户名或邮箱>')
        password = cfg.xauth_password or getpass.getpass('[-]请输入密码>')
        # 这些实际上并不是url params，但是他们与其他url params一样参与签名，
        # 最终成为Authorization header的值
        args = [
            ('x_auth_username', username),
            ('x_auth_password', password),
            ('x_auth_mode', 'client_auth')
        ]

        class OAuth1ClientPatch(OAuth1Client):
            """Patch oauthlib.oauth1.Client for xauth"""

            def get_oauth_params(self, request):
                params = super(OAuth1ClientPatch, self).get_oauth_params(
                        request)
                params.extend(args)
                return params

        sess = OAuth1Session(cfg.consumer_key, cfg.consumer_secret,
                             client_class=OAuth1ClientPatch)
        access_token = sess.fetch_access_token(cfg.access_token_url,
                                               verifier='123')
        return access_token

    def update_status(self, text, photo=None, in_reply_to_user_id=None,
                      in_reply_to_status_id=None, repost_status_id=None):
        """
        发表新状态，:meth:`Status.send()` 的快捷方式。

        :param str text: 文字
        :param str photo: 照片路径或者URL
        :param str in_reply_to_user_id: 要回复的用户ID
        :param str in_reply_to_status_id: 要回复的消息ID
        :param str repost_status_id: 要转发的消息ID
        """
        status = Status(text=text, photo=photo, in_reply_to_user_id=in_reply_to_user_id,
                        in_reply_to_status_id=in_reply_to_status_id,
                        repost_status_id=repost_status_id)
        rs = status.send()

        return rs

    @property
    def draft_box(self):
        """
        显示发送失败的消息列表

        :rtype: [Status]
        """
        return _cfg.draft_box

    # 以下是不需要 id 参数，即只能获取当前用户信息的API

    def follow(self, user):
        """
        关注用户

        :param User|str user: 被关注的用户, User对象，或id，或 loginname
        """
        if isinstance(user, User):
            user = user.id
        rs = _post('friendships/create', id=user)
        return rs

    def unfollow(self, user):
        """
        取消关注用户

        :param User|str user: 被关注的用户, User对象，或id，或 loginname
        """
        if isinstance(user, User):
            user = user.id
        rs = _post('friendships/destroy', id=user)
        return rs

    @property
    def follow_requests(self, count=60):
        """
        返回请求关注当前用户的列表

        :rtype: (bool, [User])
        """
        _, rv = _get('friendships/requests', count=count)
        if _:
            rv = [User.get(data=b) for b in rv]
        return _, rv

    def accept_follower(self, user):
        """
        接受关注请求

        :param User|str user: User对象，或id，或 loginname
        :rtype: (bool, User)
        """
        if isinstance(user, User):
            user = user.id
        rv = _get('friendships/accept', id=user)
        return rv

    def deny_follower(self, user):
        """
        拒绝关注请求

        :param User|str user: User对象，或id，或 loginname
        :rtype: (bool, User)
        """
        if isinstance(user, User):
            user = user.id
        rv = _post('friendships/deny', id=user)
        return rv

    def block(self, user):
        """
        屏蔽用户

        :param str|User user: 被屏蔽的用户User对象或者id，loginname
        :rtype: (bool, User)
        """
        if isinstance(user, User):
            user = user.id
        rs = _post('blocks/create', id=user)
        return rs

    def unblock(self, user):
        """
        解除屏蔽

        :param str|User user: 被屏蔽的用户User对象或者id，loginname
        :rtype: (bool, str)
        """
        if isinstance(user, User):
            user = user.id
        rs = _post('blocks/destroy', id=user)
        return rs

    def is_blocked(self, user):
        """
        检查是否屏蔽用户

        :param str|User user: 用户User对象或者id，loginname
        :rtype: (bool, str)
        """
        if isinstance(user, User):
            user = user.id
        return _get('blocks/exists', id=user)

    @property
    def blocked_users(self):
        """
        返回黑名单上用户列表

        :rtype: (bool, [User])
        """
        _, rv = _get('blocks/blocking')
        if _:
            rv = [User.get(data=b) for b in rv]
        return _, rv

    @property
    def blocked_users_id(self):
        """
        获取用户黑名单id列表

        :rtype: (bool, [str])
        """
        return _get('blocks/ids')


class Event:
    """
    MESSAGE_CREATE： 当前用户发布一条状态。source为当前用户，如果消息中@其他人，则target为被提及用户，object为发布的状态
    MESSAGE_DELETE： 当前用户删除一条状态

    FRIENDS_CREATE：当前用户关注其他用户。source为当前用户，target为被关注的对象
    FRIENDS_DELETE： 当前用户取消关注其他用户
    FRIENDS_REQUEST： 当前用户对其他用户发起关注请求

    FAV_CREATE：当前用户收藏一条状态。 source 为发起收藏操作的用户，target为状态被收藏的用户，object为被收藏的状态
    FAV_DELETE：当前用户取消收藏一条状态

    USER_UPDATE_PROFILE：当前用户更新个人资料
    """
    HEART_BEAT = 0b000001_000
    ERROR = 0b000010_000

    MESSAGE_CREATE = 0b000100_001
    MESSAGE_DELETE = 0b000100_010
    MESSAGE = MESSAGE_CREATE | MESSAGE_DELETE

    FRIENDS_CREATE = 0b001000_001
    FRIENDS_DELETE = 0b001000_010
    FRIENDS_REQUEST = 0b01000_100
    FRIENDS = FRIENDS_CREATE | FRIENDS_DELETE | FRIENDS_REQUEST

    FAV_CREATE = 0b010000_001
    FAV_DELETE = 0b010000_010
    FAV = FAV_CREATE | FAV_DELETE

    USER_UPDATE_PROFILE = 0b100000_001
    USER = USER_UPDATE_PROFILE

    ALL = MESSAGE | FRIENDS | FAV | USER | HEART_BEAT | ERROR

    def __init__(self, type, data=None):
        data = data if isinstance(data, dict) else dict(object=data)
        self.type = type
        source = data.get('source')
        target = data.get('target')
        object = data.get('object')
        event = data.get('event')
        created_at = data.get('created_at')

        self.source = User.get(data=source) if isinstance(source, dict) else source
        self.target = User.get(data=target) if isinstance(target, dict) else target
        self.object = Status.get(data=object) if isinstance(object, dict) else object
        self.event = event
        self.created_at = arrow.get(created_at, 'ddd, DD MMM YYYY HH:mm:ss') if created_at else created_at

    def __str__(self):
        return '<Event {0.type} {0.source} {0.target} {0.object} {0.event} {0.created_at}>'.format(self)


Listener = namedtuple('Listener', ['on', 'func', 'ttl'])
"""监听器对象"""

_EVENT_HEART_BEAT = Event(Event.HEART_BEAT, r'\r\n')


class Stream:
    """

    """

    def __init__(self):
        self._conn = None
        self._listeners = []  # type:[Listener]
        self._lock = threading.Lock()
        self._running = True
        self.init()

    def init(self):
        """
        开始建立连接
        """
        self._conn = _session.post('http://stream.fanfou.com/1/user.json', stream=True)

    def stop(self):
        """
        停止监听事件
        """
        self._running = False

    def run(self):
        """
        开始监听事件
        """

        def go():
            for chunk in self._conn.iter_content(chunk_size=None, decode_unicode=True):
                evt = self._parse_chunk(chunk)
                for func in self._pick_listeners(evt):
                    try:
                        func(evt)
                    except Exception as e:
                        _logger.error(e)
                if not self._running:
                    break
            self._conn.close()

        thread = threading.Thread(target=go)
        thread.start()
        return thread

    def _pick_listeners(self, event):
        with self._lock:
            for lsn in self._listeners:
                if lsn.on & event.type and (lsn.ttl is None or lsn.ttl > 0):
                    yield lsn.func

                    if lsn.ttl is not None:
                        lsn.ttl -= 1

    @staticmethod
    def _parse_chunk(chunk: bytes):
        if isinstance(chunk, bytes):
            chunk = chunk.decode('utf8')
        if chunk == '\r\n':
            return _EVENT_HEART_BEAT

        try:
            data = json.loads(chunk.strip())
        except json.JSONDecodeError as e:
            _logger.error(e)
            return Event(Event.ERROR, e)

        event_name = data['event'].upper().replace('.', '_')
        type = getattr(Event, event_name, Event.ERROR)

        event = Event(type, data)
        return event

    def install_listener(self, listener):
        """
        添加新的监听器
        :param Listener listener: Listener 对象
        """
        with self._lock:
            self._listeners.append(listener)

    def on(self, event, ttl=None):
        """
        作为装饰器使用，添加新的监听器
        :param event: 监听的事件, 多个事件请用 | 连接。如 Event.MESSAGE | Event.FREIENDS
        :param int ttl: 此监听器执行的次数，None表示不限次数
        """

        def decorator(func):
            listener = Listener(event, func, ttl)
            self.install_listener(listener)

        return decorator
