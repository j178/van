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


class AuthFailed(Exception):
    def __init__(self, msg):
        self.msg = msg


def get_input(prompt=None):
    return input(prompt).strip()


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
            if failure >= 2:
                # todo 如何处理
                raise
        time.sleep(1)


_get = functools.partial(_request, 'GET')
_post = functools.partial(_request, 'POST')


class Base(object):
    endpiont = None

    def __init__(self, id=None, buffer=None):
        self._id = id
        self._buffer = None
        if not any((id, buffer)):
            raise ValueError('Requires id or buffer')
        if buffer is not None:
            if isinstance(buffer, str):
                try:
                    self._buffer = json.loads(buffer)
                except json.JSONDecodeError:
                    self._buffer = None
            elif isinstance(buffer, dict):
                self._buffer = buffer

    @property
    def id(self):
        if self._id is not None:
            return self._id
        # 构造方法保证了此时buffer不为None
        return self._buffer.get('id')

    def _load(self):
        return _get(self.endpiont, id=self._id)

    def __getattr__(self, item):
        if self._buffer is None:
            _, rs = self._load()
            if _:
                self._buffer = rs
        return self._buffer.get(item)


class User(Base):
    # 需要 id 参数，可查看其他用户信息的 API 在此类中（也可以省略 id 表示当前用户）
    endpiont = 'users/show'

    def __init__(self, id=None, buffer=None):
        super(User, self).__init__(id, buffer)

    def statuses(self, since_id=None, max_id=None, count=None):
        """返回此用户已发送的消息"""
        # since_id, max_id, count
        _, statuses = _get('statuses/user_timeline', id=self.id,
                           since_id=since_id, max_id=max_id, count=count)
        if _:
            return Timeline(self, statuses)

    def timeline(self, since_id=None, max_id=None, count=None):
        """
        返回此**看到的**时间线
        此用户为当前用户的关注对象或未设置隐私"""
        # since_id, max_id, count
        _, timeline = _get('statuses/home_timeline', id=self.id)
        if _:
            return Timeline(self, timeline)

    def followers(self, count=100):
        """
        返回此用户的关注者(前100个)
        此用户为当前用户的关注对象或未设置隐私"""
        # count=100
        _, followers = _get('statuses/followers', id=self.id, count=count)
        if _:
            return [User(buffer=f) for f in followers]

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
            return [User(buffer=f) for f in friends]

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

    def is_friend(self, other):
        """
        此用户是否关注 other
        :param str|User other: 其他用户
        """
        if isinstance(other, User):
            other = other.id
        _, rs = _get('friendships/show', source_id=self.id, target_id=other)
        if _:
            return rs['relationship']['source']['following']

            # def __str__(self):
            #     return self.name


class Status(Base):
    endpiont = 'statuses/show'
    _user_buffer = {}  # 避免重复创建 user 对象

    _at_re = re.compile(r'@<a.*?>(.*?)</a>', re.I)
    _topic_re = re.compile(r'#<a.*?>(.*?)</a>#', re.I)
    _link_re = re.compile(r'<a.*?rel="nofollow" target="_blank">(.*)</a>', re.I)

    def __init__(self, owner=None, id=None, buffer=None):
        self._owner = None
        if not owner and buffer:
            owner = User(buffer=buffer['user'])
        self._owner = self._user_buffer.setdefault(owner.id, owner)

        super(Status, self).__init__(id, buffer)

    def _load(self):
        _, rs = super()._load()
        # load status 之后更新自己的 user
        if _:
            owner = User(buffer=rs['user'])
            self._owner = self._user_buffer.setdefault(owner.id, owner)
        return _, rs

    @property
    def owner(self):
        if self._owner:
            return self._owner
        elif not self._buffer:
            _, rs = self._load()
            if _:
                self._buffer = rs
        user = User(buffer=self._buffer['user'])
        self._owner = self._user_buffer.setdefault(user.id, user)
        return self._owner

    @property
    def text(self):
        if not self._buffer:
            _, rs = self._load()
            if _:
                self._buffer = rs
        text = self._buffer['text']
        text = self._at_re.sub(r'@\1', text)
        text = self._topic_re.sub(r'#\1#', text)
        text = self._link_re.sub(r'\1', text)
        return text

    def delete(self):
        """删除此消息（当前用户发出的消息）"""
        _, rs = _post('statuses/destroy', id=self.id)
        if _:
            return rs

    def context(self):
        """按照时间先后顺序显示消息上下文"""
        _, rs = _get('statuses/context_timeline', id=self.id)
        if _:
            return Timeline(self, rs)

    def reply(self, response, photo=None):
        """回复这条消息"""
        response = '@{poster} {resp}'.format(resp=response,
                                             poster=self.owner.screen_name)
        _, rv = Fan._update_status(response, photo,
                                   in_reply_to_user_id=self.owner.id,
                                   in_reply_to_status_id=self.id)
        if _:
            return rv

    def repost(self, repost, photo=None):
        """转发这条消息"""
        repost = '{repost}{repost_style_left}@{name} {origin}{repost_style_right}'.format(
                repost=repost,
                repost_style_left=_cfg.repost_style_left,
                name=self.owner.screen_name,
                origin=self.text,
                repost_style_right=_cfg.repost_style_right)
        _, rv = Fan._update_status(repost, photo, repost_status_id=self.id)
        if _:
            return rv

    def favorite(self):
        """收藏此消息"""
        _, rs = _post('favorites/create', id=self.id)
        if _:
            return rs

    def unfavorite(self):
        "取消收藏此消息"
        _, rs = _post('favorites/destroy', id=self.id)
        if _:
            return rs

            # def __str__(self):
            #     return self.text


