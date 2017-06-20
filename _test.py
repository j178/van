from .van import Fan, Config, User
import sys


class MyConfig(Config):
    consumer_key = 'b55d535f350dcc59c3f10e9cf43c1749'
    consumer_secret = 'e9d72893b188b6340ad35f15b6aa7837'
    access_token = {
        "oauth_token": sys.argv[1],
        "oauth_token_secret": sys.argv[2]
    }


me = Fan(MyConfig())
s = me.update_status('测试一下1', 'D:/win/Desktop/1.jpg')
pass
