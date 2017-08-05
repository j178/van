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
import threading
from urllib.parse import urlparse

import arrow
import requests
from requests_oauthlib.oauth1_session import OAuth1Session

__version__ = '0.0.4'
__all__ = ['Fan', 'User', 'Status', 'Timeline']
logger = logging.getLogger(__name__)


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
                    resp.close()
                    return False
                return resp.raw
        except requests.RequestException:
            return False
    return False


def pager(fan, endpoint, **params):
    page = 1
    while True:
        _, rv = fan.get(endpoint, page=page, **params)
        if _:
            if not rv:
                return
            for r in rv:
                yield r
            page += 1
        else:
            return


def log(func):
    logger = logging.getLogger(func.__module__)

    @functools.wraps(func)
    def decorator(self, *args, **kwargs):
        logger.debug('Entering: %s', func.__name__)
        result = func(self, *args, **kwargs)
        logger.debug(result)
        logger.debug('Exiting: %s', func.__name__)
        return result

    return decorator


class FanfouError(Exception):
    """所有异常的基类"""


class NetworkError(FanfouError):
    """真实的网络错误：DNS解析出错，拒绝连接等"""


class Timeout(NetworkError):
    pass


class ApiRequestError(FanfouError):
    """API请求出错，参数错误、验证失败等"""


class AuthError(ApiRequestError):
    pass


