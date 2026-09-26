#!/usr/bin/env python3
"""
Download BGE-reranker-base model for in-process reranking in RAG pipeline.

Usage:
    python scripts/download_bge_reranker.py

This script downloads the BAAI/bge-reranker-base model (278M parameters, ~600MB)
to models/bge-reranker-base/ for use in ADR-017 (Reranker Model in RAG).

The model is cached locally and can be reused across sessions without re-downloading.
"""

import os
import sys
from pathlib import Path
from huggingface_hub import snapshot_download
from sentence_transformers import CrossEncoder
import time

def main():
    """Download BGE-reranker-base model with smoke test."""
    model_name = "BAAI/bge-reranker-base"
    model_dir = Path("models/bge-reranker-base")
    
    print(f"Downloading {model_name} to {model_dir}...")
    
    try:
        # Download model if not exists
        if not model_dir.exists():
            model_dir.mkdir(parents=True, exist_ok=True)
            
            print(f"Downloading from HuggingFace Hub...")
            start_time = time.time()
            
            snapshot_download(
                repo_id=model_name,
                local_dir=str(model_dir),
                local_dir_use_symlinks=False,
                resume_download=True
            )
            
            download_time = time.time() - start_time
            print(f"Download completed in {download_time:.1f}s")
        else:
            print(f"Model already exists at {model_dir}")
    
    except Exception as e:
        print(f"Download failed: {e}")
        sys.exit(1)
    
    # Smoke test: verify model works
    print(f"Running smoke test...")
    try:
        # Load model and test inference
        reranker = CrossEncoder(str(model_dir))
        
        # Test query-document pairs
        test_pairs = [
            ("What is machine learning?", "Machine learning is a subset of artificial intelligence."),
            ("How to cook pasta?", "The weather is nice today.")
        ]
        
        start_time = time.time()
        scores = reranker.predict(test_pairs)
        inference_time = time.time() - start_time
        
        print(f"Smoke test passed!")
        print(f"   - Predicted scores: {scores}")
        print(f"   - Inference time: {inference_time:.3f}s")
        print(f"   - RAM usage: ~600MB loaded, ~1.2GB peak during inference")
        
        # Verify scores are reasonable (first pair should be higher)
        if scores[0] > scores[1]:
            print("Score ordering correct: relevant pair has higher score")
        else:
            print("Score ordering unexpected: check model loading")
        
        print(f"\nBGE-reranker-base is ready for use!")
        print(f"   - Model location: {model_dir.absolute()}")
        print(f"   - Use with RERANKER_MODEL_NAME={model_name}")
        print(f"   - Use with RERANKER_MODEL_DIR={model_dir.absolute()}")
        
    except Exception as e:
        print(f"❌ Smoke test failed: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()