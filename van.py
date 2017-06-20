#!/usr/bin/env python
# encoding=utf8

from __future__ import print_function, unicode_literals, absolute_import

import atexit
import io
import json
import logging
import os
import sys
import time
from urllib.parse import urlparse

import requests
from requests_oauthlib.oauth1_session import OAuth1Session, TokenRequestDenied

__version__ = '0.0.1'
__all__ = ['Fan', 'User', 'Status', 'Timeline', 'Config']

_session = None


class AuthFailed(Exception):
    def __init__(self, msg):
        self.msg = msg


class ApiRequestError(Exception):
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

    url = 'http://api.fanfou.com/{}.json'.format(endpoint)
    d = {'params': None, 'data': None, 'files': None}
    d[{'GET': 'params', 'POST': 'data', 'FILE': 'files'}[method]] = data
    method = 'POST' if method == 'FILE' else method

    for failure in range(3):
        try:
            result = _session.request(method, url, **d, timeout=3)
            j = result.json()
            if result.status_code == 200:
                return j
            raise ApiRequestError(j['error'])
        except requests.RequestException as e:
            if failure >= 2:
                # todo 看看如何处理
                raise ApiRequestError(str(e))
        time.sleep(1)


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

    def _get(self, endpoint, **data):
        try:
            rs = _request('GET', endpoint, **data)
            return rs
        except ApiRequestError as e:
            logging.error(e)
            return None

    def _post(self, endpoint, **data):
        try:
            rs = _request('POST', endpoint, **data)
            return rs
        except ApiRequestError as e:
            logging.error(e)
            return None

    def _file(self, endpoint, **data):
        try:
            rs = _request('FILE', endpoint, **data)
            return rs
        except ApiRequestError as e:
            logging.error(e)
            return None

    def _load(self):
        rs = self._get(self.endpiont, id=self._id)
        return rs

    def __getattr__(self, item):
        if self._buffer is None:
            self._buffer = self._load()
        return self._buffer.get(item)


class User(Base):
    # 需要 id 参数，可查看其他用户信息的 API 在此类中（也可以省略 id 表示当前用户）
    endpiont = 'users/show'

    def __init__(self, id=None, buffer=None):
        super(User, self).__init__(id, buffer)

    def statuses(self, since_id=None, max_id=None, count=None):
        """返回此用户已发送的消息"""
        # since_id, max_id, count
        statuses = self._get('statuses/user_timeline', id=self.id, since_id=since_id, max_id=max_id, count=count)
        if statuses is not None:
            return [Status(owner=self, buffer=s) for s in statuses]

    def timeline(self):
        """
        返回此**看到的**时间线
        此用户为当前用户的关注对象或未设置隐私"""
        # since_id, max_id, count
        timeline = self._get('statuses/home_timeline', id=self.id)
        if timeline is not None:
            return Timeline(timeline)

    def followers(self):
        """
        返回此用户的关注者(前100个)
        此用户为当前用户的关注对象或未设置隐私"""
        # count=100
        followers = self._get('statuses/followers', id=self.id)
        if followers is not None:
            return [(User(buffer=f) for f in followers)]

    def followers_id(self):
        """返回此用户关注者的id列表"""
        # count=1..60
        ids = self._get('followers/ids', id=self.id)
        return ids

    def friends(self):
        """
        返回此用户的关注对象(前100个)
        此用户为当前用户的关注对象或未设置隐私"""
        # count=100
        friends = self._get('statuses/friends', id=self.id)
        if friends is not None:
            return [User(buffer=f) for f in friends]

    def friends_id(self):
        """返回此用户关注对象的id列表"""
        # count=1..60
        ids = self._get('friends/ids', id=self.id)
        return ids

    def photos(self):
        """浏览指定用户的图片"""
        # since_id, max_id, count
        photos = self._get('photos/user_timeline', id=self.id)
        if photos is not None:
            return Timeline(photos)

    def favorites(self):
        """浏览此用户收藏的消息"""
        favorites = self._get('favorites/id', id=self.id)
        if favorites is not None:
            return Timeline(favorites)

    def is_friend(self, other):
        """
        此用户是否关注 other
        :param str|User other: 其他用户
        """
        if isinstance(other, User):
            other = other.id
        rs = self._get('friendships/show', source_id=self.id, target_id=other)
        if rs is not None:
            return rs['relationship']['source']['following']

            # def __str__(self):
            #     return self.name


class Status(Base):
    endpiont = 'statuses/show'
    # 避免重复创建 user 对象
    _user_buffer = {}

    def __init__(self, owner=None, id=None, buffer=None):
        if owner:
            self._owner = self._user_buffer.setdefault(owner.id, owner)
        if buffer is not None:
            user = buffer.pop('user', None)
            if user and not self._owner:
                user = User(user)
                self._owner = self._user_buffer.setdefault(user.id, user)

        super(Status, self).__init__(id, buffer)

    @property
    def owner(self):
        if self._owner is not None:
            return self._owner
        if self._buffer is None:
            self._buffer = self._load()
        user = self._buffer.pop('user')
        user = User(user)
        self._owner = self._user_buffer.setdefault(user.id, user)
        return self._owner

    def delete(self):
        """删除此消息（当前用户发出的消息）"""
        rs = self._post('statuses/destroy', id=self.id)
        return rs['xxx'] == ''

    def context(self):
        """按照时间先后顺序显示消息上下文"""
        rs = self._get('statuses/context_timeline', id=self.id)
        return rs['xxx'] == ''

    def favorite(self):
        """收藏此消息"""
        rs = self._post('favorites/create', id=self.id)
        return rs['xxx'] == ''

    def unfavorite(self):
        "取消收藏此消息"
        rs = self._post('favorites/destroy', id=self.id)
        return rs['xxx'] == ''

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

    def __init__(self, array):
        super(Timeline, self).__init__()
        self.pos = 0
        self.window_size = 5
        self.extend(Status(s) for s in array)

    def _fetch(self):
        res = [Status()]
        self.extend(res)

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
    save_path = os.path.join(os.path.expanduser('~'), '.fancache')
    # or you can offer the ``access_token`` directly
    access_token = None
    xauth_username = None
    xauth_password = None
    auto_auth = True
    redirect_url = 'http://localhost:8000/callback'
    # API related urls
    request_token_url = 'http://fanfou.com/oauth/request_token'
    authorize_url = 'http://fanfou.com/oauth/authorize'
    access_token_url = 'http://fanfou.com/oauth/access_token'

    def __init__(self):
        atexit.register(self.dump)
        if self.access_token is not None and not isinstance(self.access_token, dict):
            raise ValueError('access token should be a dict')

    def dump(self):
        if self.save_token:
            print(self)
            # with open(self.save_path, 'w', encoding='utf8') as f:
            # todo
            # json.dump(f, {})

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.dump()