class Fan:
    """
    API操作入口
    """

    def __init__(self, consumer_key, consumer_secret, oauth_token=None, mobile=False):
        self._consumer_key = consumer_key
        self._consumer_secret = consumer_secret
        self._oauth_token = oauth_token
        self._session = OAuth1Session(consumer_key, consumer_secret)
        if oauth_token:
            self._session._populate_attributes(oauth_token)
        self._oauth_type = None

        self.request_token_url = 'http://fanfou.com/oauth/request_token'
        self.authorize_url = 'http://fanfou.com/oauth/authorize'
        self.access_token_url = 'http://fanfou.com/oauth/access_token'
        if mobile:
            self.authorize_url = 'http://m.fanfou.com/oauth/authorize'

        self._me = None
        self.draft_box = []
        self.mentions = Timeline(self, None, 'statuses/mentions')
        self.replies = Timeline(self, None, 'statuses/replies')
        self.public_timeline = Timeline(self, None, 'statuses/public_timeline')

    @property
    def session(self):
        """获取session"""
        return self._session

    def authorization_url(self, oauth_callback='oob'):
        """
        引导用户访问的授权页面URL
        当 oauth_callback = 'oob' 时表示使用 PIN码授权
        """
        self._oauth_type = oauth_callback
        self._session.fetch_request_token(self.request_token_url)
        url = self._session.authorization_url(self.authorize_url, oauth_callback=oauth_callback)
        return url

    def oauth(self, pin_code=None, redirect_url=None):
        """通过授权后的PIN码或者浏览器重定向的URL获取最终的token"""
        if pin_code and redirect_url:
            raise ValueError('pin_code and redirect_url are mutually exclusive')
        if pin_code:
            token = self._session.fetch_access_token(self.access_token_url, verifier=pin_code)
        elif redirect_url:
            self._session.parse_authorization_response(redirect_url)
            token = self._session.fetch_access_token(self.access_token_url, verifier='x')
        else:
            raise ValueError('Either pin_code nor redirect_url is valid')
        self._oauth_token = token
        self._session._populate_attributes(token)
        return token

    def xauth(self, username, password):
        import oauthlib.oauth1.rfc5849.utils
        # patch to allow x_auth_* params
        oauthlib.oauth1.rfc5849.utils.filter_oauth_params = lambda _: _

        client = self._session._client.client

        class OAuth1Client(oauthlib.oauth1.rfc5849.Client):
            def get_oauth_params(self, request):
                params = super().get_oauth_params(request)
                args = [
                    ('x_auth_username', username),
                    ('x_auth_password', password),
                    ('x_auth_mode', 'client_auth')
                ]
                params += args
                return params

        sess = OAuth1Session(client.client_key, client.client_secret, client_class=OAuth1Client)
        token = sess.fetch_access_token(self.access_token_url, verifier='x')
        self._oauth_token = token
        self._session._populate_attributes(token)
        return token

    @property
    def authorized(self):
        """当前会话是否已授权"""
        return self._session.authorized

    def request(self, method, endpoint, params=None, data=None, files=None, **kwargs):
        """发出请求"""
        # 1-tuple (not a tuple at all)
        # {fieldname: file_object}
        # 2-tuple
        # {fieldname: (filename, file_object)}
        # 3-tuple
        # {fieldname: (filename, file_object, content_type)}
        # 4-tuple
        # {fieldname: (filename, file_object, content_type, headers)}
        kwargs.setdefault('timeout', (5, 5))
        url = 'http://api.fanfou.com/{}.json'.format(endpoint)

        try:
            response = self._session.request(method, url, params=params, data=data, files=files, **kwargs)
        except requests.Timeout:
            raise Timeout
        except requests.ConnectionError:
            raise NetworkError
        else:
            try:
                json_data = response.json()
            except ValueError:
                raise ApiRequestError('Invalid server response')
            if response.status_code == 200:
                return json_data
            if json_data.get('error'):
                raise ApiRequestError(json_data['error'])
            raise ApiRequestError('Invalid error response')

    def get(self, endpoint, **params):
        params.setdefault('mode', 'lite')
        params.setdefault('format', 'html')
        return self.request('GET', endpoint, params=params)

    def post(self, endpoint, files=None, **data):
        data.setdefault('mode', 'lite')
        data.setdefault('format', 'html')
        return self.request('POST', endpoint, data=data, files=files)

    @property
    def me(self):
        """获取授权用户的信息"""
        if self._me is None:
            me = User.from_id(self)
            me.mentions = self.mentions
            me.replies = self.replies
            self._me = me
        return self._me

    @log
    def update_status(self, status, photo=None,
                      in_reply_to_user_id=None,
                      in_reply_to_status_id=None,
                      repost_status_id=None,
                      location=None,
                      source=None):
        """
        发表新状态，:meth:`Status.send()` 的快捷方式。

        :param str text: 文字
        :param str photo: 照片路径或者URL
        :param str in_reply_to_user_id: 要回复的用户ID
        :param str in_reply_to_status_id: 要回复的消息ID
        :param str repost_status_id: 要转发的消息ID
        :param str location: 位置信息，使用'地点名称' 或 '一个半角逗号分隔的经纬度坐标'
        :param str source: source 消息来源
        """
        data = dict(status=status,
                    in_reply_to_user_id=in_reply_to_user_id,
                    in_reply_to_status_id=in_reply_to_status_id,
                    repost_status_id=repost_status_id,
                    locaion=location, source=source)
        try:
            if photo is not None:
                result = self.post('photos/upload', files=dict(photo=photo), **data)
            else:
                result = self.post('statuses/update', **data)
        except FanfouError:
            data['photo'] = photo
            self.draft_box.append(data)
            raise

        return Status.from_json(self, result)

    def resend_draft_box(self):
        pass

    # 以下是不需要 id 参数，即只能获取当前用户信息的API
    @log
    def follow(self, user):
        """
        关注用户

        :param User|str user: 被关注的用户, User对象，或id，或 loginname
        """
        if isinstance(user, User):
            user = user.id
        rs = self.post('friendships/create', id=user)
        return rs

    @log
    def unfollow(self, user):
        """
        取消关注用户

        :param User|str user: 被关注的用户, User对象，或id，或 loginname
        """
        if isinstance(user, User):
            user = user.id
        rs = self.post('friendships/destroy', id=user)
        return rs

    @property
    @log
    def follow_requests(self, count=60):
        """
        返回请求关注当前用户的列表

        :rtype: (bool, [User])
        """
        for fo in pager(self, 'friendships/requests', count=count):
            yield User.from_json(self, fo)

    @log
    def accept_follower(self, user):
        """
        接受关注请求

        :param User|str user: User对象，或id，或 loginname
        :rtype: (bool, User)
        """
        if isinstance(user, User):
            user = user.id
        rv = self.get('friendships/accept', id=user)
        return rv

    @log
    def deny_follower(self, user):
        """
        拒绝关注请求

        :param User|str user: User对象，或id，或 loginname
        :rtype: (bool, User)
        """
        if isinstance(user, User):
            user = user.id
        rv = self.post('friendships/deny', id=user)
        return rv

    @log
    def block(self, user):
        """
        屏蔽用户

        :param str|User user: 被屏蔽的用户User对象或者id，loginname
        :rtype: (bool, User)
        """
        if isinstance(user, User):
            user = user.id
        rs = self.post('blocks/create', id=user)
        return rs

    @log
    def unblock(self, user):
        """
        解除屏蔽

        :param str|User user: 被屏蔽的用户User对象或者id，loginname
        :rtype: (bool, str)
        """
        if isinstance(user, User):
            user = user.id
        rs = self.post('blocks/destroy', id=user)
        return rs

    def is_blocked(self, user):
        """
        检查是否屏蔽用户

        :param str|User user: 用户User对象或者id，loginname
        :rtype: (bool, str)
        """
        if isinstance(user, User):
            user = user.id
        return self.get('blocks/exists', id=user)

    @property
    def blocked_users(self):
        """
        返回黑名单上用户列表

        :rtype: (bool, [User])
        """
        for bl in pager(self, 'blocks/blocking'):
            yield User.from_json(self, bl)

    @property
    @log
    def blocked_users_id(self):
        """
        获取用户黑名单id列表

        :rtype: (bool, [str])
        """
        for bl in pager(self, 'blocks/ids'):
            yield bl

    @property
    @log
    def trends(self):
        return self.get('trends/list')


