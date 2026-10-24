# Slash commands

> For the complete documentation index, see [llms.txt](https://learn.chatgpt.com/llms.txt). Markdown versions of documentation pages are available by appending `.md` to the page URL.

Slash commands let you run actions without leaving the chat composer. Available
commands vary based on your environment and access.

## Use a slash command

1. In the chat composer, type `/`.
2. Select a command from the list, or keep typing to filter (for example, `/status`).

You can also explicitly invoke skills by typing `$` in the chat composer. See
[Skills & Plugins](https://learn.chatgpt.com/docs/skills-and-plugins).

Enabled skills also appear in the slash command list. Custom prompts appear as
`/prompts:<name>` commands.

## Available slash commands

| Slash command        | Description                                                                             |
| -------------------- | --------------------------------------------------------------------------------------- |
| `/approve`           | Approve one retry of a recent automatic-review denial, when automatic review is active. |
| `/archive`           | Archive the current chat.                                                               |
| `/chat`              | Choose a chat without a project before starting a new chat.                             |
| `/cloud`             | Run the chat in the cloud, when cloud execution is available.                           |
| `/cloud-environment` | Choose the cloud environment for the chat.                                              |
| `/compact`           | Compact the current chat's context.                                                     |
| `/fast`              | Turn a catalog-provided Fast service tier on or off, when available.                    |
| `/feedback`          | Open the feedback dialog to submit feedback and optionally include logs.                |
| `/fork`              | Copy a local chat into a new local chat or worktree.                                    |
| `/goal`              | Set a persistent goal for ChatGPT to work toward; use `/plan` first to shape it.        |
| `/ide-context`       | Turn shared IDE context on or off.                                                      |
| `/init`              | Generate an `AGENTS.md` scaffold for the current project.                               |
| `/local`             | Run the chat in the selected local project.                                             |
| `/mcp`               | Open MCP status to view connected servers.                                              |
| `/memories`          | Configure whether the chat can use or generate memories, when Memories is available.    |
| `/model`             | Choose the model for the current chat.                                                  |
| `/new`               | Start a blank chat in the same local workspace, when available.                         |
| `/pet`               | Wake or tuck away the desktop pet.                                                      |
| `/pin`               | Pin or unpin the current chat, when available.                                          |
| `/plan`              | Toggle plan mode for multi-step planning.                                               |
| `/project`           | Choose a project for new chats.                                                         |
| `/reasoning`         | Choose the reasoning effort for the current chat.                                       |
| `/rename`            | Rename the current chat.                                                                |
| `/review`            | Start code review mode to review uncommitted changes or compare against a base branch.  |
| `/side`              | Start a temporary side chat without interrupting the main chat.                         |
| `/status`            | Show the chat ID, context usage, and rate limits.                                       |
| `/usage`             | Open usage and billing settings, when available with ChatGPT sign-in.                   |
| `/worktree`          | Run the chat in a new Git worktree.                                                     |

## Set or manage a goal with `/goal`

Use `/goal` in the app composer to start Goal mode. A goal is a persistent
objective that ChatGPT works toward until it finishes the task, pauses, or needs
more input. To define the goal with ChatGPT first, start with `/plan`, then set
the refined goal with `/goal`.


  

> Illustration: ChatGPT desktop app goal progress controls above the composer




When a goal is active, the app shows its progress above the composer. Use the
buttons in that progress row to pause or resume the goal, edit the goal text, or
clear the goal instead of typing another slash command. You can keep steering
ChatGPT with follow-up messages while the goal runs.

For guidance on writing effective goals, see [Goal mode](https://learn.chatgpt.com/docs/prompting#goal-mode).