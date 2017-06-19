import atexit
import json
import os
import time

import requests
import sys
from requests_oauthlib.oauth1_session import OAuth1Session, TokenRequestDenied

_session = None


def get_input(prompt=None):
    return input(prompt).strip()


def _request(method, category, action, **data):
    # 1-tuple (not a tuple at all)
    # {fieldname: file_object}
    # 2-tuple
    # {fieldname: (filename, file_object)}
    # 3-tuple
    # {fieldname: (filename, file_object, content_type)}
    # 4-tuple
    # {fieldname: (filename, file_object, content_type, headers)}
    url = 'http://api.fanfou.com/{}/{}.json'.format(category, action)
    d = {'params': None, 'data': None, 'files': None}
    d[{'GET': 'params', 'POST': 'data', 'FILE': 'files'}[method]] = data

    for failure in range(3):
        try:
            result = _session.request(method, url, **d, timeout=3)
            j = result.json()
            if result.status_code == 200:
                return j
            raise requests.RequestException(j['error'])
        except requests.RequestException:
            if failure >= 2:
                raise
        time.sleep(1)


class AuthFailed(Exception): pass


class Base:
    endpiont = None

    def __init__(self, id=None, buffer=None):
        self._buffer = None
        self._id = id
        if buffer is not None:
            if isinstance(buffer, str):
                try:
                    self._buffer = json.loads(buffer)
                except json.JSONDecodeError:
                    self._buffer = None
            elif isinstance(buffer, dict):
                self._buffer = buffer

    def _load(self):
        return _request('GET', self.endpiont, 'show', id=self._id)

    def __getattr__(self, item):
        if self._buffer is None:
            self._buffer = self._load()
        return self._buffer.get(item)


class User(Base):
    endpiont = 'users'

    def __init__(self, id=None, buffer=None):
        super().__init__(id, buffer)

    def statuses(self):
        """返回此用户已发送的消息"""
        'statuses/user_timeline'
        timeline = _request('GET', 'statuses', 'user_timeline')

    def timeline(self, id=None):
        """
        返回目标用户**看到的**时间线
        目标用户为当前用户，或当前用户的关注对象或未设置隐私"""
        'statuses/home_timeline'

    def followers(self, id=None):
        """
        返回目标用户的关注者
        目标用户为当前用户，或当前用户的关注对象或未设置隐私"""
        'statuses/followers'

    def friends(self, id=None):
        """
        返回目标用户的关注对象
        目标用户为当前用户，或当前用户的关注对象或未设置隐私"""
        'statuses/friends'

    def replies(self):
        """返回当前用户收到的回复"""
        'statuses/replies'

    def mentions(self):
        """返回回复/提到当前用户的20条消息"""
        '?这个和replies有什么区别？'

    def __str__(self):
        return ''


class Status(Base):
    endpiont = 'statuses'

    def __init__(self, id=None, buffer=None):
        super().__init__(id, buffer)

    def __str__(self):
        return ''


class Timeline(list):
    """
    需求:
    1. 完全隐藏网络请求，将此对象看作无尽的数组，随便取数据
    2. 整合搜索 API
    3. 提供多种获取方式，id、id区间、时间区间、关键字
    4. 提供历史记录，可以往回翻页

    """

    def __init__(self, array):
        super().__init__()
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


class Fan(User):
    def __init__(self, cfg: Config):
        super().__init__()

        global _session

        self._cfg = cfg
        _session = OAuth1Session(cfg.consumer_key, cfg.consumer_secret)
        if not cfg.access_token:
            if cfg.auth_type == 'oauth':
                cfg.access_token = self._oauth()
            else:
                cfg.access_token = self._xauth()
        _session._populate_attributes(cfg.access_token)

        self._buffer = self._load()

    def _oauth(self):
        from http.server import BaseHTTPRequestHandler, HTTPServer
        from urllib.parse import urlparse

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

        username = get_input('[-]请输入用户名或邮箱>')
        password = getpass.getpass('[-]请输入密码>')
        # 这些实际上并不是url params，但是他们与其他url params一样参与签名，最终成为Authorization header的值
        args = [
            ('x_auth_username', username),
            ('x_auth_password', password),
            ('x_auth_mode', 'client_auth')
        ]

        class OAuth1ClientPatch(OAuth1Client):
            """Patch oauthlib.oauth1.Client for xauth"""

            def get_oauth_params(self, request):
                params = super().get_oauth_params(request)
                params.extend(args)
                return params

        sess = OAuth1Session(self._cfg.consumer_key, self._cfg.consumer_secret, client_class=OAuth1ClientPatch)
        access_token = sess.fetch_access_token(self._cfg.access_token_url, verifier='123')
        return access_token

    def update_status(self, status, photo=None):
        pass

    def delete_status(self, status_id):
        pass