class Base:
    """
    :class:`User` 和 :class:`Status` 的基类。
    为子类提供对象缓存和自动加载功能。
    """
    endpiont = None
    attrs = ('id',)

    def __init__(self, fan, **kwargs):
        # 构造函数的三种使用方式：
        # 1. User.get(id='') 由id获取对象
        # 2. User.get(data=rv) 由API返回的字典构造对象
        # 3. Status(text='abc') 提供一些参数构造一个不完全的对象(一般是没有ID)，API调用之后用返回结果补完
        # 4. User.get(master=True) 作为主人的特殊待遇
        self.fan = fan  # type: Fan
        self.dict = kwargs  # type: dict

    def __getattr__(self, item):
        if item in self.attrs:
            if item not in self.dict:
                id = self.dict.get('id')
                result = self.fan.get(self.endpiont, id=id)
                self.dict.update(result.copy())
            return self.dict.get(item)
        raise AttributeError

    @classmethod
    def from_json(cls, fan, data):
        if not data:
            return None

        data = data.copy()
        return cls(fan, **data)

    @classmethod
    def from_id(cls, fan, id=None):
        result = fan.get(cls.endpiont, id=id)
        return cls.from_json(fan, result)

    def to_dict(self):
        return self.dict


class Timeline:
    """
    时间线管理类
    """

    def __init__(self, fan, user_id, endpoint):
        self.fan = fan
        self.user_id = user_id  # type:User
        """:class:`~van.User` 时间线的主人"""
        self.endpoint = endpoint
        self._pool = []  # type: [Status]
        self._max_id = None
        self._max_rawid = -1
        self._since_id = None
        self._since_rawid = 1 << 32  # 什么时候饭否消息会达到这个数字呢？
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
                raise ValueError('offset should be zero or positive while whence=0')
            self._curr = min(offset, max(len(self._pool) - 1, 0))
        elif whence == 1:
            self._curr += offset
            self._curr = min(max(self._curr, 0), len(self._pool) - 1)
        else:
            if offset > 0:
                raise ValueError('offset should be zero or negative while whence=2')
            else:
                self._curr = max(len(self._pool) + offset, 0)
        return self._curr

    def read(self, count=10):
        """
        从当前游标位置处往后读取 `count` 条消息, 数组长度可能小于要求的大小。

        :param int count: 读取数量
        :return: :class:`Status` 数组
        :rtype: [Status]
        """
        while self._curr + count >= len(self._pool):
            if self._fetch_older() == 0:
                break
        rv = self._pool[self._curr:self._curr + count]
        self._curr += len(rv)
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
        rv = self.fan.get(self.endpoint, id=self.user_id,
                          since_id=since_id, max_id=max_id, count=count)
        return [Status.from_json(self.fan, s) for s in rv]

    def _fetch_older(self):
        rv = self.fetch(max_id=self._since_id)
        if rv:
            self._since_id = rv[-1].id
            self._since_rawid = rv[-1].rawid
            if rv[0].rawid > self._max_rawid:
                self._max_id = rv[0].id
                self._max_rawid = rv[0].rawid
            self._pool.extend(rv)
            return len(rv)
        return 0

    def _fetch_newer(self):
        rv = self.fetch(since_id=self._max_id)
        if rv:
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
                    return
            yield self._pool[self._curr]
            self._curr += 1

    def __len__(self):
        return len(self._pool)


