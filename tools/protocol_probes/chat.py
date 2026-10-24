"""Chat spine for the Linux Gemini client.

Method paths and message types are recovered contracts (PROTOCOL_SPEC.md §2-4):
  - /google.internal.cloud.code.v1internal.CloudCode/StreamGenerateChat
    (GenerateChatRequest -> stream GenerateChatResponse)
  - /genai.InteractionService/CreateInteractionBidiStream
    (stream ClientEventBatch <-> stream ServerEventBatch)

Live calls need a Google OAuth token (client/auth.py); `selfcheck` runs offline.
"""
import argparse
import json
import shutil
import subprocess
import sys

import grpc

from tools.protocol_probes import auth, gemini_proto

CLOUDCODE_HOST = "cloudcode-pa.googleapis.com:443"
INTERACTION_HOST = "cloudcode-pa.googleapis.com:443"

GENERATE_CHAT_REQUEST = "google.internal.cloud.code.v1internal.GenerateChatRequest"
GENERATE_CHAT_RESPONSE = "google.internal.cloud.code.v1internal.GenerateChatResponse"
CLIENT_EVENT_BATCH = "genai.ClientEventBatch"
SERVER_EVENT_BATCH = "genai.ServerEventBatch"

STREAM_GENERATE_CHAT = gemini_proto.method_path(
    "google.internal.cloud.code.v1internal", "CloudCode", "StreamGenerateChat")
CREATE_INTERACTION_BIDI = gemini_proto.method_path(
    "genai", "InteractionService", "CreateInteractionBidiStream")


def _ser(msg):
    return msg.SerializeToString()


def _de(cls):
    return lambda buf: cls.FromString(buf)


def stream_generate_chat(request, token, host=CLOUDCODE_HOST):
    """Server-streaming chat: yields GenerateChatResponse."""
    resp_cls = gemini_proto.message(GENERATE_CHAT_RESPONSE)
    with grpc.secure_channel(host, grpc.ssl_channel_credentials()) as ch:
        call = ch.unary_stream(
            STREAM_GENERATE_CHAT,
            request_serializer=_ser,
            response_deserializer=_de(resp_cls),
        )
        yield from call(request, metadata=auth.bearer(token))


def create_interaction_bidi_stream(events, token, host=INTERACTION_HOST):
    """Bidirectional interaction stream (ClientEventBatch in, ServerEventBatch out)."""
    in_cls = gemini_proto.message(CLIENT_EVENT_BATCH)
    out_cls = gemini_proto.message(SERVER_EVENT_BATCH)

    def requests():
        for ev in events:
            yield ev if isinstance(ev, in_cls) else in_cls.FromString(ev)

    with grpc.secure_channel(host, grpc.ssl_channel_credentials()) as ch:
        call = ch.stream_stream(
            CREATE_INTERACTION_BIDI,
            request_serializer=_ser,
            response_deserializer=_de(out_cls),
        )
        yield from call(requests(), metadata=auth.bearer(token))


def build_request(type_name, **values):
    """Build a dynamic message, setting only descriptor-declared fields."""
    cls = gemini_proto.message(type_name)
    msg = cls()
    for name, value in values.items():
        setattr(msg, name, value)  # AttributeError if the contract lacks it
    return msg


def build_chat_prompt(prompt, request_id="", project=""):
    """One chat turn as GenerateChatRequest.

    Field names verified against the recovered cloudcode.proto contract
    (selfcheck): user_message is the prompt, request_id/project optional.
    """
    return build_request(GENERATE_CHAT_REQUEST,
                         user_message=prompt,
                         request_id=request_id,
                         project=project)


