from countdown.perms import can_manage, can_query, is_astrbot_admin


class _Event:
    def __init__(self, uid: str, *, admin=False, role="member"):
        self._uid = uid
        self._admin = admin
        self.message_obj = type("Msg", (), {"sender": type("S", (), {"role": role})()})()

    def get_sender_id(self):
        return self._uid

    def is_admin(self):
        return self._admin


def test_astrbot_admin_always_manages():
    event = _Event("10001", admin=True)
    assert is_astrbot_admin(event, None) is True
    assert can_manage(event, context=None, mode="astrbot_admin", plugin_admin_ids=[]) is True


def test_plugin_admin_ids():
    event = _Event("20002")
    assert can_manage(event, context=None, mode="plugin_admin", plugin_admin_ids=["20002"]) is True
    assert can_manage(event, context=None, mode="plugin_admin", plugin_admin_ids=["1"]) is False


def test_group_admin_and_all():
    member = _Event("3", role="member")
    owner = _Event("4", role="owner")
    assert can_manage(member, context=None, mode="group_admin", plugin_admin_ids=[]) is False
    assert can_manage(owner, context=None, mode="group_admin", plugin_admin_ids=[]) is True
    assert can_manage(member, context=None, mode="all", plugin_admin_ids=[]) is True


def test_query_permission():
    member = _Event("3")
    assert (
        can_query(member, context=None, allow_all=True, mode="astrbot_admin", plugin_admin_ids=[])
        is True
    )
    assert (
        can_query(member, context=None, allow_all=False, mode="astrbot_admin", plugin_admin_ids=[])
        is False
    )
