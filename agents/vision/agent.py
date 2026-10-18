#!/usr/bin/env python3
"""VisionLab agent: Agent Chat Protocol over an Agentverse mailbox, usable from ASI:One.

    agents\\.venv\\Scripts\\python agents/vision/agent.py

On first start it prints an Agent Inspector link: open it, sign in to
Agentverse and connect the mailbox. After that the agent can be found and
chatted with from asi1.ai while this process runs on your machine.
"""
import asyncio
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from uagents import Agent, Context, Protocol  # noqa: E402
from uagents_core.contrib.protocols.chat import (ChatAcknowledgement, ChatMessage, EndSessionContent,  # noqa: E402
                                                 StartSessionContent, TextContent, chat_protocol_spec)

from visionlab.requests import parse  # noqa: E402
from visionlab.tasks import run  # noqa: E402


def _seed() -> str:
    # the seed is the agent's identity (its address is derived from it), so it
    # lives in a gitignored .env, never in the code
    for env in (HERE.parents[1] / "mobile" / ".env", HERE.parent / ".env"):
        if env.is_file():
            for line in env.read_text(encoding="utf-8").splitlines():
                if line.startswith("VISIONLAB_SEED="):
                    return line.split("=", 1)[1].strip()
    seed = os.environ.get("VISIONLAB_SEED")
    if not seed:
        raise SystemExit("Set VISIONLAB_SEED (any long random phrase) in mobile/.env or agents/.env first.")
    return seed


# python 3.14 stopped making an event loop on demand, and uagents still asks
# for "the current loop" when it's built, so one is set up first
asyncio.set_event_loop(asyncio.new_event_loop())
agent = Agent(name="visionlab", seed=_seed(), port=8011, mailbox=True,
              description="VisionLab turns images into data: it detects and outlines trees, buildings, water, vegetation, "
                          "shadow or anything you teach it in aerial imagery, returns polygons and measurements as JSON, "
                          "compares them with your datasets to find what's missing, and predicts unmeasured values like heights.")
chat = Protocol(spec=chat_protocol_spec)


def reply(text: str, end: bool = True) -> ChatMessage:
    content = [TextContent(type="text", text=text)]
    if end:
        content.append(EndSessionContent(type="end-session"))
    return ChatMessage(timestamp=datetime.now(timezone.utc), msg_id=uuid4(), content=content)


@chat.on_message(ChatMessage)
async def on_message(ctx: Context, sender: str, msg: ChatMessage):
    await ctx.send(sender, ChatAcknowledgement(timestamp=datetime.now(timezone.utc), acknowledged_msg_id=msg.msg_id))
    for item in msg.content:
        if isinstance(item, StartSessionContent):
            continue
        if isinstance(item, TextContent):
            ctx.logger.info(f"request from {sender[:16]}…: {item.text[:120]}")
            request = parse(item.text)
            if request.action == "path":
                # a walk is a dozen tiles (about half a minute), so say so first
                # instead of leaving the chat silent
                await ctx.send(sender, reply(f"On it: planning the walk and analyzing it in {120} m stretches "
                                             "(about 30 seconds)...", end=False))
            # fetching imagery and running the model takes a few seconds, so it
            # runs on a worker thread and the agent keeps answering pings meanwhile
            answer = await asyncio.to_thread(run, request)
            await ctx.send(sender, reply(answer))


@chat.on_message(ChatAcknowledgement)
async def on_ack(ctx: Context, sender: str, msg: ChatAcknowledgement):
    pass


agent.include(chat, publish_manifest=True)

if __name__ == "__main__":
    print(f"VisionLab address: {agent.address}")
    agent.run()
