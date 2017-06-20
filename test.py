from van import Fan, Config, User
import os

consumer_key = 'b55d535f350dcc59c3f10e9cf43c1749'
consumer_secret = 'e9d72893b188b6340ad35f15b6aa7837'
access_token = {
    "oauth_token": os.environ['ACCESS_TOKEN'],
    "oauth_token_secret": os.environ['ACCESS_TOKEN_SECRET']
}


class TestAuth:
    def setup(self):
        class MyConfig(Config):
            consumer_key = consumer_key
            consumer_secret = consumer_secret
            auth_type = 'xauth'
            xauth_username = os.environ['XAUTH_USERNAME']
            xauth_password = os.environ['XAUTH_PASSWORD']

        self.fan = Fan(MyConfig())

    def test_xauth(self):
        assert isinstance(self.fan._cfg.access_token, dict)
