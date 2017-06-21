#!/usr/bin/env python
# encoding=utf8

from __future__ import print_function, unicode_literals, absolute_import

import atexit
import io
import json
import logging
import os
import re
import sys
import time
from urllib.parse import urlparse

import functools
import requests
from requests_oauthlib.oauth1_session import OAuth1Session, TokenRequestDenied

__version__ = '0.0.2'
__all__ = ['Fan', 'User', 'Status', 'Timeline', 'Config']

_session = None  # type: OAuth1Session
_cfg = None  # type: Config
_logger = logging.getLogger(__name__)
_draft_box = []  # type:[Status]
_sentinel = object()


# 动作的返回为 (bool, reason)
# 为了获取结果的API返回为 result or None

class AuthFailed(Exception):
    def __init__(self, msg):
        self.msg = msg


def get_input(prompt=None):
    return input(prompt).strip()


def get_photo(p):
    if p is None:
        return False
    if os.path.isfile(p):
        f = open(p, 'rb')
        return f
    else:
        try:
            url = p.strip('\'').strip('"')
            if urlparse(url).scheme != '':
                resp = requests.get(url)
                resp.raise_for_status()
                if not resp.headers.get('Content-Type', '').lower().startswith('image/'):
                    return False
                data = io.BytesIO(resp.content)
                return data
        except requests.RequestException as e:
            return False
    return False


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

    for failure in range(3):
        try:
            result = _session.request(method, url, **d, files=files, timeout=3)
            j = result.json()
            if result.status_code == 200:
                return True, j
            _logger.error(j['error'])
            return False, j['error']
        except requests.RequestException as e:
            _logger.error(e)
            if failure >= 2:
                # todo 如何处理
                raise
        time.sleep(1)


_get = functools.partial(_request, 'GET')
_post = functools.partial(_request, 'POST')


class Base:
    endpiont = None

    def __init__(self, from_dict=None, fill=False, id=None):
        self.id = id
        self._filled = False

        # raise ValueError('fill and from_dict are exclusive')
        if from_dict:
            fill = False

        if isinstance(from_dict, dict):
            for attr, value in from_dict.items():
                if attr == 'user':
                    value = User.get(value)
                setattr(self, attr, value)
        elif fill and not self._filled:
            # if not self.id:
            #     raise ValueError('Specialize id to fill the object')
            self.fill()

    def fill(self):
        _, rv = _get(self.endpiont, id=self.id)
        self._filled = True
        if _:
            for attr, value in rv.items():
                if attr == 'user':
                    value = User.get(value)
                setattr(self, attr, value)


