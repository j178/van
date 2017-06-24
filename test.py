import base64
import io
import os
import random
import string

import arrow
from nose.tools import *

try:
    from fanfou_sdk import van
    from fanfou_sdk.van import Fan, Config, Status, User, Photo, Stream, Event
except ImportError:
    import van
    from van import Fan, Config, Status, User, Photo, Stream, Event

ACCESS_TOKEN = {
    "oauth_token": os.environ.get('ACCESS_TOKEN'),
    "oauth_token_secret": os.environ.get('ACCESS_TOKEN_SECRET')
}


class MyConfig(Config):
    consumer_key = 'b55d535f350dcc59c3f10e9cf43c1749'
    consumer_secret = 'e9d72893b188b6340ad35f15b6aa7837'


RAW_PHOTO = b'/9j/4AAQSkZJRgABAQEASABIAAD/2wBDAAIBAQEBAQIBAQECAgICAgQDAgICAgUEBAMEBgUGBgYF\nBgYGBwkIBgcJBwYGCAsICQoKCgoKBggLDAsKDAkKCgr/2wBDAQICAgICAgUDAwUKBwYHCgoKCgoK\nCgoKCgoKCgoKCgoKCgoKCgoKCgoKCgoKCgoKCgoKCgoKCgoKCgoKCgoKCgr/wAARCABgAGADASIA\nAhEBAxEB/8QAHwAAAQUBAQEBAQEAAAAAAAAAAAECAwQFBgcICQoL/8QAtRAAAgEDAwIEAwUFBAQA\nAAF9AQIDAAQRBRIhMUEGE1FhByJxFDKBkaEII0KxwRVS0fAkM2JyggkKFhcYGRolJicoKSo0NTY3\nODk6Q0RFRkdISUpTVFVWV1hZWmNkZWZnaGlqc3R1dnd4eXqDhIWGh4iJipKTlJWWl5iZmqKjpKWm\np6ipqrKztLW2t7i5usLDxMXGx8jJytLT1NXW19jZ2uHi4+Tl5ufo6erx8vP09fb3+Pn6/8QAHwEA\nAwEBAQEBAQEBAQAAAAAAAAECAwQFBgcICQoL/8QAtREAAgECBAQDBAcFBAQAAQJ3AAECAxEEBSEx\nBhJBUQdhcRMiMoEIFEKRobHBCSMzUvAVYnLRChYkNOEl8RcYGRomJygpKjU2Nzg5OkNERUZHSElK\nU1RVVldYWVpjZGVmZ2hpanN0dXZ3eHl6goOEhYaHiImKkpOUlZaXmJmaoqOkpaanqKmqsrO0tba3\nuLm6wsPExcbHyMnK0tPU1dbX2Nna4uPk5ebn6Onq8vP09fb3+Pn6/9oADAMBAAIRAxEAPwD3ttc1\nawuE83eWH8LpguPcD/0JCfcV6d4C/a9X4d6TNq/i68Fzp1tFunaeRVmgUDrvzhxxwTkn17V53c6R\n9pjMUV+JUxxHcp5i/XPDZ9814F+3JZ6jpfw4haKQqr6mivskJD/upDye/I75Pua/lLhTOszwWZU6\nWHqOKk9V0fyP2PEZHl+dVIwrwv59T6X0v9uHWP2qPD9/Jptnb6dplrf+XBYCVmlkAG5WmcYBzwdq\njAx1PbnLyMSXL3MjO5kGx2BAkuMA/u1P8EY5yf16k/DP7MHx3vPhB408y8Z5dPuwIr+EHnbnh1H9\n5f1GRX25b3tr4t02HWPD99FcWt5GrRzoQysh6Af7PqO54NdPG8MxqZm6+Ik3GW3ZeR7MMko5LH2d\n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\njGatJXOqKcXpuf/Z\n'


def random_str(length=10):
    return ''.join(random.choice(string.printable) for _ in range(length))


class TestAuth:
    def setup(self):
        self.cfg = MyConfig()

    def test_xauth(self):
        self.cfg.auth_type = 'xauth'
        self.cfg.xauth_username = os.environ['XAUTH_USERNAME']
        self.cfg.xauth_password = os.environ['XAUTH_PASSWORD']
        Fan.setup(cfg=self.cfg)
        assert isinstance(van._cfg.access_token, dict)


class TestConfig:
    def setup(self):
        # teardown 和 setup 在每个测试函数调用时都会调用一次
        cfg = MyConfig()
        cfg.save_token = True
        self.cfg = cfg

    def test_load(self):
        self.cfg.load()

    def test_dump(self):
        self.cfg.dump()
        assert os.path.isfile(self.cfg.save_path)
        os.remove(self.cfg.save_path)