class Timeline(list):
    """
    需求:
    1. 完全隐藏网络请求，将此对象看作无尽的数组，随便取数据
    2. 整合搜索 API
    3. 提供多种获取方式，id、id区间、时间区间、关键字
    4. 提供历史记录，可以往回翻页

    """

    def __init__(self, owner, array):
        super(Timeline, self).__init__()
        self.owner = owner
        self.pos = 0
        self.window_size = 5
        self.extend(Status(owner, buffer=s) for s in array)

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

    def __str__(self):
        pass


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
    def __init__(self, cfg):
        """
        :param Config cfg: Config 对象
        """
        # Fan as a user with access_token, could not offer id
        try:
            super(Fan, self).__init__()
        except ValueError:
            pass

        global _session, _cfg

        _cfg = self._cfg = cfg
        _session = OAuth1Session(cfg.consumer_key, cfg.consumer_secret)
        if not cfg.access_token:
            if cfg.auth_type == 'oauth':
                cfg.access_token = self._oauth()
            else:
                cfg.access_token = self._xauth()
        _session._populate_attributes(cfg.access_token)

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

    @property
    def id(self):
        # 主人的id，没有时可以为None而不是发起网络请求，但是如果已经请求了，就使用已有的
        if self._buffer is not None:
            return self._buffer.get('id')
        return self._id

    @classmethod
    def _update_status(cls, status, photo=None,
                       in_reply_to_user_id=None,
                       in_reply_to_status_id=None,
                       repost_status_id=None):
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
                        if not resp.headers.get('Content-Type',
                                                '').lower().startswith(
                                'image/'):
                            return False
                        data = io.BytesIO(resp.content)
                        return data
                except requests.RequestException as e:
                    return False
            return False

        p = get_photo(photo)
        if p:
            rs = _post('photos/upload', status=status, files=dict(photo=p),
                       in_reply_to_user_id=in_reply_to_user_id,
                       in_reply_to_status_id=in_reply_to_status_id,
                       repost_status_id=repost_status_id)
            # 上传文件也可以写成这样：
            # rs=_file('photos/upload',
            # status=(None,status,'text/plain'),
            # photo=('photo',p,''application/octet-stream'')
            p.close()
        else:
            rs = _post('statuses/update', status=status,
                       in_reply_to_user_id=in_reply_to_user_id,
                       in_reply_to_status_id=in_reply_to_status_id,
                       repost_status_id=repost_status_id)

        return rs

    def update_status(self, status, photo=None):
        """发表新状态"""
        _, rs = self._update_status(status, photo)
        if _:
            return rs

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
        _, rs = _post('friendships/create', id=user)
        if _:
            return rs

    def unfollow(self, user):
        """
        关注用户
        :param User|str user: 被关注的用户, User对象，或id，或 loginname
        """
        if isinstance(user, User):
            user = user.id
        _, rs = _post('friendships/destroy', id=user)
        if _:
            return rs

    def block(self, user):
        """
        屏蔽用户
        :param str|User user: 被屏蔽的用户User对象或者id，loginname
        """
        if isinstance(user, User):
            user = user.id
        _, rs = _post('blocks/create', id=user)
        if _:
            return rs

    def unblock(self, user):
        """
        解除屏蔽
        :param str|User user: 被屏蔽的用户User对象或者id，loginname
        """
        if isinstance(user, User):
            user = user.id
        _, rs = _post('blocks/destroy', id=user)
        if _:
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
            return [User(buffer=b) for b in blocks]

    def blocks_id(self):
        """获取用户黑名单id列表"""
        _, ids = _get('blocks/ids')
        if _:
            return ids
