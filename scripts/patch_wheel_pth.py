"""Patch the built wheel to place ctx_retriever_autoinstall.pth at purelib root.

When installed by pip, a .pth file at the wheel's purelib root goes directly
into site-packages, where Python executes it on every startup (if it starts
with 'import'). This enables zero-friction auto-wiring of CTX hooks after
a plain `pip install ctx-retriever` with no extra commands.
"""
import base64
import glob
import hashlib
import sys
import zipfile
from pathlib import Path

PTH_NAME = "ctx_retriever_autoinstall.pth"
PTH_CONTENT = b"import ctx_retriever._autoinstall\n"


def sha256_record(data: bytes) -> str:
    digest = hashlib.sha256(data).digest()
    return "sha256=" + base64.urlsafe_b64encode(digest).rstrip(b"=").decode()


def patch(wheel_path: Path) -> None:
    entries: dict[str, tuple] = {}
    record_name: str | None = None

    with zipfile.ZipFile(wheel_path, "r") as zf:
        for item in zf.infolist():
            # Drop any .pth added by setuptools in the wrong location
            if PTH_NAME in item.filename and item.filename != PTH_NAME:
                print(f"  removing misplaced: {item.filename}")
                continue
            entries[item.filename] = (item, zf.read(item.filename))
            if item.filename.endswith("/RECORD"):
                record_name = item.filename

    assert record_name, "WHEEL has no RECORD file"

    # Rebuild RECORD
    record_lines = [
        l for l in entries[record_name][1].decode().splitlines()
        if l and PTH_NAME not in l
    ]
    record_lines.append(
        f"{PTH_NAME},{sha256_record(PTH_CONTENT)},{len(PTH_CONTENT)}"
    )
    new_record = "\n".join(
        f"{record_name},," if l.split(",")[0] == record_name else l
        for l in record_lines
    ) + "\n"

    out = wheel_path.with_name(wheel_path.stem + "-patching.whl")
    with zipfile.ZipFile(out, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for fname, (info, data) in entries.items():
            zf.writestr(info, new_record.encode() if fname == record_name else data)
        zf.writestr(PTH_NAME, PTH_CONTENT)

    wheel_path.unlink()
    out.rename(wheel_path)
    print(f"  patched: {wheel_path.name}")


def main() -> None:
    wheels = glob.glob("dist/*.whl")
    if not wheels:
        print("No wheels found in dist/ — skipping pth patch.")
        return
    for w in wheels:
        patch(Path(w))


if __name__ == "__main__":
    main()