class User(Base):
    """
    用户类
    """
    # 需要 id 参数，可查看其他用户信息的 API 在此类中（也可以省略 id 表示当前用户）
    endpiont = 'users/show'
    attrs = ('id', 'unique_id', 'name', 'screen_name', 'location', 'gender', 'birthday',
             'description', 'url', 'protected', 'followers_count', 'friends_count', 'favourites_count',
             'statuses_count', 'photo_count', 'following', 'notifications', 'created_at', 'utc_offset',
             'profile_image_url', 'profile_image_url_large')

    def __init__(self, fan, **kwargs):
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
        super().__init__(fan, **kwargs)
        self.created_at = arrow.get(self.dict['created_at'], 'ddd MMM DD HH:mm:ss Z YYYY')

        self.timeline = Timeline(self.fan, self.id, 'statuses/home_timeline')  # 返回此用户看到的时间线
        self.statues = Timeline(self.fan, self.id, 'statuses/user_timeline')  # 返回此用户已发送的消息
        self.photos = Timeline(self.fan, self.id, 'photos/user_timeline')  # 浏览指定用户的图片

    @property
    def followers(self, count=60):
        """
        返回此用户的关注者
        此用户为当前用户的关注对象或未设置隐私

        :param int count: 每次获取的数量
        """
        for fo in pager(self.fan, 'statuses/followers', id=self.id, count=count):
            yield User.from_json(self.fan, fo)

    @property
    def followers_id(self, count=60):
        """
        返回此用户关注者的id列表

        :param int count: 每次获取的数量
        """
        for fo in pager(self.fan, 'followers/ids', id=self.id, count=count):
            yield fo

    @property
    def friends(self, count=60):
        """
        返回此用户的关注对象
        此用户为当前用户的关注对象或未设置隐私
        """
        for fr in pager(self.fan, 'statuses/friends', id=self.id, count=count):
            yield User.from_json(self.fan, fr)

    @property
    def friends_id(self, count=60):
        """返回此用户关注对象的id列表"""
        for fr in pager(self.fan, 'friends/ids', id=self.id, count=count):
            yield fr

    @property
    def favorites(self, count=60):
        """浏览此用户收藏的消息"""
        for fo in pager(self.fan, 'favorites/id', id=self.id, count=count):
            yield Status.from_json(self.fan, fo)

    def relationship(self, other):
        """
        返回此用户与 other 的关系： 是否屏蔽，是否关注，是否被关注

        :param str|User other: 其他用户
        :rtype: (a_blocked_b, a_following_b, a_followed_b)
        """
        if isinstance(other, User):
            other = other.id
        rv = self.fan.get('friendships/show', source_id=self.id, target_id=other)
        source = rv['relationship']['source']
        rv = (source['blocking'] == 'true', source['following'] == 'true', source['followed_by'] == 'true')
        return rv

    def __str__(self):
        return '<User ({}@{})>'.format(self.name, self.id)

    def __hash__(self):
        return hash(self.id)

    __repr__ = __str__


