"""Solari smoke test — resolves wayfinder ticket #7.

Throwaway spike. Proves the three primitives run, and probes the facts that
issue #2's research recorded as INFERRED rather than documented:

  A. Does the Free tier's concurrency counter include Desktop VMs alongside
     Sandboxes? (blocks #16)
  B. What does the `default` desktop template actually ship? (docs and cookbook
     contradict each other)
  C. Is session recording really rrweb rather than video, and does the replay
     URL really expire?

Written against the surface actually installed in .venv (solari-browser 0.1.3,
solari-sandbox / solari-desktop / solari-core 0.2.0), not against the docs.

Run:  .venv/Scripts/python.exe spikes/solari_smoke.py
Needs SOLARI_API_KEY in a .env at the repo root (gitignored).
"""

import asyncio
import os
import sys
import time
import traceback
from pathlib import Path

BASE_URL = "https://api.getsolari.com"
OUT = Path(__file__).parent / "out"

RESULTS: list[tuple[str, str, str]] = []


def record(step: str, outcome: str, detail: str = "") -> None:
    RESULTS.append((step, outcome, detail))
    print(f"[{outcome.upper():4}] {step}" + (f" — {detail}" if detail else ""), flush=True)


def load_key() -> str:
    key = os.environ.get("SOLARI_API_KEY")
    if not key:
        env_path = Path(__file__).resolve().parent.parent / ".env"
        if env_path.exists():
            for line in env_path.read_text(encoding="utf-8").splitlines():
                if line.strip().startswith("SOLARI_API_KEY="):
                    key = line.split("=", 1)[1].strip().strip("\"'")
                    break
    if not key:
        sys.exit("SOLARI_API_KEY not found — put it in .env at the repo root.")
    print(f"key loaded: {key[:12]}...{key[-4:]} ({len(key)} chars)\n", flush=True)
    return key


async def phase_browser(key: str) -> None:
    from solari_browser import Solari

    client = Solari(key)
    t0 = time.monotonic()
    # recording=True so probe C can look at what recording actually returns.
    session = await client.launch(recording=True)
    record("browser.launch", "info", f"cold start {time.monotonic() - t0:.1f}s")
    try:
        page = await session.new_page()
        await page.goto("https://example.com")
        title = await page.title()
        record("browser.navigate", "ok" if "Example" in title else "fail", f"title={title!r}")

        OUT.mkdir(exist_ok=True)
        shot = OUT / "browser.png"
        await page.screenshot(path=str(shot))
        record("browser.screenshot", "ok", f"{shot.stat().st_size} bytes")

        record("browser.endpoints", "info",
               f"ws={str(session.ws_endpoint)[:40]}... cdp={str(session.cdp_endpoint)[:40]}...")
        sid = session.id
    finally:
        t1 = time.monotonic()
        await session.close()
        record("browser.teardown", "ok", f"{time.monotonic() - t1:.1f}s")

    # PROBE C — close() returns None by design; the replay is fetched afterwards
    # from the sessions API by session id.
    try:
        # The replay is NOT ready the instant close() returns — it 404s with
        # "No replay available for this session" for a few seconds while the
        # gateway finalises it. Poll rather than assume.
        replay = None
        for _ in range(6):
            await asyncio.sleep(5)
            try:
                replay = await client.sessions.get_replay_url(sid)
                break
            except Exception:  # noqa: BLE001
                continue
        if replay is None:
            raise RuntimeError("replay never became available after 30s")
        record("PROBE C: replay url", "ok",
               f"expires_in={getattr(replay, 'expires_in_seconds', '?')}s "
               f"encoding={getattr(replay, 'content_encoding', '?')}")
        blob = await client.sessions.download_replay(sid)
        head = bytes(blob[:2])
        kind = "gzip" if head == b"\x1f\x8b" else f"raw({head!r})"
        (OUT / "replay.bin").write_bytes(blob)
        record("PROBE C: replay bytes", "ok", f"{len(blob)} bytes, {kind}")
        # Is it really rrweb NDJSON rather than video?
        import gzip
        try:
            text = gzip.decompress(blob).decode("utf-8", "replace") if kind == "gzip" \
                else blob.decode("utf-8", "replace")
            first = text.splitlines()[0][:180] if text.strip() else "(empty)"
            record("PROBE C: replay format", "info", f"first line: {first}")
        except Exception as exc:  # noqa: BLE001
            record("PROBE C: replay format", "info", f"not text: {type(exc).__name__}")
    except Exception as exc:  # noqa: BLE001
        record("PROBE C: replay", "fail", f"{type(exc).__name__}: {str(exc)[:200]}")


