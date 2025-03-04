import logging
import os
from datetime import datetime
from datetime import timezone
from enum import Enum

from marshmallow import fields
from marshmallow import Schema

from app.logging import threadctx
from app.models import TagsSchema
from app.queue.metrics import event_serialization_time
from app.serialization import serialize_canonical_facts

logger = logging.getLogger(__name__)


EventType = Enum("EventType", ("created", "updated", "delete"))


def hostname():
    return os.uname().nodename


# Schemas
class SerializedHostSchema(Schema):
    id = fields.UUID()
    display_name = fields.Str()
    ansible_host = fields.Str()
    account = fields.Str(required=True)
    insights_id = fields.Str()
    subscription_manager_id = fields.Str()
    satellite_id = fields.Str()
    fqdn = fields.Str()
    bios_uuid = fields.Str()
    ip_addresses = fields.List(fields.Str())
    mac_addresses = fields.List(fields.Str())
    provider_id = fields.Str()
    provider_type = fields.Str()
    created = fields.Str()
    updated = fields.Str()
    stale_timestamp = fields.Str()
    stale_warning_timestamp = fields.Str()
    culled_timestamp = fields.Str()
    reporter = fields.Str()
    tags = fields.List(fields.Nested(TagsSchema))
    system_profile = fields.Dict()
    per_reporter_staleness = fields.Dict()


class HostEventMetadataSchema(Schema):
    request_id = fields.Str(required=True)


class HostCreateUpdateEvent(Schema):
    type = fields.Str()
    host = fields.Nested(SerializedHostSchema())
    timestamp = fields.DateTime(format="iso8601")
    platform_metadata = fields.Dict()
    metadata = fields.Nested(HostEventMetadataSchema())


class HostDeleteEvent(Schema):
    id = fields.UUID()
    timestamp = fields.DateTime(format="iso8601")
    type = fields.Str()
    account = fields.Str()
    insights_id = fields.Str()
    request_id = fields.Str()
    metadata = fields.Nested(HostEventMetadataSchema())


def message_headers(event_type, insights_id):
    return {
        "event_type": event_type.name,
        "request_id": threadctx.request_id,
        "producer": hostname(),
        "insights_id": insights_id,
    }


def host_create_update_event(event_type, host, platform_metadata=None):
    return (
        HostCreateUpdateEvent,
        {
            "timestamp": datetime.now(timezone.utc),
            "type": event_type.name,
            "host": host,
            "platform_metadata": platform_metadata,
            "metadata": {"request_id": threadctx.request_id},
        },
    )


def host_delete_event(event_type, host):
    return (
        HostDeleteEvent,
        {
            "timestamp": datetime.now(timezone.utc),
            "type": event_type.name,
            "id": host.id,
            **serialize_canonical_facts(host.canonical_facts),
            "account": host.account,
            "request_id": threadctx.request_id,
            "metadata": {"request_id": threadctx.request_id},
        },
    )


EVENT_TYPE_MAP = {
    EventType.created: host_create_update_event,
    EventType.updated: host_create_update_event,
    EventType.delete: host_delete_event,
}


def build_event(event_type, host, **kwargs):
    with event_serialization_time.labels(event_type.name).time():
        build = EVENT_TYPE_MAP[event_type]
        schema, event = build(event_type, host, **kwargs)
        result = schema().dumps(event)
        return result


def operation_results_to_event_type(results):
    return EventType[results.name]