class Photo:
    def __init__(self, photo_url):
        self.photo_url = photo_url
        self.url = self.get(photo_url)

    @staticmethod
    def encode_params(params):
        pass

    def get(self, width=None, height=None, edge=None,
            larger=None, percentage=None, background_color=None):
        """
        图片处理服务
        :param width: 1-4096 指定目标缩略图的宽度
        :param height: 1-4096 指定目标缩略图的高度
        :param edge: 0/1/2/4，默认值为0 缩略优先边。0代表长边优先；1代表短边优先；2代表强制缩略；4代表短边优先缩略后填充
        :param larger: 0/1，默认值为0 目标缩略图大于原图是否处理。0代表处理；1代表不处理
        :param percentage: 1-1000 倍数百分比。100为原图；大于100为放大；小于100为缩小
        :param background_color: red, green, blue[0-255] 填充部分的背景色。默认不指定（白色填充）。例如：100-100-100bgc
        :return: 图片URL
        """
        if isinstance(background_color, (list, tuple)):
            pass
        params = {
            'w': width,
            'h': height,
            'e': edge,
            'l': larger,
            'p': percentage,
            'bgc': background_color
        }
        return self.encode_params(params)


class Status(Base):
    """
    消息类
    """
    endpiont = 'statuses/show'
    attrs = ('id', 'text', 'photo', 'created_at', 'in_reply_to_user_id', 'in_reply_to_status_id',
             'in_reply_to_screen_name', 'repost_status_id', 'repost_status', 'repost_user_id',
             'repost_screen_name', 'favorited', 'rawid', 'source', 'truncated', 'is_self', 'location')

    def __init__(self, fan, **kwargs):
        """
        :param str text: 消息内容
        :param str id: status id
        :param bool fill: 是否立即发起请求，填充对象属性。默认为False，当省略该值，并且只提供了id时，fill为True
        :param dict|File photo: 图片URL字典 imageurl=图片地址 thumburl=缩略图地址 largeurl=图片原图地址
        :param Status|dict repost_status: 被转发消息的详细信息
        :param User|dict user: 消息的主人
        """
        super().__init__(fan, **kwargs)

        self.user = User.from_json(fan, self.dict['user'])  # type:User
        self.created_at = arrow.get(self.dict['created_at'], 'ddd MMM DD HH:mm:ss Z YYYY')
        if self.repost_status:
            self.repost_status = Status.from_json(fan, self.dict['repost_status'])
        if self.photo:
            self.photo = Photo(self.dict['photo']['imageurl'])

    @staticmethod
    def process_text(text):
        at_re = re.compile(r'@<a.*?>(.*?)</a>', re.I)
        topic_re = re.compile(r'#<a.*?>(.*?)</a>#', re.I)
        link_re = re.compile(r'<a.*?rel="nofollow" target="_blank">(.*)</a>', re.I)

        text = at_re.sub(r'@\1', text)
        text = topic_re.sub(r'#\1#', text)
        text = link_re.sub(r'\1', text)
        return text

    @staticmethod
    def process_photo_link(photo):
        large_url = photo['largeurl']
        origin_url = re.sub(r'@.+\..+$', '', large_url)
        type = re.match(r'^.+\.(.+)$', origin_url).group(1)
        photo['originurl'] = origin_url
        photo['type'] = type
        return photo

    def delete(self):
        """删除此消息（当前用户发出的消息）"""
        result = self.fan.post('statuses/destroy', id=self.id)
        result = Status.from_json(self.fan, result)
        return result

    @property
    def context(self):
        """按照时间先后顺序显示消息上下文"""
        result = self.fan.get('statuses/context_timeline', id=self.id)
        context = [Status.from_json(self.fan, s) for s in result]
        return context

    def reply(self, response, photo=None, location=None, format='@{poster} {response}', **kwargs):
        """回复这条消息"""
        text = format.format(response=response,
                             poster=self.user.screen_name,
                             **kwargs)
        data = dict(status=text,
                    photo=photo,
                    location=location,
                    in_reply_to_user_id=self.user.id,
                    in_reply_to_status_id=self.id)
        result = self.fan.update_status(**data)
        return result

    def repost(self, repost, photo=None, location=None,
               format='{repost}{repost_style_left}@{name} {origin}{repost_style_right}',
               **kwargs):
        """转发这条消息"""
        kwargs.setdefault('repost_style_left', ' ')
        kwargs.setdefault('repost_style_right', '')

        text = format.format(repost=repost,
                             name=self.user.screen_name,
                             origin=self.process_text(self.text),
                             **kwargs)
        data = dict(status=text,
                    photo=photo,
                    location=location,
                    repost_status_id=self.id)
        result = self.fan.update_status(**data)
        return result

    def favorite(self):
        """收藏此消息"""
        # fuck, 为啥就这一个API不一样…
        result = self.fan.post('favorites/create/' + self.id)
        return Status.from_json(self.fan, result)

    def unfavorite(self):
        """取消收藏此消息"""
        result = self.fan.post('favorites/destroy/' + self.id)
        return Status.from_json(self.fan, result)

    def __str__(self):
        return '<Status ("{}" @{})>'.format(self.text, self.user.id)

    __repr__ = __str__


