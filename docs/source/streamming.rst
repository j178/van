Streamming API
==============

Demo
----
::

    from van import Config, Fan, Stream, Event

    class MyConfig(Config):
        consumer_key = 'xxxx'
        consumer_secret = 'xxx'

    Fan.setup(MyConfig())
    s = Stream()

    @s.on(Event.MESSAGE)
    def handle_message(event):
        print(event.object.text)

    @s.on(Event.USER | Event.MESSAGE_CREATE)
    def handle_something(event):
        do_something(event)

    @s.on(Event.ALL)
    def handle_all(event):
        print(event.object)

    if __name__ == '__main__':
        s.start()
