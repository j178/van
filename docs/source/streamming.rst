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

    thread = s.run()
    thread.join()