def probe(token, host=CLOUDCODE_HOST):
    """Probe recovered endpoints with a token; report each one's verdict."""
    import urllib.error
    import urllib.request

    rows = []

    def rpc(label, path, req_type, _host=None, **fields):
        target = _host or host
        try:
            req = build_request(req_type, **fields)
            svc_name, meth = path.strip("/").split("/")
            out_type = gemini_proto.pool().FindServiceByName(
                svc_name).methods_by_name[meth].output_type.full_name
            resp_cls = gemini_proto.message(out_type)
        except Exception as e:
            rows.append((label, f"BUILD FAIL: {e}"))
            return
        try:
            with grpc.secure_channel(target, grpc.ssl_channel_credentials()) as ch:
                fn = ch.unary_unary(
                    path, request_serializer=_ser,
                    response_deserializer=_de(resp_cls))
                fn(req, timeout=20, metadata=auth.bearer(token))
            rows.append((label, "OK"))
        except grpc.RpcError as e:
            rows.append((label, f"{e.code().name} — {e.details()}"))

    rpc("StreamGenerateChat", STREAM_GENERATE_CHAT, GENERATE_CHAT_REQUEST,
        user_message="ping")
    rpc("LoadCodeAssist",
        gemini_proto.method_path("google.internal.cloud.code.v1internal",
                                 "CloudCode", "LoadCodeAssist"),
        "google.internal.cloud.code.v1internal.LoadCodeAssistRequest")
    rpc("GetUserInfo",
        gemini_proto.method_path("google.gca.aicode.v1main",
                                 "ManagementService", "GetUserInfo"),
        "google.gca.aicode.v1main.GetUserInfoRequest", name="users/me")
    rpc("FetchConfig",
        gemini_proto.method_path("google.gca.aicode.v1main",
                                 "ManagementService", "FetchConfig"),
        "google.gca.aicode.v1main.FetchConfigRequest")
    rpc("CreateInteraction",
        gemini_proto.method_path("genai", "InteractionService", "CreateInteraction"),
        "genai.CreateInteractionEvent")
    rpc("CreateInteraction@genai-host",
        gemini_proto.method_path("genai", "InteractionService", "CreateInteraction"),
        "genai.CreateInteractionEvent", _host="generativelanguage.googleapis.com:443")

    try:
        from google.protobuf.json_format import MessageToDict
        req = build_request(
            "google.internal.cloud.code.v1internal.LoadCodeAssistRequest")
        svc, meth = gemini_proto.method_path(
            "google.internal.cloud.code.v1internal", "CloudCode",
            "LoadCodeAssist").strip("/").split("/")
        out_type = gemini_proto.pool().FindServiceByName(
            svc).methods_by_name[meth].output_type.full_name
        fn = None
        with grpc.secure_channel(host, grpc.ssl_channel_credentials()) as ch:
            fn = ch.unary_unary(
                gemini_proto.method_path(
                    "google.internal.cloud.code.v1internal", "CloudCode",
                    "LoadCodeAssist"),
                request_serializer=_ser,
                response_deserializer=_de(gemini_proto.message(out_type)))
            out = fn(req, timeout=20, metadata=auth.bearer(token))
        detail = json.dumps(MessageToDict(out), default=str)
        rows.append(("LoadCodeAssist detail", detail[:700]))
    except Exception as e:
        rows.append(("LoadCodeAssist detail", f"{type(e).__name__}: {e}"))

    for label, url in [
            ("gemini-api /v1beta/models", "https://generativelanguage.googleapis.com/v1beta/models"),
            ("userinfo", "https://www.googleapis.com/oauth2/v2/userinfo")]:
        r = urllib.request.Request(url, headers={"authorization": f"Bearer {token}"})
        try:
            with urllib.request.urlopen(r, timeout=20) as resp:
                rows.append((label, f"HTTP {resp.status}"))
        except urllib.error.HTTPError as e:
            rows.append((label, f"HTTP {e.code} — {e.read().decode()[:140]}"))

    for label, status in rows:
        print(f"  {label:26s} {status}")
    return 0


def run_agy(prompt, model=None, effort=None, timeout=300):
    """Chat via the Antigravity CLI (agy): Pro-subscription models, the
    supported successor client to the deprecated Gemini CLI."""
    binary = shutil.which("agy") or "/home/charleton/.local/bin/agy"
    cmd = [binary, "--print", prompt]
    if model:
        cmd += ["--model", model]
    if effort:
        cmd += ["--effort", effort]
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.strip()[-300:] or f"agy exit {proc.returncode}")
    return proc.stdout


def selfcheck():
    print("== method paths ==")
    print(" ", STREAM_GENERATE_CHAT)
    print(" ", CREATE_INTERACTION_BIDI)
    for t in (GENERATE_CHAT_REQUEST, GENERATE_CHAT_RESPONSE,
              CLIENT_EVENT_BATCH, SERVER_EVENT_BATCH):
        prov = gemini_proto.provenance().get(
            {"google.internal.cloud.code.v1internal.GenerateChatRequest":
             "google/internal/cloud/code/v1internal/cloudcode.proto",
             "google.internal.cloud.code.v1internal.GenerateChatResponse":
             "google/internal/cloud/code/v1internal/cloudcode.proto",
             "genai.ClientEventBatch": "learning/genai/api/interactions/proto/events.proto",
             "genai.ServerEventBatch": "learning/genai/api/interactions/proto/events.proto"}[t],
            "??")
        print(f"\n== {t}  [defined by: {prov}]")
        for number, name, kind, presence, type_name in gemini_proto.fields(t):
            print(f"   {number:3d}  {name}  kind={kind} presence={presence} {type_name}")

    print("\n== round-trip ==")
    req = build_request("jetski.product.v1.CreateConversationRequest",
                        title="linux-client-selfcheck")
    wire = req.SerializeToString()
    back = gemini_proto.message("jetski.product.v1.CreateConversationRequest").FromString(wire)
    print(f"  CreateConversationRequest {len(wire)}B round-trip title={back.title!r}")

    print("\n== auth ==")
    url = auth.auth_url()
    print(f"  auth URL ({len(url)} chars): {url[:100]}...")
    form = auth.token_exchange_form("EXAMPLE_CODE")
    print(f"  token form keys: {sorted(form)}")
    return 0