class User(Base):
    # 需要 id 参数，可查看其他用户信息的 API 在此类中（也可以省略 id 表示当前用户）
    endpiont = 'users/show'
    _user_buffer = {}  # 每个User只存在一份，这样比较好管理他们的Timeline

    @classmethod
    def get(cls, *args, **kwargs):
        # make sure every user only has one instance
        id = kwargs.get('id')
        if id not in cls._user_buffer:
            user = cls(*args, **kwargs, fill=True)
            cls._user_buffer[user.id] = user
            return user
        return cls._user_buffer[id]

    def __init__(self, from_dict=None, fill=_sentinel, id=None, name=None, screen_name=None, location=None,
                 gender=None, birthday=None, description=None, url=None, protected=None, followers_count=None,
                 friends_count=None, favourites_count=None, statuses_count=None, following=None, notifications=None,
                 created_at=None, utc_offset=None, **misc):
        """
        :param dict from_dict: 从一个字典中获取填充值（用 API 返回的数据构造对象）
        :param bool fill: 是否立即发起请求，填充对象属性。默认为False，当省略该值，并且只提供了id时，fill为True
        :param str id:
        :param str name:
        :param str screen_name:
        :param str location:
        :param str gender:
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
        :param int utc_offset: UTC offset)
        """
        self.name = name
        self.screen_name = screen_name
        self.location = location
        self.gender = gender
        self.birthday = birthday
        self.description = description
        self.url = url
        self.protected = protected
        self.followers_count = followers_count
        self.friends_count = friends_count
        self.favourites_count = favourites_count
        self.statuses_count = statuses_count
        self.following = following
        self.notifications = notifications
        self.created_at = created_at
        self.utc_offset = utc_offset
        self.timeline = Timeline(self)

        if fill == _sentinel:
            # only offer id, so fill it
            if id and not any([from_dict, name, screen_name]):
                fill = True
            else:
                fill = False
        super(User, self).__init__(from_dict, fill, id)

    def statuses(self, since_id=None, max_id=None, count=None):
        """返回此用户已发送的消息"""
        # since_id, max_id, count
        _, statuses = _get('statuses/user_timeline', id=self.id,
                           since_id=since_id, max_id=max_id, count=count)
        if _:
            return Timeline(self, statuses)

            # def home_timeline(self, since_id=None, max_id=None, count=None):
            #     """
            #     返回此**看到的**时间线
            #     此用户为当前用户的关注对象或未设置隐私"""
            #     since_id, max_id, count
            # _, timeline = _get('statuses/home_timeline', id=self.id,
            #                    since_id=since_id, max_id=max_id, count=count)
            # if _:
            #     return Timeline(self, timeline)

    def followers(self, count=100):
        """
        返回此用户的关注者(前100个)
        此用户为当前用户的关注对象或未设置隐私"""
        # count=100
        _, followers = _get('statuses/followers', id=self.id, count=count)
        if _:
            return [User.get(f) for f in followers]

    def followers_id(self, count=None):
        """返回此用户关注者的id列表"""
        # count=1..60
        _, ids = _get('followers/ids', id=self.id, count=count)
        if _:
            return ids

    def friends(self, count=100):
        """
        返回此用户的关注对象(前100个)
        此用户为当前用户的关注对象或未设置隐私"""
        # count=100
        _, friends = _get('statuses/friends', id=self.id, count=count)
        if _:
            return [User.get(f) for f in friends]

    def friends_id(self, count=None):
        """返回此用户关注对象的id列表"""
        # count=1..60
        _, ids = _get('friends/ids', id=self.id, count=count)
        if _:
            return ids

    def photos(self, since_id=None, max_id=None, count=None):
        """浏览指定用户的图片"""
        # since_id, max_id, count
        _, photos = _get('photos/user_timeline', id=self.id,
                         since_id=since_id, max_id=max_id, count=count)
        if _:
            return Timeline(self, photos)

    def favorites(self, count=None):
        """浏览此用户收藏的消息"""
        _, favorites = _get('favorites/id', id=self.id, count=count)
        if _:
            return Timeline(self, favorites)

    def relationship(self, other):
        """
        返回此用户与 other 的关系： 是否屏蔽，是否关注，是否被关注
        :param str|User other: 其他用户
        :return (a_blocked_b, a_following_b, a_followed_b)
        """
        if isinstance(other, User):
            other = other.id
        _, rs = _get('friendships/show', source_id=self.id, target_id=other)
        if _:
            source = rs['relationship']['source']
            return (source['blocking'], source['following'], source['followed_by'])

    def __str__(self):
        return '<User ({}@{})>'.format(self.name, self.id)

    __repr__ = __str__


class Status(Base):
    endpiont = 'statuses/show'

    _at_re = re.compile(r'@<a.*?>(.*?)</a>', re.I)
    _topic_re = re.compile(r'#<a.*?>(.*?)</a>#', re.I)
    _link_re = re.compile(r'<a.*?rel="nofollow" target="_blank">(.*)</a>', re.I)

    def __init__(self, from_dict=None, fill=_sentinel, text='', id=None, photo=None, user=None, created_at=None,
                 in_reply_to_user_id=None, in_reply_to_status_id=None,
                 in_reply_to_screen_name=None, repost_status_id=None, repost_status=None,
                 repost_user_id=None, repost_screen_name=None, favorited=False,
                 rawid=None, source='', truncated=False, is_self=False, location=None, **misc):
        """
        :param str text: 消息内容
        :param str id: status id
        :param bool fill: 是否立即发起请求，填充对象属性。默认为False，当省略该值，并且只提供了id时，fill为True
        :param dict|File photo: 图片URL字典 imageurl=图片地址 thumburl=缩略图地址 largeurl=图片原图地址
        :param Status|dict repost_status: 被转发消息的详细信息
        :param User|dict user: 消息的主人
        """
        self.text = text
        self.photo = photo
        self.user = user if (not user or isinstance(user, User)) else User.get(user)
        self.created_at = created_at
        self.in_reply_to_user_id = in_reply_to_user_id
        self.in_reply_to_status_id = in_reply_to_status_id
        self.in_reply_to_screen_name = in_reply_to_screen_name
        self.repost_status_id = repost_status_id
        self.repost_status = repost_status if (not repost_status or isinstance(repost_status, Status)) \
            else Status(repost_status)
        self.repost_user_id = repost_user_id
        self.repost_screen_name = repost_screen_name
        self.favorited = favorited
        self.rawid = rawid
        self.source = source
        self.truncated = truncated
        self.is_self = is_self
        self.location = location

        if fill == _sentinel:
            # only offer id, so fill it
            if id and not any([from_dict, text, photo]):
                fill = True
            else:
                fill = False
        super(Status, self).__init__(from_dict, fill, id)

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
        :rtype (bool, dict|str)
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
            rs = Status(rs)
        return _, rs

    def delete(self):
        """删除此消息（当前用户发出的消息）"""
        rs = _post('statuses/destroy', id=self.id)
        return rs

    def context(self):
        """按照时间先后顺序显示消息上下文"""
        _, rs = _get('statuses/context_timeline', id=self.id)
        if _:
            return Timeline(self, rs)

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
        rs = _post('favorites/create', id=self.id)
        return rs

    def unfavorite(self):
        "取消收藏此消息"
        rs = _post('favorites/destroy', id=self.id)
        return rs

    def __str__(self):
        return '<Status ("{}" @{})>'.format(self.text, self.user.id)

    __repr__ = __str__


