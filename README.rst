Van - Fanfou SDK
################

.. image:: https://travis-ci.org/j178/van.svg?branch=master
    :target: https://travis-ci.org/j178/van

.. image:: https://readthedocs.org/projects/van/badge/?version=latest
    :target: http://van.readthedocs.io/zh/latest/?badge=latest
    :alt: Documentation Status

.. image:: https://badge.fury.io/py/van.svg
    :target: https://pypi.python.org/pypi/van

.. image:: https://img.shields.io/badge/python-3.5-blue.svg
    :target: https://pypi.python.org/pypi/fanfou-cli

.. image:: https://img.shields.io/badge/license-MIT-blue.svg
    :target: https://pypi.python.org/pypi/fanfou-cli

.. image:: https://badges.gitter.im/fanfou-cli2/Lobby.svg
    :target: https://gitter.im/fan-van/Lobby?utm_source=badge&utm_medium=badge&utm_campaign=pr-badge&utm_content=body_badge


详细文档请前往 ➔ `Readthedocs <http://van.readthedocs.io>`_


Example
=======

.. code-block:: python

    from van import Fan

    fan = Fan(consumer_key, consumer_secret)
    fan.xauth(username,password)
    # or use oauth
    # url = fan.authorization_url()
    # visit the authorization url and copy the redirect url
    # fan.oauth(redirect url)
    fan.update_status('你好啊，李银河！')

Installation
============

van 只支持 Python3, 请前往官网下载安装 Python 3.5 以上版本。

*如果你是开发者，你也可以帮助我兼容 Python2*

之后可以使用 `pip`_ 安装:

.. code-block:: shell

    pip3 install van

或者下载源码安装:

.. code-block:: shell

    git clone https://github.com/j178/van
    cd van
    pip3 install . --user

申请应用
==========

要使用 van 你还需要在饭否中申请一个应用：

#. 在 http://fanfou.com/apps 中创建新应用
#. 应用名称、主页、描述等信息可以随意填写
#. 记录下 `Consumer Key` 和 `Consumer Secret`


.. _Python: https://www.python.org
.. _饭否: http://www.fanfou.com
.. _饭否官方API: https://github.com/FanfouAPI/FanFouAPIDoc/wiki
.. _SDK: https://en.wikipedia.org/wiki/Software_development_kit
.. _pip: https://pypi.python.org/pypi/pip