class Event:
    """
    事件对象，模拟一个事件发生时相关的数据

    每个事件都有一个类型，当前可用的类型有：

        * MESSAGE_CREATE： 当前用户发布一条状态。source为当前用户，如果消息中@其他人，则target为被提及用户，object为发布的状态
        * MESSAGE_DELETE： 当前用户删除一条状态
        * MESSAGE： 与 MESSAGE 相关的所有类型的事件，即 `MESSAGE_CREATE` 与 `MESSAGE_DELETE` 的合事件。
        * FRIENDS_CREATE：当前用户关注其他用户。source为当前用户，target为被关注的对象
        * FRIENDS_DELETE： 当前用户取消关注其他用户
        * FRIENDS_REQUEST： 当前用户对其他用户发起关注请求
        * FRIENDS：FRIENDS 相关的所有类型的事件
        * FAV_CREATE：当前用户收藏一条状态。 source 为发起收藏操作的用户，target为状态被收藏的用户，object为被收藏的状态
        * FAV_DELETE：当前用户取消收藏一条状态
        * FAV：FAV 相关的所有事件
        * DM_CREATE： 用户收到一条私信
        * USER_UPDATE_PROFILE：当前用户更新个人资料
        * ALL：所有事件
    """

    HEART_BEAT = 0b000001000
    ERROR = 0b000010000

    MESSAGE_CREATE = 0b000100001
    MESSAGE_DELETE = 0b000100010
    MESSAGE = MESSAGE_CREATE | MESSAGE_DELETE

    FRIENDS_CREATE = 0b001000001
    FRIENDS_DELETE = 0b001000010
    FRIENDS_REQUEST = 0b01000100
    FRIENDS = FRIENDS_CREATE | FRIENDS_DELETE | FRIENDS_REQUEST

    FAV_CREATE = 0b010000001
    FAV_DELETE = 0b010000010
    FAV = FAV_CREATE | FAV_DELETE

    USER_UPDATE_PROFILE = 0b100000001
    USER = USER_UPDATE_PROFILE

    ALL = MESSAGE | FRIENDS | FAV | USER | HEART_BEAT | ERROR

    def __init__(self, fan, type, data=None):
        self.fan = fan
        self.type = type
        data = data if isinstance(data, dict) else dict(object=data)
        source = data.get('source')
        target = data.get('target')
        object = data.get('object')
        event = data.get('event')
        created_at = data.get('created_at')

        self.source = User.from_json(fan, source) if isinstance(source, dict) else source
        self.target = User.from_json(fan, target) if isinstance(target, dict) else target
        self.object = User.from_json(fan, object) if isinstance(object, dict) else object
        self.event = event
        self.created_at = arrow.get(created_at, 'ddd, DD MMM YYYY HH:mm:ss') if created_at else created_at

    def __str__(self):
        return '<Event {0.type} {0.source} {0.target} {0.object} {0.event} {0.created_at}>'.format(self)