class Timeline(list):
    """
    需求:
    1. 完全隐藏网络请求，将此对象看作无尽的数组，随便取数据
    2. 整合搜索 API
    3. 提供多种获取方式，id、id区间、时间区间、关键字
    4. 提供历史记录，可以往回翻页

    """

    def __init__(self, user, array=None):
        super(Timeline, self).__init__()
        self.user = user
        self.pos = 0
        self.window_size = 5
        if array:
            self.extend(Status(s) for s in array)

    def _fetch(self):
        # res = [Status()]
        # self.extend(res)
        pass

    @property
    def window(self):
        return self[self.pos:self.pos + self.window_size]

        # def __getitem__(self, item):
        #     """
        #     支持使用 range 获取区间中的 timeline，如 timeline[date(1,2,3):date(2,3)]
        #     :param item:
        #     :return:
        #     :rtype list[Status]
        #     """
        #     return
        #
        # def __iter__(self):
        #     """
        #     支持遍历
        #     :return:
        #     """
        #     return self
        #
        # def __next__(self):
        #     yield 1


class Config:
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
                     'access_token_url']
            with open(self.save_path, 'w', encoding='utf8') as f:
                config = {x: getattr(self, x) for x in attrs}
                json.dump(config, f)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.dump()


class Fan(User):
    def __init__(self, from_dict=None, cfg=None, fill=_sentinel, id=None, name=None, screen_name=None, location=None,
                 gender=None, birthday=None, description=None, url=None, protected=None, followers_count=None,
                 friends_count=None, favourites_count=None, statuses_count=None, following=None, notifications=None,
                 created_at=None, utc_offset=None, **misc):
        """
        :param Config cfg: Config 对象
        """
        # Fan as a user with access_token, could not offer id

        global _session, _cfg

        self._cfg = _cfg = cfg
        _session = OAuth1Session(cfg.consumer_key, cfg.consumer_secret)
        if not cfg.access_token:
            if cfg.auth_type == 'oauth':
                cfg.access_token = self._oauth()
            else:
                cfg.access_token = self._xauth()
        _session._populate_attributes(cfg.access_token)

        if fill == _sentinel:
            # only offer id, so fill it
            if id and not any([from_dict, name, screen_name]):
                fill = True
            else:
                fill = False
        super(Fan, self).__init__(from_dict, fill, id)

    def _oauth(self):
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
            _session.fetch_request_token(self._cfg.request_token_url)
            authorization_url = _session.authorization_url(
                    self._cfg.authorize_url,
                    callback_uri=self._cfg.redirect_url)

            print('[-] 初次使用，此工具需要你的授权才能工作/_\\', 'cyan')
            if get_input('[-] 是否自动在浏览器中打开授权链接(y/n)>') == 'y':
                import webbrowser
                webbrowser.open_new_tab(authorization_url)
            else:
                print('[-] 请在浏览器中打开此链接: ', 'cyan')
                print(authorization_url)

            if self._cfg.auto_auth:
                start_oauth_server(self._cfg.redirect_url)
            else:
                callback_request = get_input('[-] 请手动粘贴跳转后的链接>')

            if callback_request:
                try:
                    _session.parse_authorization_response(
                            self._cfg.redirect_url + callback_request)
                    # requests-oauthlib换取access token时verifier是必须的，
                    # 而饭否在上一步是不返回verifier的，所以必须手动设置
                    access_token = _session.fetch_access_token(
                            self._cfg.access_token_url, verifier='123')
                except ValueError:
                    raise AuthFailed
                return access_token
            else:
                raise AuthFailed
        except TokenRequestDenied:
            raise AuthFailed('授权失败，请检查本地时间与网络时间是否同步')

    def _xauth(self):
        from oauthlib.oauth1 import Client as OAuth1Client
        from oauthlib.oauth1.rfc5849 import utils
        import getpass
        # patch utils.filter_params
        utils.filter_oauth_params = lambda t: t

        username = self._cfg.xauth_username or get_input('[-]请输入用户名或邮箱>')
        password = self._cfg.xauth_password or getpass.getpass('[-]请输入密码>')
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

        sess = OAuth1Session(self._cfg.consumer_key, self._cfg.consumer_secret,
                             client_class=OAuth1ClientPatch)
        access_token = sess.fetch_access_token(self._cfg.access_token_url,
                                               verifier='123')
        return access_token

    def update_status(self, text, photo=None, in_reply_to_user_id=None,
                      in_reply_to_status_id=None, repost_status_id=None):
        """发表新状态"""
        status = Status(text=text, photo=photo, in_reply_to_user_id=in_reply_to_user_id,
                        in_reply_to_status_id=in_reply_to_status_id,
                        repost_status_id=repost_status_id)
        rs = status.send()
        if not rs[0]:
            _logger.error('Send faile, saved to draft box, you can send it later')
            _draft_box.append(status)

        return rs

    def draft_box(self):
        """
        显示发送失败的消息列表
        :rtype [Status]
        """
        return _draft_box

    # 以下是不需要 id 参数，即只能获取当前用户信息的API

    def replies(self, since_id=None, max_id=None, count=None):
        """返回当前用户收到的回复"""
        _, replies = _get('statuses/replies',
                          since_id=since_id, max_id=max_id, count=count)
        if _:
            return Timeline(self, replies)

    def mentions(self, since_id=None, max_id=None, count=None):
        """
        返回回复/提到当前用户的20条消息
        """
        _, mentions = _get('statuses/mentions',
                           since_id=since_id, max_id=max_id, count=count)
        if _:
            return Timeline(self, mentions)

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
        关注用户
        :param User|str user: 被关注的用户, User对象，或id，或 loginname
        """
        if isinstance(user, User):
            user = user.id
        rs = _post('friendships/destroy', id=user)
        return rs

    def follow_requests(self, count=60):
        """
        返回请求关注当前用户的列表
        """
        _, rv = _get('friendships/requests', count=count)
        if _:
            return [User.get(b) for b in rv]

    def accept_follower(self, user):
        """
        接受关注请求
        :param User|str user: User对象，或id，或 loginname
        """
        if isinstance(user, User):
            user = user.id
        rv = _get('friendships/accept', id=user)
        return rv

    def deny_follower(self, user):
        """
        接受关注请求
        :param User|str user: User对象，或id，或 loginname
        """
        if isinstance(user, User):
            user = user.id
        rv = _post('friendships/deny', id=user)
        return rv

    def block(self, user):
        """
        屏蔽用户
        :param str|User user: 被屏蔽的用户User对象或者id，loginname
        """
        if isinstance(user, User):
            user = user.id
        rs = _post('blocks/create', id=user)
        return rs

    def unblock(self, user):
        """
        解除屏蔽
        :param str|User user: 被屏蔽的用户User对象或者id，loginname
        """
        if isinstance(user, User):
            user = user.id
        rs = _post('blocks/destroy', id=user)
        return rs

    def is_blocked(self, user):
        """
        检查是否屏蔽用户
        :param str|User user: 用户User对象或者id，loginname
        """
        if isinstance(user, User):
            user = user.id
        _, rs = _get('blocks/exists', id=user)
        if _:
            return rs

    def blocks(self):
        """返回黑名单上用户资料"""
        _, blocks = _get('blocks/blocking')
        if _:
            return [User.get(b) for b in blocks]

    def blocks_id(self):
        """获取用户黑名单id列表"""
        _, ids = _get('blocks/ids')
        if _:
            return ids

    def public_timeline(self, since_id=None, max_id=None, count=None):
        _, rv = _get('statuses/public_timeline',
                     since_id=since_id, max_id=max_id, count=count)
        if _:
            return Timeline(self, rv)
