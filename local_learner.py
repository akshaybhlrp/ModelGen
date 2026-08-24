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

SUPPORTED_CODE_EXTS = {".py"}
SUPPORTED_IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".bmp"}
SUPPORTED_VIDEO_EXTS = {".mp4", ".mov", ".mkv", ".avi", ".webm"}
SUPPORTED_AUDIO_EXTS = {".mp3", ".wav", ".m4a", ".ogg"}
SUPPORTED_DOC_EXTS = {".md", ".txt", ".json", ".yaml", ".yml"}

def process_media_file(file_path: Path, conn) -> list:
    """Extracts algorithmic patterns, OCR text, or descriptions from image/video/audio media."""
    items = []
    ext = file_path.suffix.lower()
    
    # 1. Images (OCR or image captioning extraction)
    if ext in SUPPORTED_IMAGE_EXTS:
        try:
            # Fallback OCR with pytesseract / PIL if installed, otherwise basic metadata descriptor
            from PIL import Image
            img = Image.open(file_path)
            w, h = img.size
            desc = f"Image asset: {file_path.name} (dimensions {w}x{h})"
            # Attempt OCR extraction
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

    # 2. Videos / Audio (metadata and transcript hooks)
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
    media_files = [f for f in all_files if f.suffix.lower() in (SUPPORTED_IMAGE_EXTS | SUPPORTED_VIDEO_EXTS | SUPPORTED_AUDIO_EXTS)]

    total_found = 0
    total_stored = 0
    modules_stored = []
    lock = threading.Lock()

    print(f"\n[+] Async Scanning Directory: {target} ({len(code_files)} Python, {len(media_files)} Media files across {max_workers} threads)")

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
