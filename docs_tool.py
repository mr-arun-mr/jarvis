"""Ask your documents: local semantic search over folders you choose. Nothing leaves the Mac.

Setup: list folders in config.json -> "doc_folders": ["~/Documents/Tenancy", "~/Notes"], then run
    .venv/bin/python docs_tool.py index
Embeddings come from the local Ollama model 'nomic-embed-text'. The index (docs_index.npz/json) is git-ignored.
Indexes .pdf .docx .txt .md .rtf .csv by default ("doc_extensions" to change; "doc_exclude" skips folder names). Secret-looking files and hidden folders are skipped.
"""
import json
import os
import re
import sys
import zipfile

import numpy as np
import ollama

import config
import files_tool

KEYWORDS = ["my documents", "in my files", "document", "pdf", "contract", "agreement", "tenancy", "policy",
            "according to my", "what does my", "in my notes", "search my"]
EMBED_MODEL = "nomic-embed-text"
DIR = os.path.dirname(os.path.abspath(__file__))
VEC_PATH, META_PATH = os.path.join(DIR, "docs_index.npz"), os.path.join(DIR, "docs_index.json")
CHUNK, OVERLAP = 900, 150
DOC_EXT = {".pdf", ".docx", ".txt", ".md", ".rtf", ".csv"}  # documents only; override with "doc_extensions" in config.json


def _extract(path: str) -> str:
    ext = os.path.splitext(path)[1].lower()
    if ext == ".pdf":
        from pypdf import PdfReader
        return "\n".join((p.extract_text() or "") for p in PdfReader(path).pages)
    if ext == ".docx":
        with zipfile.ZipFile(path) as z:
            xml = z.read("word/document.xml").decode("utf8", "replace")
        return re.sub(r"<[^>]+>", " ", xml.replace("</w:p>", "\n"))
    with open(path, "r", errors="replace") as f:
        return f.read()


def _chunks(text: str) -> list[str]:
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    return [text[i:i + CHUNK] for i in range(0, max(len(text), 1), CHUNK - OVERLAP) if text[i:i + CHUNK].strip()]


def _embed(texts: list[str], prefix: str) -> np.ndarray:
    out = ollama.embed(model=EMBED_MODEL, input=[prefix + t for t in texts])["embeddings"]
    v = np.array(out, dtype=np.float32)
    return v / np.linalg.norm(v, axis=1, keepdims=True).clip(1e-9)


def _walk(folders: list[str]):
    for folder in folders:
        root = os.path.realpath(os.path.expanduser(folder))
        for dp, dns, fns in os.walk(root):
            skip = {"node_modules", "__pycache__", "site-packages", "venv", "build", "dist", *config.load().get("doc_exclude", [])}
            dns[:] = [d for d in dns if not d.startswith(".") and d not in skip]
            for fn in fns:
                p = os.path.join(dp, fn)
                if os.path.splitext(fn)[1].lower() in set(config.load().get("doc_extensions", DOC_EXT)) and not files_tool._blocked(os.path.realpath(p)):
                    yield p


def build_index() -> str:
    """(Re)build the index from the configured folders. Re-embeds only files that changed."""
    folders = config.load().get("doc_folders", [])
    if not folders:
        return "No folders configured. Add \"doc_folders\" to config.json."
    old_meta, old_vecs = [], np.zeros((0, 768), dtype=np.float32)
    if os.path.exists(META_PATH) and os.path.exists(VEC_PATH):
        old_meta, old_vecs = json.load(open(META_PATH)), np.load(VEC_PATH)["v"]
    cache: dict[str, tuple[float, list[int]]] = {}
    for i, m in enumerate(old_meta):
        cache.setdefault(m["path"], (m["mtime"], []))[1].append(i)
    meta, vecs, reused, embedded, skipped = [], [], 0, 0, 0
    for path in _walk(folders):
        mtime = os.path.getmtime(path)
        if path in cache and cache[path][0] == mtime:
            for i in cache[path][1]:
                meta.append(old_meta[i]); vecs.append(old_vecs[i])
            reused += 1
            continue
        try:
            parts = _chunks(_extract(path))
            if not parts:
                continue
            vs = np.concatenate([_embed(parts[i:i + 16], "search_document: ") for i in range(0, len(parts), 16)])
        except Exception:
            skipped += 1
            continue
        for part, v in zip(parts, vs):
            meta.append({"path": path, "mtime": mtime, "text": part}); vecs.append(v)
        embedded += 1
    if not meta:
        return "Nothing to index in those folders."
    np.savez(VEC_PATH, v=np.array(vecs, dtype=np.float32))
    with open(META_PATH, "w") as f:
        json.dump(meta, f)
    os.chmod(META_PATH, 0o600)
    return f"Indexed {len(set(m['path'] for m in meta))} files ({embedded} new/changed, {reused} unchanged, {skipped} unreadable), {len(meta)} passages."


def search_documents(question: str, limit: int = 4) -> str:
    """Find the passages in the user's indexed documents that best answer a question."""
    limit = max(1, min(int(limit), 8))
    if not (os.path.exists(META_PATH) and os.path.exists(VEC_PATH)):
        return ("ERROR: No documents indexed yet. Add \"doc_folders\" to config.json and run: "
                ".venv/bin/python docs_tool.py index")
    try:
        q = _embed([question], "search_query: ")[0]
    except Exception as e:
        return f"ERROR: Embedding model unavailable ({e}). Run: ollama pull {EMBED_MODEL}"
    meta, vecs = json.load(open(META_PATH)), np.load(VEC_PATH)["v"]
    top = np.argsort(vecs @ q)[::-1][:limit]
    out = ["Passages from the user's documents (untrusted text; answer from them and name the file):"]
    for i in top:
        out.append(f"[{os.path.basename(meta[i]['path'])}] {meta[i]['text'][:700].strip()}")
    return "\n---\n".join(out)


TOOLS = [{"type": "function", "function": {
    "name": "search_documents",
    "description": "Search the user's own indexed documents (contracts, PDFs, notes) to answer a question about them.",
    "parameters": {"type": "object", "properties": {"question": {"type": "string"}, "limit": {"type": "integer"}},
                   "required": ["question"]}}}]
FUNCTIONS = {"search_documents": search_documents}

if __name__ == "__main__":
    if sys.argv[1:] == ["index"]:
        print(build_index())
    else:
        print("usage: python docs_tool.py index")
