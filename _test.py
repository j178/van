from fanfou_sdk import Fan, Config, User


class MyConfig(Config):
    consumer_key = 'b55d535f350dcc59c3f10e9cf43c1749'
    consumer_secret = 'e9d72893b188b6340ad35f15b6aa7837'
    access_token = {
        "oauth_token": "1478511-b424da7a7c87bbf9787489bf4632cebe",
        "oauth_token_secret": "678a3f6d7852da2881cdab7e7fb1fefc"
    }


me = Fan(MyConfig())
s = me.update_status('测试一下1','D:/win/Desktop/1.jpg')
pass