class TestAPI:
    def setup(self):
        cfg = MyConfig()
        cfg.access_token = ACCESS_TOKEN
        cfg.timeout = 10
        cfg.fail_sleep_time = 10

        self.cfg = cfg
        self.me = Fan.get(cfg=cfg)  # type:Fan

    def test_user_api(self):
        assert_is(self.me, Fan.get(id=self.me.id))

        assert_is_not_none(self.me.id)
        assert_is_not_none(self.me.name)
        assert_is_not_none(self.me.location)
        assert_is_not_none(self.me.screen_name)
        assert_is_not_none(self.me.unique_id)
        assert_is_not_none(self.me.gender)
        assert_is_instance(self.me.created_at, arrow.Arrow)

        assert_is_not_none(self.me.followers)
        assert_is_not_none(self.me.followers_id)
        assert_is_not_none(self.me.friends)
        assert_is_not_none(self.me.friends_id)
        assert_is_not_none(self.me.photos)
        assert_is_not_none(self.me.favorites)
        assert_is_not_none(self.me.follow_requests)
        assert_is_not_none(self.me.draft_box)
        assert_is_not_none(self.me.blocked_users)
        assert_is_not_none(self.me.blocked_users_id)

    def test_follow(self):
        other = User.get(id='john.j')  # type:Fan

        self.me.follow(other)
        assert_true(self.me.relationship(other)[1][1])
        self.me.unfollow(other)
        assert_false(self.me.relationship(other)[1][1])

    def test_block(self):
        other = User.get(id='john.j')  # type:Fan

        self.me.block(other)
        assert_true(self.me.relationship(other)[1][0])
        assert_true(self.me.is_blocked(other)[1])
        self.me.unblock(other)
        assert_false(self.me.relationship(other)[1][0])

    def test_status(self):
        _, status = Status(text=random_str()).send()
        _, photo_status = Status(text=random_str(), photo=io.BytesIO(base64.decodebytes(RAW_PHOTO))).send()

        assert_is_not_none(status.text)
        assert_is_not_none(status.context)
        assert_is_instance(photo_status.photo, Photo)
        assert_is(status.user, self.me)
        assert_is_instance(status.created_at, arrow.Arrow)

        status.reply(random_str())
        status.reply(random_str(), photo=io.BytesIO(base64.decodebytes(RAW_PHOTO)))
        status.repost(random_str())
        status.repost(random_str(), photo=io.BytesIO(base64.decodebytes(RAW_PHOTO)))

        assert_true(status.favorite()[1].favorited)
        assert_false(status.unfavorite()[1].favorited)


class TestTimeline:
    def setup(self):
        cfg = MyConfig()
        cfg.access_token = ACCESS_TOKEN
        cfg.timeout = 10
        cfg.fail_sleep_time = 10

        self.cfg = cfg
        self.me = Fan.get(cfg=cfg)  # type:Fan
        self.tl = self.me.timeline

    def test_access(self):
        self.tl.read()
        self.me.statues.read()
        self.me.replies.read()
        self.me.mentions.read()
        self.me.public_timeline.read()

    def test_call(self):
        tl = self.tl
        assert_is_not_none(tl.fetch(count=10))

    def test_seek(self):
        tl = self.tl
        tl.read(count=60)
        assert_equal(tl.tell(), 60)

        tl.rewind()
        assert_equal(tl.tell(), 0)
        assert_equal(tl.seek(10), 10)
        assert_raises(ValueError, tl.seek, -1)
        assert_equal(tl.seek(1000), len(tl) - 1)

        tl.rewind()
        tl.seek(10)
        assert_equal(tl.seek(10, 1), 20)
        assert_equal(tl.seek(-10, 2), len(tl) - 10)

        tl.rewind()
        tl.seek(10)
        assert_equal(tl.seek(-5, 1), 5)
        assert_equal(tl.seek(1000, 1), len(tl) - 1)

        tl.rewind()
        assert_equal(tl.seek(1000, 2), len(tl) - 1)
        assert_equal(tl.seek(-1000, 2), 0)


class TestStream:
    def setup(self):
        cfg = MyConfig()
        cfg.access_token = ACCESS_TOKEN
        Fan.setup(cfg)
        self.s = Stream()
        self.thread = self.s.run()

    def teardown(self):
        self.s.stop()

    def test_api(self):
        @self.s.on(Event.ALL)
        def listener(evt):
            print(evt)

        assert_equal(len(self.s._listeners), 1)

        @self.s.on(Event.MESSAGE | Event.FAV, ttl=3)
        def _(evt):
            print(evt)

        assert_equal(len(self.s._listeners), 2)

        @self.s.on(Event.HEART_BEAT)
        def _(evt):
            assert_is_instance(evt, Event)
            assert_equal(evt.object, r'\r\n')
