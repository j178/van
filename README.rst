Van - Fanfou SDK
================

.. image:: https://badges.gitter.im/fan-van/Lobby.svg
   :alt: Join the chat at https://gitter.im/fan-van/Lobby
   :target: https://gitter.im/fan-van/Lobby?utm_source=badge&utm_medium=badge&utm_campaign=pr-badge&utm_content=badge

How to use
----------

.. code-block:: python

    from .fanfou import Fan, Config


    # 1. Subclass the ``Config`` class and offer your configs
    class MyConfig(Config):
        consumer_key = 'xxxx'
        consumer_secret = 'xxxx'


    # 2. Instancialize the ``Fan`` class
    me = Fan(MyConfig())
    # 3. call methods of ``fan``
    me.update_status('你好啊，李银河！')