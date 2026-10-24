#!/usr/bin/env python3
"""Linux Gemini client bootstrap: load the recovered protocol descriptors.

Builds a google.protobuf DescriptorPool from the FileDescriptorProtos extracted
from `agy` (see PROTOCOL_SPEC.md §6). Missing dependency files become shells;
unresolved type references are satisfied by ONE union shell per package built
up front (so no symbol is ever defined twice — upb aborts on duplicates);
content conflicts reduce to empty shells. Real service definitions always win.

Usage: python3 client/bootstrap.py
"""
import glob
import os
import re
import sys
from collections import defaultdict
from pathlib import Path

from google.protobuf import (
    any_pb2,
    descriptor_pb2,
    duration_pb2,
    empty_pb2,
    field_mask_pb2,
    struct_pb2,
    text_format,
    timestamp_pb2,
    wrappers_pb2,
)
from google.protobuf.descriptor_pb2 import (
    DescriptorProto,
    EnumDescriptorProto,
    EnumValueDescriptorProto,
    FileDescriptorProto,
)
from google.protobuf.descriptor_pool import DescriptorPool
from google.protobuf.message_factory import GetMessageClass

HERE = os.path.dirname(os.path.abspath(__file__))
PROTO_DIR = os.path.join(HERE, "..", "protos")

WELL_KNOWN = [any_pb2, descriptor_pb2, duration_pb2, empty_pb2,
              field_mask_pb2, struct_pb2, timestamp_pb2, wrappers_pb2]


def package_of(proto_name):
    return proto_name.rsplit("/", 1)[0].replace("/", ".")


def refs_of(d):
    out = {}

    def msg_refs(m):
        for f in m.field:
            if f.type_name:
                name = f.type_name.lstrip(".")
                out[name] = out.get(name, True) and (f.type == 14)
        for nt in m.nested_type:
            msg_refs(nt)
        for ext in m.extension:
            out[ext.extendee.lstrip(".")] = False
            if ext.type_name:
                name = ext.type_name.lstrip(".")
                out[name] = out.get(name, True) and (ext.type == 14)

    for m in d.message_type:
        msg_refs(m)
    for ext in d.extension:
        out[ext.extendee.lstrip(".")] = False
        if ext.type_name:
            name = ext.type_name.lstrip(".")
            out[name] = out.get(name, True) and (ext.type == 14)
    for svc in d.service:
        for m in svc.method:
            out[m.input_type.lstrip(".")] = False
            out[m.output_type.lstrip(".")] = False
    return out


def defined_names(d):
    names = set()

    def walk(m, prefix):
        full = prefix + m.name
        names.add(full)
        for nt in m.nested_type:
            walk(nt, full + ".")
        for et in m.enum_type:
            names.add(full + "." + et.name)

    for m in d.message_type:
        walk(m, d.package + "." if d.package else "")
    for et in d.enum_type:
        names.add((d.package + "." if d.package else "") + et.name)
    pkg = d.package + "." if d.package else ""
    for s in d.service:
        names.add(pkg + s.name)
    for x in d.extension:
        names.add(pkg + x.name)
    return names


def sanitize_against(d, taken):
    """Strip definitions whose full names already exist (upb aborts on dupes)."""
    pkg = d.package + "." if d.package else ""

    def strip_msgs(msgs, prefix):
        keep = []
        for m in msgs:
            full = prefix + m.name
            if full in taken:
                continue
            strip_msgs(m.nested_type, full + ".")
            ek = [e for e in m.enum_type if full + "." + e.name not in taken]
            del m.enum_type[:]
            m.enum_type.extend(ek)
            keep.append(m)
        del msgs[:]
        msgs.extend(keep)

    strip_msgs(d.message_type, pkg)

    e_keep = [e for e in d.enum_type if pkg + e.name not in taken]
    del d.enum_type[:]
    d.enum_type.extend(e_keep)

    s_keep = [s for s in d.service if pkg + s.name not in taken]
    del d.service[:]
    d.service.extend(s_keep)

    x_keep = [x for x in d.extension if pkg + x.name not in taken]
    del d.extension[:]
    d.extension.extend(x_keep)


def insert_type(msgs, enums, rel, is_enum, counter):
    parts = rel.split(".")
    for part in parts[:-1]:
        nxt = next((m for m in msgs if m.name == part), None)
        if nxt is None:
            nxt = DescriptorProto(name=part)
            msgs.append(nxt)
        msgs, enums = nxt.nested_type, nxt.enum_type
    leaf = parts[-1]
    if is_enum:
        if not any(e.name == leaf for e in enums):
            e = EnumDescriptorProto(name=leaf)
            # proto2 enum values share package scope: names must be unique.
            e.value.append(EnumValueDescriptorProto(name=f"STUB_{next(counter)}", number=0))
            enums.append(e)
    else:
        if not any(m.name == leaf for m in msgs):
            msgs.append(DescriptorProto(name=leaf))