class Listener:
    def __init__(self, on, action, ttl=None):
        self.on = on
        self.action = action
        self.ttl = ttl


class Stream(threading.Thread):
    """
    Streamming API, 实时监测用户动作
    """

    def __init__(self, fan):
        super().__init__()
        self.fan = fan
        self._conn = None
        self._listeners = []  # type:[Listener]
        self._lock = threading.RLock()
        # self._counter = itertools.count()  # counter 记录监听器加入顺序
        self._running = True
        self._init()

    def _init(self):
        """
        开始建立长连接
        """
        self._conn = self.fan.session.post('http://stream.fanfou.com/1/user.json', stream=True)
        if self._conn.encoding is None:
            self._conn.encoding = 'utf8'

    def stop(self):
        """
        停止监听事件
        """
        self._running = False

    def run(self):
        """
        开始监听事件
        """
        for chunk in self._conn.iter_content(chunk_size=None, decode_unicode=True):
            evt = self._parse_chunk(chunk)
            for action in self._pick_listeners(evt):
                try:
                    action(evt)
                except Exception as e:
                    logger.error(e)
            if not self._running:
                break
        self._conn.close()

    def _pick_listeners(self, event):
        with self._lock:
            # 将堆导出为一个有序的列表
            # listeners = self._listeners[:]
            # queue = list(map(heapq.heappop, [listeners] * len(listeners)))

            for lsn in self._listeners:
                if lsn.on & event.type and (lsn.ttl is None or lsn.ttl > 0):
                    yield lsn.action

                    if lsn.ttl is not None:
                        lsn.ttl -= 1

    def _parse_chunk(self, chunk):
        if chunk == '\r\n':
            return Event(self.fan, Event.HEART_BEAT, r'\r\n')

        try:
            data = json.loads(chunk)
        except json.JSONDecodeError as e:
            logger.error(e)
            return Event(Event.ERROR, e)

        event_name = data['event'].upper().replace('.', '_')
        type = getattr(Event, event_name, Event.ERROR)

        event = Event(self.fan, type, data)
        return event

    def install_listener(self, listener):
        """
        添加新的监听器
        :param Listener listener: Listener 对象
        """
        # seq = next(self._counter)
        with self._lock:
            self._listeners.append(listener)

    def on(self, event, ttl=None):
        """
        作为装饰器使用，添加新的监听器

        :param event: 监听的事件, 多个事件请用 | 连接。如 `Event.MESSAGE | Event.FREIENDS`
        :param int priority：监听器的优先级，数字越小优先级越高
        :param int ttl: 此监听器执行的次数，`None` 表示不限次数
        """

        def decorator(func):
            listener = Listener(event, func, ttl)
            self.install_listener(listener)

        return decorator
