Van - Fanfou SDK
################

.. image:: https://travis-ci.org/j178/van.svg?branch=master
    :target: https://travis-ci.org/j178/van

.. image:: https://badge.fury.io/py/van.svg
    :target: https://pypi.python.org/pypi/van

.. image:: https://img.shields.io/badge/python-3.5-blue.svg
    :target: https://pypi.python.org/pypi/fanfou-cli

.. image:: https://img.shields.io/badge/license-MIT-blue.svg
    :target: https://pypi.python.org/pypi/fanfou-cli

.. image:: https://badges.gitter.im/fanfou-cli2/Lobby.svg
    :target: https://gitter.im/fan-van/Lobby?utm_source=badge&utm_medium=badge&utm_campaign=pr-badge&utm_content=body_badge

Example
=======

.. code-block:: python

    from van import Fan, Config


    # 1. Subclass the ``Config`` class and offer your configs
    class MyConfig(Config):
        consumer_key = 'xxxx'
        consumer_secret = 'xxxx'


    # 2. Instancialize the ``Fan`` class
    me = Fan.get(MyConfig())
    # 3. call methods of ``me``
    me.update_status('你好啊，李银河！')
