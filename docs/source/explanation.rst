Explanation
===========

总体设计
---------

van 的所有功能分布在五个类中, `Fan`、 `Config`、 `User`、 `Status` 和 `Timeline`.

van 的所有 API 调用均返回一个二元组 (bool, value)。
第一个元素如果为 `True`, 则表示调用成功，那么第二个元素为调用的结果；
如果第一个元素为 `False`，表示调用失败，那么第二个元素表示失败的原因。
所以，调用 API 之后一定要先判断第一个元素，再决定是否使用第二个元素。通常的使用方式为::
    _, rv = me.follow(user)
    if _:
        # 使用 rv 做一些事

User - 猜猜我是谁？
---------------------

`User` 是对 API 接口返回的 user 对象的封装，可以通过它访问用户的属性，比如 :attr:`User.id`, :attr:`User.name`, :attr:`User.location` 等。
它还有一些所有用户共有的一些操作，比如获取用户的消息列表 :meth:`User.statuses` 、关注者列表 :meth:`User.followers` 、好友列表 :meth:`User.friends` 等。

=================   ==================================
timeline            返回此用户看到的时间线
statues             返回此用户已发送的消息
photos              浏览此用户发送的图片
followers           返回此用户的关注者
friends             返回此用户的关注对象
favorites           浏览此用户收藏的消息
relationship        返回此用户与 other 的关系
=================   ==================================

Fan - 我才是老大！
--------------------

`Fan` 是 `User` 的子类，所以它有 `User` 的所有属性和操作，但它还有一些需要授权才能进行的操作，比如更新状态 :meth:`Fan.update_status`、关注好友 :meth:`Fan.follow` 等。
它也是整个程序的开始点和其他API访问的入口点。程序需要先实例化一个 `Fan` 对象，并为其提供一个 `Config` 对象，然后通过 `Fan` 对象访问其他 API。

================== =================================
draft_box          显示发送失败的消息列表
mentions           返回提到当前用户的20条消息
replies            返回当前用户收到的回复
blocked_users      返回黑名单上用户列表
public_timeline    返回公共时间线
follow_requests    返回请求关注当前用户的列表
update_status()    更新状态
follow()           关注用户
unfollow()         取消关注用户
accept_follower()  接受关注请求
deny_follower()    拒绝关注请求
block()            屏蔽用户
unblock()          解除屏蔽
is_blocked()       检查是否屏蔽用户
================== =================================

Config - 我该怎么做？
-----------------------

:class:`~van.Config` 顾名思义，是用来控制程序行为的类。van 提供的 Config 定义了一组默认配置，其中只有 `consumer_key` 和 `consumer_secret` 是必须提供的，
其他的配置都可以使用默认值。

================  =========================================
consumer_key      申请应用后获取
consumer_secret   申请应用后获取
auth_type         授权类型。默认为 xauth, 需要提供 xauth_username 和 xauth_password， 即用户名和密码。

                  可选为 oauth, 这种不要用户名和密码，比较安全，但是一些手动操作，无法自动完成。

                  推荐在不方便手动操作的场景使用 xauth, 在一般场合使用 oauth。
save_token        van 获取 Access Token 之后是否保存在文件中，下次启动无需重新授权。保存路径由 save_path 指定。
save_path         Access Token 及其他配置文件的保存路径，默认为当前路径。
access_token      如果你已经获取了 Access Token，则可以直接填写，可以省略其他授权过程。
xauth_username    auth_type 为 xauth 时填写
xauth_password    auth_type 为 xauth 时填写
auto_auth         auth_type 为 oauth 时是否在本地启动服务器自动验证，否则需要手动粘贴授权后跳转的链接。默认为 True。
================  =========================================

Status - 我的实例最多~
-------------------------

没错，`Status` 是程序运行时创建最多的对象。 它与 `User` 一样，是对 API 数据的封装，但是它上面也部署了一些符合语义的方法，比如 回复消息 :meth:`Status.reply`、转发消息 :meth:`Status.repost`、
收藏消息 :meth:`Status.favorite` (是不是挺像在御饭中左滑消息时的操作？)

================    ==================================
photo               :class:`~van.Photo` 对象，拥有 url, largeurl, imageurl, thumburl, originurl, type 属性
user                :class:`~van.User` 对象，此消息的作者
context             按照时间先后顺序显示消息上下文
send()              发送此消息
delete()            删除此消息
reply()             回复这条消息
repost()            转发这条消息
favorite()          收藏此消息
unfavorite()        取消收藏此消息
================    ==================================

Timeline - 天生优雅
-----------------------

Timeline 即时间线，或者说一组按时间排序的 `Status` 的列表： [ 最新的消息, ..., 稍旧的消息 ]

在原始 API 中，我们为了获取一段时间内的时间线，需要提供 `since_id` 和 `max_id` 两个参数来控制时间线的区间，我们需要经常记录并更新这两个值，比较麻烦。

在 Timeline 的实现中，van 将时间线模拟成一个文件对象，内部维护一个可用的消息数组，一个游标表示当前消息在数组中的位置。
调用 `read()` 方法，向后移动游标，返回一个消息数组，表示读取了一部分消息。

最神奇的地方在于，如果内部数组被消耗完了， Timeline 会自动获取消息填充。所以，完全可以将 Timeline 看作是一个无穷的数组，不用去关心 `since_id`，`max_id` 等问题，也不用手动获取新的状态，
只要像数组一样随意读取、遍历即可。

`User`、`Fan` 中符合 Timeline 特征的都是 Timeline 对象。

============= ========================
\__call__()   调用内部 `_fetch` 方法获取数据。

              可以自己提供 `since_id`, `max_id` 和 `count` 参数，获取的结果不加入内部数组。
\__iter__()   可以在 for 循环中使用此对象
tell()        返回当前游标的位置
rewind()      获取最新的状态插入到时间线的头部，并将指针置为0（指向最新的状态）
seek()        移动游标的位置
read()        从当前游标位置处往后读取消息
============= ========================

Base - 背后的大佬
----------------------

`Base` 是 `User`、`Fan` 和 `Status` 的基类，主要提供两个功能：

1. 对象缓存，ID 相同的对象只会创建一次
2. 自动请求 API 填充对象

为了使用对象缓存功能，创建 `User`、`Fan` 和 `Status` 实例都需要使用其 `get()` 方法，而不是直接调用构造函数，这一点需要注意。