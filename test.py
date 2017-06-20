import os

from nose.tools import raises
from van import Fan, Config

access_token = {
    "oauth_token": os.environ['ACCESS_TOKEN'],
    "oauth_token_secret": os.environ['ACCESS_TOKEN_SECRET']
}


class MyConfig(Config):
    consumer_key = 'b55d535f350dcc59c3f10e9cf43c1749'
    consumer_secret = 'e9d72893b188b6340ad35f15b6aa7837'


class TestAuth:
    def setup(self):
        self.cfg = MyConfig()

    def test_xauth(self):
        self.cfg.auth_type = 'xauth'
        self.cfg.xauth_username = os.environ['XAUTH_USERNAME']
        self.cfg.xauth_password = os.environ['XAUTH_PASSWORD']
        fan = Fan(self.cfg)
        assert isinstance(fan._cfg.access_token, dict)

        # @raises(AuthFailed)
        # def test_oauth(self):
        #     fake_token = 'ac2ee1b976a94f46fed55d5a98c8d519'
        #
        #     def mock_callback():
        #         time.sleep(5)
        #         requests.get(
        #                 self.cfg.redirect_url +
        #                 '/callback?oauth_token=' + fake_token)
        #
        #     threading.Thread(target=mock_callback).start()
        #     self.cfg.auth_type = 'oauth'
        #     fan = Fan(self.cfg)


class TestConfig:
    def setup(self):
        cfg = MyConfig()
        cfg.save_token = True
        self.cfg = cfg

    def test_dump(self):
        self.cfg.dump()
        assert os.path.isfile(self.cfg.save_path)

    def test_load(self):
        self.cfg.load()

    def teardown(self):
        try:
            os.remove(self.cfg.save_path)
        except FileNotFoundError:
            print('fuck you !!!')


class TestBaseClass:
    pass
