# Gemini Desktop / Antigravity Engine — Protocol Specification (recovered)

**Source of truth:** 48 protobuf `FileDescriptorProto`s extracted from `agy` (Gemini 1.128.14.1166, SHA-256 `4065d818…`), containing **2,832 message types and 507 RPCs**. Machine-readable forms in `protos/*.textproto`; complete RPC index in `protos/_services.tsv`. Companion architecture report: `RE_REPORT.md`.
**Lineage [OBSERVED]:** package namespaces `exa.*`, `codeium_common_pb`, `cortex_pb`, `Cascade*` — the engine is Windsurf/Codeium-lineage code inside Google ("Antigravity"); `google.internal.cloud.code.v1internal` is the Cloud Code Assist backend ("Jetski").

---

## 1. Topology

```mermaid
flowchart LR
    subgraph local [Linux client side]
        UI[Client UI]
        LS[LanguageServerService<br/>agent engine RPCs]
        ES[ExtensionServerService<br/>host/IDE bridge]
        IX[IndexService + IndexManagement<br/>embeddings, code index]
        UI <--> LS
        UI <--> ES
        LS <--> IX
    end
    subgraph cloud [Google cloud]
        CC[CloudCode + JetskiService<br/>cloudcode-pa.googleapis.com]
        IN[InteractionService<br/>bidi streaming]
        MG[ManagementService<br/>aicode v1main]
        AP[ApiService (boq)<br/>instances, mesh, signaling]
        CV[ConversationService<br/>jetski.product.v1]
        MD[(generativelanguage / aiplatform)]
    end
    LS -->|gRPC| CC
    LS -->|gRPC| IN
    LS -->|gRPC| MG
    UI -->|OAuth2| AU[(accounts.google.com / sts.googleapis.com)]
    CC --> MD
    AP <-.mesh.- LS
```

Observed endpoints (RE_REPORT §4): `cloudcode-pa.googleapis.com`, `aiplatform.googleapis.com`, `generativelanguage.googleapis.com`, `www.googleapis.com/oauth2/v4/token`, `sts.googleapis.com/v1/oauthtoken`, `notifications-pa.googleapis.com`, `update.googleapis.com/service/update2/json`, `http://localhost:2444/submit` + `http://127.0.0.1:<port>` (local webview/loopback bridge).

**Transport evidence [OBSERVED strings]:** the main `Gemini` binary embeds **zero** cloud gRPC method paths — it is UI-only. Its network markers are `application/grpc`, `application/grpc+proto`, `application/grpc-web`, `application/json`, `grpc-status/encoding/timeout`, and exactly one loopback endpoint `localhost:2444`. All full gRPC method-path strings live in `agy` (families: `LanguageServerService` ~151, `cortex` 61, `cli` 37, `genai`/`interactions` 31, `prompt`, `fs`, `git_utils`, `terminal`, `remoting`, `product_api`, `gateway`, plus `ApiServerService`/`AnalyticsService` below). Conclusion: **shell↔engine = local gRPC(-web)/JSON; engine↔cloud = gRPC**.

## 2. Service inventory