class Fan(User):
    def __init__(self, cfg):
        # Fan as a user with access_token, could not offer id
        try:
            super(Fan, self).__init__()
        except ValueError:
            pass

        global _session

        self._cfg = cfg
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
                    self.send_header('Content-type', 'text/html; charset=utf-8')
                    self.end_headers()
                    self.wfile.write("<h1>授权成功</h1>".encode('utf8'))
                    self.wfile.write('<p>快去刷饭吧~</p>'.encode('utf8'))
                else:
                    self.send_response(403)
                    self.send_header('Content-type', 'text/html; charset=utf-8')
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
            serve_message = "[-] 已在本地启动HTTP服务器，等待饭否君的到来 (http://{host}:{port}/) ..."
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
            authorization_url = _session.authorization_url(self._cfg.authorize_url,
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
                    _session.parse_authorization_response(self._cfg.redirect_url + callback_request)
                    # requests-oauthlib换取access token时verifier是必须的，而饭否在上一步是不返回verifier的，所以必须手动设置
                    access_token = _session.fetch_access_token(self._cfg.access_token_url, verifier='123')
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
        # 这些实际上并不是url params，但是他们与其他url params一样参与签名，最终成为Authorization header的值
        args = [
            ('x_auth_username', username),
            ('x_auth_password', password),
            ('x_auth_mode', 'client_auth')
        ]

        class OAuth1ClientPatch(OAuth1Client):
            """Patch oauthlib.oauth1.Client for xauth"""

            def get_oauth_params(self, request):
                params = super(OAuth1ClientPatch, self).get_oauth_params(request)
                params.extend(args)
                return params

        sess = OAuth1Session(self._cfg.consumer_key, self._cfg.consumer_secret, client_class=OAuth1ClientPatch)
        access_token = sess.fetch_access_token(self._cfg.access_token_url, verifier='123')
        return access_token

    @property
    def id(self):
        return self._id

    def update_status(self, status, photo=None):
        def get_photo(p):
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

        p = get_photo(photo)
        if p:
            rs = self._file('photos/upload', status=status, photo=p)
            # 上传文件也可以写成这样：
            # rs=self._file('photos/upload', status=(None,status,'text/plain'), photo=('photo',p,''application/octet-stream'')
            p.close()
        else:
            rs = self._post('statuses/update', status=status)
        return rs

    def delete_status(self, status_id):
        rs = self._post('statuses/destroy', id=status_id)
        return rs

    # 以下是不需要 id 参数，即只能获取当前用户信息的API
    def replies(self):
        """返回当前用户收到的回复"""
        # since_id, max_id, count
        replies = self._get('statuses/replies')

    def mentions(self):
        """返回回复/提到当前用户的20条消息"""
        # todo 这个和replies有什么区别？
        # since_id, max_id, count
        mentions = self._get('statuses/mentions')

    def follow(self, user):
        """
        关注用户
        :param User|str user: 被关注的用户, User对象，或id，或 loginname
        """
        if isinstance(user, User):
            user = user.id
        rs = self._post('friendships/create', id=user)
        return rs['xxx'] == ''

    def unfollow(self, user):
        """
        关注用户
        :param User|str user: 被关注的用户, User对象，或id，或 loginname
        """
        if isinstance(user, User):
            user = user.id
        rs = self._post('friendships/destroy', id=user)
        return rs['xxx'] == ''

    def block(self, user):
        """
        屏蔽用户
        :param str|User user: 被屏蔽的用户User对象或者id，loginname
        """
        if isinstance(user, User):
            user = user.id
        rs = self._post('blocks/create', id=user)
        return rs['xxx'] == ''

    def unblock(self, user):
        """
        解除屏蔽
        :param str|User user: 被屏蔽的用户User对象或者id，loginname
        """
        if isinstance(user, User):
            user = user.id
        rs = self._post('blocks/destroy', id=user)
        return rs['xxx'] == ''

    def is_blocked(self, user):
        """
        检查是否屏蔽用户
        :param str|User user: 用户User对象或者id，loginname
        """
        if isinstance(user, User):
            user = user.id
        rs = self._get('blocks/exists', id=user)
        return rs['xxx'] == ''

    def blocks(self):
        """返回黑名单上用户资料"""
        blocks = self._get('blocks/blocking')
        if blocks is not None:
            return [User(b) for b in blocks]

    def blocks_id(self):
        """获取用户黑名单id列表"""
        ids = self._get('blocks/ids')
        return ids