def sanitize_msg(m):
    def uniq(lst):
        seen, out = set(), []
        for x in lst:
            if x.name in seen:
                continue
            seen.add(x.name)
            out.append(x)
        del lst[:]
        lst.extend(out)

    for nt in m.nested_type:
        sanitize_msg(nt)
    uniq(m.nested_type)
    uniq(m.enum_type)
    for et in m.enum_type:
        seen, vals = set(), []
        for v in et.value:
            if v.name in seen:
                continue
            seen.add(v.name)
            vals.append(v)
        del et.value[:]
        et.value.extend(vals)


def sanitize_file(d):
    """Extraction artifacts: duplicate names abort upb; edition/public_dep
    must be consistent. Normalize before the descriptor touches the pool."""
    def uniq(lst):
        seen, out = set(), []
        for x in lst:
            if x.name in seen:
                continue
            seen.add(x.name)
            out.append(x)
        del lst[:]
        lst.extend(out)

    for m in d.message_type:
        sanitize_msg(m)
    uniq(d.message_type)
    uniq(d.enum_type)
    uniq(d.service)
    uniq(d.extension)
    for svc in d.service:
        uniq(svc.method)
    for et in d.enum_type:
        seen, vals = set(), []
        for v in et.value:
            if v.name in seen:
                continue
            seen.add(v.name)
            vals.append(v)
        del et.value[:]
        et.value.extend(vals)
    if d.syntax != "editions" and d.HasField("edition"):
        d.ClearField("edition")

    def clear_features(opts):
        try:
            if opts.HasField("features"):
                opts.ClearField("features")
        except Exception:
            pass

    def clear_all_features(m):
        clear_features(m.options)
        for f in m.field:
            clear_features(f.options)
        for nt in m.nested_type:
            clear_all_features(nt)
        for e in m.enum_type:
            clear_features(e.options)
            for v in e.value:
                clear_features(v.options)

    clear_features(d.options)
    for m in d.message_type:
        clear_all_features(m)
    for e in d.enum_type:
        clear_features(e.options)
        for v in e.value:
            clear_features(v.options)
    for s in d.service:
        clear_features(s.options)
        for meth in s.method:
            clear_features(meth.options)
    for x in d.extension:
        clear_features(x.options)
    for attr in ("public_dependency", "weak_dependency"):
        idxs = [i for i in getattr(d, attr) if i < len(d.dependency)]
        del getattr(d, attr)[:]
        getattr(d, attr).extend(idxs)