| Layer | Service (proto package) | Purpose | Size of surface |
|---|---|---|---|
| Cloud chat/agent | `CloudCode` (`google.internal.cloud.code.v1internal`) | `StreamGenerateChat`/`GenerateChat`, `GenerateCode`, `CompleteCode`, `TransformCode`, `InternalAtomicAgenticChat`, `LoadCodeAssist`, `OnboardUser`, `ListAgents`, `ListModelConfigs`, `ListExperiments`, `FetchAdminControls`, user settings, metrics | 22 RPCs |
| Cloud agent | `JetskiService` (same pkg) | `GetHealth`, `FetchUserInfo`, `GetAgentPlugin`/`ListAgentPlugins`, `CheckUrlAntivirus`, `CheckUrlDenylist`, `FetchFromTrawlerCache`, `GetBundleWriteMint`, BattleMode | ~12+ RPCs |
| Cloud streaming | `InteractionService` (`genai`) | `CreateInteractionBidiStream(ClientEventBatch→ServerEventBatch)` ← **primary streaming channel**, `CreateInteractionStream`, `CreateInteraction` | 3 RPCs |
| Cloud mgmt | `ManagementService` (`google.gca.aicode.v1main`) | `FetchConfig` (incl. `agy_surface_config`), `GetUserInfo`, `GetUserSettings`, `FetchLicenses` | 5 RPCs |
| Cloud mesh | `ApiService` (`devtools_jetski_boq_api_proto`) | instance lifecycle, `InitiateMeshSession`, signaling, proxy commands, `RegisterWebPush`, authorized devices | 19 RPCs |
| Cloud conversations | `ConversationService` (`jetski.product.v1`) | Conversation CRUD | 5 RPCs |
| Cloud backend | `ApiServerService` (`exa.api_server_pb`) | `GetMQuery`, `GetWebSearchResults`, `GetEmbeddings`, `GetCascadeModelConfigs`, `GetMcpServerTemplates`, `GetTranscription`, `GetUserAllowlist`, `JoinWaitlist`, telemetry/log | 25+ RPCs |
| Analytics | `AnalyticsService` (`exa.analytics_pb`) | `RecordCommandUsage`, `RecordCortexTrajectory` | 2+ RPCs |
| Local engine | `LanguageServerService` (`exa.language_server_pb`) | the agent brain's local API (see §3) | ~200 RPCs |
| Host bridge | `ExtensionServerService` (`exa.extension_server_pb`) | terminal, files, notebooks, browser launch, secrets, UI actions | ~45 RPCs |
| Code index | `IndexManagementService` + `IndexService` (`exa.index_pb`) | indexes/repos, embeddings (`GetNearestCCIsFromEmbedding`) | 21 RPCs |
| Misc | `RemotingService`, `CascadePluginsService`, `DevService`, `S2AService` | remote control, plugin marketplace, dev, TLS handshake | 12 RPCs |

