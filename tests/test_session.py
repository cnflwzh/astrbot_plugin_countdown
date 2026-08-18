from countdown.session import group_id, session_key


class _Msg:
    def __init__(self, group: str):
        self.group_id = group


class _Event:
    def __init__(self, *, platform="bot-qq", group="123456", umo="bot-qq:GroupMessage:123456_999"):
        self.unified_msg_origin = umo
        self.message_obj = _Msg(group)
        self._platform = platform
        self._group = group

    def get_platform_id(self):
        return self._platform

    def get_platform_name(self):
        return "aiocqhttp"

    def get_group_id(self):
        return self._group


def test_session_key_uses_group_not_unique_session():
    event = _Event()
    assert session_key(event) == "bot-qq:GroupMessage:123456"
    assert group_id(event) == "123456"


def test_private_session_falls_back_to_umo():
    event = _Event(group="", umo="bot-qq:FriendMessage:10001")
    event.message_obj.group_id = ""
    assert session_key(event) == "bot-qq:FriendMessage:10001"