async def phase_sandbox(key: str, holder: list):
    from solari_sandbox import SandboxClient

    client = SandboxClient(api_key=key, base_url=BASE_URL)
    t0 = time.monotonic()
    sandbox = await client.create()
    # Register for teardown IMMEDIATELY. A failure after this point must not
    # strand the session — on Free there is only one slot, and an orphan blocks
    # every subsequent run.
    holder.append(sandbox)
    record("sandbox.create", "info", f"cold start {time.monotonic() - t0:.1f}s")

    # Not in the docs or the cookbook snippet: create() alone is not enough,
    # the handle must be connected before any code call.
    t1 = time.monotonic()
    await sandbox.connect()
    record("sandbox.connect", "ok", f"{time.monotonic() - t1:.1f}s")

    ctx = await sandbox.create_code_context("python")
    out: list[str] = []

    # Two separate calls threading one context_id. If the second sees the
    # variable the first set, the kernel is genuinely stateful.
    await sandbox.run_code("smoke_value = 6 * 7", context_id=ctx)
    await sandbox.run_code("print(smoke_value)", context_id=ctx,
                           on_stdout=out.append)
    joined = "".join(out).strip()
    record("sandbox.stateful", "ok" if "42" in joined else "fail",
           f"second call saw: {joined!r}")

    # Does a fresh context NOT see it? Confirms isolation, not global state.
    out2: list[str] = []
    ctx2 = await sandbox.create_code_context("python")
    await sandbox.run_code(
        "print('leaked' if 'smoke_value' in dir() else 'isolated')",
        context_id=ctx2, on_stdout=out2.append)
    record("sandbox.context isolation", "info", "".join(out2).strip())

    # Which document-processing packages are already present?
    out3: list[str] = []
    await sandbox.run_code(
        "import importlib.util as u\n"
        "mods=['pdfplumber','fitz','pypdf','pytesseract','PIL','reportlab']\n"
        "print({m: u.find_spec(m) is not None for m in mods})",
        context_id=ctx, on_stdout=out3.append)
    record("sandbox.packages", "info", "".join(out3).strip()[:250])

    return client, sandbox


async def phase_desktop(key: str, label: str = "desktop"):
    from solari_desktop import DesktopClient

    client = DesktopClient(api_key=key, base_url=BASE_URL)
    t0 = time.monotonic()
    vm = await client.create(template="default")
    record(f"{label}.create", "info", f"cold start {time.monotonic() - t0:.1f}s")

    for attr in ("stream_url", "streamUrl", "preview_url"):
        val = getattr(vm, attr, None)
        if val:
            record(f"{label}.stream ({attr})", "ok", str(val)[:100])
            break
    else:
        record(f"{label}.stream", "fail", "no stream/preview url attribute found")

    shot = await vm.screenshot()
    OUT.mkdir(exist_ok=True)
    (OUT / "desktop.png").write_bytes(shot)
    record(f"{label}.screenshot", "ok", f"{len(shot)} bytes")

    # PROBE B — what does the `default` template actually ship?
    probes = [
        ("desktop env", "sh", ["-c", "echo $XDG_CURRENT_DESKTOP $DESKTOP_SESSION; "
                                     "ls /usr/share/xsessions 2>/dev/null"]),
        ("apps", "sh", ["-c", "ls /usr/share/applications 2>/dev/null | head -30"]),
        ("binaries", "sh", ["-c", "for b in firefox chromium xterm java python3 "
                                  "libreoffice mariadbd; do command -v $b || echo \"no $b\"; done"]),
        ("os", "sh", ["-c", "cat /etc/os-release | head -3; free -m | head -2"]),
    ]
    for name, cmd, args in probes:
        try:
            res = await vm.exec(cmd, args=args)
            text = getattr(res, "stdout", None) or str(res)
            record(f"PROBE B: {name}", "info", str(text).replace("\n", " | ")[:300])
        except Exception as exc:  # noqa: BLE001
            record(f"PROBE B: {name}", "fail", f"{type(exc).__name__}: {exc}")

    return client, vm


async def main() -> int:
    key = load_key()
    from solari_core import ConcurrencyLimitError, PlanError

    live: list = []
    sandbox = vm = None

    try:
        await phase_browser(key)
    except Exception:  # noqa: BLE001
        record("browser", "fail", traceback.format_exc(limit=3).strip()[-400:])

    try:
        _, sandbox = await phase_sandbox(key, live)
    except Exception:  # noqa: BLE001
        record("sandbox", "fail", traceback.format_exc(limit=3).strip()[-400:])
        sandbox = live[0] if live else None

    # PROBE A — create a Desktop while the Sandbox is still alive. If the
    # Free-tier counter is shared, this is where it fails, and the failure is
    # itself the finding that #16 is waiting on.
    try:
        _, vm = await phase_desktop(key)
        record("PROBE A: shared concurrency counter", "ok",
               "Sandbox + Desktop held open together — counter is NOT shared")
    except (ConcurrencyLimitError, PlanError) as exc:
        record("PROBE A: shared concurrency counter", "info",
               f"{type(exc).__name__} while Sandbox alive — counter IS shared: {str(exc)[:150]}")
        if sandbox is not None:
            try:
                await sandbox.kill()
                sandbox = None
                record("PROBE A: sandbox killed, retrying desktop", "info")
                _, vm = await phase_desktop(key, label="desktop(retry)")
                record("PROBE A: confirmed", "ok",
                       "Desktop succeeded once Sandbox died — sequencing is mandatory on this plan")
            except Exception:  # noqa: BLE001
                record("PROBE A: retry", "fail", traceback.format_exc(limit=3)[-400:])
    except Exception:  # noqa: BLE001
        record("desktop", "fail", traceback.format_exc(limit=3).strip()[-400:])

    for name, obj in (("sandbox", sandbox), ("desktop", vm)):
        if obj is None:
            continue
        try:
            await obj.kill()
            record(f"{name}.teardown", "ok")
        except Exception as exc:  # noqa: BLE001
            record(f"{name}.teardown", "fail", f"{type(exc).__name__}: {exc}")

    print("\n" + "=" * 78)
    print("SMOKE TEST SUMMARY")
    print("=" * 78)
    for step, outcome, detail in RESULTS:
        print(f"{outcome.upper():5} {step:44} {detail[:150]}")
    failed = [r for r in RESULTS if r[1] == "fail"]
    print(f"\n{len(RESULTS)} steps, {len(failed)} failed")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