def build_pool():
    pool = DescriptorPool()
    added = {}
    for mod in WELL_KNOWN:
        pool.AddSerializedFile(mod.DESCRIPTOR.serialized_pb)
        added[mod.DESCRIPTOR.name] = "builtin"

    files = sorted(glob.glob(os.path.join(PROTO_DIR, "*.textproto")))
    real, own_defined = {}, set()
    for path in files:
        d = FileDescriptorProto()
        text_format.Parse(open(path).read(), d)
        sanitize_file(d)
        real[d.name] = d
        own_defined |= defined_names(d)

    notes = []

    def exists(sym):
        for finder in (pool.FindMessageTypeByName, pool.FindEnumTypeByName,
                       pool.FindServiceByName, pool.FindFileByName):
            try:
                finder(sym)
                return True
            except Exception:
                pass
        return False

    taken = set()

    def add_new(d, kind):
        if d.name in added:
            return False
        if kind == "real":
            sanitize_against(d, taken)
        try:
            pool.Add(d)
        except Exception:
            return False
        added[d.name] = kind
        taken.update(defined_names(d))
        return True

    stubbed_syms = set()
    stub_counter = iter(range(100_000))
    tier2 = False
    PROTECT = {
        "google/internal/cloud/code/v1internal/cloudcode.proto",
        "google/internal/cloud/code/v1internal/jetski_service.proto",
        "google/internal/cloud/code/v1internal/prediction_service.proto",
        "learning/genai/api/interactions/proto/interaction_service.proto",
        "learning/genai/api/interactions/proto/external_events.proto",
        "third_party/jetski/product_api_pb/v1/conversation_service.proto",
        "third_party/jetski/product_api_pb/v1/content.proto",
        "third_party/gemini_coder/proto/service.proto",
    }
    protected_syms = set()
    for n, d in real.items():
        if n in PROTECT:
            protected_syms |= defined_names(d)

    def union_type_shells(allow_stuck_owned):
        needed = {}
        for d in real.values():
            for sym, is_enum in refs_of(d).items():
                if sym in stubbed_syms or exists(sym) or sym in protected_syms:
                    continue
                if sym in own_defined and not allow_stuck_owned:
                    continue
                if sym in needed:
                    needed[sym] = needed[sym] and is_enum  # message wins conflicts
                else:
                    needed[sym] = is_enum
        # A name that is a strict prefix of another needed name is a package
        # namespace misread as a type ref: drop the prefix, keep the leaves.
        all_names = set(needed)
        for sym in list(needed):
            if any(other != sym and other.startswith(sym + ".") for other in all_names):
                needed.pop(sym, None)
        by_pkg = defaultdict(list)
        for sym, is_enum in needed.items():
            pkg = sym.rsplit(".", 1)[0] if "." in sym else ""
            by_pkg[pkg].append((sym, is_enum))
        made = 0
        for pkg, items in sorted(by_pkg.items()):
            base = f"__stub_{re.sub(r'[^A-Za-z0-9]', '_', pkg)}"
            fname, i = base + ".proto", 1
            while fname in added:
                fname = f"{base}_{i}.proto"
                i += 1
            d = FileDescriptorProto(name=fname,
                                    package=pkg, syntax="proto2")
            counter = stub_counter
            for sym, is_enum in sorted(items):
                insert_type(d.message_type, d.enum_type,
                            sym[len(pkg) + 1:] if pkg else sym, is_enum, counter)
            if add_new(d, "stub"):
                made += 1
                stubbed_syms.update(sym for sym, _ in items)
            else:
                notes.append(f"shell rejected: {d.name}")
        return made

    for _ in range(400):
        progress = False
        for n, d in list(real.items()):
            if add_new(d, "real"):
                del real[n]
                progress = True
        if not real:
            break
        missing = {dep for d in real.values() for dep in d.dependency
                   if dep not in added and dep not in real}
        for dep in sorted(missing):
            if add_new(FileDescriptorProto(name=dep, package=package_of(dep),
                                           syntax="proto2"), "stub"):
                progress = True
        if progress:
            continue
        if union_type_shells(tier2):
            continue
        if not tier2:
            tier2 = True
            continue
        # Phantom alias edges can leave files mutually blocked: as a last resort,
        # sacrifice one non-contract member so its dependents can load real.
        if real:
            victim = next((n for n in sorted(real)
                           if n not in PROTECT and n not in added), None)
            if victim is not None:
                v = real[victim]
                shell = FileDescriptorProto(name=v.name, package=v.package, syntax="proto2")
                shell.message_type.add(name=f"_Placeholder{len(added)}")
                if add_new(shell, "empty"):
                    notes.append(f"stall -> placeholder shell: {victim}")
                    del real[victim]
                    continue
        for n, d in sorted(real.items()):
            sanitize_against(d, taken)
            try:
                pool.Add(d)
                added[n] = "real"
                taken.update(defined_names(d))
                del real[n]
                progress = True
                break
            except Exception as e:
                msg = str(e)
                if "duplicate symbol" in msg or "duplicate file name" in msg:
                    if n in PROTECT:
                        notes.append(f"conflict on protected {n}: {msg[:80]}")
                        continue
                    if add_new(FileDescriptorProto(name=d.name, package=d.package,
                                                   syntax=d.syntax), "empty"):
                        notes.append(f"content conflict -> empty shell: {n}")
                        del real[n]
                        progress = True
                        break
                notes.append(f"unresolved {n}: {msg[:110]}")
        if not progress:
            break

    return pool, added, real, notes


def main():
    pool, added, real, notes = build_pool()
    real_loaded = sum(1 for v in added.values() if v in ("real", "builtin"))
    print(f"pool: {len(added)} files (real/builtin: {real_loaded}, "
          f"shells/stubs: {len(added) - real_loaded})")
    print(f"real descriptors still unresolved: {len(real)}")
    for n in sorted(real):
        print(f"  unresolved: {n}")
    if notes:
        events = [e for e in notes if "stall" in e or "conflict" in e or "rejected" in e]
        print(f"placeholder-shelled during resolution: {len(events)}")
        for e in events:
            print(f"  {e}")

    count = 0
    for path in sorted(Path.cwd().rglob("*.proto")):
        d = FileDescriptorProto()
        try:
            text_format.Parse(path.read_text(errors="replace"), d)
        except Exception:  # noqa: BLE001 - a probe, not a product path
            continue
        for svc in d.service:
            count += len(svc.method)
    print(f"RPCs defined in descriptors: {count}")

    cls = GetMessageClass(pool.FindMessageTypeByName("jetski.product.v1.CreateConversationRequest"))
    msg = cls(title="linux-client-bootstrap")
    wire = msg.SerializeToString()
    print(f"smoke OK: {cls.__name__} serialized {len(wire)} bytes: {wire.hex()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
