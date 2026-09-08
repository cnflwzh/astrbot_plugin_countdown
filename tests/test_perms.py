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

    def get_group_id(self):
        return "123"


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


def test_string_admin_id_is_not_split_into_digits():
    assert not can_manage(_Event("2"), context=None, mode="plugin_admin", plugin_admin_ids="20002")
    assert can_manage(_Event("20002"), context=None, mode="plugin_admin", plugin_admin_ids="20002")


def test_admin_fallback_uses_current_session_config():
    event = _Event("10001")
    event.unified_msg_origin = "qq:GroupMessage:2_10001"

    class Context:
        def get_config(self, umo=None):
            return {"admins_id": [] if umo == event.unified_msg_origin else ["10001"]}

    assert not is_astrbot_admin(event, Context())


def test_legacy_admin_config_and_malformed_ids():
    class Context:
        def get_config(self):
            return {"admins_id": ["10001"]}

    assert is_astrbot_admin(_Event("10001"), Context())
    for ids in (None, {"2": True}, True):
        assert not can_manage(_Event("2"), context=None, mode="plugin_admin", plugin_admin_ids=ids)


def test_private_sender_role_does_not_grant_group_admin():
    event = _Event("4", role="owner")
    event.get_group_id = lambda: ""
    assert not can_manage(event, context=None, mode="group_admin", plugin_admin_ids=[])
