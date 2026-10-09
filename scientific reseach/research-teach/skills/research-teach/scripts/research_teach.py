#!/usr/bin/env python3
from __future__ import annotations

import argparse
import functools
import getpass
import http.server
import json
import subprocess
import sys
from socketserver import ThreadingTCPServer
from typing import Any

from converter import (
    configure_mineru,
    convert_document,
    doctor,
    inspect_upload,
    mineru_config_status,
)
from rtlib import (
    ResearchTeachError,
    accept_proposal,
    build_graph,
    cache_status,
    clean_cache,
    create_proposal,
    init_global,
    init_project,
    load_config,
    config_path,
    preview_proposal,
    project_status,
    reject_proposal,
)


def emit(value: Any) -> None:
    if isinstance(value, str):
        print(value)
    else:
        print(json.dumps(value, ensure_ascii=False, indent=2))


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(
        prog="research-teach",
        description="Initialize and maintain local-first research teaching projects.",
    )
    sub = root.add_subparsers(dest="command", required=True)

    global_init = sub.add_parser("init-global", help="Create an approved global AgentContext.")
    global_init.add_argument("--agent-context", required=True)

    project_init = sub.add_parser("init", help="Initialize a research teaching project.")
    project_init.add_argument("--project", default=".")
    project_init.add_argument("--global-context", required=True)
    project_init.add_argument("--topic", default="")

    status = sub.add_parser("status", help="Show project state.")
    status.add_argument("--project", default=".")

    check = sub.add_parser("doctor", help="Check conversion and project dependencies.")
    check.add_argument("--project", default=".")

    mineru_config = sub.add_parser(
        "configure-mineru", help="Store the MinerU API key in a private user env file."
    )
    mineru_config.add_argument("--env-file")
    mineru_config.add_argument("--base-url", default="https://mineru.net/api/v4")
    mineru_config.add_argument(
        "--token-stdin",
        action="store_true",
        help="Read the token from stdin instead of a hidden interactive prompt.",
    )

    mineru_status = sub.add_parser("mineru-config", help="Show redacted MinerU configuration.")
    mineru_status.add_argument("--env-file")

    inspect = sub.add_parser("inspect-upload", help="Review a file before remote conversion.")
    inspect.add_argument("path")
    inspect.add_argument("--project", default=".")

    convert = sub.add_parser("convert", help="Convert a document into an Inbox source note.")
    convert.add_argument("path")
    convert.add_argument(
        "--document-type",
        choices=("reference", "project_document", "confidential"),
        required=True,
    )
    convert.add_argument("--approve-upload", action="store_true")
    convert.add_argument("--install-fallback", action="store_true")
    convert.add_argument("--timeout", type=int, default=900)
    convert.add_argument("--project", default=".")

    graph = sub.add_parser("build-graph", help="Build the offline graph and dashboard.")
    graph.add_argument("--project", default=".")

    serve = sub.add_parser("serve", help="Serve the offline dashboard on localhost.")
    serve.add_argument("--project", default=".")
    serve.add_argument("--bind", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8765)

    proposal = sub.add_parser("propose", help="Create a learner-context update proposal.")
    proposal.add_argument("--target", required=True)
    proposal.add_argument("--title", required=True)
    proposal.add_argument("--content", required=True)
    proposal.add_argument("--rationale", required=True)
    proposal.add_argument("--project", default=".")

    preview = sub.add_parser("preview-proposal", help="Preview a proposal as a unified diff.")
    preview.add_argument("path")
    preview.add_argument("--project", default=".")

    accept = sub.add_parser("accept-proposal", help="Apply an explicitly approved proposal.")
    accept.add_argument("path")
    accept.add_argument("--project", default=".")

    reject = sub.add_parser("reject-proposal", help="Reject a pending proposal.")
    reject.add_argument("path")
    reject.add_argument("--reason", required=True)

    cache = sub.add_parser("cache", help="Inspect or clean disposable conversion cache.")
    cache_sub = cache.add_subparsers(dest="cache_command", required=True)
    cache_show = cache_sub.add_parser("status")
    cache_show.add_argument("--project", default=".")
    cache_clean = cache_sub.add_parser("clean")
    cache_clean.add_argument("--project", default=".")

    return root


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        if args.command == "init-global":
            emit(init_global(args.agent_context))
        elif args.command == "init":
            emit(init_project(args.project, args.global_context, args.topic))
        elif args.command == "status":
            emit(project_status(args.project))
        elif args.command == "doctor":
            emit(doctor(args.project))
        elif args.command == "configure-mineru":
            if args.token_stdin:
                token = sys.stdin.readline().strip()
            elif sys.stdin.isatty():
                token = getpass.getpass("MinerU API token: ")
            else:
                raise ResearchTeachError(
                    "No interactive terminal. Use --token-stdin and provide the token on stdin."
                )
            emit(
                configure_mineru(
                    token,
                    base_url=args.base_url,
                    env_file=args.env_file,
                )
            )
        elif args.command == "mineru-config":
            emit(mineru_config_status(args.env_file))
        elif args.command == "inspect-upload":
            emit(inspect_upload(args.path, args.project))
        elif args.command == "convert":
            emit(
                convert_document(
                    args.path,
                    document_type=args.document_type,
                    approve_upload=args.approve_upload,
                    install_fallback=args.install_fallback,
                    project=args.project,
                    timeout_seconds=args.timeout,
                )
            )
        elif args.command == "build-graph":
            emit(build_graph(args.project))
        elif args.command == "serve":
            root, config = load_config(args.project)
            dashboard = config_path(root, config, "dashboard")
            if not (dashboard / "index.html").is_file():
                build_graph(root)
            handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(dashboard))
            with ThreadingTCPServer((args.bind, args.port), handler) as server:
                print(f"Serving Research Teach dashboard at http://{args.bind}:{args.port}/")
                server.serve_forever()
        elif args.command == "propose":
            emit(
                {
                    "proposal": str(
                        create_proposal(
                            args.target,
                            args.title,
                            args.content,
                            args.rationale,
                            args.project,
                        )
                    )
                }
            )
        elif args.command == "preview-proposal":
            emit(preview_proposal(args.path, args.project))
        elif args.command == "accept-proposal":
            emit(accept_proposal(args.path, args.project))
        elif args.command == "reject-proposal":
            emit(reject_proposal(args.path, args.reason))
        elif args.command == "cache" and args.cache_command == "status":
            emit(cache_status(args.project))
        elif args.command == "cache" and args.cache_command == "clean":
            emit(clean_cache(args.project))
        else:
            raise ResearchTeachError(f"Unsupported command: {args.command}")
    except (ResearchTeachError, OSError, subprocess.SubprocessError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