**Scope note [INFERRED, evidence-backed]:** `agy` is the bundled **Antigravity-lineage agent engine** (CLI-shaped runtime: `Usage: %s <command>`, `add-dir`, `--headless`; packages `exa.*`/`Cortex`/`Cascade`; built from `gdm/apps/janus/*` — the app's own internal project). The desktop shell is its *consumer surface* (chat + skills/cowork + local-file tools) and invokes a **subset** of the engine's 507 RPCs — the developer-IDE surface (terminals, VCS RPCs, indexing) ships inside the app but is likely dormant there (§7 gap). The `git_mcp_server`/`obsidian_mcp_server` helpers are the app's **bundled skill tools** (`AgentMode__enable_{git,obsidian,messages,blender}_bundled_mcp_tools`), consistent with the Gemini "skills" feature launched 2026-09-30. This is distinct from **Gemini CLI** (`google-gemini/gemini-cli`, TypeScript) — a separate product sharing only the MCP / Agent Skills open standards.

## 3. Local engine surface (`LanguageServerService`) — what the Linux client must host or call

| Domain | RPCs (representative) |
|---|---|
| **Agent runs (Cascade)** | `StartCascade`, `SendUserCascadeMessage`, `SendAgentMessage`, `SendStepsToBackground`, `StreamCascadeReactiveUpdates`, `StreamAgentStateUpdates`, `HandleCascadeUserInteraction`, `RevertToCascadeStep`, `WaitForConversationFullyIdle`, `StartBattleMode` |
| Files/workspace | `ReadFile`, `WriteFile`, `ReadDir`, `StatUri`, `WatchDirectory`, `GetWorkingDirectories`, `ResolveFolder`, `GetWorkspaceInfos`, `GetWorkspaceEditState` |
| VCS | `GitCommit/Stage/Unstage/Push/Discard`, `JjCommit/JjSquash/JjAbandon/JjSync/JjUpload`, `RepoAmend/RepoCommit/RepoSync/RepoUpload`, `GetWorktreeDiff`, `UpdatePRForWorktree` |
| Terminal | `ExecuteCommand`, `StreamTerminalShellCommand`, `StreamTerminalOutput`, `SendTerminalInput`, `OpenTerminal`, `ListTerminals`, `TerminateCommand` |
| Search/code intel | `SearchCode`, `StreamSearchCode`, `SearchFiles`, `SearchContext`, `ResolveContextUri`, `GetDefinition`, `FindAllReferences` |
| MCP | `ListMcpResources`, `ListMcpPrompts`, `ToggleMcpServer`, `SubscribeToMcpServerStates`, `RefreshMcpServers`, `LaunchMcpApp`, `ResolveCommandPlugin` |
| Auth/state | `Login`, `LoginWithBrowser`, `HasAuthToken`, `SetCloudCodeURL`, `JetboxSubscribeToState/OAuthState/GcertState`, `SetOrVerifyStaticConfig` |
| Media | `SendAudioChunk`, `StreamAudioTranscription`, `StartNarration`, `StartScreenRecording`, `HandleScreenRecording`, `SaveMediaAsArtifact` |
| Conversations/memory | `SearchConversations`, `LoadTrajectory`, `GetUserTrajectory`, `ReplayGroundTruthTrajectory`, `GetUserMemories`, `UpdateCascadeMemory` |
| Misc | `ImportFromCursor`, `SearchDriveFiles`, `UploadToDrive`, `SearchMarketplace`, `InstallCustomization`, triggers/schedules (`ListTriggers`, `UpdateTrigger`) |

## 4. Key message shapes (field-level, from descriptors)

- **`genai.ExternalClientEvent`**: `1:create_interaction`, `2:reconnect_interaction`, `4:complete_interaction`, `5:cancel_interaction`, `9:disconnect`, `11:input`, `12:media_stream_append`, `14:call_hook_response`, `15:function_result`, `16:elicitation_result` ↔ **`ExternalServerEvent`**: `1:interaction_created`, `2:interaction_reconnected`, `3:event`, `4:interaction_completed`.
- **`CloudCode` chat spine** (`google.internal.cloud.code.v1internal`, shapes verified via `client/chat.py selfcheck`): `GenerateChatRequest{1:project, 2:request_id, 3:user_message ← prompt, 4:history(ChatMessage), 5:ide_context, 6:metadata(ClientMetadata), 7:enable_prompt_enhancement, 8:yield_info, 11:function_declarations, 12:include_thinking_summaries, 13:tier_id, 14:model_config_id, 15:user_prompt_id}` → stream `GenerateChatResponse{1:markdown ← streamed text, 2:citations, 9:agent_processing_details, 11:blocked, 12:workspace_change, 16:finish_reason(FinishReason), 17:suggested_prompts, 19:function_calls, 20:usage_metadata}`. `genai.ClientEventBatch`/`ServerEventBatch` are stubs (their `events.proto` is genuinely absent from the binary — §7 gap).
- **`jetski.product.v1.CreateConversationRequest`**: `project_id, environment_id, title, tags, model, prompt(Content)`.
- **Tool config (`exa.cortex_pb.CascadeToolConfig`)** — the agent's tool palette to reimplement: `code`, `intent`, `grep`, `find`, `run_command`, `knowledge_base_search`, `view_file`, `write_to_file`, `replace_content`, `search_web`, `read_url_content`, `mcp`, `list_dir`, `view_code_item`, `command_status`, `notebook_edit`, `skill_search`, `schedule`, `ask_permission`, `ask_custom_permission`, `ask_question`, `wait`, `finish`, `invoke_subagent`, `browser` (`AntigravityBrowserToolConfig`: subagent, screenshots, pixel clicks, network capture, DOM extraction), `memory`, `task_boundary`.
- **Permissions**: `PermissionConfig{effective_grants, default_grants, allow_always_config(dangerous_binaries/subcommands), permissions_v2, effective_permission_preset}`, `PolicyGuardianConfig{enabled, model, antivirus, url_vetting, tool_rounds}`, `AutoCommandConfig{allow/deny/noop lists, auto_execution_policy}`.
- **Execution**: `CascadeConfig{planner_config, checkpoint_config, executor_config, trajectory_conversion_config, conversation_history_config, battle_mode_config}`, `CheckpointConfig{strategy, max_tokens, snapshot inclusion}`, `TaskItem/TaskDelta` (task list protocol).

## 5. Auth model [OBSERVED strings + descriptors]

- OAuth2 auth-code with the two embedded client IDs (`839509190550-2rlon2is770e9fuk252ven6rdneak3gm…`, `…-l232s7lupkp6f57818eshd7u4sl4920h….apps.googleusercontent.com`), `https://accounts.google.com/o/oauth2/auth`, token refresh `www.googleapis.com/oauth2/v4/token`, STS exchange `sts.googleapis.com/v1/oauthtoken`.
- Scopes: `auth/gemini`, `auth/aicode`, `auth/drive`, `auth/calendar`, `auth/assistant`, `auth/notifications`, `auth/experimentsandconfigs`, `auth/cloud-platform`, `auth/photos.image.readonly`, `auth/photospicker.mediaitems.readonly`, `auth/supportcontent`, `auth/oauth_integrations`, `auth/userinfo.{email,profile}`.
- TLS: S2A (`S2AService.SetUpSession`, `s2a.proto.v2`) for key/identity handling; `gRPCCertificates.bundle` = trust roots.
- Machine identity/updates: Omaha `update2/json` (channel `m1-prod`); push `notifications-pa.googleapis.com/v1/`.

## 6. Building a Linux client from this spec

1. **Codegen**: `protos/*.textproto` are complete `FileDescriptorProto`s — load them into a `google.protobuf.descriptor_pool`, then either (a) generate stubs with any codegen that accepts descriptor sets, or (b) call dynamically in Python via `grpc.unary_unary("/<package>.<Service>/<Method>", ...)` with messages built from the pool. Full method paths = `/<proto package>.<Service>/<Method>` (e.g. `/google.internal.cloud.code.v1internal.CloudCode/StreamGenerateChat`).
**Authorization boundary [OBSERVED 2026-10-14, third-party token probes]:** `CloudCode.StreamGenerateChat`/`LoadCodeAssist` on `cloudcode-pa.googleapis.com` answer `PERMISSION_DENIED — insufficient authentication scopes` to a basic-scope (openid/email/profile) account token — **host, method paths, and auth plumbing are correct**; the endpoints are gated by first-party-only scopes (`auth/gemini`, `auth/aicode` are refused at consent for third-party clients: `invalid_scope`, "Some requested scopes cannot be shown"). `ManagementService.*` and `genai.InteractionService.*` return `UNIMPLEMENTED` on cloudcode-pa (they live on other hosts — unresolved). The public `generativelanguage.googleapis.com` API likewise requires `cloud-platform` or an API key. Conclusion: the desktop protocol is reachable but **first-party-identity-gated**; third-party paths are (a) a Gemini API key (public API surface) or (b) recovery of the app's runtime-constructed client secret (`JanusLibWrapperImpl` "OAuth clients data").

**Live status [OBSERVED 2026-10-14]:** Path A is **operational** — `client/gemini_api.py` (API-key backend) completed a live `streamGenerateContent` call with `gemini-3.8-flash` from this Linux host and received a streamed response. The desktop-protocol backend (`client/chat.py --token`) stays wired behind the same chat interface and remains first-party-gated. The API key exposes 50 models including `antigravity-preview-*` (agent-tuned) and `gemini-2.5-computer-use-preview`. **Skills layer [OBSERVED 2026-10-14]:** `client/skills.py` exposes the 27 recovered tools as Gemini function declarations; a live `--skills` run had the model call `git_status` and `obsidian_create_note` autonomously (note created on disk, 22 s, `gemini-flash-lite-latest`). Model-matrix notes: `gemini-pro-latest` 429 (free-tier quota), `antigravity-preview-*` 400 "only supports Interaction…" — the agent models require the recovered `InteractionService` streaming protocol.

**Entitlement model [OBSERVED 2026-10-14]:** with a `cloud-platform` token (Gemini CLI cache, refreshed via the CLI's public OAuth client), `POST https://cloudcode-pa.googleapis.com/v1internal:loadCodeAssist` (Google simple-RPC JSON, `Content-Type: application/json`) returns `currentTier: {id: "standard-tier", name: "Gemini Code Assist", description: "Unlimited coding assistant with the most powerful Gemini models"}`. `generateChat`/`streamGenerateChat` gate in stages: (1) strict field validation against the real descriptor — proving the recovered `GenerateChatRequest` field set is complete (`cloudaicompanionProject` rejected as unknown; `project`, `userMessage`, `metadata`, `tierId` accepted); (2) project IAM — `projects/cloudshell-gca` → missing `cloudaicompanion.companions.generateChat`; (3) product license — own project `429859117534` → `#3501` ("no valid license of this product") ⇒ enable `cloudaicompanion.googleapis.com` on the project. The Gemini CLI bundle (readable JS) supplied: tiers `free-tier|legacy-tier|standard-tier`; `loadCodeAssist({cloudaicompanionProject, metadata:{ideType,platform,pluginType,duetProject}, mode:"HEALTH_CHECK"})`; and the Live endpoint `wss://generativelanguage.googleapis.com/ws/google.ai.generativelanguage.v1beta.GenerativeService.BidiGenerateContent` — the public face of the recovered `genai.InteractionService` (create/reconnect/event-batch semantics), which is what the `antigravity-preview-*` models require.

**Antigravity path [OBSERVED 2026-10-14]:** the Gemini CLI is **deprecated** for Code Assist individuals — sign-in returns *"This client is no longer supported… migrate to the Antigravity suite of products"* — which is the real nature of the `#3501`-family denials for `generateChat`/`onboardUser` (client `681255809395-…` retired, not a missing seat). The supported successor, **`agy` (Antigravity CLI 1.3.1)**, uses its own OAuth clients (`1071006060591-…`, `884354919052-…`) via device-code flow, reports `consumerOnboardingComplete: true`, and runs **Pro-subscription models** (`Gemini 3.8 Flash (High)`) on this host: `agy --print "…"` answered live. `client/chat.py` now carries three backends behind one interface: `--backend agy` (Pro subscription), `--backend api` (API key), `--backend desktop` (recovered protocol).

**Verified loader:** `client/bootstrap.py` (run with `client/.venv/bin/python`) builds the pool from all 128 recovered descriptors → 590-file pool (121 real/builtin incl. every contract file: `cloudcode.proto`, `jetski_service.proto`, `prediction_service.proto`, `interaction_service.proto`, `external_events.proto`, `conversation_service.proto`, `content.proto`, `gemini_coder/service.proto`), 528 RPCs addressable, 0 unresolved symbols. Referenced-but-absent annotation/option protos become shells; 11 mutually-blocked config files (cortex/trajectory/config/…) are placeholder-shelled — their message bodies remain available in `protos/*.textproto` for regeneration; `google/protobuf/any.proto` resolves via the well-known type. Smoke: `jetski.product.v1.CreateConversationRequest` builds and serializes through the pool.

2. **Streaming core**: implement `CreateInteractionBidiStream` / `StreamGenerateChat` first — that is the chat spine; wrap `ClientEventBatch`/`ServerEventBatch`.
3. **Agent loop**: host `LanguageServerService` semantics locally (your own implementation) or treat it as a spec for an in-process engine; wire `StartCascade` → `SendUserCascadeMessage` → `StreamCascadeReactiveUpdates`.
4. **Tools/MCP**: the recovered skill surface is **implemented and smoke-verified** — `client/mcp_git_server.py` (12 tools) and `client/mcp_obsidian_server.py` (15 tools), both clean-room stdio MCP servers speaking the recovered schemas/wordings (RE_REPORT §3.3); they register into any MCP-capable host directly.
5. **Feature flags**: `experimentsandconfigs/v1/getExperimentsAndConfigs` + Unleash (`GetUnleashData`, `ShouldEnableUnleash`) gate features client-side.

## 7. Open gaps (needs the pending main-binary Ghidra pass)

- ~~Per-service transport binding~~ — resolved at evidence level (§1): UI-only shell over `localhost:2444` + gRPC(-web)/JSON; cloud gRPC lives in `agy`.
- **Function-level xref depth on `Contents/MacOS/Gemini` — unresolved.** Two full Ghidra headless passes (default heap 2h08m; `MAXMEM=10G` 2h15m) both failed inside `DBHandle.doEndTransaction` at final commit; the project DB rolled back to 40 KB both times (disk was 96% full — pressure is a plausible contributor, unconfirmed). No third attempt: this is optional depth. Open because of it: exact per-call-site transport headers and which subset of the 507 RPCs the macOS shell invokes.
- Auth handshake specifics (mint tokens `GetBundleWriteMint`, gcert state, header names).
- `turrellMesh` shader semantics (visible-function refusal) and 2 asset catalogs remain unexamined.