def main(argv=None):
    p = argparse.ArgumentParser(prog="client.chat", description=__doc__)
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("selfcheck", help="offline verification + contract shapes")
    sub.add_parser("auth-url", help="print the OAuth authorization URL")
    pr = sub.add_parser("probe", help="probe recovered endpoints with a token")
    pr.add_argument("--token-file", default="client/token.json")
    d = sub.add_parser("describe", help="print fields of a message type")
    d.add_argument("type_name")
    c = sub.add_parser("chat", help="one streaming chat turn (API key or --token)")
    c.add_argument("--prompt", required=True)
    c.add_argument("--token", help="OAuth access token (desktop-protocol backend)")
    c.add_argument("--host", default=CLOUDCODE_HOST)
    c.add_argument("--api-key", help="Gemini API key (defaults to GEMINI_API_KEY/credentials.json)")
    c.add_argument("--model", help="API model (default gemini-3.8-flash)")
    c.add_argument("--skills", action="store_true",
                   help="enable the 27 recovered skill tools (function calling)")
    c.add_argument("--repo", help="default git repo_path for skill tools")
    c.add_argument("--vault", help="default obsidian vault_path for skill tools")
    c.add_argument("--backend", choices=["agy", "api", "desktop"],
                   help="agy=Antigravity CLI (Pro), api=Gemini API key, "
                        "desktop=recovered protocol (default: agy if installed)")
    c.add_argument("--effort", help="agy reasoning effort (low|medium|high|xhigh|max)")
    m = sub.add_parser("models", help="list models available to the API key")
    m.add_argument("--api-key")
    args = p.parse_args(argv)

    if args.cmd == "selfcheck":
        return selfcheck()
    if args.cmd == "auth-url":
        print(auth.auth_url())
        return 0
    if args.cmd == "probe":
        import json as _json
        token = _json.load(open(args.token_file))["access_token"]
        return probe(token)
    if args.cmd == "describe":
        for row in gemini_proto.fields(args.type_name):
            print(row)
        return 0
    if args.cmd == "chat" and args.token and args.backend in (None, "desktop"):
        req = build_chat_prompt(args.prompt)
        final = ""
        for resp in stream_generate_chat(req, args.token, host=args.host):
            if resp.markdown:
                print(resp.markdown, end="", flush=True)
            if resp.blocked:
                final = "blocked"
            elif resp.finish_reason:
                final = f"finish_reason={resp.finish_reason}"
        print(f"\n[{final}]" if final else "")
        return 0
    if args.cmd == "chat" and (args.backend == "agy" or
                               (args.backend is None and not args.api_key
                                and shutil.which("agy"))):
        print(run_agy(args.prompt, model=args.model, effort=args.effort))
        return 0
    if args.cmd in ("chat", "models"):
        from tools.protocol_probes import gemini_api
        key = args.api_key or gemini_api.api_key()
        if not key:
            print("no API key: pass --api-key, set GEMINI_API_KEY, "
                  "or add api_key to client/credentials.json", file=sys.stderr)
            return 2
        if args.cmd == "models":
            for name in gemini_api.list_models(key):
                print(name)
            return 0
        model = args.model or gemini_api.DEFAULT_MODEL
        print(f"[{model}]", file=sys.stderr)
        if args.skills:
            from tools.protocol_probes import skills
            system = ("You operate the user's local files through tools. "
                      "Prefer small, verifiable steps and report results briefly.")
            if args.repo:
                system += f" Default repo_path for git tools: {args.repo}"
            if args.vault:
                system += f" Default vault_path for obsidian tools: {args.vault}"
            final, _ = gemini_api.chat_with_tools(
                args.prompt, key, model=model,
                tools=[{"functionDeclarations": skills.declarations()}],
                system=system, execute=skills.execute,
                log=lambda m: print(m, file=sys.stderr))
            print(final)
            return 0
        for delta in gemini_api.stream_generate_content(args.prompt, key, model=model):
            print(delta, end="", flush=True)
        print()
        return 0
    return 2


if __name__ == "__main__":
    sys.exit(main())
