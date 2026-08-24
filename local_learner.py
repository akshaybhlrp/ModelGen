import os
import sys
import threading
import concurrent.futures
from pathlib import Path
from kernel import init_db, store
from harvester import extract_ast
from mutation_tester import evaluate_mutation_score
from decontaminate import DecontaminationGate
from learned_router import train_learned_router

import zipfile
import tarfile
import tempfile

SUPPORTED_CODE_EXTS = {".py"}
SUPPORTED_IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".bmp"}
SUPPORTED_VIDEO_EXTS = {".mp4", ".mov", ".mkv", ".avi", ".webm"}
SUPPORTED_AUDIO_EXTS = {".mp3", ".wav", ".m4a", ".ogg"}
SUPPORTED_DOC_EXTS = {".md", ".txt", ".json", ".yaml", ".yml", ".pdf", ".csv", ".tsv"}
SUPPORTED_ARCHIVE_EXTS = {".zip", ".tar", ".gz", ".tgz", ".bz2", ".tar.gz", ".tar.bz2"}

def extract_pdf_text(pdf_path: Path) -> str:
    """Extracts text, code blocks, and doc contents from a PDF file."""
    text_content = []
    # 1. Try pypdf / pypdf2 / pdfplumber if installed
    try:
        from pypdf import PdfReader
        reader = PdfReader(str(pdf_path))
        for page in reader.pages[:50]:
            t = page.extract_text()
            if t:
                text_content.append(t)
    except Exception:
        pass
    
    if not text_content:
        # 2. Try pdftotext CLI tool fallback
        try:
            import subprocess
            r = subprocess.run(["pdftotext", str(pdf_path), "-"], capture_output=True, text=True, timeout=5)
            if r.returncode == 0 and r.stdout:
                text_content.append(r.stdout)
        except Exception:
            pass

    return "\n".join(text_content) if text_content else f"PDF Document: {pdf_path.name}"

def process_archive_file(archive_path: Path, conn) -> int:
    """Unpacks compressed archives in an isolated temp folder and ingests contained code & media."""
    learned = 0
    with tempfile.TemporaryDirectory() as tmp_extract_dir:
        tmp_target = Path(tmp_extract_dir)
        try:
            if zipfile.is_zipfile(archive_path):
                with zipfile.ZipFile(archive_path, 'r') as zf:
                    zf.extractall(tmp_target)
            elif tarfile.is_tarfile(archive_path):
                with tarfile.open(archive_path, 'r:*') as tf:
                    tf.extractall(tmp_target)
            
            # Recursively ingest the unpacked contents
            sub_res = ingest_local_directory(str(tmp_target), conn=conn, retrain_neural_weights=False, max_workers=4)
            learned = sub_res.get("learned_count", 0)
        except Exception:
            pass
    return learned

def process_media_file(file_path: Path, conn) -> list:
    """Extracts algorithmic patterns, OCR text, or descriptions from image/video/audio/pdf media."""
    items = []
    ext = file_path.suffix.lower()
    
    # 1. PDF Documents
    if ext == ".pdf":
        try:
            pdf_text = extract_pdf_text(file_path)
            # Check if PDF contains executable Python code
            from harvester import extract_ast
            extracted_code = extract_ast(pdf_text)
            if extracted_code:
                for fn_name, fn_code, test_code in extracted_code:
                    items.append((fn_name, fn_code, test_code))
            else:
                items.append((f"pdf_{file_path.stem}", f"# PDF Document {file_path.name}\n# Content Summary:\n# {pdf_text[:300]}\npass", "def test():\n    pass\n"))
        except Exception:
            pass

    # 2. Images (OCR or image captioning extraction)
    elif ext in SUPPORTED_IMAGE_EXTS:
        try:
            from PIL import Image
            img = Image.open(file_path)
            w, h = img.size
            desc = f"Image asset: {file_path.name} (dimensions {w}x{h})"
            try:
                import pytesseract
                ocr_text = pytesseract.image_to_string(img).strip()
                if ocr_text:
                    desc += f"\nOCR Extracted text:\n{ocr_text}"
            except Exception:
                pass
            items.append((f"img_{file_path.stem}", f"# {desc}\npass", "def test():\n    pass\n"))
        except Exception:
            pass

    # 3. Videos / Audio (metadata and transcript hooks)
    elif ext in SUPPORTED_VIDEO_EXTS or ext in SUPPORTED_AUDIO_EXTS:
        try:
            size_mb = round(file_path.stat().st_size / (1024 * 1024), 2)
            desc = f"Media file {file_path.name} ({ext[1:].upper()}, {size_mb} MB)"
            items.append((f"media_{file_path.stem}", f"# {desc}\npass", "def test():\n    pass\n"))
        except Exception:
            pass

    return items

