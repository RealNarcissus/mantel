"""Dynamic access to the Gemini protocol descriptors recovered from `agy`.

All message types and RPC method paths come from FileDescriptorProtos extracted
from the shipped binary (PROTOCOL_SPEC.md §2-4). Nothing here is guessed.
"""
from google.protobuf.message_factory import GetMessageClass

from tools.protocol_probes.bootstrap import build_pool

_pool = None
_provenance = None


def pool():
    global _pool, _provenance
    if _pool is None:
        _pool, _provenance, _real, _notes = build_pool()
    return _pool


def provenance():
    pool()
    return dict(_provenance)


def message(name):
    """Dynamic message class for a fully-qualified type name."""
    return GetMessageClass(pool().FindMessageTypeByName(name))


def method_path(package, service, method):
    """gRPC full method path, e.g. /google.internal.cloud.code.v1internal.CloudCode/StreamGenerateChat"""
    return f"/{package}.{service}/{method}"


def fields(name):
    """(number, name, kind, presence, type_name) for every field of a message."""
    desc = message(name).DESCRIPTOR

    def presence(f):
        if f.is_repeated:
            return "repeated"
        return "optional" if f.has_presence else "implicit"

    def type_ref(f):
        target = f.message_type if f.message_type is not None else f.enum_type
        return target.full_name if target is not None else ""

    return [(f.number, f.name, f.type, presence(f), type_ref(f))
            for f in desc.fields]
