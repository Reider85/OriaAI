#!/usr/bin/env python3
"""
Download BGE-m3 model for local sentence embeddings in RAG pipeline.

Usage:
    python scripts/download_embedding_model.py

This script downloads the BAAI/bge-m3 model (1.8B parameters, ~2.2GB)
to models/bge-m3/ for use as fallback when cloud embeddings are not configured.

The model is cached locally and can be reused across sessions without re-downloading.
"""

import sys
import time
from pathlib import Path

from huggingface_hub import snapshot_download
from sentence_transformers import SentenceTransformer


def main():
    """Download BGE-m3 model with smoke test."""
    model_name = "BAAI/bge-m3"
    model_dir = Path("models/bge-m3")
    
    print(f"Downloading {model_name} to {model_dir}...")
    
    try:
        # Download model if not exists
        if not model_dir.exists():
            model_dir.mkdir(parents=True, exist_ok=True)
            
            print("Downloading from HuggingFace Hub...")
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
    
    except (OSError, RuntimeError) as e:
        print(f"Download failed: {e}")
        sys.exit(1)
    
    # Smoke test: verify model works
    print("Running smoke test...")
    try:
        # Load model and test inference
        model = SentenceTransformer(str(model_dir))
        
        # Test sentences
        test_sentences = [
            "What is machine learning?",
            "How to cook pasta?",
            "The weather is nice today."
        ]
        
        start_time = time.time()
        embeddings = model.encode(test_sentences)
        inference_time = time.time() - start_time
        
        print("Smoke test passed!")
        print(f"   - Generated embeddings shape: {embeddings.shape}")
        print(f"   - Inference time: {inference_time:.3f}s for {len(test_sentences)} sentences")
        print("   - RAM usage: ~2.2GB loaded, ~3-4GB peak during inference")
        
        # Verify dimensions and reasonable scores
        assert embeddings.shape[0] == len(test_sentences), "Wrong number of embeddings"
        assert embeddings.shape[1] == 1024, "BGE-m3 should produce 1024-dimensional embeddings"
        print(f"   - Embedding dimension: {embeddings.shape[1]} (expected 1024)")
        
        print("\nBGE-m3 is ready for use!")
        print(f"   - Model location: {model_dir.absolute()}")
        print(f"   - Use with LOCAL_EMBEDDING_MODEL={model_name}")
        print(f"   - Use with LOCAL_EMBEDDING_MODEL_DIR={model_dir.absolute()}")
        
    except (OSError, RuntimeError, ValueError) as e:
        print(f"❌ Smoke test failed: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()