def ingest_local_directory(dir_path: str, conn=None, retrain_neural_weights: bool = True, max_workers: int = 8) -> dict:
    """Asynchronous, multi-worker recursive directory scanner for code and multimodal media."""
    target = Path(dir_path).resolve()
    if not target.exists() or not target.is_dir():
        return {"status": "error", "message": f"Directory not found: {dir_path}", "learned_count": 0}

    if conn is None:
        conn = init_db()

    decontam = DecontaminationGate()
    
    # Discover all code, media, and docs recursively
    all_files = []
    for root, dirs, files in os.walk(target):
        # Ignore hidden / build / virtualenv directories
        dirs[:] = [d for d in dirs if not d.startswith(".") and d not in {"venv", ".venv", "__pycache__", "node_modules", "build", "dist"}]
        for f in files:
            if not f.startswith("."):
                all_files.append(Path(root) / f)

    code_files = [f for f in all_files if f.suffix.lower() in SUPPORTED_CODE_EXTS]
    media_files = [f for f in all_files if f.suffix.lower() in (SUPPORTED_IMAGE_EXTS | SUPPORTED_VIDEO_EXTS | SUPPORTED_AUDIO_EXTS | {".pdf"})]
    archive_files = [f for f in all_files if any(f.name.lower().endswith(ext) for ext in SUPPORTED_ARCHIVE_EXTS)]

    total_found = 0
    total_stored = 0
    modules_stored = []
    lock = threading.Lock()

    print(f"\n[+] Async Scanning Directory: {target} ({len(code_files)} Code, {len(media_files)} Media/PDF, {len(archive_files)} Archives across {max_workers} threads)")

    def process_single_code_file(py_file: Path):
        nonlocal total_found, total_stored
        active_conn = conn if conn is not None else init_db()
        try:
            content = py_file.read_text(encoding="utf-8", errors="ignore")
            if len(content) < 30:
                return
            extracted = extract_ast(content)
            for fn_name, fn_code, test_code in extracted:
                with lock:
                    total_found += 1

                # Decontamination check
                is_contam, _ = decontam.is_contaminated(fn_code, test_code, source_url=f"local:{py_file}")
                if is_contam:
                    continue

                # Mutation quality check
                mut_score, killed, total = evaluate_mutation_score(fn_code, test_code, max_mutants=5)
                if mut_score < 0.40:
                    continue

                with lock:
                    mid = store(active_conn, fn_name, fn_code, test_code, "Local", f"local:{py_file}")
                    if mid:
                        total_stored += 1
                        modules_stored.append(fn_name)
                        print(f"  [VERIFIED & LEARNED] #{mid} '{fn_name}' from {py_file.name} (Mutation Kill-Rate: {mut_score:.1%})")
        except Exception:
            pass

    def process_single_media(m_file: Path):
        nonlocal total_found, total_stored
        active_conn = conn if conn is not None else init_db()
        try:
            m_items = process_media_file(m_file, active_conn)
            for m_name, m_code, m_tests in m_items:
                with lock:
                    total_found += 1
                    mid = store(active_conn, m_name, m_code, m_tests, "MediaAsset", f"local_media:{m_file}")
                    if mid:
                        total_stored += 1
                        modules_stored.append(m_name)
                        print(f"  [MEDIA INDEXED] #{mid} '{m_name}' ({m_file.suffix})")
        except Exception:
            pass

    # Process files
    if max_workers <= 1 or len(code_files) + len(media_files) <= 1:
        for f in code_files:
            process_single_code_file(f)
        for f in media_files:
            process_single_media(f)
    else:
        # Multi-threaded concurrent execution pool
        with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
            code_futures = [executor.submit(process_single_code_file, f) for f in code_files]
            media_futures = [executor.submit(process_single_media, f) for f in media_files]
            concurrent.futures.wait(code_futures + media_futures)

    # Process compressed archives
    for arc_file in archive_files:
        try:
            arc_learned = process_archive_file(arc_file, conn)
            total_stored += arc_learned
            if arc_learned > 0:
                print(f"  [ARCHIVE UNPACKED & LEARNED] {arc_file.name} -> {arc_learned} items")
        except Exception:
            pass

    # On-the-fly neural router weight retraining
    if total_stored > 0 and retrain_neural_weights:
        print(f"\n[+] Adapting Neural Router Weights for {total_stored} newly learned items...")
        train_learned_router(conn, epochs=10)

    return {
        "status": "success",
        "scanned_files": len(all_files),
        "code_files": len(code_files),
        "media_files": len(media_files),
        "candidates_found": total_found,
        "learned_count": total_stored,
        "modules": modules_stored
    }

def ingest_async_background(dir_path: str, conn=None):
    """Launches directory scan non-blockingly in a background thread."""
    t = threading.Thread(target=ingest_local_directory, args=(dir_path, conn), daemon=True)
    t.start()
    return t

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python3 local_learner.py <path_to_directory>")
        sys.exit(1)

    path = sys.argv[1]
    res = ingest_local_directory(path)
    print(f"\n[+] Async Ingestion Complete. Learned {res['learned_count']} modules from {res['scanned_files']} files ({res['media_files']} media).")
