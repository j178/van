# How to use

from fanfousdk.sdk import Fan, Config


# 1. Subclass the ``Config`` class and offer your configs
class MyConfig(Config):
    consumer_key = 'b55d535f350dcc59c3f10e9cf43c1749'
    consumer_secret = 'e9d72893b188b6340ad35f15b6aa7837'


# 2. Instancialize the ``Fan`` class
me = Fan(MyConfig())
# 3. call methods of ``fan``
me.update_status('你好啊，李银河！')

