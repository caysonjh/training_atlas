from app.services.webhooks import accepts_create_activity, event_key_for


def test_event_key_is_stable_for_duplicate_delivery():
    event = {
        "subscription_id": 123,
        "object_type": "activity",
        "object_id": 456,
        "aspect_type": "create",
        "event_time": 789,
    }
    assert event_key_for(event) == "123:activity:456:create:789"


def test_only_create_activity_events_are_enqueued():
    assert accepts_create_activity({"object_type": "activity", "aspect_type": "create"})
    assert not accepts_create_activity({"object_type": "activity", "aspect_type": "update"})
    assert not accepts_create_activity({"object_type": "athlete", "aspect_type": "create"})
