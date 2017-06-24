API Reference
=============

Config
------

.. autoclass:: van.Config
   :members:
   :undoc-members:


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