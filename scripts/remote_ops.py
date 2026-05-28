#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import posixpath
import sys
from pathlib import Path

import paramiko


def _expand_path(raw: str | None) -> str | None:
    if not raw:
        return None
    return str(Path(raw).expanduser().resolve())


def _build_client(args: argparse.Namespace) -> paramiko.SSHClient:
    password = ""
    if args.password:
        password = args.password
    elif args.password_env:
        password = os.getenv(args.password_env, "")

    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    connect_kwargs = {
        "hostname": args.host,
        "port": args.port,
        "username": args.user,
        "timeout": args.timeout,
        "banner_timeout": args.timeout,
        "auth_timeout": args.timeout,
        "look_for_keys": False,
        "allow_agent": False,
    }
    key_path = _expand_path(args.key_path)
    if key_path:
        connect_kwargs["key_filename"] = key_path
    if password:
        connect_kwargs["password"] = password
    client.connect(**connect_kwargs)
    return client


def _mkdir_p(sftp: paramiko.SFTPClient, remote_dir: str) -> None:
    parts = []
    current = remote_dir
    while current and current not in ("/", "."):
        parts.append(current)
        current = posixpath.dirname(current)
    for path in reversed(parts):
        try:
            sftp.stat(path)
        except OSError:
            sftp.mkdir(path)


def _run_exec(args: argparse.Namespace) -> int:
    command = args.command or ""
    if args.command_b64:
        import base64

        command = base64.b64decode(args.command_b64.encode("ascii")).decode("utf-8")
    if not command:
        raise SystemExit("missing --command or --command-b64")

    client = _build_client(args)
    try:
        stdin, stdout, stderr = client.exec_command(command, timeout=args.timeout)
        stdout.channel.set_combine_stderr(False)
        out = stdout.read()
        err = stderr.read()
        if out:
            sys.stdout.buffer.write(out)
        if err:
            sys.stderr.buffer.write(err)
        return stdout.channel.recv_exit_status()
    finally:
        client.close()


def _run_upload(args: argparse.Namespace) -> int:
    client = _build_client(args)
    try:
        sftp = client.open_sftp()
        try:
            remote_parent = posixpath.dirname(args.remote_path)
            if remote_parent:
                _mkdir_p(sftp, remote_parent)
            sftp.put(args.local_path, args.remote_path)
        finally:
            sftp.close()
        return 0
    finally:
        client.close()


def _run_download(args: argparse.Namespace) -> int:
    client = _build_client(args)
    try:
        sftp = client.open_sftp()
        try:
            local_parent = Path(args.local_path).resolve().parent
            local_parent.mkdir(parents=True, exist_ok=True)
            sftp.get(args.remote_path, args.local_path)
        finally:
            sftp.close()
        return 0
    finally:
        client.close()


def _add_common_auth(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--host", required=True)
    parser.add_argument("--port", type=int, default=22)
    parser.add_argument("--user", required=True)
    parser.add_argument("--key-path")
    parser.add_argument("--password")
    parser.add_argument("--password-env", default="REMOTE_OPS_PASSWORD")
    parser.add_argument("--timeout", type=int, default=600)


def main() -> int:
    parser = argparse.ArgumentParser(description="Simple SSH/SFTP helper for deployment scripts.")
    subparsers = parser.add_subparsers(dest="action", required=True)

    exec_parser = subparsers.add_parser("exec")
    _add_common_auth(exec_parser)
    exec_parser.add_argument("--command")
    exec_parser.add_argument("--command-b64")

    upload_parser = subparsers.add_parser("upload")
    _add_common_auth(upload_parser)
    upload_parser.add_argument("--local-path", required=True)
    upload_parser.add_argument("--remote-path", required=True)

    download_parser = subparsers.add_parser("download")
    _add_common_auth(download_parser)
    download_parser.add_argument("--remote-path", required=True)
    download_parser.add_argument("--local-path", required=True)

    args = parser.parse_args()
    if args.action == "exec":
        return _run_exec(args)
    if args.action == "upload":
        return _run_upload(args)
    if args.action == "download":
        return _run_download(args)
    raise SystemExit(f"unsupported action: {args.action}")


if __name__ == "__main__":
    raise SystemExit(main())
