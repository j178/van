Quick Start & Installation
==========================

Van [#释名]_ 是一个 `Python`_ 编写的 `饭否`_ `SDK`_ ，基于 `饭否官方API`_ 。Van 对官方 API 做了合理的抽象和封装，开发者可以使用简洁优雅的接口，轻松操作用户在饭否上的数据。

Van 计划添加一些数据获取接口和任务调度功能，使饭否 Bot 开发更简单。

Quick Start Demo
----------------

下面是一个极简的使用 Demo, 附有简单的注释， 具体的使用我们会在后文详细说明。

.. code-block:: python

    from van import Fan

    # 实例化 Fan 类
    fan = Fan(consumer_key, consumer_secret)

    # 使用 xauth 授权方式
    fan.xauth(username,password)

    # 或者使用 oauth 授权方式
    # url = fan.authorization_url()
    # 访问此 url 并复制 PIN 码 （或重定向后的 URL）
    # fan.oauth(pin_code)

    # 调用 API
    fan.update_status('你好啊，李银河！')


Installation
------------

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
---------

要使用 van 你还需要在饭否中申请一个应用：

#. 在 http://fanfou.com/apps 中创建新应用
#. 应用名称、主页、描述等信息可以随意填写
#. 记录下 `Consumer Key` 和 `Consumer Secret`


.. _Python: https://www.python.org
.. _饭否: http://www.fanfou.com
.. _饭否官方API: https://github.com/FanfouAPI/FanFouAPIDoc/wiki
.. _SDK: https://en.wikipedia.org/wiki/Software_development_kit
.. _pip: https://pypi.python.org/pypi/pip

.. rubric:: P.S.

.. [#释名] `van` 是 `fan` 在舌头打结时的发音