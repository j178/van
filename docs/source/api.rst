API Reference
=============

Config
------
.. py:class:: van.Config

   .. py:attribute:: consumer_key

      申请应用之后获得

   .. py:attribute:: consumer_secret

      申请应用之后获得

   .. py:attribute:: auth_type

      授权类型：xauth 或者 oauth

   .. py:attribute:: save_token

      是否保存授权后获得的 token，下次使用无需重新授权

   .. py:attribute:: save_path

      token 的保存位置。默认为当前目录下的 `van.cfg` 文件

   .. py:attribute:: access_token

      如果你已经获得了 token, 可以直接填写在这里。

   .. py:attribute:: xauth_username

      使用 xauth 授权方式时需要的用户名。

   .. py:attribute:: xauth_password

      使用 xauth 授权方式时需要的密码。

   .. warning::

      建议用户名和密码，和 token 都不要直接写在代码中，可以使用环境变量提供或者在程序运行时手动输入。

   .. py:attribute:: auto_auth

      如果使用 oauth 认证方式，是否自动在本地开启服务器等待授权。

   .. py:attribute:: repost_style_left

      转发消息的样式，左边部分。

   .. py:attribute:: repost_style_right

      转发消息的样式，右边部分。

   .. py:attribute:: timeout

      网络请求的 timeout。

   .. py:attribute:: fail_sleep_time

      API 请求失败后的 sleep 时间。


Fan
----

.. autoclass:: van.Fan
   :members:

User
----

.. autoclass:: van.User
   :members:


Status
------

.. autoclass:: van.Status
   :members:


Timeline
--------

.. autoclass:: van.Timeline
   :members:
   :special-members: __iter__, __len__


Base
----

.. autoclass:: van.Base
   :members:

Stream
------

.. autoclass:: van.Stream
   :members:

Event
-----

.. autoclass:: van.Event
   :members:

Listener
--------

监听器对象

.. py:class:: van.Listener(on, func, ttl=None)

   .. attribute:: on

       此监听器监听的事件类型，可用的值均为 :class:`Event` 类中的属性，如 :attr:`Event.MESSAGE` 表示监听消息相关的事件。
       多个事件可以使用 `|` 连接，组合为一个事件，如 `Event.MESSAGE | Event.FREIENDS`

   .. attribute:: func

       一个可调用对象，接受一个 :class:`Event` 对象，当 `on` 中监听的事件发生时被调用。

   .. attribute:: ttl

       计算机术语，Time To Live。在这里表示此监听器最多工作的次数，超过次数之后就不再调用此监听器。


Misc
----

.. autodata:: van.Photo